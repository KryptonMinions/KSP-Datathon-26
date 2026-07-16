"""Fact-sheet + prompt-template pools for FIR narrative generation, shared
across golden threads A/B/C and the background corpus (SEED_RUNBOOK.md §6.4).

Split out of 03_synthetic.py during the Thread A narrative-quality retrofit.
Root cause of the original bug: prompts were built from a near-constant
template string with only crime_type_id swapped in, so 12 FIRs' worth of
complaint_text read almost identically. Fix has two independent parts, both
necessary:
  1. Fact injection — every prompt pulls in this FIR's own locality name,
     victim name, time of day, and MO-specific detail (tool/target from the
     linked mo_codes row, or CRIME_TYPE_MO_HINTS fallback when no mo_code_id
     is set), instead of a fixed "Mysuru Ring Road corridor" / "two-wheeler"
     clause.
  2. Template variety — each build_*_prompt picks from a small pool of
     differently-shaped instruction templates via a seeded draw. Fact
     variety alone isn't enough: a single template shape with different
     nouns dropped in still reads structurally identical across records.

This module owns *domain content* (which facts go into which prompt).
narrative_gen.py owns the *generation mechanism* (Ollama call, disk cache,
Kannada mirror) — callers should route through narrative_gen.generate_narrative(),
not narrative_gen.generate_english() directly, so caching actually applies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from geo_helpers import deterministic_choice

# Generic MO grounding for FIRs with no mo_code_id linked — same column
# shape as mo_codes, so build_mo_description_free_prompt() can treat a real
# mo_codes row and this fallback dict identically. Extend as new
# crime_type_id values appear in Thread B/C and the background corpus.
CRIME_TYPE_MO_HINTS: dict[str, dict] = {
    "SNATCHING-CHAIN": {"target_type": "Person", "tool_used": "two-wheeler, pillion snatch", "time_pattern": "Evening"},
    "SNATCHING-GENERAL": {"target_type": "Person", "tool_used": "on foot or bicycle", "time_pattern": "Variable"},
    "ROBBERY": {"target_type": "Person", "tool_used": "knife or blunt weapon", "time_pattern": "Night"},
    "THEFT-VEHICLE": {"target_type": "Vehicle", "tool_used": "duplicate/master key", "time_pattern": "Night"},
    "THEFT-GENERAL": {"target_type": "Person", "tool_used": "none, opportunistic", "time_pattern": "Variable"},
    "THEFT-PICKPOCKET": {"target_type": "Person", "tool_used": "blade/razor, bag-slitting", "time_pattern": "Evening"},
    "HOUSE-BREAKING": {"target_type": "Residential", "tool_used": "crowbar", "time_pattern": "Night"},
    "EXTORTION": {"target_type": "Commercial", "tool_used": "none, threats", "time_pattern": "Business_Hours"},
    "RECEIVING-STOLEN": {"target_type": "Property", "tool_used": "scrap-dealer resale network", "time_pattern": "Business_Hours"},
}


@dataclass
class FIRFactSheet:
    fir_id: str
    crime_type_id: str
    station_name: str
    district_name: str
    locality_name: str
    victim_name: str
    time_of_day: str  # "late night" | "evening" | "daytime" | "early morning"
    mo_target_type: Optional[str]
    mo_tool_used: Optional[str]
    mo_time_pattern: Optional[str]
    mo_catalog_description: Optional[str]  # verbatim mo_codes.mo_description, when linked — grounding only, never to be echoed
    num_accused: int


def _time_of_day(hour: int) -> str:
    if 0 <= hour < 5:
        return "late night"
    if 5 <= hour < 8:
        return "early morning"
    if 8 <= hour < 17:
        return "daytime"
    if 17 <= hour < 20:
        return "evening"
    return "night"


def build_fact_sheet(
    *,
    fir_id: str,
    crime_type_id: str,
    station_name: str,
    district_name: str,
    locality_name: str,
    victim_name: str,
    incident_hour: int,
    mo_row: Optional[dict],
    num_accused: int,
) -> FIRFactSheet:
    """mo_row: a dict with target_type/tool_used/time_pattern/mo_description
    keys — either fetched from a real mo_codes row (when fir.mo_code_id is
    set) or CRIME_TYPE_MO_HINTS[crime_type_id] as fallback grounding. Pass
    None only if crime_type_id has no hint entry either (should not happen
    for the crime types currently in use — add a CRIME_TYPE_MO_HINTS entry
    instead of silently falling back to generic text).
    """
    hint = mo_row or CRIME_TYPE_MO_HINTS.get(crime_type_id)
    return FIRFactSheet(
        fir_id=fir_id,
        crime_type_id=crime_type_id,
        station_name=station_name,
        district_name=district_name,
        locality_name=locality_name,
        victim_name=victim_name,
        time_of_day=_time_of_day(incident_hour),
        mo_target_type=hint.get("target_type") if hint else None,
        mo_tool_used=hint.get("tool_used") if hint else None,
        mo_time_pattern=hint.get("time_pattern") if hint else None,
        mo_catalog_description=hint.get("mo_description") if hint else None,
        num_accused=num_accused,
    )


# ============================================================
# Prompt template pools. Each build_* function returns (prompt, temperature).
# Template choice is deterministic per-FIR-per-field (via deterministic_choice
# keyed on fir_id+field name), not the module-level RNG — so a standalone
# retrofit script gets the same template a fresh generation run would,
# without needing to replay unrelated RNG draws in the original call order.
# ============================================================

_COMPLAINT_TEMPLATES = [
    "Write a 3-sentence police FIR complaint narrative in English, first-person from "
    "the victim ({victim_name}), describing a {crime_desc} that happened {time_of_day} "
    "near {locality_name}. The offender used {tool_used}. Do not include the victim's "
    "name or any dates in the text itself — describe only the incident and immediate aftermath.",

    "Write a 3-sentence first-person police complaint in English from a victim of a "
    "{crime_desc} near {locality_name}, {time_of_day}. Open with what the victim was "
    "doing right before the incident (not 'I was walking'), then describe the offender's "
    "approach using {tool_used}, then the loss. No names or dates.",

    "Write a 2-3 sentence first-person FIR complaint narrative in English for a "
    "{crime_desc} in the {locality_name} area, occurring {time_of_day}. Focus on a "
    "specific, concrete sensory detail (a sound, a vehicle description, what was said) "
    "rather than a generic account. The offender used {tool_used}. No names or dates.",

    "Write a 3-sentence police complaint statement in English, first-person, for a "
    "{crime_desc} near {locality_name} during the {time_of_day}. Describe the moment of "
    "realization (when the victim noticed the loss) before describing the offender's "
    "escape via {tool_used}. No names or dates.",
]

_FIR_NARRATIVE_TEMPLATES = [
    "Write a 2-sentence formal police FIR narrative summary in English (third-person, "
    "investigative tone) for a {crime_desc} case near {locality_name}, under "
    "investigation by {station_name}. Reference the {time_of_day} timing.",

    "Write a 2-sentence formal FIR narrative in English, third-person investigative "
    "tone, opening with the legal classification of a {crime_desc} case at "
    "{locality_name}, then noting the number of accused persons ({num_accused}) "
    "believed involved.",

    "Write a 2-sentence official FIR case narrative in English for {station_name}, "
    "third-person, covering a {crime_desc} reported at {locality_name} during the "
    "{time_of_day} — emphasize the modus operandi ({tool_used}) as the basis for "
    "linking this case to a suspected pattern.",
]

_VICTIM_STATEMENT_TEMPLATES = [
    "Write a 2-sentence victim statement in English for a {crime_desc} police report, "
    "first-person from {victim_name}, describing being approached by an offender using "
    "{tool_used} near {locality_name}.",

    "Write a 2-sentence first-person victim statement in English, given to police "
    "following a {crime_desc} near {locality_name} {time_of_day}. Include one specific "
    "detail about the offender's appearance or the vehicle used.",
]

_DIARY_ACTIONS = [
    ("Suspect_Enquiry", "enquiring with local informants and known associates about possible suspects"),
    ("CCTV_Review", "reviewing CCTV footage from nearby commercial establishments"),
    ("Record_Request", "requesting call detail records / phone tower dumps for the incident window"),
    ("Witness_Reexamination", "re-examining a witness for additional detail"),
    ("Surveillance", "conducting surveillance near a location frequented by the suspect(s)"),
]

_DIARY_TEMPLATES = [
    "Write a 1-2 sentence police case-diary entry #{entry_number} in English for the "
    "{crime_desc} case at {locality_name}, documenting the investigating officer "
    "{action_desc}.",

    "Write a 1-2 sentence police case-diary entry #{entry_number} in English, "
    "third-person, noting progress on the {crime_desc} investigation at {station_name} — "
    "specifically {action_desc}.",
]

_MO_FREE_TEMPLATES_LINKED = [
    "Write a 2-sentence modus-operandi description in English, in an investigating "
    "officer's field-narrative style, for a {crime_desc} case at {locality_name}. "
    "Ground it in these established facts: target={mo_target_type}, method={mo_tool_used}, "
    "typical timing={mo_time_pattern}. Do not copy this catalog wording verbatim — vary "
    "sentence structure and phrasing, and reference this specific case's own details "
    "({num_accused} accused, {time_of_day}).",
]
_MO_FREE_TEMPLATES_UNLINKED = [
    "Write a 2-sentence modus-operandi description in English, in an investigating "
    "officer's field-narrative style, for a {crime_desc} case at {locality_name} "
    "occurring {time_of_day}, believed to involve {num_accused} accused using "
    "{mo_tool_used}.",
]


_CRIME_DESC_OVERRIDES = {
    # Generic hyphen-to-space conversion reads ambiguously for this one
    # ("receiving stolen") and the LLM tends to hallucinate an unrelated
    # burglary/theft narrative instead — spell out the offense.
    "RECEIVING-STOLEN": "receiving/handling stolen property (fencing)",
}


def _crime_desc(crime_type_id: str) -> str:
    if crime_type_id in _CRIME_DESC_OVERRIDES:
        return _CRIME_DESC_OVERRIDES[crime_type_id]
    return crime_type_id.replace("-", " ").lower()


def build_complaint_prompt(facts: FIRFactSheet) -> tuple[str, float]:
    template = deterministic_choice(f"{facts.fir_id}:complaint_text", _COMPLAINT_TEMPLATES)
    prompt = template.format(
        victim_name=facts.victim_name, crime_desc=_crime_desc(facts.crime_type_id),
        locality_name=facts.locality_name, time_of_day=facts.time_of_day,
        tool_used=facts.mo_tool_used or "an unspecified method",
    )
    return prompt, 0.9


def build_fir_narrative_prompt(facts: FIRFactSheet) -> tuple[str, float]:
    template = deterministic_choice(f"{facts.fir_id}:fir_narrative", _FIR_NARRATIVE_TEMPLATES)
    prompt = template.format(
        crime_desc=_crime_desc(facts.crime_type_id), locality_name=facts.locality_name,
        station_name=facts.station_name, time_of_day=facts.time_of_day,
        num_accused=facts.num_accused, tool_used=facts.mo_tool_used or "an unspecified method",
    )
    return prompt, 0.75


def build_victim_statement_prompt(facts: FIRFactSheet) -> tuple[str, float]:
    template = deterministic_choice(f"{facts.fir_id}:victim_statement", _VICTIM_STATEMENT_TEMPLATES)
    prompt = template.format(
        crime_desc=_crime_desc(facts.crime_type_id), victim_name=facts.victim_name,
        locality_name=facts.locality_name, time_of_day=facts.time_of_day,
        tool_used=facts.mo_tool_used or "an unspecified method",
    )
    return prompt, 0.85


def build_diary_entry_prompt(facts: FIRFactSheet, entry_number: int) -> tuple[str, float, str]:
    """Returns (prompt, temperature, action_taken) — action_taken is picked
    here (not by the caller) so it stays consistent with what the prompt
    actually describes.
    """
    action_taken, action_desc = deterministic_choice(
        f"{facts.fir_id}:diary:{entry_number}", _DIARY_ACTIONS
    )
    template = deterministic_choice(f"{facts.fir_id}:diary_template:{entry_number}", _DIARY_TEMPLATES)
    prompt = template.format(
        entry_number=entry_number, crime_desc=_crime_desc(facts.crime_type_id),
        locality_name=facts.locality_name, station_name=facts.station_name, action_desc=action_desc,
    )
    return prompt, 0.9, action_taken


_POLICE_REPORT_TEMPLATES = [
    "Write a 2-3 sentence police information report in English, third-person, documenting "
    "how investigating officers at {station_name} developed information leading to a "
    "{crime_desc} case at {locality_name}, based on recoveries linked to prior cases in "
    "the area. No victim names — this is a suo-moto/informant-based report.",

    "Write a 2-3 sentence official police report in English, third-person investigative "
    "tone, describing a {crime_desc} case registered at {station_name} following a "
    "raid/inspection at {locality_name}. Frame it as police-initiated action, not a "
    "victim complaint.",
]


def build_police_report_prompt(facts: FIRFactSheet) -> tuple[str, float]:
    """For suo-moto/police-initiated FIRs (e.g. RECEIVING-STOLEN cases against a
    known fence) where there is no victim complainant, so build_complaint_prompt's
    first-person victim framing doesn't apply.
    """
    template = deterministic_choice(f"{facts.fir_id}:complaint_text", _POLICE_REPORT_TEMPLATES)
    prompt = template.format(
        crime_desc=_crime_desc(facts.crime_type_id), locality_name=facts.locality_name,
        station_name=facts.station_name,
    )
    return prompt, 0.7


def build_mo_description_free_prompt(facts: FIRFactSheet) -> tuple[str, float]:
    linked = facts.mo_catalog_description is not None
    pool = _MO_FREE_TEMPLATES_LINKED if linked else _MO_FREE_TEMPLATES_UNLINKED
    template = deterministic_choice(f"{facts.fir_id}:mo_description_free", pool)
    prompt = template.format(
        crime_desc=_crime_desc(facts.crime_type_id), locality_name=facts.locality_name,
        mo_target_type=facts.mo_target_type or "unspecified", mo_tool_used=facts.mo_tool_used or "unspecified",
        mo_time_pattern=facts.mo_time_pattern or "variable", num_accused=facts.num_accused,
        time_of_day=facts.time_of_day,
    )
    return prompt, 0.7
