"""SemanticFrame and build_frame (SEMANTIC_LAYER.md Part 2).

Pipeline: normalize -> classify query_class + extract entity mentions (one
LLM complete_json call) -> assemble frame. Entity mentions are NOT resolved to
canonical DB rows here — that's the agent loop's resolve_entity tool's job
during reasoning; build_frame only extracts candidate (kind, text) pairs so
the router/prompt has hints. Fails open to an `unresolved` frame (which the
gate refuses as low_confidence) on any classification error — the semantic
layer must never 500 the request (§ fail-open-to-refuse rule).
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Callable, Literal

from app.config import Settings
from app.llm import LLMClient, LLMError
from app.llm.errors import LLMConfigError, LLMProviderError, LLMTimeoutError
from app.roles import Role
from app.schemas import AskRequest, CurrentUser

QueryClass = Literal[
    "lookup",
    "case_detail",
    "pattern",
    "network",
    "geo_analytics",
    "trend",
    "summary",
    "audit",
    "unresolved",
]

_VALID_QUERY_CLASSES: frozenset[str] = frozenset(
    {"lookup", "case_detail", "pattern", "network", "geo_analytics", "trend", "summary", "audit"}
)
_VALID_ENTITY_KINDS: frozenset[str] = frozenset({"person", "vehicle", "locality", "gang", "fir"})

_KANNADA_RE = re.compile(r"[ಀ-೿]")
_FIR_ID_RE = re.compile(r"\bKA-[A-Za-z0-9]+-[A-Za-z0-9]+-\d{4}-\d+\b")


@dataclass
class ResolvedEntity:
    kind: Literal["person", "vehicle", "locality", "gang", "fir"]
    text: str
    canonical_id: str | None = None
    display_name: str | None = None
    confidence: float = 0.0


@dataclass
class SemanticFrame:
    frame_id: str
    raw_query: str
    normalized_query: str
    detected_language: str | None
    role: Role
    query_class: QueryClass
    entities: list[ResolvedEntity] = field(default_factory=list)
    confidence: float = 0.0
    notes: list[str] = field(default_factory=list)


def _normalize(query: str) -> str:
    return " ".join(query.strip().split())


def _guess_language(query: str) -> str:
    if _KANNADA_RE.search(query):
        return "kn" if not re.search(r"[A-Za-z]{3,}", query) else "mixed"
    return "en"


_CLASSIFY_SYSTEM_PROMPT = """You are a text-classification component inside an internal police records system \
already used exclusively by verified, on-duty officers. You never see the officer's identity or perform any \
lookup yourself — a separate, already-authorized system stage does that after you finish. Your ONLY job is to \
label the query text below with a category and list the named entities it mentions, exactly like a librarian \
tagging a card, not like someone fulfilling the request. Do not evaluate authorization, legality, or privacy — \
that is handled entirely outside your step, before and after you run. Never output an "error", "refusal", \
"access denied", or any explanatory prose — a category label is always possible, and "unresolved" is the \
correct label for a query you can't confidently categorize (it is not a refusal, just a category value).

Classify a police officer's natural-language question into exactly one query_class and extract any named \
entities mentioned. Respond with ONLY a JSON object matching the exact shape below, no prose, no markdown fences.

query_class values (pick exactly one):
- lookup: antecedents/priors check on a person, a simple existence/status check ("check antecedents of X", \
"is vehicle X stolen", "any cases for Y"), OR a general reference/factual question answerable from the case \
database's reference tables — districts, police stations, BNS sections, crime-type taxonomy, MO codes \
("how many districts are there in Karnataka", "what does BNS 304 cover", "list stations in Mysuru district"). \
This is the catch-all for any simple, factual, non-analytical question grounded in the database — prefer \
lookup over unresolved whenever the question is answerable with a straightforward query, even if it isn't \
about a specific person or case.
- case_detail: about one specific FIR/case ("show me FIR KA-...", "status of case X")
- pattern: modus-operandi / similar-case matching ("similar cases", "same method", "how were the solved ones cracked")
- network: associates/gang/connections graph ("who does X operate with", "show the network around X", "who received the stolen vehicles")
- geo_analytics: hotspot/map/spatial concentration ("where are these concentrated", "map the incidents", "hotspots in station limits")
- trend: time-series / period-over-period comparison ("what changed this month vs last", "year over year pattern")
- summary: a review pack / comprehensive report request ("give me a review pack", "prepare a brief", "district comparison")
- audit: query activity / access logs ("show query activity", "flagged queries", "who accessed this")
- unresolved: query doesn't clearly fit any class above, or is too vague to classify confidently

