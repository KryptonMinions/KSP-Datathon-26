"""Layer-2 role gating (DATA_ARCHITECTURE_SCHEMA_V2.md §1.3; ORCHESTRATOR O-10).

Pure allow/refuse table over (role, query_class). This is the UX scope boundary
that runs BEFORE any LLM/tool spend; the hard data boundary is Postgres RLS.

O-10 amendment (LOCKED): network, geo_analytics, trend for investigating_officer
change from refuse to ALLOW. Station scoping is then applied downstream per
ORCHESTRATOR_STEERING.md §4.1 — it is deliberately NOT encoded in GateDecision
(§13.1). Use `is_scoped()` for that.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.roles import Role
from app.schemas import NoAnswerReason

from .frame import QueryClass

# Classes each role may invoke. Admin sees audit only (no case-data grants at
# all — RLS default-denies case tables for admin). Supervisor/Analyst/IO share
# the full analytical set; IO's analytics are station-scoped downstream.
_ALLOWED: dict[Role, set[str]] = {
    Role.INVESTIGATING_OFFICER: {
        "lookup", "case_detail", "pattern", "summary",
        "network", "geo_analytics", "trend",
    },
    Role.SUPERVISOR: {
        "lookup", "case_detail", "pattern", "summary",
        "network", "geo_analytics", "trend",
    },
    Role.ANALYST: {
        "lookup", "case_detail", "pattern", "summary",
        "network", "geo_analytics", "trend",
    },
    Role.ADMIN: {"audit"},
}

# Only IO analytical classes are station-scoped (§4.1). Supervisor/Analyst are
# never scoped; IO lookups/antecedents stay cross-jurisdiction (Golden Thread A).
_IO_SCOPED_CLASSES: set[str] = {"network", "geo_analytics", "trend"}


@dataclass(frozen=True)
class GateDecision:
    allow: bool
    reason: NoAnswerReason | None = None


def gate(role: Role, query_class: QueryClass) -> GateDecision:
    if query_class == "unresolved":
        # Could not classify the request — withhold rather than guess.
        return GateDecision(allow=False, reason="low_confidence")
    if query_class in _ALLOWED.get(role, set()):
        return GateDecision(allow=True)
    return GateDecision(allow=False, reason="out_of_scope")


def is_scoped(role: Role, query_class: QueryClass) -> bool:
    """True when this turn must be station-scoped (§4.1 enforcement applies)."""
    return role == Role.INVESTIGATING_OFFICER and query_class in _IO_SCOPED_CLASSES
