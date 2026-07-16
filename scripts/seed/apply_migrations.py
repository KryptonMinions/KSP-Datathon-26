#!/usr/bin/env python3
"""Stage 2 — apply db/migrations/*.sql to Supabase in order (SEED_RUNBOOK.md
§3, Gate 2). Each file runs as its own transaction; a failure stops the run
immediately rather than continuing past a broken migration.

Usage:
    python apply_migrations.py                # apply all migration files
    python apply_migrations.py --from 005      # resume from 005_*.sql onward
    python apply_migrations.py --verify        # only run the post-apply checks

Each file commits independently (see db.run_migration_file) — a failure
partway through a file rolls back only that file (Postgres's simple-query
protocol treats one execute() call's ;-separated statements as one implicit
transaction), so a fix-and-resume with --from is safe: already-committed
earlier files are left untouched.
"""

from __future__ import annotations

import sys
from pathlib import Path

from db import connect, run_migration_file

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "db" / "migrations"

EXPECTED_TABLE_COUNT = 35


def apply_all(*, from_prefix: str | None = None) -> None:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        raise RuntimeError(f"no migration files found in {MIGRATIONS_DIR}")
    if from_prefix:
        files = [f for f in files if f.name >= from_prefix]
        if not files:
            raise RuntimeError(f"no migration files at or after {from_prefix!r}")
    with connect() as conn:
        for path in files:
            run_migration_file(conn, path)


def verify() -> bool:
    ok = True
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
                "AND table_name != 'user_directory';"
            )
            table_count = cur.fetchone()[0]
            print(f"tables in public schema (excl. user_directory): {table_count}")
            if table_count != EXPECTED_TABLE_COUNT:
                print(f"  EXPECTED {EXPECTED_TABLE_COUNT} — MISMATCH", file=sys.stderr)
                ok = False

            cur.execute("SELECT PostGIS_Version();")
            print(f"PostGIS version: {cur.fetchone()[0]}")

            cur.execute(
                "SELECT extname FROM pg_extension "
                "WHERE extname IN ('postgis', 'pg_trgm', 'vector', 'pgcrypto') "
                "ORDER BY extname;"
            )
            extensions = [r[0] for r in cur.fetchall()]
            print(f"extensions enabled: {extensions}")
            if len(extensions) != 4:
                print("  MISSING an expected extension", file=sys.stderr)
                ok = False

            cur.execute(
                "SELECT count(*) FROM pg_indexes WHERE schemaname = 'public';"
            )
            print(f"indexes in public schema: {cur.fetchone()[0]}")

            cur.execute(
                "SELECT relname FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relrowsecurity = true "
                "ORDER BY relname;"
            )
            rls_tables = [r[0] for r in cur.fetchall()]
            print(f"tables with RLS enabled: {len(rls_tables)}")
    return ok


if __name__ == "__main__":
    if "--verify" in sys.argv:
        raise SystemExit(0 if verify() else 1)
    resume_from = None
    if "--from" in sys.argv:
        resume_from = sys.argv[sys.argv.index("--from") + 1]
    apply_all(from_prefix=resume_from)
    print("\n--- verification ---")
    raise SystemExit(0 if verify() else 1)