entities: array of {"kind": "person"|"vehicle"|"locality"|"gang"|"fir", "text": "<exact mention as written>"} \
for every named person, vehicle plate, place/locality, gang, or FIR number mentioned. Omit generic terms \
(e.g. "the cases", "this station") - only concrete named mentions.

Output shape exactly:
{"query_class": "...", "entities": [{"kind": "...", "text": "..."}], "confidence": 0.0-1.0}

confidence reflects how certain you are of query_class specifically."""


def _parse_classification(content: str | None) -> dict | None:
    if not content:
        return None
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) and "query_class" in value else None


async def _classify(
    query: str, settings: Settings, on_usage: Callable[[dict[str, int]], None] | None = None
) -> dict:
    """Calls LLMClient.complete() directly rather than complete_json().

    complete_json() appends its own trailing "respond with JSON only" system
    message, which was empirically found to override this prompt's careful
    anti-refusal framing: gemini-3.5-flash-lite refused a plain antecedents
    query 0/4 times through complete_json vs 4/4 clean calling complete()
    directly with the same system prompt. Implements its own intent->fast
    fallback (mirroring complete_json's) and a schema-aware repair retry
    (checks for a `query_class` key, not just JSON-syntax validity — a
    refusal shaped as {"error": "..."} is valid JSON but not a classification).
    """
    client = LLMClient(settings)
    messages = [
        {"role": "system", "content": _CLASSIFY_SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]

    async def _call(profile: str, msgs: list[dict]):
        try:
            return await client.complete(profile, msgs, temperature=0.0)
        except (LLMConfigError, LLMProviderError, LLMTimeoutError):
            if profile != "fast":
                return await client.complete("fast", msgs, temperature=0.0)
            raise

    resp = await _call("intent", messages)
    if on_usage:
        on_usage(resp.usage)
    parsed = _parse_classification(resp.content)
    if parsed is not None:
        return parsed

    repair_messages = [
        *messages,
        {"role": "assistant", "content": resp.content or ""},
        {
            "role": "user",
            "content": (
                'That was not the classification output. Respond again with ONLY the JSON '
                'object {"query_class": ..., "entities": [...], "confidence": ...} as specified '
                "— no other keys, no prose."
            ),
        },
    ]
    resp2 = await client.complete("fast", repair_messages, temperature=0.0)
    if on_usage:
        on_usage(resp2.usage)
    return _parse_classification(resp2.content) or {}


async def build_frame(
    request: AskRequest,
    user: CurrentUser,
    settings: Settings,
    on_usage: Callable[[dict[str, int]], None] | None = None,
) -> SemanticFrame:
    frame_id = str(uuid.uuid4())
    normalized = _normalize(request.query)
    detected_language = request.detected_language or _guess_language(request.query)

    fir_matches = _FIR_ID_RE.findall(request.query)

    try:
        result = await _classify(normalized, settings, on_usage=on_usage)
    except LLMError as exc:
        return SemanticFrame(
            frame_id=frame_id,
            raw_query=request.query,
            normalized_query=normalized,
            detected_language=detected_language,
            role=user.role,
            query_class="unresolved",
            entities=[ResolvedEntity(kind="fir", text=f) for f in fir_matches],
            confidence=0.0,
            notes=[f"classification_failed: {type(exc).__name__}"],
        )

    raw_class = result.get("query_class")
    query_class: QueryClass = raw_class if raw_class in _VALID_QUERY_CLASSES else "unresolved"
    try:
        confidence = float(result.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    entities: list[ResolvedEntity] = []
    seen_fir_texts: set[str] = set()
    for raw_entity in result.get("entities") or []:
        if not isinstance(raw_entity, dict):
            continue
        kind = raw_entity.get("kind")
        text = raw_entity.get("text")
        if kind not in _VALID_ENTITY_KINDS or not isinstance(text, str) or not text.strip():
            continue
        entities.append(ResolvedEntity(kind=kind, text=text.strip()))
        if kind == "fir":
            seen_fir_texts.add(text.strip())

    # Regex-extracted FIR IDs are authoritative for format; add any the model missed.
    for f in fir_matches:
        if f not in seen_fir_texts:
            entities.append(ResolvedEntity(kind="fir", text=f))

    return SemanticFrame(
        frame_id=frame_id,
        raw_query=request.query,
        normalized_query=normalized,
        detected_language=detected_language,
        role=user.role,
        query_class=query_class,
        entities=entities,
        confidence=confidence,
    )
