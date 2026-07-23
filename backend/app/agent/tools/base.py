"""Tool protocol (ORCHESTRATOR_STEERING.md §9).

Every tool is an in-process Python callable (O-3 — no MCP). Tools declare a
JSON-Schema parameter spec (handed to the LLM as an OpenAI tool spec) and return
a JSON-serializable ToolResult. DB access is always via app/supabase.py helpers
(PostgREST/RPC, secret key) — never a direct Postgres driver in the app tier.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.config import Settings
    from app.schemas import CurrentUser
    from app.semantic import SemanticFrame


@dataclass
class ToolResult:
    """Uniform tool return. Errors are values, not exceptions, so the model can
    self-correct (§6.2.6). `payload_id` links to a scratchpad-registered block."""

    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    payload_id: str | None = None


@dataclass
class ToolContext:
    user: "CurrentUser"
    frame: "SemanticFrame"
    settings: "Settings"
    # scratchpad is attached at loop time (avoids an import cycle here).
    scratchpad: Any = None


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
