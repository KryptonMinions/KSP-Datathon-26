"""Shared Postgres connection + demo-date helpers for the seed pipeline.

Loads backend/.env directly (the seed scripts are not the FastAPI app, so they
don't go through app/config.py) and expose a single psycopg connection factory
plus the parsed SEED_DEMO_DATE. All seeding writes go through SUPABASE_DB_URL —
the direct Postgres connection — never through the httpx/PostgREST client in
backend/app/supabase.py, since DDL, PostGIS functions, and bulk COPY aren't
expressible over PostgREST (SEED_RUNBOOK.md §0).
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ENV = REPO_ROOT / "backend" / ".env"

load_dotenv(BACKEND_ENV)


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"{name} is not set in {BACKEND_ENV}. See SEED_RUNBOOK.md §0."
        )
    return value


def get_db_url() -> str:
    return _require_env("SUPABASE_DB_URL")


def get_demo_date() -> dt.date:
    raw = _require_env("SEED_DEMO_DATE")
    try:
        return dt.date.fromisoformat(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"SEED_DEMO_DATE={raw!r} is not in YYYY-MM-DD format "
            "(see SEED_RUNBOOK.md §0)."
        ) from exc


def connect(*, autocommit: bool = False) -> psycopg.Connection:
    """Open a direct Postgres connection using the service-role connection string.

    RLS is bypassed by design here — seed scripts are the only writers of
    case/reference data in v1 (DATA_ARCHITECTURE_SCHEMA_V2.md §1.3).
    """
    return psycopg.connect(get_db_url(), autocommit=autocommit)


def run_migration_file(conn: psycopg.Connection, path: Path) -> None:
    """Execute a single numbered migration file as one transaction."""
    sql = path.read_text()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print(f"applied {path.name}")
