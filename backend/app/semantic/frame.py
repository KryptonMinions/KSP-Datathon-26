"""SemanticFrame and build_frame (SEMANTIC_LAYER.md Part 2).

P0 SCAFFOLD: types are final; build_frame is a stub that will be implemented in
P2 (normalize -> entity extract/resolve -> classify -> gate -> assemble). It is
NOT yet wired into routers/ask.py.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Literal

from app.config import Settings
from app.roles import Role
from app.schemas import AskRequest, CurrentUser

# 8 query classes + the unresolved fallback (DATA_ARCHITECTURE_SCHEMA_V2.md §1.3).
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


async def build_frame(
    request: AskRequest,
    user: CurrentUser,
    settings: Settings,
) -> SemanticFrame:
    """P0 stub. Real pipeline (P2): normalize the query, extract + resolve
    entities against the DB, classify intent/query_class, attach role. Fail
    open to a refusable `unresolved` frame on any pipeline error."""
    raise NotImplementedError("build_frame lands in P2")
