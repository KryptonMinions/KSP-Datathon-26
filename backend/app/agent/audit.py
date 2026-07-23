"""Per-turn audit persistence (ORCHESTRATOR_STEERING.md §12, O-12).

One query_audit_log row + one ask_turn_traces row per turn (answered or
refused). Failures to write audit must never fail the user's response — caught
and swallowed here, never raised to the caller.
"""

from __future__ import annotations

from app.config import Settings
from app.schemas import AskRequest, AssistantMessage, CurrentUser
from app.supabase import SupabaseError, insert_row

from .scratchpad import TurnScratchpad


async def write(
    *,
    request: AskRequest,
    user: CurrentUser,
    query_class: str,
    message: AssistantMessage,
    scratchpad: TurnScratchpad,
    specialist_name: str | None,
    request_id: str,
    thread_id: str,
    settings: Settings,
) -> None:
    response_reason = "answered"
    response_summary = message.text or ""
    if message.blocks and message.blocks[0].type == "no_answer":
        na = message.blocks[0]
        response_reason = na.reason or "low_confidence"
        if not response_summary:
            response_summary = na.message
    elif not response_summary and message.blocks:
        first = message.blocks[0]
        if first.type == "text":
            response_summary = first.content

    components_used = ([specialist_name] if specialist_name else []) + sorted(set(scratchpad.tools_used))

    log_row = {
        "officer_id": user.officer_id,
        "session_id": user.id,
        "query_text": request.query,
        "query_language": request.detected_language,
        "query_type": query_class if query_class != "unresolved" else None,
        "records_accessed": sorted(scratchpad.records_accessed)[:100],
        "response_summary": response_summary[:500],
        "components_used": components_used,
        "is_flagged": False,
        "input_modality": request.input_modality,
        "response_reason": response_reason,
        "thread_id": thread_id,
        "request_id": request_id,
    }

    log_id: str | None = None
    try:
        inserted = await insert_row("query_audit_log", log_row, settings)
        log_id = inserted[0]["log_id"] if inserted else None
    except SupabaseError:
        pass

    trace_row = {
        "log_id": log_id,
        "request_id": request_id,
        "trace": {
            "events": scratchpad.events,
            "usage": scratchpad.usage,
            "components_used": components_used,
        },
    }
    try:
        await insert_row("ask_turn_traces", trace_row, settings)
    except SupabaseError:
        pass
