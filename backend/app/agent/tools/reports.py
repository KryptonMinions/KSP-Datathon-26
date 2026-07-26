"""build_pack_report — comparative review-pack metrics for report_composer.

Not in the original v1 tool contract — added 2026-07-26 to close a gap found
empirically during the P6 demo pass: report_composer had `pack_report` in its
allowed_blocks but no tool that ever produced one, so "review pack"/
"bandobast brief" requests either substituted the wrong block type or burned
the full iteration budget on exploratory run_sql calls (confirmed as both a
missing-block bug and the session's latency outlier — same root cause).

Computes a fixed set of period-over-period metrics (FIR count, open cases,
chargesheets filed, upcoming chargesheet deadlines, crime-type breakdown)
scoped by district/station/gang/crime_type, comparing the requested period
against an equal-length immediately-preceding period. Fixed, parameterized
SQL — never model-authored — same pattern as geo_query/trend_series/mo_match.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from app.schemas import Citation, PackReportBlock, TrendMetric
from app.supabase import SupabaseError, call_rpc

from .base import ToolContext, ToolResult, is_safe_code, is_valid_uuid, sql_escape


def _pct_delta(current: float, previous: float) -> float:
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round((current - previous) / previous * 100, 1)


def _trend(current: float, previous: float) -> str:
    if current > previous:
        return "up"
    if current < previous:
        return "down"
    return "stable"


async def _select_rows(sql: str, settings, row_cap: int) -> list[dict]:
    result = await call_rpc("execute_agent_select", {"p_sql": sql, "p_scope": "case", "p_row_cap": row_cap}, settings)
    return (result or {}).get("rows") or []


async def _select_one(sql: str, settings) -> dict:
    rows = await _select_rows(sql, settings, 1)
    return rows[0] if rows else {}


class BuildPackReportTool:
    name = "build_pack_report"
    label = "Building review pack"
    description = (
        "Build a comparative review-pack (period-over-period metrics: FIR count, open cases, "
        "chargesheets filed, upcoming chargesheet deadlines within 7 days, crime-type breakdown) "
        "scoped by district/station/gang/crime_type. Use for 'review pack'/'bandobast brief'/"
        "district-comparison summary requests — do not hand-build this from run_sql."
    )

    @property
    def params_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "period_label": {"type": "string", "description": "e.g. 'This month', 'Last 30 days'"},
                "date_from": {"type": "string", "description": "current period start, YYYY-MM-DD"},
                "date_to": {"type": "string", "description": "current period end, YYYY-MM-DD"},
                "filters": {
                    "type": "object",
                    "properties": {
                        "district_id": {"type": "string"},
                        "station_id": {"type": "string"},
                        "gang_id": {"type": "string", "description": "canonical UUID from resolve_entity/run_sql"},
                        "crime_type_id": {"type": "string"},
                    },
                },
            },
            "required": ["title", "period_label", "date_from", "date_to"],
        }

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        title = (args.get("title") or "Review Pack").strip()
        period_label = (args.get("period_label") or "").strip()
        date_from, date_to = args.get("date_from"), args.get("date_to")
        if not (date_from and date_to):
            return ToolResult(ok=False, error="date_from and date_to are required (YYYY-MM-DD)")
        try:
            d_from, d_to = date.fromisoformat(date_from), date.fromisoformat(date_to)
        except ValueError:
            return ToolResult(ok=False, error="date_from/date_to must be YYYY-MM-DD")
        if d_to < d_from:
            return ToolResult(ok=False, error="date_to must not be before date_from")

        span_days = (d_to - d_from).days + 1
        cmp_to = d_from - timedelta(days=1)
        cmp_from = cmp_to - timedelta(days=span_days - 1)

        filters = args.get("filters") or {}
        where: list[str] = []
        join_gang = ""
        for key, col in (("district_id", "district_id"), ("station_id", "station_id"), ("crime_type_id", "crime_type_id")):
            value = filters.get(key)
            if value and is_safe_code(value):
                where.append(f"f.{col} = '{sql_escape(value)}'")
        gang_id = filters.get("gang_id")
        if gang_id:
            if not is_valid_uuid(gang_id):
                return ToolResult(ok=False, error="filters.gang_id must be a canonical UUID (resolve it first)")
            join_gang = (
                "JOIN fir_accused fa ON fa.fir_id = f.fir_id "
                "JOIN gang_memberships gm ON gm.person_id = fa.person_id "
                f"AND gm.gang_id = '{sql_escape(gang_id)}' AND gm.is_active = true"
            )
        where_clause = ("AND " + " AND ".join(where)) if where else ""

        try:
            return await self._build(ctx, title, period_label, d_from, d_to, cmp_from, cmp_to, join_gang, where_clause)
        except SupabaseError as exc:
            return ToolResult(ok=False, error=f"build_pack_report query failed: {exc}")

    async def _build(
        self, ctx: ToolContext, title: str, period_label: str,
        d_from: date, d_to: date, cmp_from: date, cmp_to: date, join_gang: str, where_clause: str,
    ) -> ToolResult:
        settings = ctx.settings
        metrics: list[TrendMetric] = []
        fir_citations: set[str] = set()
        window_pred = f"f.registration_date::date BETWEEN '{cmp_from}' AND '{d_to}'"

        def period_counts_sql(extra_pred: str = "") -> str:
            # count(DISTINCT f.fir_id), not count(*): join_gang fans a FIR out
            # to one row per gang-member accused, so count(*) over-counts any
            # FIR with more than one gang-member co-accused.
            return f"""
                SELECT
                    count(DISTINCT f.fir_id) FILTER (WHERE f.registration_date::date BETWEEN '{d_from}' AND '{d_to}'{extra_pred}) AS current_count,
                    count(DISTINCT f.fir_id) FILTER (WHERE f.registration_date::date BETWEEN '{cmp_from}' AND '{cmp_to}'{extra_pred}) AS previous_count
                FROM firs f {join_gang}
                WHERE {window_pred} {where_clause}
            """

        row = await _select_one(period_counts_sql(), settings)
        cur, prev = float(row.get("current_count") or 0), float(row.get("previous_count") or 0)
        metrics.append(TrendMetric(category="FIR count", current=cur, previous=prev, delta_pct=_pct_delta(cur, prev), trend=_trend(cur, prev)))

        # Citation-worthy sample of the actual FIRs behind these numbers
        # (DEMO_SCENARIOS.md §6.2: every answer block needs >=1 real citation
        # — the deadline-flag list alone can be empty on a clean period).
        sample_sql = f"""
            SELECT DISTINCT f.fir_id, f.registration_date FROM firs f {join_gang}
            WHERE {window_pred} {where_clause}
            ORDER BY f.registration_date DESC
            LIMIT 20
        """
        fir_citations.update(r["fir_id"] for r in await _select_rows(sample_sql, settings, 20))

        row = await _select_one(period_counts_sql(" AND f.investigation_status IN ('Open','Under_Investigation')"), settings)
        cur, prev = float(row.get("current_count") or 0), float(row.get("previous_count") or 0)
        metrics.append(TrendMetric(category="Open cases", current=cur, previous=prev, delta_pct=_pct_delta(cur, prev), trend=_trend(cur, prev)))

        cs_sql = f"""
            SELECT
                count(DISTINCT cs.fir_id) FILTER (WHERE cs.filing_date BETWEEN '{d_from}' AND '{d_to}') AS current_count,
                count(DISTINCT cs.fir_id) FILTER (WHERE cs.filing_date BETWEEN '{cmp_from}' AND '{cmp_to}') AS previous_count
            FROM chargesheets cs
            JOIN firs f ON f.fir_id = cs.fir_id {join_gang}
            WHERE cs.filing_date BETWEEN '{cmp_from}' AND '{d_to}' {where_clause}
        """
        row = await _select_one(cs_sql, settings)
        cur, prev = float(row.get("current_count") or 0), float(row.get("previous_count") or 0)
        metrics.append(TrendMetric(category="Chargesheets filed", current=cur, previous=prev, delta_pct=_pct_delta(cur, prev), trend=_trend(cur, prev)))

        deadline_sql = f"""
            SELECT DISTINCT f.fir_id, f.chargesheet_deadline
            FROM firs f {join_gang}
            WHERE f.chargesheet_deadline IS NOT NULL
              AND f.chargesheet_deadline BETWEEN '{d_to}' AND '{d_to + timedelta(days=7)}'
              AND f.investigation_status IN ('Open','Under_Investigation')
              {where_clause}
            ORDER BY f.chargesheet_deadline
            LIMIT 20
        """
        deadline_rows = await _select_rows(deadline_sql, settings, 20)
        deadline_firs = [r["fir_id"] for r in deadline_rows]
        fir_citations.update(deadline_firs)
        metrics.append(TrendMetric(
            category="Chargesheet deadlines (next 7 days)", current=float(len(deadline_firs)), previous=0.0,
            delta_pct=0.0, trend="stable",
            anomaly=len(deadline_firs) > 0,
            anomaly_note=f"{len(deadline_firs)} FIR(s) due within 7 days" if deadline_firs else None,
            underlying_fir_ids=deadline_firs or None,
        ))

        breakdown_sql = f"""
            SELECT ct.crime_type_name,
                count(DISTINCT f.fir_id) FILTER (WHERE f.registration_date::date BETWEEN '{d_from}' AND '{d_to}') AS current_count,
                count(DISTINCT f.fir_id) FILTER (WHERE f.registration_date::date BETWEEN '{cmp_from}' AND '{cmp_to}') AS previous_count
            FROM firs f {join_gang}
            JOIN crime_types ct ON ct.crime_type_id = f.crime_type_id
            WHERE {window_pred} {where_clause}
            GROUP BY ct.crime_type_name
            ORDER BY current_count DESC
            LIMIT 5
        """
        for r in await _select_rows(breakdown_sql, settings, 5):
            cur, prev = float(r.get("current_count") or 0), float(r.get("previous_count") or 0)
            if cur == 0 and prev == 0:
                continue
            metrics.append(TrendMetric(category=r["crime_type_name"], current=cur, previous=prev, delta_pct=_pct_delta(cur, prev), trend=_trend(cur, prev)))

        block = PackReportBlock(
            id=f"pack-{uuid.uuid4().hex[:8]}",
            title=title,
            period=period_label or f"{d_from.isoformat()} to {d_to.isoformat()}",
            metrics=metrics,
            exportable=True,
            citations=[Citation(level="fir", fir_id=f) for f in sorted(fir_citations)] or None,
        )

        payload_id = None
        if ctx.scratchpad is not None:
            payload_id = ctx.scratchpad.register_payload(block)
            for f in fir_citations:
                ctx.scratchpad.register_provenance("fir", {"fir_id": f})

        return ToolResult(ok=True, data={"metric_count": len(metrics), "period": block.period}, payload_id=payload_id)
