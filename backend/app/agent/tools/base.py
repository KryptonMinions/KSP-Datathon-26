"""Tool protocol (ORCHESTRATOR_STEERING.md §9).

Every tool is an in-process Python callable (O-3 — no MCP). Tools declare a
JSON-Schema parameter spec (handed to the LLM as an OpenAI tool spec) and return
a JSON-serializable ToolResult. DB access is always via app/supabase.py helpers
(PostgREST/RPC, secret key) — never a direct Postgres driver in the app tier.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.config import Settings
    from app.schemas import CurrentUser
    from app.semantic import SemanticFrame


@dataclass
class ToolResult:
    """Uniform tool return. Errors are values, not exceptions, so the model can
    self-correct (§6.2.6). `payload_id` links to a scratchpad-registered block.

    `hard_refuse_reason`: set only for security-relevant refusals that must
    NOT be left to the model's discretion (§4.1 rule 3 — anchor admission).
    When set, loop.py forces status=no_answer with this reason immediately,
    bypassing the model entirely — "enforcement is tool-level and
    deterministic, never prompt-only."
    """

    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    payload_id: str | None = None
    hard_refuse_reason: str | None = None


@dataclass
class ToolContext:
    user: "CurrentUser"
    frame: "SemanticFrame"
    settings: "Settings"
    # scratchpad is attached at loop time (avoids an import cycle here).
    scratchpad: Any = None
    # "case" | "audit" — selects the executor's privilege-dropped role and the
    # SQLGuard allowlist. Set to "audit" only for the audit_analyst specialist.
    sql_scope: str = "case"
    # §4.1 — set only on IO turns for network/geo_analytics/trend query
    # classes. When set, geo_query/trend_series MUST inject this as
    # station_id (overriding any model-supplied station_id/district_id) and
    # build_network MUST perform anchor admission before traversing.
    scoped_station_id: str | None = None


@runtime_checkable
class Tool(Protocol):
    name: str
    label: str  # static status label streamed to the timeline

    @property
    def params_schema(self) -> dict[str, Any]:
        """JSON Schema for this tool's arguments."""
        ...

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult: ...


def to_openai_spec(tool: Tool) -> dict[str, Any]:
    """Render a Tool as an OpenAI-compatible function tool spec."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": getattr(tool, "description", tool.label),
            "parameters": tool.params_schema,
        },
    }


# ---------------------------------------------------------------------------
# Shared helpers for tools that build fixed SQL (get_case, mo_match,
# build_network, geo_query, trend_series). These templates are NEVER
# model-authored — args are individually validated/escaped, not concatenated
# raw — but the executor still runs them under the same privilege-dropped
# role as run_sql, so escaping is defense in depth, not the only guard.
# ---------------------------------------------------------------------------

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_FIR_ID_RE = re.compile(r"^KA-[A-Za-z0-9]+-[A-Za-z0-9]+-\d{4}-\d+$")
_SAFE_CODE_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


def sql_escape(value: str) -> str:
    return value.replace("'", "''")


def is_valid_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(value))


def is_valid_fir_id(value: str) -> bool:
    return bool(_FIR_ID_RE.match(value))


def is_safe_code(value: str) -> bool:
    """District/station/crime-type/mo-code ids: alphanumeric + - + _ only."""
    return bool(_SAFE_CODE_RE.match(value))
