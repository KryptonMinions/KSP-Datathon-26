"""build_network (ORCHESTRATOR_STEERING.md §9.7).

Fixed SQL over known_associates + co-accusal pairs (derived from shared
fir_accused.fir_id) + gang_memberships; breadth-first from a seed person or
gang, capped at max_nodes. Discovered persons are canonicalized to their
er_cluster's Canonical representative (Python-side, after fetching er_status
alongside each edge) so duplicate name-variants collapse to one node.

§4.1 rule 3 (IO-scoped turns only): anchor admission check before any
traversal — seed person must appear in fir_accused of >=1 FIR at the
operator's station; seed gang must have >=1 member with a FIR there. Failure
sets ToolResult.hard_refuse_reason="out_of_scope", which loop.py enforces
immediately regardless of what the model does next (never prompt-only).
"""

from __future__ import annotations

import uuid
from typing import Any

from app.schemas import Citation, GraphEdge, GraphNode, NetworkGraphBlock
from app.supabase import SupabaseError, call_rpc

from .base import ToolContext, ToolResult, is_valid_uuid


class _PersonNode:
    __slots__ = ("person_id", "display_name", "is_history_sheeted", "cluster_key")

    def __init__(self, person_id: str, display_name: str, is_history_sheeted: bool, cluster_key: str):
        self.person_id = person_id
        self.display_name = display_name
        self.is_history_sheeted = is_history_sheeted
        self.cluster_key = cluster_key


async def _run_select(sql: str, settings, row_cap: int = 200) -> list[dict]:
    result = await call_rpc(
        "execute_agent_select", {"p_sql": sql, "p_scope": "case", "p_row_cap": row_cap}, settings
    )
    return (result or {}).get("rows") or []


async def _canonical_person_row(person_id: str, settings) -> dict | None:
    sql = f"""
        SELECT person_id, full_name, er_cluster_id, er_status, is_history_sheeted
        FROM persons WHERE person_id = '{person_id}'
    """
    rows = await _run_select(sql, settings, row_cap=1)
    return rows[0] if rows else None


def _cluster_key(row: dict) -> str:
    return row.get("er_cluster_id") or row["person_id"]


async def _check_person_admission(person_id: str, cluster_key_val: str, station_id: str, settings) -> bool:
    """Admission passes if the seed person (or any person sharing its
    er_cluster) has an accused-role FIR at the operator's station."""
    sql = f"""
        SELECT 1 FROM fir_accused fa
        JOIN firs f ON f.fir_id = fa.fir_id
        JOIN persons p ON p.person_id = fa.person_id
        WHERE f.station_id = '{station_id}'
          AND (p.person_id = '{person_id}' OR COALESCE(p.er_cluster_id::text, p.person_id::text) = '{cluster_key_val}')
        LIMIT 1
    """
    rows = await _run_select(sql, settings, row_cap=1)
    return bool(rows)


async def _check_gang_admission(gang_id: str, station_id: str, settings) -> bool:
    sql = f"""
        SELECT 1 FROM gang_memberships gm
        JOIN fir_accused fa ON fa.person_id = gm.person_id
        JOIN firs f ON f.fir_id = fa.fir_id
        WHERE gm.gang_id = '{gang_id}' AND f.station_id = '{station_id}'
        LIMIT 1
    """
    rows = await _run_select(sql, settings, row_cap=1)
    return bool(rows)


