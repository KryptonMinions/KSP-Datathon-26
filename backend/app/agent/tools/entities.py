"""resolve_entity + get_case (ORCHESTRATOR_STEERING.md §9.4-9.5).

resolve_entity wraps the resolve_{person,vehicle,locality}_candidates RPCs
(db/migrations/008_resolve_entity.sql). get_case is a fixed join over firs +
station + sections + accused/victim counts + status + IO name.
"""

from __future__ import annotations

from typing import Any

from app.schemas import CaseCardBlock, CaseSummary, Citation, EntitySummary
from app.supabase import SupabaseError, call_rpc

from .base import ToolContext, ToolResult


class ResolveEntityTool:
    name = "resolve_entity"
    label = "Resolving entity"
    description = (
        "Fuzzy-match a person name, vehicle plate, or locality name against the "
        "database. Returns ranked candidates with canonical IDs. Person results "
        "are already collapsed to distinct entities (er_cluster_id groups name "
        "variants of the same real person)."
    )

    @property
    def params_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["person", "vehicle", "locality"]},
                "text": {"type": "string", "description": "The name/plate/locality text to resolve."},
            },
            "required": ["kind", "text"],
        }

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        kind = args.get("kind")
        text = (args.get("text") or "").strip()
        if not text:
            return ToolResult(ok=False, error="no text provided")

        try:
            if kind == "person":
                rows = await call_rpc(
                    "resolve_person_candidates", {"q": text, "limit_n": 5}, ctx.settings
                )
                candidates = _dedupe_person_clusters(rows or [])
                if ctx.scratchpad is not None:
                    for c in candidates:
                        pid = c.get("person_id")
                        if pid:
                            ctx.scratchpad.record_accessed(pid)
            elif kind == "vehicle":
                rows = await call_rpc(
                    "resolve_vehicle_candidates", {"plate": text, "limit_n": 5}, ctx.settings
                )
                candidates = rows or []
            elif kind == "locality":
                rows = await call_rpc(
                    "resolve_locality_candidates", {"q": text, "limit_n": 5}, ctx.settings
                )
                candidates = rows or []
            else:
                return ToolResult(ok=False, error=f"unknown kind '{kind}' (expected person|vehicle|locality)")
        except SupabaseError as exc:
            return ToolResult(ok=False, error=f"resolve_entity failed: {exc}")

        return ToolResult(ok=True, data={"kind": kind, "candidates": candidates})


def _dedupe_person_clusters(rows: list[dict]) -> list[dict]:
    """Collapse to one candidate per er_cluster_id (best similarity wins),
    treating rows with no cluster as singletons. RPC already orders by
    similarity DESC, so the first occurrence per cluster is the best."""
    seen: set[str] = set()
    out: list[dict] = []
    for row in rows:
        key = row.get("er_cluster_id") or row.get("person_id")
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


class GetCaseTool:
    name = "get_case"
    label = "Loading case"
    description = "Load one FIR's summary (station, sections, status, IO, accused/victim counts) by exact FIR ID."

    @property
    def params_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"fir_id": {"type": "string"}},
            "required": ["fir_id"],
        }

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        fir_id = (args.get("fir_id") or "").strip()
        if not fir_id:
            return ToolResult(ok=False, error="no fir_id provided")

        sql = f"""
            SELECT
                f.fir_id, f.registration_date, f.incident_date, f.incident_location,
                f.investigation_status, f.chargesheet_deadline,
                ps.station_name, bs.bns_section, bs.bns_description,
                io.name AS io_officer_name,
                (SELECT count(*) FROM fir_accused fa WHERE fa.fir_id = f.fir_id) AS accused_count,
                (SELECT count(*) FROM fir_victims fv WHERE fv.fir_id = f.fir_id) AS victim_count
            FROM firs f
            JOIN police_stations ps ON ps.station_id = f.station_id
            LEFT JOIN bns_sections bs ON bs.section_id = f.primary_bns_section
            LEFT JOIN officers io ON io.officer_id = f.io_officer_id
            WHERE f.fir_id = '{_sql_escape(fir_id)}'
        """
        try:
            result = await call_rpc(
                "execute_agent_select",
                {"p_sql": sql, "p_scope": "case", "p_row_cap": 1},
                ctx.settings,
            )
        except SupabaseError as exc:
            return ToolResult(ok=False, error=f"get_case failed: {exc}")

        rows = (result or {}).get("rows") or []
        if not rows:
            return ToolResult(ok=False, error="FIR not found")
        row = rows[0]

        case = CaseSummary(
            fir_id=row["fir_id"],
            station=row["station_name"],
            offence=row.get("bns_description") or "Unspecified",
            section=row.get("bns_section") or "",
            status=row["investigation_status"],
            detail=(
                f"IO: {row['io_officer_name']}; accused: {row['accused_count']}; "
                f"victims: {row['victim_count']}"
                if row.get("io_officer_name")
                else f"accused: {row['accused_count']}; victims: {row['victim_count']}"
            ),
        )
        citation = Citation(level="fir", fir_id=row["fir_id"])
        block = CaseCardBlock(id=f"case-{row['fir_id']}", cases=[case], citations=[citation])

        payload_id = None
        if ctx.scratchpad is not None:
            payload_id = ctx.scratchpad.register_payload(block)
            ctx.scratchpad.register_provenance("fir", {"fir_id": row["fir_id"]})

        summary = (
            f"{row['fir_id']} at {row['station_name']}: {row.get('bns_description') or 'unspecified offence'} "
            f"({row['investigation_status']}), {row['accused_count']} accused, {row['victim_count']} victims."
        )
        return ToolResult(ok=True, data={"summary": summary}, payload_id=payload_id)


def _sql_escape(value: str) -> str:
    return value.replace("'", "''")


# EntitySummary is imported for downstream tools (e.g. composer/case_investigator
# building person entity chips) — re-exported here for convenience.
__all__ = ["ResolveEntityTool", "GetCaseTool", "EntitySummary"]
