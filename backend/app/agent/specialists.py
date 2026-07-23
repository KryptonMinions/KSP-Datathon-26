"""SpecialistConfig registry (ORCHESTRATOR_STEERING.md §4).

Tool lists here reflect what's actually built so far (P1: run_sql/get_schema;
P2: resolve_entity/get_case). search_narratives (RAG) and the P3 analytical
tools (mo_match, build_network, geo_query, trend_series) are added to these
lists when they land — allowed_blocks are declared per the full spec now so no
redesign is needed later; a block type simply goes unused until its tool ships.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .tools.base import Tool
from .tools.entities import GetCaseTool, ResolveEntityTool
from .tools.sql import GetSchemaTool, RunSqlTool

BlockType = Literal[
    "text", "table", "case_card", "mo_match", "network_graph", "map", "pack_report", "no_answer"
]


@dataclass(frozen=True)
class SpecialistConfig:
    name: str
    profile: Literal["fast", "smart"]
    max_iterations: int
    tools: list[Tool]
    allowed_blocks: frozenset[BlockType]
    prompt_file: str
    sql_scope: Literal["case", "audit"] = "case"


# Stateless tool instances, safe to share across turns/specialists.
_run_sql = RunSqlTool()
_get_schema = GetSchemaTool()
_resolve_entity = ResolveEntityTool()
_get_case = GetCaseTool()

CASE_INVESTIGATOR = SpecialistConfig(
    name="case_investigator",
    profile="fast",
    max_iterations=6,
    tools=[_run_sql, _get_schema, _resolve_entity, _get_case],
    allowed_blocks=frozenset({"text", "table", "case_card", "mo_match", "no_answer"}),
    prompt_file="case_investigator.v1.md",
)

INTEL_ANALYST = SpecialistConfig(
    name="intel_analyst",
    profile="fast",
    max_iterations=8,
    tools=[_run_sql, _get_schema, _resolve_entity],
    allowed_blocks=frozenset({"text", "table", "network_graph", "map", "no_answer"}),
    prompt_file="intel_analyst.v1.md",
)

REPORT_COMPOSER = SpecialistConfig(
    name="report_composer",
    profile="smart",
    max_iterations=10,
    tools=[_run_sql, _get_schema, _resolve_entity, _get_case],
    allowed_blocks=frozenset({
        "text", "table", "case_card", "mo_match", "network_graph", "map", "pack_report", "no_answer",
    }),
    prompt_file="report_composer.v1.md",
)

AUDIT_ANALYST = SpecialistConfig(
    name="audit_analyst",
    profile="fast",
    max_iterations=4,
    tools=[_run_sql, _get_schema],
    allowed_blocks=frozenset({"text", "table", "no_answer"}),
    prompt_file="audit_analyst.v1.md",
    sql_scope="audit",
)

REGISTRY: dict[str, SpecialistConfig] = {
    "case_investigator": CASE_INVESTIGATOR,
    "intel_analyst": INTEL_ANALYST,
    "report_composer": REPORT_COMPOSER,
    "audit_analyst": AUDIT_ANALYST,
}


def intel_analyst_scoped_tools() -> list[Tool]:
    """§4.1 rule 4: on station-scoped IO turns, intel_analyst runs WITHOUT
    run_sql/get_schema — closes the raw-SQL bypass around the scope
    injections. Only resolve_entity remains until P3 adds
    build_network/geo_query/trend_series (the tools that actually cover
    the three scoped classes per spec)."""
    return [_resolve_entity]
