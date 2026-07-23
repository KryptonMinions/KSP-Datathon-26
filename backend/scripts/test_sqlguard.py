"""SQLGuard unit matrix (ORCHESTRATOR_STEERING.md M1 gate — offline).

Runnable without pytest: `cd backend && python -m scripts.test_sqlguard`.
Each case asserts the guard's allow/reject verdict for a (sql, scope).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent.tools.sql import SQLGuardError, validate_sql  # noqa: E402

# (label, sql, scope, should_pass)
CASES: list[tuple[str, str, str, bool]] = [
    # --- allowed ---
    ("simple select", "SELECT * FROM firs LIMIT 5", "case", True),
    ("projected where", "SELECT fir_id, station_id FROM firs WHERE district_id = 'MYS'", "case", True),
    ("cte", "WITH x AS (SELECT fir_id FROM firs) SELECT * FROM x", "case", True),
    ("join chain",
     "SELECT f.fir_id, p.full_name FROM firs f "
     "JOIN fir_accused fa ON fa.fir_id = f.fir_id "
     "JOIN persons p ON p.person_id = fa.person_id", "case", True),
    ("group by aggregate", "SELECT district_id, count(*) FROM firs GROUP BY district_id", "case", True),
    ("union of selects", "SELECT fir_id FROM firs UNION SELECT escalated_fir_id FROM ncr_petitions", "case", True),
    ("in-subquery", "SELECT * FROM persons WHERE person_id IN (SELECT person_id FROM fir_accused)", "case", True),
    ("audit scope select", "SELECT * FROM query_audit_log WHERE is_flagged = true", "audit", True),
    ("postgis join ok", "SELECT fir_id FROM firs WHERE ST_DWithin(geom, geom, 300)", "case", True),

    # --- rejected: not read-only ---
    ("insert", "INSERT INTO firs (fir_id) VALUES ('x')", "case", False),
    ("update", "UPDATE firs SET fir_narrative = 'x'", "case", False),
    ("delete", "DELETE FROM firs", "case", False),
    ("drop", "DROP TABLE firs", "case", False),
    ("create", "CREATE TABLE x (id int)", "case", False),
    ("alter", "ALTER TABLE firs ADD COLUMN x int", "case", False),
    ("select into", "SELECT * INTO newtbl FROM firs", "case", False),
    ("cte with delete", "WITH d AS (DELETE FROM firs RETURNING fir_id) SELECT * FROM d", "case", False),

    # --- rejected: multi-statement ---
    ("two selects", "SELECT 1; SELECT 2", "case", False),
    ("select then drop", "SELECT * FROM firs; DROP TABLE firs", "case", False),

    # --- rejected: catalog / schema ---
    ("pg_catalog", "SELECT * FROM pg_catalog.pg_tables", "case", False),
    ("information_schema", "SELECT * FROM information_schema.tables", "case", False),
    ("auth schema", "SELECT * FROM auth.users", "case", False),

    # --- rejected: scope / allowlist ---
    ("non-allowlist table", "SELECT * FROM user_directory", "case", False),
    ("case table under audit scope", "SELECT * FROM firs", "audit", False),
    ("audit table under case scope", "SELECT * FROM query_audit_log", "case", False),

    # --- rejected: locking / dangerous funcs ---
    ("for update", "SELECT * FROM firs FOR UPDATE", "case", False),
    ("pg_sleep", "SELECT pg_sleep(10)", "case", False),
    ("current_setting", "SELECT current_setting('is_superuser')", "case", False),
    ("set_config", "SELECT set_config('role', 'postgres', false)", "case", False),
    ("pg_read_file", "SELECT pg_read_file('/etc/passwd')", "case", False),

    # --- rejected: length ---
    ("too long", "SELECT " + ("a" * 4001), "case", False),
]


def main() -> int:
    passed = failed = 0
    for label, sql, scope, should_pass in CASES:
        try:
            validate_sql(sql, scope)
            verdict = True
            reason = ""
        except SQLGuardError as exc:
            verdict = False
            reason = str(exc)
        ok = verdict == should_pass
        if ok:
            passed += 1
        else:
            failed += 1
            want = "ALLOW" if should_pass else "REJECT"
            got = "ALLOWED" if verdict else f"REJECTED ({reason})"
            print(f"  MISMATCH [{label}] wanted {want}, got {got}")
    print(f"\nSQLGuard matrix: {passed} passed, {failed} failed, {len(CASES)} total")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
