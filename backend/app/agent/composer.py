"""composer.py — FinalAnswer (model output contract, §7) -> AssistantMessage.

Refusal contract (central requirement): every degraded path terminates in a
single NoAnswerBlock{reason}, never a hedged answer. `not_found`/
`low_confidence` copy leads with "Insufficient information" per product
requirement; `out_of_scope` stays non-disclosure wording (must never confirm
or deny that matching records exist, so it deliberately does NOT say
"insufficient information" — that would leak that a search came up empty).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, ValidationError, model_validator

from app.schemas import (
    AssistantMessage,
    Citation,
    ContentBlock,
    NoAnswerBlock,
    NoAnswerReason,
    TableBlock,
    TableColumn,
    TextBlock,
)

from .scratchpad import TurnScratchpad
from .specialists import SpecialistConfig

# ---------------------------------------------------------------------------
# FinalAnswer schema (§7) — the model's required terminal JSON shape.
# ---------------------------------------------------------------------------


class FinalTextBlock(BaseModel):
    kind: Literal["text"] = "text"
    markdown: str
    citation_keys: list[str] = Field(default_factory=list)


class FinalTableBlock(BaseModel):
    kind: Literal["table"] = "table"
    title: str | None = None
    columns: list[str]
    rows: list[list[str]]
    citation_keys: list[str] = Field(default_factory=list)


class FinalPayloadRefBlock(BaseModel):
    kind: Literal["payload_ref"] = "payload_ref"
    payload_id: str
    title: str | None = None


FinalBlock = Annotated[
    Union[FinalTextBlock, FinalTableBlock, FinalPayloadRefBlock],
    Field(discriminator="kind"),
]


class FinalAnswer(BaseModel):
    status: Literal["answered", "no_answer"]
    reason: NoAnswerReason | None = None
    blocks: list[FinalBlock] = Field(default_factory=list)

    @model_validator(mode="after")
    def _reason_required_if_no_answer(self) -> "FinalAnswer":
        if self.status == "no_answer" and self.reason is None:
            raise ValueError("status='no_answer' requires a reason")
        return self


class FinalAnswerParseError(Exception):
    """Distinct from LLMOutputError so loop.py can apply the FinalAnswer-
    specific repair-retry (§6.2.4) independently of LLMClient's own retry."""


def parse_final_answer(data: dict) -> FinalAnswer:
    try:
        return FinalAnswer.model_validate(data)
    except ValidationError as exc:
        raise FinalAnswerParseError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Refusal copy (DEMO_SCENARIOS.md §2 intent; "insufficient information" lead
# for not_found/low_confidence per product requirement).
# ---------------------------------------------------------------------------

_REFUSAL_COPY: dict[str, str] = {
    "not_found": (
        "Insufficient information — I searched the records available to you but found "
        "no matching results. Please check the spelling or ID format, or try a partial "
        "name, plate, or FIR number."
    ),
    "low_confidence": (
        "Insufficient information — I found some partial matches, but nothing reliable "
        "enough to present with confidence. Adding one more concrete detail (e.g. a "
        "father's name, approximate age, or area) would help narrow it down."
    ),
    "out_of_scope": (
        "This type of request is outside what I can answer for your role. I can help "
        "with case lookups, antecedents, and similar-case patterns within your scope — "
        "or this request can be routed through the appropriate desk."
    ),
    "invalid_reference": (
        "That reference doesn't match the expected format. Please re-check and try again."
    ),
}


def refusal_block(reason: NoAnswerReason) -> NoAnswerBlock:
    return NoAnswerBlock(
        id=f"no-answer-{uuid.uuid4().hex[:8]}",
        message=_REFUSAL_COPY[reason],
        reason=reason,
    )


def refusal_message(reason: NoAnswerReason) -> AssistantMessage:
    return AssistantMessage(blocks=[refusal_block(reason)])


# ---------------------------------------------------------------------------
# Composer
# ---------------------------------------------------------------------------


def compose(
    final_answer: FinalAnswer | None,
    scratchpad: TurnScratchpad,
    specialist: SpecialistConfig,
) -> AssistantMessage:
    """§7 composer rules. `final_answer=None` means the loop aborted without a
    parseable answer (budget exhausted, repeated tool failure, etc.) —
    degrades to no_answer(low_confidence), never a 5xx (§15)."""
    if final_answer is None:
        return refusal_message("low_confidence")

    if final_answer.status == "no_answer":
        return refusal_message(final_answer.reason or "low_confidence")

    blocks: list[ContentBlock] = []
    for fb in final_answer.blocks:
        block = _materialize(fb, scratchpad)
        if block is None:
            continue
        if block.type not in specialist.allowed_blocks:
            continue
        blocks.append(block)

    if not blocks:
        return refusal_message("low_confidence")

    return AssistantMessage(blocks=blocks)


def _materialize(fb: FinalBlock, scratchpad: TurnScratchpad) -> ContentBlock | None:
    if isinstance(fb, FinalTextBlock):
        citations = _citations_or_none(scratchpad, fb.citation_keys)
        return TextBlock(id=_new_id("text"), content=fb.markdown, citations=citations)

    if isinstance(fb, FinalTableBlock):
        if len(fb.rows) > 10:
            # Larger tabular data must come via payload_ref (§7), not be retyped.
            return None
        columns = [TableColumn(key=c, label=c) for c in fb.columns]
        rows = [dict(zip(fb.columns, row)) for row in fb.rows]
        citations = _citations_or_none(scratchpad, fb.citation_keys)
        return TableBlock(id=_new_id("table"), title=fb.title, columns=columns, rows=rows, citations=citations)

    if isinstance(fb, FinalPayloadRefBlock):
        return scratchpad.get_payload(fb.payload_id)  # None -> block dropped (unknown payload_id)

    return None


def _citations_or_none(scratchpad: TurnScratchpad, keys: list[str]) -> list[Citation] | None:
    citations = scratchpad.citations_for(keys)
    return citations or None


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"