async def _neighbors_of(person_ids: list[str], settings) -> tuple[list[dict], list[dict], list[dict]]:
    """Returns (associate_rows, coaccusal_rows, gang_rows) for a batch of
    canonical person_ids (both directions for known_associates)."""
    if not person_ids:
        return [], [], []
    id_list = ", ".join(f"'{p}'" for p in person_ids)

    assoc_sql = f"""
        SELECT ka.person_id_a, ka.person_id_b, ka.association_type, ka.confidence, ka.first_seen_fir_id,
               pa.full_name AS name_a, pa.er_cluster_id AS cluster_a, pa.er_status AS status_a, pa.is_history_sheeted AS hs_a,
               pb.full_name AS name_b, pb.er_cluster_id AS cluster_b, pb.er_status AS status_b, pb.is_history_sheeted AS hs_b
        FROM known_associates ka
        JOIN persons pa ON pa.person_id = ka.person_id_a
        JOIN persons pb ON pb.person_id = ka.person_id_b
        WHERE ka.person_id_a IN ({id_list}) OR ka.person_id_b IN ({id_list})
    """
    coaccusal_sql = f"""
        SELECT fa1.person_id AS seed_person_id, fa2.person_id AS other_person_id, fa1.fir_id,
               p.full_name, p.er_cluster_id, p.er_status, p.is_history_sheeted
        FROM fir_accused fa1
        JOIN fir_accused fa2 ON fa2.fir_id = fa1.fir_id AND fa2.person_id != fa1.person_id
        JOIN persons p ON p.person_id = fa2.person_id
        WHERE fa1.person_id IN ({id_list})
    """
    gang_sql = f"""
        SELECT gm.person_id, gm.gang_id, gm.role_in_gang, g.gang_name
        FROM gang_memberships gm
        JOIN gangs g ON g.gang_id = gm.gang_id
        WHERE gm.person_id IN ({id_list}) AND gm.is_active = true
    """
    assoc_rows = await _run_select(assoc_sql, settings)
    coaccusal_rows = await _run_select(coaccusal_sql, settings)
    gang_rows = await _run_select(gang_sql, settings)
    return assoc_rows, coaccusal_rows, gang_rows


