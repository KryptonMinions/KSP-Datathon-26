"""Agentic Ask engine (ORCHESTRATOR_STEERING.md §3).

P0 SCAFFOLD: `run_turn` is the entry point routers/ask.py will call when
ASK_ENGINE=agent. The loop, router, specialists, composer, and tools land in
P2/P3; this stub fixes the signature so ask.py can import against it.
"""

from __future__ import annotations

from app.config import Settings
from app.schemas import AskRequest, AskResponse, CurrentUser


async def run_turn(
    request: AskRequest,
    user: CurrentUser,
    settings: Settings,
    *,
    request_id: str,
) -> AskResponse:
    """P0 stub. Real pipeline (P2): build_frame -> gate -> router -> AgentLoop
    -> composer -> ThreadStore.append -> audit.write -> AskResponse."""
    raise NotImplementedError("run_turn lands in P2")
