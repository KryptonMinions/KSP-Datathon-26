"""SQL tools: SQLGuard (app-side layer 1) + run_sql + get_schema.

SQLGuard (ORCHESTRATOR_STEERING.md §10.1) is the first of the two-layer SQL
safety model; the privilege-dropped executor RPC (migration 009) is the second.
The guard rejects anything that isn't a single read-only SELECT over the scope's
table allowlist, with an instructive reason the model can act on.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp

from app.supabase import SupabaseError, call_rpc

from .base import ToolContext, ToolResult

# ---------------------------------------------------------------------------
# Allowlists. `case` MUST match the case_tables array in migration 009 exactly.
# ---------------------------------------------------------------------------
CASE_TABLES: frozenset[str] = frozenset({
    # Group A / B / I — reference
    "districts", "admin_boundaries", "sub_divisions", "circles",
    "police_stations", "localities", "officers",
    "bns_sections", "crime_types", "mo_codes",
    # Group C-G — case / operational
    "persons", "person_addresses", "person_phones",
    "firs", "fir_accused", "fir_victims", "fir_witnesses",
    "case_diary_entries", "arrests", "chargesheets", "court_disposals",
    "ncr_petitions", "history_sheets", "history_sheet_entries",
    "gangs", "gang_memberships", "known_associates",
    "vehicles", "stolen_property", "missing_persons", "seizures",
    "district_socioeconomic", "events_calendar",
    # Group J — semantic index
    "document_chunks",
})

AUDIT_TABLES: frozenset[str] = frozenset({"query_audit_log", "ask_turn_traces"})

_BLOCKED_SCHEMAS = {"pg_catalog", "information_schema", "auth", "storage", "extensions", "vault"}
_BLOCKED_FUNCTIONS = {
    "set_config", "current_setting", "pg_sleep", "dblink", "dblink_exec",
    "lo_import", "lo_export", "pg_read_file", "pg_read_binary_file",
    "pg_ls_dir", "pg_stat_file", "query_to_xml", "txid_current",
}
_MAX_SQL_LEN = 4000


class SQLGuardError(Exception):
    """Raised with an instructive reason when a query is rejected."""


def _allowlist(scope: str) -> frozenset[str]:
    return AUDIT_TABLES if scope == "audit" else CASE_TABLES


def validate_sql(sql: str, scope: str = "case") -> None:
    """Raise SQLGuardError unless `sql` is a single read-only SELECT over the
    scope allowlist. Silence = pass."""
    if len(sql) > _MAX_SQL_LEN:
        raise SQLGuardError(f"query too long ({len(sql)} > {_MAX_SQL_LEN} chars)")

    try:
        statements = [s for s in sqlglot.parse(sql, dialect="postgres") if s is not None]
    except Exception as exc:  # noqa: BLE001 — sqlglot raises various parse errors
        raise SQLGuardError(f"could not parse SQL: {exc}") from exc

    if len(statements) != 1:
        raise SQLGuardError("exactly one statement is allowed (no multi-statement SQL)")
    stmt = statements[0]

    # Root must be a read-only query node (SELECT / set-op of SELECTs).
    if not isinstance(stmt, (exp.Select, exp.Union, exp.Intersect, exp.Except, exp.Subquery)):
        raise SQLGuardError(
            f"only SELECT queries are allowed (got {type(stmt).__name__.upper()})"
        )

    # Any mutating / command node anywhere = reject. Resolve types defensively
    # (some exp.* names vary across sqlglot versions).
    _forbidden_names = [
        "Insert", "Update", "Delete", "Merge", "Drop", "Create", "Alter",
        "Command", "TruncateTable", "Grant", "Into", "Set", "Copy",
    ]
    forbidden = tuple(
        t for t in (getattr(exp, n, None) for n in _forbidden_names) if t is not None
    )
    bad = next(iter(stmt.find_all(*forbidden)), None) if forbidden else None
    if bad is not None:
        raise SQLGuardError(
            f"statement type {type(bad).__name__.upper()} is not permitted "
            "(read-only SELECT only)"
        )
    lock_type = getattr(exp, "Lock", None)
    if lock_type is not None and next(iter(stmt.find_all(lock_type)), None) is not None:
        raise SQLGuardError("locking clauses (FOR UPDATE/SHARE) are not permitted")

    # CTE names are not real tables — exclude from the allowlist check.
    cte_names = {c.alias_or_name.lower() for c in stmt.find_all(exp.CTE)}

    allow = _allowlist(scope)
    for table in stmt.find_all(exp.Table):
        schema = (table.db or "").lower()
        if schema and schema in _BLOCKED_SCHEMAS:
            raise SQLGuardError(f"access to schema '{schema}' is not permitted")
        if schema and schema not in ("public", ""):
            raise SQLGuardError(f"schema-qualified access to '{schema}' is not permitted")
        name = (table.name or "").lower()
        if name in cte_names:
            continue
        if name not in allow:
            raise SQLGuardError(
                f"table '{name}' is not in the {scope} allowlist"
            )

    # Blocked function calls (sqlglot models unknown funcs as Anonymous).
    for fn in stmt.find_all(exp.Anonymous):
        fname = (fn.this if isinstance(fn.this, str) else fn.name or "").lower()
        if fname in _BLOCKED_FUNCTIONS or fname.startswith("pg_read"):
            raise SQLGuardError(f"function '{fname}()' is not permitted")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
class RunSqlTool:
    name = "run_sql"
    label = "Querying records"
    description = (
        "Run a single read-only SELECT over the case database and return rows. "
        "Only SELECT is allowed; results are row-capped. Provide a one-line "
        "`purpose`. Prefer get_schema first to learn exact column names."
    )

    @property
    def params_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "A single SELECT statement."},
                "purpose": {
                    "type": "string",
                    "description": "One line describing what this query is for.",
                },
            },
            "required": ["sql", "purpose"],
        }

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        sql = (args.get("sql") or "").strip()
        scope = ctx.sql_scope
        if not sql:
            return ToolResult(ok=False, error="no SQL provided")
        try:
            validate_sql(sql, scope)
        except SQLGuardError as exc:
            return ToolResult(ok=False, error=f"SQL rejected by guard: {exc}")

        try:
            result = await call_rpc(
                "execute_agent_select",
                {"p_sql": sql, "p_scope": scope, "p_row_cap": ctx.settings.ask_sql_row_cap},
                ctx.settings,
            )
        except SupabaseError as exc:
            # DB-side rejection (privilege drop, timeout, SQL error) — instructive
            # message so the model can self-correct.
            return ToolResult(ok=False, error=f"query failed: {exc}")

        rows = (result or {}).get("rows") or []
        columns = list(rows[0].keys()) if rows else []
        # Auto-register fir-level provenance for any fir_id values (§9.1).
        if ctx.scratchpad is not None:
            _register_fir_provenance(rows, ctx)
        return ToolResult(
            ok=True,
            data={
                "columns": columns,
                "rows": rows,
                "row_count": (result or {}).get("row_count", len(rows)),
                "truncated": (result or {}).get("truncated", False),
            },
        )


class GetSchemaTool:
    name = "get_schema"
    label = "Reading schema"
    description = (
        "Return columns, notes, and join hints for up to 6 tables from the "
        "curated schema card. Call this before run_sql to get exact names."
    )

    @property
    def params_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tables": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Table names (max 6).",
                }
            },
            "required": ["tables"],
        }

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        requested = (args.get("tables") or [])[:6]
        card = load_schema_card()
        allow = _allowlist(ctx.sql_scope)
        out: dict[str, Any] = {}
        unknown: list[str] = []
        for t in requested:
            key = str(t).lower()
            if key not in allow:
                unknown.append(t)
                continue
            if key in card:
                out[key] = card[key]
            else:
                unknown.append(t)
        return ToolResult(ok=True, data={"tables": out, "unknown": unknown})


# ---------------------------------------------------------------------------
# Schema card loader
# ---------------------------------------------------------------------------
_SCHEMA_CARD_PATH = Path(__file__).resolve().parent.parent / "resources" / "schema_card.json"
_schema_card_cache: dict[str, Any] | None = None


def load_schema_card() -> dict[str, Any]:
    global _schema_card_cache
    if _schema_card_cache is None:
        try:
            _schema_card_cache = json.loads(_SCHEMA_CARD_PATH.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            _schema_card_cache = {}
    return _schema_card_cache


def _register_fir_provenance(rows: list[dict], ctx: ToolContext) -> None:
    seen = 0
    for row in rows:
        fir_id = row.get("fir_id")
        if isinstance(fir_id, str) and fir_id:
            ctx.scratchpad.register_provenance("fir", {"fir_id": fir_id})
            seen += 1
            if seen >= 20:
                break
