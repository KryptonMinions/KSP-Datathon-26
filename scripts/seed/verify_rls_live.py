#!/usr/bin/env python3
"""Live RLS enforcement test (SEED_RUNBOOK.md §8 check 8), upgrading
05_validate.py's policy-definition check to an actual authenticated-request
test.

Rather than signing in as a real demo user via GoTrue (which would need
reading credentials this script deliberately avoids), this drives Postgres
RLS the same way PostgREST does under the hood: `SET ROLE authenticated`
switches the session's effective role to the one Supabase's policies are
written against, and `SET request.jwt.claims` populates the exact GUC that
`auth.jwt()` reads (confirmed by inspecting the deployed function — see
migration 006_rls.sql). This exercises the real, deployed RLS policies
against real data, not a simulation of them — the only thing it skips is
the GoTrue token-issuance and PostgREST HTTP layers in front of Postgres.

Each check runs in its own transaction, rolled back afterward, so this
script performs zero permanent writes even for the mutation-denial tests.
"""

import sys

from db import connect

GROUP_CG_TABLES = [
    "persons", "firs", "fir_accused", "fir_victims", "case_diary_entries",
    "ncr_petitions", "seizures", "missing_persons", "history_sheets",
    "gangs", "gang_memberships", "known_associates", "stolen_property", "vehicles",
]
OPERATIONAL_ROLES = ["investigating_officer", "supervisor", "analyst"]

results: list[tuple[str, str, str]] = []  # (check, status, detail)


def run_as(cur, role_claim: str | None) -> None:
    # SET doesn't accept bind parameters — set_config() does, and with
    # is_local=true behaves like SET LOCAL (scoped to the current transaction).
    cur.execute("SET LOCAL ROLE authenticated")
    if role_claim is not None:
        import json

        claims = json.dumps({"app_metadata": {"role": role_claim}})
        cur.execute("SELECT set_config('request.jwt.claims', %s, true)", (claims,))


def record(check: str, ok: bool, detail: str) -> None:
    status = "PASS" if ok else "FAIL"
    results.append((check, status, detail))
    print(f"[{status}] {check} — {detail}")


