from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator

from app.roles import Role


class LoginRequest(BaseModel):
    username: str
    password: str


class SessionUser(BaseModel):
    id: str
    role: Role


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str
    user: SessionUser


class CurrentUser(BaseModel):
    id: str
    role: Role


class VoiceTranscribeResponse(BaseModel):
    """Sarvam Saaras v3 transcript only -- no translation, no downstream
    processing (VOICE_INTAKE_STEERING.md §3, Phase A)."""

    transcript: str
    detected_language: str | None = None
    request_id: str | None = None


# --------------------------------------------------------------------------
# Ask endpoint (ASK_ENDPOINT_CONTRACT.md §2). Wire types are idiomatic
# snake_case Python/Pydantic -- consistent with every other response in this
# backend (LoginResponse.access_token, VoiceTranscribeResponse.detected_language,
# etc). RealAskService on the frontend translates snake_case wire fields into
# the camelCase shapes frontend/src/lib/types/content-blocks.ts expects, the
# same way auth-api.ts and voice-api.ts already translate their responses.
# --------------------------------------------------------------------------


class Citation(BaseModel):
    level: Literal["fir", "field", "sentence"]
    fir_id: str
    field: str | None = None
    sentence_id: str | None = None
    excerpt: str | None = None


class TableColumn(BaseModel):
    key: str
    label: str
    align: Literal["left", "right"] | None = None


class TextBlock(BaseModel):
    type: Literal["text"] = "text"
    id: str
    content: str
    citations: list[Citation] | None = None


class TableBlock(BaseModel):
    type: Literal["table"] = "table"
    id: str
    title: str | None = None
    columns: list[TableColumn]
    rows: list[dict[str, str | int]]
    citations: list[Citation] | None = None


GraphNodeKind = Literal["person", "gang", "phone", "address"]


class GraphNode(BaseModel):
    id: str
    label: str
    kind: GraphNodeKind
    status: str | None = None


class GraphEdge(BaseModel):
    source: str
    target: str
    label: str
    fir_id: str


class NetworkGraphBlock(BaseModel):
    type: Literal["network_graph"] = "network_graph"
    id: str
    central_node_id: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    citations: list[Citation] | None = None


MoOutcome = Literal["convicted", "trial_pending", "investigation_ongoing", "closed_false"]


class MoMatch(BaseModel):
    fir_id: str
    station: str
    similarity: float
    outcome: MoOutcome
    cracked_by: str | None = None


class MoMatchBlock(BaseModel):
    type: Literal["mo_match"] = "mo_match"
    id: str
    query_description: str
    matches: list[MoMatch]
    common_thread: str | None = None
    citations: list[Citation] | None = None


class EntitySummary(BaseModel):
    id: str
    name: str
    kind: Literal["person", "case", "fir", "location", "gang", "phone", "address"]
    subtitle: str | None = None


class CaseSummary(BaseModel):
    fir_id: str
    station: str
    offence: str
    section: str
    status: str
    detail: str | None = None


class HistorySheetSummary(BaseModel):
    id: str
    station: str
    opened_on: str
    category: str
    risk_level: Literal["Low", "Medium", "High"]
    registered_cases: int
    convictions: int
    absconding_instances: int


class CaseCardBlock(BaseModel):
    type: Literal["case_card"] = "case_card"
    id: str
    person: EntitySummary | None = None
    cases: list[CaseSummary]
    history_sheet: HistorySheetSummary | None = None
    citations: list[Citation] | None = None


class NoAnswerBlock(BaseModel):
    type: Literal["no_answer"] = "no_answer"
    id: str
    message: str
    citations: list[Citation] | None = None


class TrendMetric(BaseModel):
    category: str
    current: float
    previous: float
    delta_pct: float
    trend: Literal["up", "down", "stable"]
    anomaly: bool | None = None
    anomaly_note: str | None = None
    underlying_fir_ids: list[str] | None = None


class PackReportBlock(BaseModel):
    type: Literal["pack_report"] = "pack_report"
    id: str
    title: str
    period: str
    metrics: list[TrendMetric]
    exportable: bool | None = None
    citations: list[Citation] | None = None


ContentBlock = Annotated[
    Union[
        TextBlock,
        TableBlock,
        NetworkGraphBlock,
        MoMatchBlock,
        CaseCardBlock,
        NoAnswerBlock,
        PackReportBlock,
    ],
    Field(discriminator="type"),
]


class AssistantMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    # Not in the ASK_ENDPOINT_CONTRACT.md §2.4 shape as written, but every
    # ported story fixture carries a top-level spoken-language summary
    # alongside its blocks (frontend/src/lib/types/content-blocks.ts
    # ChatMessage.text) -- omitting it would make the real and mock paths
    # render different content, which fails the §5 acceptance criterion.
    text: str | None = None
    blocks: list[ContentBlock] = Field(min_length=1)


class AskRequest(BaseModel):
    query: str
    thread_id: str | None = None
    turn_index: int
    input_modality: Literal["text", "voice"]
    detected_language: str | None = None
    client_ts: str

    @field_validator("query")
    @classmethod
    def _query_length(cls, value: str) -> str:
        trimmed = value.strip()
        if not 1 <= len(trimmed) <= 2000:
            raise ValueError("query must be 1..2000 characters after trimming")
        return trimmed

    @field_validator("turn_index")
    @classmethod
    def _turn_index_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("turn_index must be >= 0")
        return value


class AskResponse(BaseModel):
    thread_id: str
    message_id: str
    server_ts: str
    message: AssistantMessage
