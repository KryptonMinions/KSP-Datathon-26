"""geo_query (ORCHESTRATOR_STEERING.md §9.8). Parameterized PostGIS SQL
templates — never model-authored SQL. Three ops:

- incident_points: raw point extraction (lat/lng, capped at 30 markers).
- hotspot_localities: count-by-locality aggregation (coarse, non-DBSCAN).
- cluster_dbscan: ST_ClusterDBSCAN over incident points, reprojected to
  EPSG:32643 (UTM 43N — matches the source shapefiles' CRS per
  dataset/README) so eps_m is genuinely meters, not degrees. Verified live
  against seeded geometry before being wired in here.

On IO-scoped turns (§4.1 rule 1), station_id is injected server-side and
overrides any model-supplied station_id/district_id filter; the payload
carries an applied-scope note.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.schemas import Citation, MapBlock, MapCenter, MapMarker, MapRadius
from app.supabase import SupabaseError, call_rpc

from .base import ToolContext, ToolResult, is_safe_code, sql_escape

_UTM_43N = 32643  # Karnataka source shapefiles' CRS (dataset/README).
_MAX_MARKERS = 30


def _build_filter_where(filters: dict, ctx: ToolContext) -> tuple[list[str], str | None]:
    filters = dict(filters)
    scope_note = None
    if ctx.scoped_station_id:
        filters["station_id"] = ctx.scoped_station_id
        filters.pop("district_id", None)
        scope_note = f"Scope: station {ctx.scoped_station_id}"

    where: list[str] = []
    for key, col in (
        ("crime_type_id", "crime_type_id"), ("district_id", "district_id"), ("station_id", "station_id"),
    ):
        value = filters.get(key)
        if value and is_safe_code(value):
            where.append(f"{col} = '{sql_escape(value)}'")
    date_from = filters.get("date_from")
    if isinstance(date_from, str) and date_from:
        where.append(f"registration_date >= '{sql_escape(date_from)}'")
    date_to = filters.get("date_to")
    if isinstance(date_to, str) and date_to:
        where.append(f"registration_date <= '{sql_escape(date_to)}'")
    return where, scope_note


class GeoQueryTool:
    name = "geo_query"
    label = "Running geospatial query"
    description = (
        "Geospatial analysis over FIR locations: incident_points (raw markers), "
        "hotspot_localities (count by locality), or cluster_dbscan (density clusters "
        "with centroid + radius, eps_m/min_points tunable)."
    )

    @property
    def params_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "op": {"type": "string", "enum": ["incident_points", "hotspot_localities", "cluster_dbscan"]},
                "filters": {
                    "type": "object",
                    "properties": {
                        "crime_type_id": {"type": "string"},
                        "district_id": {"type": "string"},
                        "station_id": {"type": "string"},
                        "date_from": {"type": "string"},
                        "date_to": {"type": "string"},
                    },
                },
                "eps_m": {"type": "number", "default": 300, "description": "cluster_dbscan only"},
                "min_points": {"type": "integer", "default": 4, "description": "cluster_dbscan only"},
                "top_k": {"type": "integer", "default": 30},
            },
            "required": ["op"],
        }

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        op = args.get("op")
        filters = args.get("filters") or {}
        where, scope_note = _build_filter_where(filters, ctx)
        where_clause = ("AND " + " AND ".join(where)) if where else ""

        try:
            if op == "incident_points":
                return await self._incident_points(where_clause, scope_note, args, ctx)
            if op == "hotspot_localities":
                return await self._hotspot_localities(where_clause, scope_note, args, ctx)
            if op == "cluster_dbscan":
                return await self._cluster_dbscan(where_clause, scope_note, args, ctx)
        except SupabaseError as exc:
            return ToolResult(ok=False, error=f"geo_query failed: {exc}")

        return ToolResult(ok=False, error=f"unknown op '{op}' (expected incident_points|hotspot_localities|cluster_dbscan)")

    async def _incident_points(self, where_clause: str, scope_note: str | None, args: dict, ctx: ToolContext) -> ToolResult:
        top_k = min(int(args.get("top_k", _MAX_MARKERS) or _MAX_MARKERS), _MAX_MARKERS)
        sql = f"""
            SELECT fir_id, latitude, longitude, investigation_status
            FROM firs
            WHERE geom IS NOT NULL {where_clause}
            ORDER BY registration_date DESC
            LIMIT {top_k}
        """
        result = await call_rpc("execute_agent_select", {"p_sql": sql, "p_scope": "case", "p_row_cap": top_k}, ctx.settings)
        rows = (result or {}).get("rows") or []
        if not rows:
            return ToolResult(ok=True, data={"marker_count": 0})

        markers = [
            MapMarker(
                id=f"fir-{r['fir_id']}", lat=float(r["latitude"]), lng=float(r["longitude"]),
                kind="fir", label=r["fir_id"], fir_id=r["fir_id"], status=r.get("investigation_status"),
            )
            for r in rows
        ]
        return self._respond_map(markers, None, scope_note, [r["fir_id"] for r in rows], "Incident points", ctx)

    async def _hotspot_localities(self, where_clause: str, scope_note: str | None, args: dict, ctx: ToolContext) -> ToolResult:
        top_k = min(int(args.get("top_k", 20) or 20), _MAX_MARKERS)
        sql = f"""
            SELECT l.locality_id, l.locality_name, ST_Y(l.centroid::geometry) AS lat, ST_X(l.centroid::geometry) AS lng,
                   count(f.fir_id) AS n
            FROM firs f
            JOIN localities l ON l.locality_id = f.incident_locality_id
            WHERE f.geom IS NOT NULL {where_clause}
            GROUP BY l.locality_id, l.locality_name, l.centroid
            ORDER BY n DESC
            LIMIT {top_k}
        """
        result = await call_rpc("execute_agent_select", {"p_sql": sql, "p_scope": "case", "p_row_cap": top_k}, ctx.settings)
        rows = (result or {}).get("rows") or []
        if not rows:
            return ToolResult(ok=True, data={"marker_count": 0})

        markers = [
            MapMarker(
                id=f"loc-{r['locality_id']}", lat=float(r["lat"]), lng=float(r["lng"]),
                kind="hotspot", label=f"{r['locality_name']} ({r['n']})",
            )
            for r in rows
        ]
        return self._respond_map(markers, None, scope_note, [], "Hotspot localities", ctx, extra={"clusters": rows})

    async def _cluster_dbscan(self, where_clause: str, scope_note: str | None, args: dict, ctx: ToolContext) -> ToolResult:
        eps_m = float(args.get("eps_m", 300) or 300)
        min_points = int(args.get("min_points", 4) or 4)
        sql = f"""
            WITH pts AS (
                SELECT fir_id, latitude, longitude, geom,
                       ST_ClusterDBSCAN(ST_Transform(geom::geometry, {_UTM_43N}), eps := {eps_m}, minpoints := {min_points}) OVER () AS cluster_id
                FROM firs
                WHERE geom IS NOT NULL {where_clause}
            ),
            clustered AS (SELECT * FROM pts WHERE cluster_id IS NOT NULL),
            centroids AS (
                SELECT cluster_id, count(*) AS n, avg(latitude) AS centroid_lat, avg(longitude) AS centroid_lng
                FROM clustered GROUP BY cluster_id
            )
            SELECT c.cluster_id, c.n, c.centroid_lat, c.centroid_lng,
                   max(ST_Distance(p.geom, ST_SetSRID(ST_MakePoint(c.centroid_lng, c.centroid_lat), 4326)::geography)) AS radius_m,
                   array_agg(p.fir_id) AS fir_ids
            FROM clustered p JOIN centroids c ON c.cluster_id = p.cluster_id
            GROUP BY c.cluster_id, c.n, c.centroid_lat, c.centroid_lng
            ORDER BY c.n DESC
        """
        result = await call_rpc("execute_agent_select", {"p_sql": sql, "p_scope": "case", "p_row_cap": 30}, ctx.settings)
        rows = (result or {}).get("rows") or []
        if not rows:
            return ToolResult(ok=True, data={"cluster_count": 0})

        markers: list[MapMarker] = []
        radii: list[dict] = []
        all_fir_ids: list[str] = []
        for r in rows:
            markers.append(MapMarker(
                id=f"cluster-{r['cluster_id']}", lat=float(r["centroid_lat"]), lng=float(r["centroid_lng"]),
                kind="hotspot", label=f"Cluster {r['cluster_id']} ({r['n']} incidents)",
            ))
            radii.append({
                "center_lat": float(r["centroid_lat"]), "center_lng": float(r["centroid_lng"]),
                "radius_meters": float(r["radius_m"]) if r["radius_m"] is not None else eps_m,
                "cluster_id": r["cluster_id"], "count": r["n"],
            })
            all_fir_ids.extend(r.get("fir_ids") or [])

        # MapBlock carries a single `radius` field; use the largest cluster's
        # radius overlay (the primary hotspot) — full per-cluster breakdown is
        # returned in `data.clusters` for the model to summarize as text/table.
        largest = max(radii, key=lambda x: x["count"])
        primary_radius = MapRadius(
            center_lat=largest["center_lat"], center_lng=largest["center_lng"],
            radius_meters=largest["radius_meters"],
            label=f"{len(rows)} clusters (eps={eps_m}m, min_points={min_points})",
        )
        return self._respond_map(
            markers, primary_radius, scope_note, all_fir_ids, "DBSCAN hotspot clusters", ctx,
            extra={"clusters": [{k: v for k, v in r.items() if k != "geom"} for r in rows]},
        )

    def _respond_map(
        self, markers: list[MapMarker], radius: MapRadius | None, scope_note: str | None,
        fir_ids: list[str], title: str, ctx: ToolContext, extra: dict | None = None,
    ) -> ToolResult:
        if not markers:
            return ToolResult(ok=True, data={"marker_count": 0, **(extra or {})})

        full_title = f"{title} — {scope_note}" if scope_note else title
        center = MapCenter(
            lat=sum(m.lat for m in markers) / len(markers),
            lng=sum(m.lng for m in markers) / len(markers),
        )
        citations = [Citation(level="fir", fir_id=f) for f in dict.fromkeys(fir_ids)][:30]
        block = MapBlock(
            id=f"map-{uuid.uuid4().hex[:8]}", title=full_title, center=center,
            markers=markers[:_MAX_MARKERS], radius=radius, citations=citations,
        )
        payload_id = None
        if ctx.scratchpad is not None:
            payload_id = ctx.scratchpad.register_payload(block)
            for f in dict.fromkeys(fir_ids):
                ctx.scratchpad.register_provenance("fir", {"fir_id": f})

        return ToolResult(
            ok=True,
            data={"marker_count": len(markers), "scope_applied": ctx.scoped_station_id is not None, **(extra or {})},
            payload_id=payload_id,
        )