class BuildNetworkTool:
    name = "build_network"
    label = "Building network"
    description = (
        "Build an associate/co-accusal/gang network graph from a seed person or gang, "
        "depth 1 or 2, capped at max_nodes."
    )

    @property
    def params_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "seed": {
                    "type": "object",
                    "properties": {"person_id": {"type": "string"}, "gang_id": {"type": "string"}},
                    "description": "Provide exactly one of person_id or gang_id (canonical UUIDs from resolve_entity).",
                },
                "depth": {"type": "integer", "enum": [1, 2], "default": 2},
                "max_nodes": {"type": "integer", "default": 40, "maximum": 60},
            },
            "required": ["seed"],
        }

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        seed = args.get("seed") or {}
        seed_person_id = seed.get("person_id")
        seed_gang_id = seed.get("gang_id")
        depth = args.get("depth", 2)
        if depth not in (1, 2):
            depth = 2
        max_nodes = min(int(args.get("max_nodes", 40) or 40), 60)

        if seed_person_id and not is_valid_uuid(seed_person_id):
            return ToolResult(ok=False, error="seed.person_id must be a canonical UUID (use resolve_entity first)")
        if seed_gang_id and not is_valid_uuid(seed_gang_id):
            return ToolResult(ok=False, error="seed.gang_id must be a canonical UUID")
        if not seed_person_id and not seed_gang_id:
            return ToolResult(ok=False, error="seed must include person_id or gang_id")

        try:
            return await self._run(seed_person_id, seed_gang_id, depth, max_nodes, ctx)
        except SupabaseError as exc:
            return ToolResult(ok=False, error=f"build_network query failed: {exc}")

    async def _run(
        self, seed_person_id: str | None, seed_gang_id: str | None, depth: int, max_nodes: int, ctx: ToolContext
    ) -> ToolResult:
        settings = ctx.settings

        # §4.1 rule 3 — anchor admission before ANY traversal, on scoped turns only.
        if ctx.scoped_station_id:
            if seed_person_id:
                row = await _canonical_person_row(seed_person_id, settings)
                if row is None:
                    return ToolResult(ok=False, error="seed person not found")
                admitted = await _check_person_admission(
                    seed_person_id, _cluster_key(row), ctx.scoped_station_id, settings
                )
            else:
                admitted = await _check_gang_admission(seed_gang_id, ctx.scoped_station_id, settings)
            if not admitted:
                return ToolResult(
                    ok=False,
                    error="anchor has no case at your station",
                    hard_refuse_reason="out_of_scope",
                )

        nodes: dict[str, GraphNode] = {}
        edges: list[GraphEdge] = []
        cluster_to_canonical: dict[str, str] = {}
        # Maps every RAW person_id ever seen to its canonical node id. Distinct
        # from cluster_to_canonical (keyed by cluster key, not by member id) —
        # frontier/edge rows always carry raw person_ids, so lookups against
        # them must go through this map, not cluster_to_canonical directly.
        raw_to_canonical: dict[str, str] = {}
        fir_citations: set[str] = set()
        central_node_id: str

        def _person_graph_node(row: dict, node_id: str) -> GraphNode:
            return GraphNode(
                id=node_id, label=row["full_name"], kind="person",
                status="History-sheeted" if row.get("is_history_sheeted") else None,
            )

        def upsert_person(row: dict) -> str:
            """Registers/returns the canonical person_id node for a raw person
            row (with er_cluster_id/er_status/full_name/is_history_sheeted).

            If a later row turns out to be the cluster's true Canonical member
            (discovered after an earlier, non-canonical row from the same
            cluster already got a provisional node), migrates: redirects
            existing edges and raw_to_canonical entries from the old
            provisional node to the new canonical one, so the same real person
            never ends up as two disconnected graph nodes.
            """
            key = row.get("er_cluster_id") or row["person_id"]
            existing = cluster_to_canonical.get(key)
            is_canonical_row = row.get("er_status") == "Canonical"

            if existing is None:
                canonical = row["person_id"]
                cluster_to_canonical[key] = canonical
                nodes[canonical] = _person_graph_node(row, canonical)
            elif is_canonical_row and existing != row["person_id"]:
                old, new = existing, row["person_id"]
                cluster_to_canonical[key] = new
                nodes[new] = _person_graph_node(row, new)
                nodes.pop(old, None)
                for raw_id, canon_id in list(raw_to_canonical.items()):
                    if canon_id == old:
                        raw_to_canonical[raw_id] = new
                for e in edges:
                    if e.source == old:
                        e.source = new
                    if e.target == old:
                        e.target = new
                canonical = new
            else:
                canonical = existing

            raw_to_canonical[row["person_id"]] = canonical
            return canonical

        frontier: list[str] = []
        if seed_person_id:
            seed_row = await _canonical_person_row(seed_person_id, settings)
            if seed_row is None:
                return ToolResult(ok=False, error="seed person not found")
            central_node_id = upsert_person(seed_row)
            frontier = [seed_row["person_id"]]
        else:
            gang_rows = await _run_select(
                f"SELECT gang_id, gang_name FROM gangs WHERE gang_id = '{seed_gang_id}'", settings, row_cap=1
            )
            if not gang_rows:
                return ToolResult(ok=False, error="seed gang not found")
            central_node_id = seed_gang_id
            nodes[central_node_id] = GraphNode(id=central_node_id, label=gang_rows[0]["gang_name"], kind="gang")
            member_rows = await _run_select(
                f"""SELECT p.person_id, p.full_name, p.er_cluster_id, p.er_status, p.is_history_sheeted,
                           gm.role_in_gang
                    FROM gang_memberships gm JOIN persons p ON p.person_id = gm.person_id
                    WHERE gm.gang_id = '{seed_gang_id}' AND gm.is_active = true LIMIT {max_nodes}""",
                settings,
            )
            for r in member_rows:
                pid = upsert_person(r)
                edges.append(GraphEdge(source=central_node_id, target=pid, label=r["role_in_gang"], fir_id=""))
                frontier.append(r["person_id"])

        visited_raw: set[str] = set(frontier) | ({seed_person_id} if seed_person_id else set())

        for _ in range(depth):
            if len(nodes) >= max_nodes or not frontier:
                break
            assoc_rows, coaccusal_rows, gang_rows_n = await _neighbors_of(frontier, settings)
            next_frontier: list[str] = []

            for r in assoc_rows:
                if len(nodes) >= max_nodes:
                    break
                a_id, b_id = r["person_id_a"], r["person_id_b"]
                a = upsert_person({"person_id": a_id, "full_name": r["name_a"], "er_cluster_id": r["cluster_a"], "er_status": r["status_a"], "is_history_sheeted": r["hs_a"]})
                b = upsert_person({"person_id": b_id, "full_name": r["name_b"], "er_cluster_id": r["cluster_b"], "er_status": r["status_b"], "is_history_sheeted": r["hs_b"]})
                if a != b:
                    edges.append(GraphEdge(source=a, target=b, label=r["association_type"], fir_id=r.get("first_seen_fir_id") or ""))
                    if r.get("first_seen_fir_id"):
                        fir_citations.add(r["first_seen_fir_id"])
                for raw_id in (a_id, b_id):
                    if raw_id not in visited_raw:
                        visited_raw.add(raw_id)
                        next_frontier.append(raw_id)

            for r in coaccusal_rows:
                if len(nodes) >= max_nodes:
                    break
                # The seed side of a co-accusal row is always already a node
                # (it came from a prior iteration's frontier, which is only
                # ever populated with already-upserted persons) — just look
                # up its canonical id, don't re-upsert with placeholder data.
                seed_canonical = raw_to_canonical.get(r["seed_person_id"], r["seed_person_id"])
                if seed_canonical not in nodes:
                    continue
                other_pid = upsert_person({
                    "person_id": r["other_person_id"], "full_name": r["full_name"],
                    "er_cluster_id": r["er_cluster_id"], "er_status": r["er_status"],
                    "is_history_sheeted": r["is_history_sheeted"],
                })
                if other_pid != seed_canonical:
                    edges.append(GraphEdge(source=seed_canonical, target=other_pid, label="Co_Accused", fir_id=r["fir_id"]))
                    fir_citations.add(r["fir_id"])
                if r["other_person_id"] not in visited_raw:
                    visited_raw.add(r["other_person_id"])
                    next_frontier.append(r["other_person_id"])

            for r in gang_rows_n:
                if len(nodes) >= max_nodes:
                    break
                gid = r["gang_id"]
                if gid not in nodes:
                    g_rows = await _run_select(f"SELECT gang_name FROM gangs WHERE gang_id = '{gid}'", settings, row_cap=1)
                    nodes[gid] = GraphNode(id=gid, label=g_rows[0]["gang_name"] if g_rows else gid, kind="gang")
                person_canonical = raw_to_canonical.get(r["person_id"], r["person_id"])
                if person_canonical in nodes:
                    edges.append(GraphEdge(source=person_canonical, target=gid, label=r["role_in_gang"], fir_id=""))

            frontier = next_frontier

        key_members = sorted(
            (n for n in nodes.values() if n.kind == "person"),
            key=lambda n: sum(1 for e in edges if e.source == n.id or e.target == n.id),
            reverse=True,
        )[:5]
        gangs_touched = [n.label for n in nodes.values() if n.kind == "gang"]

        block = NetworkGraphBlock(
            id=f"network-{uuid.uuid4().hex[:8]}",
            central_node_id=central_node_id,
            nodes=list(nodes.values()),
            edges=edges,
            citations=[Citation(level="fir", fir_id=f) for f in fir_citations],
        )
        payload_id = None
        if ctx.scratchpad is not None:
            payload_id = ctx.scratchpad.register_payload(block)
            for f in fir_citations:
                ctx.scratchpad.register_provenance("fir", {"fir_id": f})

        return ToolResult(
            ok=True,
            data={
                "node_count": len(nodes), "edge_count": len(edges),
                "key_members": [n.label for n in key_members], "gangs_touched": gangs_touched,
            },
            payload_id=payload_id,
        )