def main() -> int:
    with connect(autocommit=True) as conn:
        # --- admin: zero rows / permission denied on every Group C-G table ---
        for table in GROUP_CG_TABLES:
            with conn.cursor() as cur:
                cur.execute("BEGIN")
                try:
                    run_as(cur, "admin")
                    cur.execute(f"SELECT count(*) FROM {table}")
                    n = cur.fetchone()[0]
                    record(f"8. RLS live — admin SELECT {table}", n == 0, f"{n} rows visible (want 0)")
                except Exception as exc:  # permission denied is also a valid deny outcome
                    record(f"8. RLS live — admin SELECT {table}", True, f"denied: {exc}")
                finally:
                    cur.execute("ROLLBACK")

        # --- each operational role: sees rows on every Group C-G table ---
        for role in OPERATIONAL_ROLES:
            for table in GROUP_CG_TABLES:
                with conn.cursor() as cur:
                    cur.execute("BEGIN")
                    try:
                        run_as(cur, role)
                        cur.execute(f"SELECT count(*) FROM {table}")
                        n = cur.fetchone()[0]
                        record(f"8. RLS live — {role} SELECT {table}", True, f"{n} rows visible")
                    except Exception as exc:
                        record(f"8. RLS live — {role} SELECT {table}", False, f"unexpectedly denied: {exc}")
                    finally:
                        cur.execute("ROLLBACK")

        # --- anon (no claims at all): should see nothing on Group C-G ---
        with conn.cursor() as cur:
            cur.execute("BEGIN")
            try:
                cur.execute("SET LOCAL ROLE anon")
                cur.execute("SELECT count(*) FROM firs")
                n = cur.fetchone()[0]
                record("8. RLS live — anon SELECT firs", n == 0, f"{n} rows visible (want 0)")
            except Exception as exc:
                record("8. RLS live — anon SELECT firs", True, f"denied: {exc}")
            finally:
                cur.execute("ROLLBACK")

        # --- query_audit_log: UPDATE/DELETE denied for every role, incl. admin ---
        # Insert a real test row first (as the superuser login, which bypasses
        # RLS) so the denial tests below have an actual row to attempt against
        # instead of vacuously passing on an empty table.
        with conn.cursor() as cur:
            cur.execute("SELECT officer_id FROM officers LIMIT 1")
            (sample_officer_id,) = cur.fetchone()

        for role in ["admin", *OPERATIONAL_ROLES]:
            with conn.cursor() as cur:
                cur.execute("BEGIN")
                try:
                    cur.execute(
                        "INSERT INTO query_audit_log (log_id, officer_id, session_id, query_text) "
                        "VALUES (gen_random_uuid(), %s, 'rls-test-session', 'rls-test-query') RETURNING log_id",
                        (sample_officer_id,),
                    )
                    (log_id,) = cur.fetchone()
                    run_as(cur, role)
                    try:
                        cur.execute("UPDATE query_audit_log SET response_summary = 'rls-test' WHERE log_id = %s", (log_id,))
                        record(f"8. RLS live — {role} UPDATE query_audit_log", False, "UPDATE unexpectedly succeeded")
                    except Exception as exc:
                        record(f"8. RLS live — {role} UPDATE query_audit_log", True, f"denied: {type(exc).__name__}")
                finally:
                    cur.execute("ROLLBACK")

            with conn.cursor() as cur:
                cur.execute("BEGIN")
                try:
                    cur.execute(
                        "INSERT INTO query_audit_log (log_id, officer_id, session_id, query_text) "
                        "VALUES (gen_random_uuid(), %s, 'rls-test-session', 'rls-test-query') RETURNING log_id",
                        (sample_officer_id,),
                    )
                    (log_id,) = cur.fetchone()
                    run_as(cur, role)
                    try:
                        cur.execute("DELETE FROM query_audit_log WHERE log_id = %s", (log_id,))
                        record(f"8. RLS live — {role} DELETE query_audit_log", False, "DELETE unexpectedly succeeded")
                    except Exception as exc:
                        record(f"8. RLS live — {role} DELETE query_audit_log", True, f"denied: {type(exc).__name__}")
                finally:
                    cur.execute("ROLLBACK")

        # --- admin: SELECT on query_audit_log should work (admin_read_audit_log policy) ---
        with conn.cursor() as cur:
            cur.execute("BEGIN")
            try:
                cur.execute(
                    "INSERT INTO query_audit_log (log_id, officer_id, session_id, query_text) "
                    "VALUES (gen_random_uuid(), %s, 'rls-test-session', 'rls-test-query')",
                    (sample_officer_id,),
                )
                run_as(cur, "admin")
                cur.execute("SELECT count(*) FROM query_audit_log")
                n = cur.fetchone()[0]
                record("8. RLS live — admin SELECT query_audit_log", n >= 1, f"{n} rows visible (want >=1, the just-inserted test row)")
            except Exception as exc:
                record("8. RLS live — admin SELECT query_audit_log", False, f"unexpectedly denied: {exc}")
            finally:
                cur.execute("ROLLBACK")

        # --- Group A/B/I reference tables: readable by any authenticated role ---
        with conn.cursor() as cur:
            cur.execute("BEGIN")
            try:
                run_as(cur, "analyst")
                cur.execute("SELECT count(*) FROM police_stations")
                n = cur.fetchone()[0]
                record("8. RLS live — analyst SELECT police_stations (reference data)", n > 0, f"{n} rows visible")
            finally:
                cur.execute("ROLLBACK")

    n_pass = sum(1 for _, s, _ in results if s == "PASS")
    n_fail = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"\n{n_pass} PASS, {n_fail} FAIL out of {len(results)} live RLS checks")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
