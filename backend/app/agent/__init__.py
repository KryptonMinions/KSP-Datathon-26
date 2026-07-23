"""Agentic Ask engine — turn pipeline (ORCHESTRATOR_STEERING.md §5):

AskRequest + CurrentUser
  -> build_frame()
  -> gate refused? -> NoAnswerBlock(reason) -> audit -> return
  -> router.select(frame.query_class)
  -> §4.1 jurisdiction scope resolution (IO scoped classes only)
  -> AgentLoop.run(specialist, frame, thread_context)
  -> composer -> AssistantMessage
  -> ThreadStore.append(thread_id, turn summary)
  -> audit.write(turn)
  -> AskResponse
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from app.config import Settings
from app.schemas import AskRequest, AskResponse, AssistantMessage, CurrentUser
from app.semantic.frame import build_frame
from app.semantic.gating import gate, is_scoped
from app.supabase import SupabaseError, select_rows

from . import audit as audit_writer
from . import router
from .composer import compose, refusal_message
from .loop import AgentLoop
from .scratchpad import TurnScratchpad
from .specialists import SpecialistConfig, intel_analyst_scoped_tools
from .threads import TurnSummary, get_thread_store

_STATION_CACHE_TTL_S = 600
_station_cache: dict[str, tuple[float, dict | None]] = {}


async def _resolve_operator_station(user: CurrentUser, settings: Settings) -> dict | None:
    """§4.1 base station derivation, process-cached <=10 min. Returns None if
    officer_id is null, the officer row is missing, is_active=false, or has no
    station_id — any of which means every scoped query_class must refuse."""
    if not user.officer_id:
        return None
    cached = _station_cache.get(user.officer_id)
    now = time.time()
    if cached and now - cached[0] < _STATION_CACHE_TTL_S:
        return cached[1]

    result: dict | None = None
    try:
        rows = await select_rows(
            "officers",
            {
                "officer_id": f"eq.{user.officer_id}",
                "select": "officer_id,station_id,is_active,police_stations(station_name)",
            },
            settings,
        )
    except SupabaseError:
        rows = []

    if rows and rows[0].get("is_active") and rows[0].get("station_id"):
        row = rows[0]
        ps = row.get("police_stations")
        station_name = None
        if isinstance(ps, dict):
            station_name = ps.get("station_name")
        elif isinstance(ps, list) and ps:
            station_name = ps[0].get("station_name")
        result = {"station_id": row["station_id"], "station_name": station_name or row["station_id"]}

    _station_cache[user.officer_id] = (now, result)
    return result


def _build_response(thread_id: str, message: AssistantMessage) -> AskResponse:
    return AskResponse(
        thread_id=thread_id,
        message_id=str(uuid.uuid4()),
        server_ts=datetime.now(timezone.utc).isoformat(),
        message=message,
    )


async def run_turn(
    request: AskRequest,
    user: CurrentUser,
    settings: Settings,
    *,
    request_id: str,
) -> AskResponse:
    thread_id = request.thread_id or str(uuid.uuid4())
    frame = await build_frame(request, user, settings)
    scratchpad = TurnScratchpad()

    decision = gate(user.role, frame.query_class)
    if not decision.allow:
        message = refusal_message(decision.reason or "low_confidence")
        await audit_writer.write(
            request=request, user=user, query_class=frame.query_class, message=message,
            scratchpad=scratchpad, specialist_name=None, request_id=request_id,
            thread_id=thread_id, settings=settings,
        )
        return _build_response(thread_id, message)

    specialist: SpecialistConfig = router.select(frame.query_class)

    jurisdiction_note: str | None = None
    tools = specialist.tools
    if is_scoped(user.role, frame.query_class):
        station = await _resolve_operator_station(user, settings)
        if station is None:
            message = refusal_message("out_of_scope")
            await audit_writer.write(
                request=request, user=user, query_class=frame.query_class, message=message,
                scratchpad=scratchpad, specialist_name=specialist.name, request_id=request_id,
                thread_id=thread_id, settings=settings,
            )
            return _build_response(thread_id, message)
        jurisdiction_note = (
            f"Your analyses for this turn are limited to cases filed at "
            f"{station['station_name']} (station {station['station_id']})."
        )
        if specialist.name == "intel_analyst":
            tools = intel_analyst_scoped_tools()

    loop = AgentLoop(settings)
    result = await loop.run(
        specialist=specialist,
        tools=tools,
        frame=frame,
        user=user,
        scratchpad=scratchpad,
        thread_id=thread_id,
        sql_scope=specialist.sql_scope,
        jurisdiction_note=jurisdiction_note,
    )

    message = compose(result.final_answer, scratchpad, specialist)

    answer_summary = message.text or ""
    if not answer_summary and message.blocks:
        first = message.blocks[0]
        answer_summary = first.content if first.type == "text" else first.message if first.type == "no_answer" else f"{first.type} block"
    thread_store = get_thread_store(settings)
    await thread_store.append(
        thread_id,
        TurnSummary(
            query=frame.raw_query,
            specialist=specialist.name,
            answer_summary=answer_summary[:200],
            entity_ids=sorted(scratchpad.records_accessed)[:10],
        ),
    )

    await audit_writer.write(
        request=request, user=user, query_class=frame.query_class, message=message,
        scratchpad=scratchpad, specialist_name=specialist.name, request_id=request_id,
        thread_id=thread_id, settings=settings,
    )

    return _build_response(thread_id, message)
