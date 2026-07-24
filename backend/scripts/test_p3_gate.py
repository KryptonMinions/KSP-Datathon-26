"""P3 gate (live, no LLM needed) — direct .run() calls against live Supabase
for mo_match, build_network, geo_query, trend_series, incl. §4.1 jurisdiction
scope enforcement (filter injection + anchor admission).

Run: cd backend && python -m scripts.test_p3_gate
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent.tools.analysis import MoMatchTool, TrendSeriesTool  # noqa: E402
from app.agent.tools.base import ToolContext  # noqa: E402
from app.agent.tools.entities import ResolveEntityTool  # noqa: E402
from app.agent.tools.geo import GeoQueryTool  # noqa: E402
from app.agent.tools.network import BuildNetworkTool  # noqa: E402
from app.agent.scratchpad import TurnScratchpad  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.roles import Role  # noqa: E402
from app.schemas import CurrentUser  # noqa: E402

S = get_settings()
RESOLVE, MO, NET, GEO, TREND = ResolveEntityTool(), MoMatchTool(), BuildNetworkTool(), GeoQueryTool(), TrendSeriesTool()

passed = failed = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {label}  {detail}")
    else:
        failed += 1
        print(f"  FAIL  {label}  {detail}")


def ctx(scoped_station_id: str | None = None) -> ToolContext:
    return ToolContext(
        user=CurrentUser(id="u", role=Role.INVESTIGATING_OFFICER, officer_id="KSP-23417"),
        frame=None, settings=S, scratchpad=TurnScratchpad(), scoped_station_id=scoped_station_id,
    )


async def main() -> int:
    # --- resolve a real seed person for downstream tools ---
    r = await RESOLVE.run({"kind": "person", "text": "ravi kumara"}, ctx())
    check("resolve_entity finds Ravi Kumara", r.ok and r.data["candidates"], f"n={len(r.data.get('candidates', []))}" if r.ok else r.error)
    ravi_id = r.data["candidates"][0]["person_id"] if r.ok and r.data["candidates"] else None

    print("\n=== mo_match ===")
    # Find any FIR with an mo_code_id to anchor on.
    from app.supabase import call_rpc
    rows = (await call_rpc("execute_agent_select", {"p_sql": "SELECT fir_id FROM firs WHERE mo_code_id IS NOT NULL LIMIT 1", "p_scope": "case", "p_row_cap": 1}, S) or {}).get("rows", [])
    if rows:
        anchor_fir = rows[0]["fir_id"]
        r = await MO.run({"anchor": {"fir_id": anchor_fir}, "top_k": 5}, ctx())
        check("mo_match by fir_id anchor", r.ok, f"count={r.data.get('count')}" if r.ok else r.error)
    else:
        check("mo_match by fir_id anchor", False, "no FIR with mo_code_id found to test with")

    r = await MO.run({"anchor": {"mo_code_id": "NOT-A-REAL-CODE"}}, ctx())
    check("mo_match unknown mo_code -> empty, not error", r.ok and r.data.get("count", -1) == 0, str(r.data) if r.ok else r.error)

    print("\n=== build_network (unscoped) ===")
    if ravi_id:
        r = await NET.run({"seed": {"person_id": ravi_id}, "depth": 2, "max_nodes": 30}, ctx())
        check("build_network unscoped traversal", r.ok, f"nodes={r.data.get('node_count')} edges={r.data.get('edge_count')}" if r.ok else r.error)
    else:
        check("build_network unscoped traversal", False, "no seed person resolved")

    r = await NET.run({"seed": {"person_id": "not-a-uuid"}}, ctx())
    check("build_network rejects non-UUID seed", not r.ok, r.error or "")

    print("\n=== geo_query (unscoped) ===")
    r = await GEO.run({"op": "incident_points", "top_k": 10}, ctx())
    check("geo_query incident_points", r.ok, f"markers={r.data.get('marker_count')}" if r.ok else r.error)

    r = await GEO.run({"op": "cluster_dbscan", "eps_m": 800, "min_points": 3}, ctx())
    check("geo_query cluster_dbscan", r.ok, f"markers={r.data.get('marker_count')}" if r.ok else r.error)

    r = await GEO.run({"op": "hotspot_localities", "top_k": 10}, ctx())
    check("geo_query hotspot_localities", r.ok, f"markers={r.data.get('marker_count')}" if r.ok else r.error)

    print("\n=== trend_series (unscoped) ===")
    r = await TREND.run({"bucket": "month", "date_from": "2020-01-01", "date_to": "2027-01-01"}, ctx())
    check("trend_series no group_by", r.ok, f"rows={r.data.get('row_count')}" if r.ok else r.error)

    r = await TREND.run({"bucket": "month", "group_by": "district", "date_from": "2020-01-01", "date_to": "2027-01-01"}, ctx())
    check("trend_series group_by district", r.ok, f"rows={r.data.get('row_count')}" if r.ok else r.error)

    print("\n=== §4.1 jurisdiction scope enforcement ===")
    # Demo IO KSP-23417 is stationed at KA-MYS-012 (confirmed in P1 recon).
    demo_station = "KA-MYS-012"

    r = await GEO.run({"op": "incident_points", "filters": {"district_id": "BLR", "station_id": "KA-BLR-999"}}, ctx(scoped_station_id=demo_station))
    check(
        "geo_query: model-supplied station/district overridden by scope",
        r.ok and r.data.get("scope_applied") is True,
        str(r.data) if r.ok else r.error,
    )

    r = await TREND.run({"bucket": "month", "filters": {"district_id": "BLR"}, "date_from": "2020-01-01", "date_to": "2027-01-01"}, ctx(scoped_station_id=demo_station))
    check("trend_series: scope_applied under scoped ctx", r.ok and r.data.get("scope_applied") is True, str(r.data) if r.ok else r.error)

    # Anchor admission: a person with a real case at KA-MYS-012 should be admitted.
    rows = (await call_rpc("execute_agent_select", {"p_sql": f"SELECT DISTINCT fa.person_id FROM fir_accused fa JOIN firs f ON f.fir_id=fa.fir_id WHERE f.station_id='{demo_station}' LIMIT 1", "p_scope": "case", "p_row_cap": 1}, S) or {}).get("rows", [])
    if rows:
        admitted_person = rows[0]["person_id"]
        r = await NET.run({"seed": {"person_id": admitted_person}}, ctx(scoped_station_id=demo_station))
        check("build_network: anchor WITH case at station is admitted", r.ok and r.hard_refuse_reason is None, r.error or "")
    else:
        check("build_network: anchor WITH case at station is admitted", False, "no accused-with-case-at-station found to test with")

    # Anchor admission failure: a person resolved with NO case at that station.
    if ravi_id:
        # Ravi's FIRs are at MYS/BLR stations other than KA-MYS-012 per seed data (Thread A); verify via direct query.
        has_case = (await call_rpc("execute_agent_select", {"p_sql": f"SELECT 1 FROM fir_accused fa JOIN firs f ON f.fir_id=fa.fir_id WHERE fa.person_id='{ravi_id}' AND f.station_id='{demo_station}' LIMIT 1", "p_scope": "case", "p_row_cap": 1}, S) or {}).get("rows", [])
        r = await NET.run({"seed": {"person_id": ravi_id}}, ctx(scoped_station_id=demo_station))
        if has_case:
            check("build_network: anchor admission (Ravi happens to have a case there)", r.ok, r.error or "")
        else:
            check(
                "build_network: anchor WITHOUT case at station -> hard_refuse_reason=out_of_scope",
                (not r.ok) and r.hard_refuse_reason == "out_of_scope",
                f"ok={r.ok} hard_refuse_reason={r.hard_refuse_reason} error={r.error}",
            )

    print(f"\nP3 GATE: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
