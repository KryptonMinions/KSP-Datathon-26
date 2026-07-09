import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.schemas import AskRequest, AskResponse, AssistantMessage
from app.security import SettingsDep, verify_jwt

router = APIRouter(tags=["ask"])

_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def _normalize(query: str) -> str:
    """Same normalization as the frontend mock (trim/lowercase/collapse
    whitespace) so dispatch matching behaves identically either way."""
    return " ".join(query.strip().lower().split())


def _load_message(filename: str) -> AssistantMessage:
    data = json.loads((_FIXTURES_DIR / filename).read_text())
    return AssistantMessage.model_validate(data)


def _load_story1() -> dict[str, AssistantMessage]:
    data = json.loads((_FIXTURES_DIR / "story1_antecedents.json").read_text())
    return {key: AssistantMessage.model_validate(value) for key, value in data.items()}


_STORY1 = _load_story1()
_NO_ANSWER_MESSAGE = _load_message("no_answer.json")

# Dispatch keyed by the exact verbatim demo-script query strings (References/
# KSP_Demo_Script.pdf), matching frontend/src/lib/fixtures/story*.ts's
# STORY*_QUERY constants exactly so mock and real paths dispatch identically.
_DISPATCH: dict[str, tuple[str, AssistantMessage]] = {
    _normalize("rajan gowda antecedents — any cases in karnataka?"): (
        "story1_antecedents.q1",
        _STORY1["q1"],
    ),
    _normalize("show me only the violent offences from those results"): (
        "story1_antecedents.q2",
        _STORY1["q2"],
    ),
    _normalize("is he history-sheeted anywhere?"): (
        "story1_antecedents.q3",
        _STORY1["q3"],
    ),
    _normalize(
        "show me everyone connected to him — co-accused, associates, shared addresses"
    ): ("story4_network", _load_message("story4_network.json")),
    _normalize(
        "find similar past cases: accused on two-wheeler approaches female victim at "
        "traffic signal, snatches gold chain, flees towards main road. how were the "
        "solved ones cracked?"
    ): ("story2_mo_match", _load_message("story2_mo_match.json")),
    _normalize(
        "what changed in mysuru district this month compared to last month — and "
        "what is driving the change?"
    ): ("story10_review_pack", _load_message("story10_review_pack.json")),
}


def _error(status_code: int, code: str, message: str, request_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
        headers={"X-Request-Id": request_id},
    )


def _audit_log(**fields: object) -> None:
    # Stdout JSON, one line per record (ASK_ENDPOINT_CONTRACT.md §2.7).
    print(json.dumps(fields, default=str), file=sys.stdout, flush=True)


@router.post("/ask")
async def ask(request: Request, settings: SettingsDep) -> Response:
    request_id = str(uuid.uuid4())
    start = time.monotonic()

    auth_header = request.headers.get("authorization", "")
    token = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else ""
    if not token:
        return _error(401, "unauthenticated", "Missing or invalid JWT", request_id)
    try:
        current_user = verify_jwt(token, settings)
    except HTTPException:
        return _error(401, "unauthenticated", "Missing or invalid JWT", request_id)

    try:
        raw_body = await request.json()
        body = AskRequest.model_validate(raw_body)
    except (json.JSONDecodeError, ValidationError, ValueError):
        return _error(422, "invalid_request", "Invalid request body", request_id)

    thread_id = body.thread_id or str(uuid.uuid4())
    normalized_query = _normalize(body.query)
    matched = _DISPATCH.get(normalized_query)
    matched_fixture, message = matched if matched else (None, _NO_ANSWER_MESSAGE)

    server_ts = datetime.now(timezone.utc).isoformat()
    response = AskResponse(
        thread_id=thread_id,
        message_id=str(uuid.uuid4()),
        server_ts=server_ts,
        message=message,
    )

    latency_ms = int((time.monotonic() - start) * 1000)
    _audit_log(
        request_id=request_id,
        user_id=current_user.id,
        role=current_user.role.value,
        thread_id=thread_id,
        turn_index=body.turn_index,
        input_modality=body.input_modality,
        detected_language=body.detected_language,
        query_length=len(body.query),
        matched_fixture=matched_fixture,
        response_block_types=[block.type for block in message.blocks],
        latency_ms=latency_ms,
        server_ts=server_ts,
    )

    return JSONResponse(
        status_code=200,
        content=jsonable_encoder(response),
        headers={"X-Request-Id": request_id},
    )
