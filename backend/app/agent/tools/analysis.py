"""mo_match + trend_series (ORCHESTRATOR_STEERING.md §9.6, §9.9).

mo_match: structured match on shared mo_code_id only — narrative-similarity
re-rank via document_chunks is deferred (OVERNIGHT_BUILD_PLAN.md cut register:
"drop mo_match narrative re-rank (structured mo_code_id match only)").

trend_series: date_trunc aggregation. On IO-scoped turns (§4.1 rule 2),
station_id is injected server-side and overrides any model-supplied
station_id/district_id filter.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.schemas import Citation, MoMatch, MoMatchBlock, TableBlock, TableColumn
from app.supabase import SupabaseError, call_rpc

from .base import ToolContext, ToolResult, is_safe_code, is_valid_fir_id, sql_escape


def _map_outcome(investigation_status: str | None, court_outcome: str | None) -> str:
    if court_outcome == "Convicted":
        return "convicted"
    if investigation_status == "Chargesheet_Filed":
        return "trial_pending"
    if investigation_status in ("Open", "Under_Investigation", "Transferred"):
        return "investigation_ongoing"
    if investigation_status == "Closed":
        return "closed_false"
    return "investigation_ongoing"


class MoMatchTool:
    name = "mo_match"
    label = "Matching MO pattern"
    description = (
        "Find other FIRs sharing the same modus-operandi code as an anchor FIR or "
        "MO code. Structured match only (same mo_code_id) — top_k <= 10."
    )

    @property
    def params_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "anchor": {
                    "type": "object",
                    "properties": {"fir_id": {"type": "string"}, "mo_code_id": {"type": "string"}},
                    "description": "Provide exactly one of fir_id or mo_code_id.",
                },
                "filters": {
                    "type": "object",
                    "properties": {
                        "district_id": {"type": "string"},
                        "date_from": {"type": "string"},
                        "date_to": {"type": "string"},
                        "exclude_fir_id": {"type": "string"},
                    },
                },
                "top_k": {"type": "integer", "default": 10, "maximum": 10},
            },
            "required": ["anchor"],
        }

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        anchor = args.get("anchor") or {}
        anchor_fir_id = anchor.get("fir_id")
        mo_code_id = anchor.get("mo_code_id")

        if anchor_fir_id and not is_valid_fir_id(anchor_fir_id):
            return ToolResult(ok=False, error="anchor.fir_id is not a valid FIR ID format")
        if mo_code_id and not is_safe_code(mo_code_id):
            return ToolResult(ok=False, error="anchor.mo_code_id has an invalid format")

        if not mo_code_id and anchor_fir_id:
            lookup_sql = f"SELECT mo_code_id FROM firs WHERE fir_id = '{sql_escape(anchor_fir_id)}'"
            try:
                result = await call_rpc(
                    "execute_agent_select",
                    {"p_sql": lookup_sql, "p_scope": "case", "p_row_cap": 1},
                    ctx.settings,
                )
            except SupabaseError as exc:
                return ToolResult(ok=False, error=f"mo_match lookup failed: {exc}")
            rows = (result or {}).get("rows") or []
            if not rows or not rows[0].get("mo_code_id"):
                return ToolResult(ok=False, error="anchor FIR not found or has no MO code linked")
            mo_code_id = rows[0]["mo_code_id"]

        if not mo_code_id:
            return ToolResult(ok=False, error="anchor must include a valid fir_id or mo_code_id")

        filters = args.get("filters") or {}
        top_k = min(int(args.get("top_k", 10) or 10), 10)

        where = [f"f.mo_code_id = '{sql_escape(mo_code_id)}'"]
        exclude = filters.get("exclude_fir_id") or anchor_fir_id
        if exclude and is_valid_fir_id(exclude):
            where.append(f"f.fir_id != '{sql_escape(exclude)}'")
        district_id = filters.get("district_id")
        if district_id and is_safe_code(district_id):
            where.append(f"f.district_id = '{sql_escape(district_id)}'")
        date_from = filters.get("date_from")
        if isinstance(date_from, str) and date_from:
            where.append(f"f.registration_date >= '{sql_escape(date_from)}'")
        date_to = filters.get("date_to")
        if isinstance(date_to, str) and date_to:
            where.append(f"f.registration_date <= '{sql_escape(date_to)}'")

        sql = f"""
            SELECT f.fir_id, ps.station_name, f.registration_date, f.investigation_status,
                   cd.outcome AS court_outcome
            FROM firs f
            JOIN police_stations ps ON ps.station_id = f.station_id
            LEFT JOIN court_disposals cd ON cd.fir_id = f.fir_id
            WHERE {' AND '.join(where)}
            ORDER BY f.registration_date DESC
            LIMIT {top_k}
        """
        try:
            result = await call_rpc(
                "execute_agent_select", {"p_sql": sql, "p_scope": "case", "p_row_cap": top_k}, ctx.settings
            )
        except SupabaseError as exc:
            return ToolResult(ok=False, error=f"mo_match query failed: {exc}")

        rows = (result or {}).get("rows") or []
        if not rows:
            return ToolResult(ok=True, data={"count": 0, "mo_code_id": mo_code_id})

        matches = [
            MoMatch(
                fir_id=r["fir_id"],
                station=r["station_name"],
                similarity=1.0,
                outcome=_map_outcome(r.get("investigation_status"), r.get("court_outcome")),
            )
            for r in rows
        ]
        citations = [Citation(level="fir", fir_id=m.fir_id) for m in matches]
        block = MoMatchBlock(
            id=f"mo-{uuid.uuid4().hex[:8]}",
            query_description=f"FIRs sharing MO code {mo_code_id}",
            matches=matches,
            citations=citations,
        )
        payload_id = None
        if ctx.scratchpad is not None:
            payload_id = ctx.scratchpad.register_payload(block)
            for m in matches:
                ctx.scratchpad.register_provenance("fir", {"fir_id": m.fir_id})

        return ToolResult(ok=True, data={"count": len(matches), "mo_code_id": mo_code_id}, payload_id=payload_id)


_GROUP_COLUMNS = {"crime_type": "crime_type_id", "station": "station_id", "district": "district_id"}


class TrendSeriesTool:
    name = "trend_series"
    label = "Computing trend"
    description = "FIR-count time series (week/month buckets), optionally grouped by crime_type/station/district."

    @property
    def params_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "metric": {"type": "string", "enum": ["fir_count"]},
                "bucket": {"type": "string", "enum": ["week", "month"]},
                "group_by": {"type": "string", "enum": ["crime_type", "station", "district"]},
                "filters": {
                    "type": "object",
                    "properties": {
                        "crime_type_id": {"type": "string"},
                        "district_id": {"type": "string"},
                        "station_id": {"type": "string"},
                    },
                },
                "date_from": {"type": "string"},
                "date_to": {"type": "string"},
            },
            "required": ["bucket", "date_from", "date_to"],
        }

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        bucket = args.get("bucket")
        if bucket not in ("week", "month"):
            return ToolResult(ok=False, error="bucket must be 'week' or 'month'")

        group_by = args.get("group_by")
        if group_by is not None and group_by not in _GROUP_COLUMNS:
            return ToolResult(ok=False, error=f"group_by must be one of {sorted(_GROUP_COLUMNS)}")

        filters = dict(args.get("filters") or {})
        scope_note = None
        if ctx.scoped_station_id:
            filters["station_id"] = ctx.scoped_station_id
            filters.pop("district_id", None)
            scope_note = f"Scope: station {ctx.scoped_station_id}"

        where: list[str] = []
        for key, col in (("crime_type_id", "crime_type_id"), ("district_id", "district_id"), ("station_id", "station_id")):
            value = filters.get(key)
            if value and is_safe_code(value):
                where.append(f"{col} = '{sql_escape(value)}'")
        date_from, date_to = args.get("date_from"), args.get("date_to")
        if not (isinstance(date_from, str) and date_from and isinstance(date_to, str) and date_to):
            return ToolResult(ok=False, error="date_from and date_to are both required")
        where.append(f"registration_date >= '{sql_escape(date_from)}'")
        where.append(f"registration_date <= '{sql_escape(date_to)}'")
        where_clause = "WHERE " + " AND ".join(where)

        group_select = ""
        group_by_clause = "GROUP BY bucket"
        if group_by:
            col = _GROUP_COLUMNS[group_by]
            group_select = f", {col} AS group_key"
            group_by_clause = f"GROUP BY bucket, {col}"

        sql = f"""
            SELECT date_trunc('{bucket}', registration_date) AS bucket, count(*) AS fir_count{group_select}
            FROM firs
            {where_clause}
            {group_by_clause}
            ORDER BY bucket
        """
        try:
            result = await call_rpc(
                "execute_agent_select", {"p_sql": sql, "p_scope": "case", "p_row_cap": 500}, ctx.settings
            )
        except SupabaseError as exc:
            return ToolResult(ok=False, error=f"trend_series query failed: {exc}")

        rows = (result or {}).get("rows") or []
        columns = [TableColumn(key="bucket", label="Period")]
        if group_by:
            columns.append(TableColumn(key="group_key", label=group_by.replace("_", " ").title()))
        columns.append(TableColumn(key="fir_count", label="FIR Count", align="right"))

        table_rows = []
        for r in rows:
            row = {"bucket": str(r.get("bucket")), "fir_count": r.get("fir_count", 0)}
            if group_by:
                row["group_key"] = r.get("group_key") or "(unassigned)"
            table_rows.append(row)

        title = f"FIR count by {bucket}" + (f", grouped by {group_by}" if group_by else "")
        if scope_note:
            title += f" — {scope_note}"
        block = TableBlock(id=f"trend-{uuid.uuid4().hex[:8]}", title=title, columns=columns, rows=table_rows)

        payload_id = None
        if ctx.scratchpad is not None:
            payload_id = ctx.scratchpad.register_payload(block)

        return ToolResult(
            ok=True,
            data={"row_count": len(table_rows), "scope_applied": ctx.scoped_station_id is not None},
            payload_id=payload_id,
        )
