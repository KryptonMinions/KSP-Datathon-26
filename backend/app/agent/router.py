"""Router (ORCHESTRATOR_STEERING.md §4). Pure lookup, no LLM — gating has
already run in build_frame, so the router only ever sees allowed frames."""

from __future__ import annotations

from app.semantic.frame import QueryClass

from .specialists import AUDIT_ANALYST, CASE_INVESTIGATOR, INTEL_ANALYST, REPORT_COMPOSER, SpecialistConfig

_ROUTE: dict[str, SpecialistConfig] = {
    "lookup": CASE_INVESTIGATOR,
    "case_detail": CASE_INVESTIGATOR,
    "pattern": CASE_INVESTIGATOR,
    "network": INTEL_ANALYST,
    "geo_analytics": INTEL_ANALYST,
    "trend": INTEL_ANALYST,
    "summary": REPORT_COMPOSER,
    "audit": AUDIT_ANALYST,
}


def select(query_class: QueryClass) -> SpecialistConfig:
    specialist = _ROUTE.get(query_class)
    if specialist is None:
        raise ValueError(
            f"no specialist route for query_class={query_class!r} "
            "(the gate should have refused before reaching the router)"
        )
    return specialist
