"""P1 gate (live) — golden queries + privilege-drop proofs through the real
runtime path: run_sql -> execute_agent_select RPC -> SET ROLE ask_agent_ro.

Needs live Supabase creds in backend/.env. Run:
    cd backend && python -m scripts.test_p1_gate
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent.tools.base import ToolContext  # noqa: E402
from app.agent.tools.sql import RunSqlTool  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.roles import Role  # noqa: E402
from app.schemas import CurrentUser  # noqa: E402
from app.supabase import SupabaseError, call_rpc  # noqa: E402

S = get_settings()
RS = RunSqlTool()


def _ctx(scope: str = "case") -> ToolContext:
    return ToolContext(
        user=CurrentUser(id="u", role=Role.INVESTIGATING_OFFICER, officer_id="KSP-23417"),
        frame=None,
        settings=S,
        sql_scope=scope,
    )


async def run_sql(sql: str, scope: str = "case"):
    return await RS.run({"sql": sql, "purpose": "p1 gate"}, _ctx(scope))


async def main() -> int:
    passed = failed = 0

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"  PASS  {label}  {detail}")
        else:
            failed += 1
            print(f"  FAIL  {label}  {detail}")

    print("=== Golden queries (Thread A) — expect rows ===")
    r = await run_sql(
        "SELECT p.full_name, f.fir_id, f.investigation_status "
        "FROM persons p JOIN fir_accused fa ON fa.person_id = p.person_id "
        "JOIN firs f ON f.fir_id = fa.fir_id "
        "WHERE p.full_name ILIKE '%ravi kumara%'"
    )
    check("ravi kumara antecedents", r.ok and r.data["row_count"] > 0,
          f"rows={r.data['row_count'] if r.ok else r.error}")
    if r.ok and r.data["rows"]:
        print(f"        sample: {r.data['rows'][0]}")

    r = await run_sql(
        "SELECT hs.hs_number, hs.category, hs.risk_level FROM history_sheets hs "
        "JOIN persons p ON p.person_id = hs.person_id "
        "WHERE p.full_name ILIKE '%ravi kumara%'"
    )
    check("history sheet lookup", r.ok, f"rows={r.data['row_count'] if r.ok else r.error}")

    r = await run_sql("SELECT gang_name, operating_district FROM gangs WHERE gang_name ILIKE '%chain gang%'")
    check("chain gang lookup", r.ok and r.data["row_count"] > 0,
          f"{r.data['rows'] if r.ok else r.error}")

    r = await run_sql("SELECT count(*) AS n FROM firs WHERE station_id = 'KA-MYS-012'")
    check("count firs at demo IO station", r.ok, f"{r.data['rows'] if r.ok else r.error}")

    r = await run_sql(
        "SELECT ka.association_type, ka.confidence FROM known_associates ka "
        "JOIN persons a ON a.person_id = ka.person_id_a "
        "JOIN persons b ON b.person_id = ka.person_id_b LIMIT 5"
    )
    check("known_associates join", r.ok, f"rows={r.data['row_count'] if r.ok else r.error}")

    print("\n=== Privilege drop (bypass the app guard, hit the RPC directly) ===")
    # DML straight to the RPC — must NOT execute.
    try:
        await call_rpc("execute_agent_select",
                       {"p_sql": "DELETE FROM firs WHERE fir_id = 'nope'", "p_scope": "case", "p_row_cap": 10}, S)
        check("direct DELETE via RPC blocked", False, "RPC accepted a DELETE!")
    except SupabaseError as exc:
        check("direct DELETE via RPC blocked", True, f"rejected ({str(exc)[:70]}...)")

    # SELECT from a non-granted table — valid SQL, must fail on privileges.
    try:
        await call_rpc("execute_agent_select",
                       {"p_sql": "SELECT * FROM user_directory", "p_scope": "case", "p_row_cap": 10}, S)
        check("non-granted table read blocked", False, "read user_directory!")
    except SupabaseError as exc:
        check("non-granted table read blocked", True, f"rejected ({str(exc)[:70]}...)")

    # Scope isolation: case table under audit role must be denied.
    try:
        await call_rpc("execute_agent_select",
                       {"p_sql": "SELECT * FROM firs", "p_scope": "audit", "p_row_cap": 1}, S)
        check("audit-scope cannot read case table", False, "read firs under audit scope!")
    except SupabaseError as exc:
        check("audit-scope cannot read case table", True, f"rejected ({str(exc)[:70]}...)")

    # Audit scope CAN read audit table.
    r = await run_sql("SELECT count(*) AS n FROM query_audit_log", scope="audit")
    check("audit-scope reads query_audit_log", r.ok, f"{r.data['rows'] if r.ok else r.error}")

    print("\n=== RAG vector RPC (match_document_chunks) structural check ===")
    vec = "[" + ",".join(["0.02"] * 768) + "]"
    try:
        res = await call_rpc("match_document_chunks", {"p_embedding": vec, "p_filters": {}, "p_k": 3}, S)
        ok = isinstance(res, list) and len(res) > 0 and "similarity" in res[0]
        check("match_document_chunks returns chunks", ok,
              f"got {len(res) if isinstance(res, list) else res} rows; first_field={res[0].get('source_field') if ok else '-'}")
    except SupabaseError as exc:
        check("match_document_chunks returns chunks", False, str(exc)[:100])

    print(f"\nP1 GATE: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
