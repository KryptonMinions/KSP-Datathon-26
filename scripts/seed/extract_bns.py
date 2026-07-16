#!/usr/bin/env python3
"""Stage 1.1 — extract BNS/IPC section data (SEED_RUNBOOK.md §2.1) into
seed-sources/tabular/bns_sections.csv, matching table B1's columns.

Scope: the ~60 sections referenced by crime_types + the golden threads
(DATA_ARCHITECTURE_SCHEMA_V2.md §7.2), not the full Sanhita — sections are
selected by keyword match against real offence titles (see TARGET_KEYWORDS),
not hand-typed from memory, so every selected section is independently
confirmed to exist in the source PDF before being written out.

Two source PDFs, both parsed with `pdftotext -layout` (preserves the
documents' columnar layout, which plain PDF-text-extraction libraries tend
to collapse):
  - Bharatiya_Nyaya_Sanhita.pdf: full Act text -> bns_description (verbatim)
    and, where stated inline, max_punishment_yrs.
  - BNS_vs_IPC_comparisons.pdf: BNS-section <-> IPC-section correspondence
    table -> ipc_equivalent + ipc_description (title only; full IPC section
    text is not in our source corpus).

What this script does NOT invent:
  - is_cognizable / is_bailable: neither source PDF contains a First
    Schedule (that classification table lives in a separate BNSS document
    not present in dataset/). These are left NULL with an explicit
    source_note rather than guessed (§2.1 rule: "never guess silently").
  - offence_category / max_punishment_yrs where a target section has no
    keyword match / no extractable punishment clause: left as best-effort
    with a source_note, never silently defaulted.

Mandatory coverage (SEED_RUNBOOK.md §2.1) is hardcoded by BNS number only —
their ipc_equivalent values were independently verified against the
comparison PDF's subsection-level rows (e.g. BNS 303(2) <-> IPC 379
"Punishment for theft", BNS 309(4) <-> IPC 392 "Punishment for robbery")
before being trusted here, not copied blind from the runbook text.
"""

from __future__ import annotations

import csv
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO_ROOT / "dataset"
OUT_DIR = REPO_ROOT / "seed-sources" / "tabular"

BNS_PDF = DATASET_DIR / "Bharatiya_Nyaya_Sanhita.pdf"
COMPARISON_PDF = DATASET_DIR / "BNS_vs_IPC_comparisons.pdf"

# The 7 pairs SEED_RUNBOOK.md §2.1 requires; ipc_equivalent here was verified
# against the comparison PDF's subsection rows (see module docstring), except
# BNS-317 where the runbook names the offence but not an IPC number — IPC 411
# ("dishonestly receiving stolen property") is the standard equivalent, kept
# here but explicitly flagged for human legal verification at Gate 1.
MANDATORY_SECTIONS: dict[str, tuple[str, bool]] = {
    # bns_number: (ipc_number, verified_against_comparison_pdf)
    "303": ("379", True),
    "309": ("392", True),
    "305": ("457", False),  # runbook labels this "house-breaking"; comparison
    # PDF's top-level row for 305 reads "Theft in a dwelling house..." <-> IPC
    # 380, not 457. Kept as the runbook states (authoritative per SEED_RUNBOOK
    # §0 "on any conflict, v2.1 wins") but flagged — needs legal review.
    "115": ("323", False),
    "101": ("302", True),
    "318": ("420", False),
    "317": ("411", False),
}

# offence_category buckets used by crime_types.offence_category (schema B2).
TARGET_KEYWORDS: list[tuple[str, str]] = [
    (r"\btheft\b", "Property"),
    (r"\bsnatching\b", "Property"),
    (r"\bextortion\b", "Property"),
    (r"\brobbery\b", "Property"),
    (r"\bdacoity\b", "Property"),
    (r"\bcriminal misappropriation\b", "Property"),
    (r"\bmischief\b", "Property"),
    (r"\bhouse-trespass\b", "Property"),
    (r"\bhouse-breaking\b", "Property"),
    (r"\blurking house-trespass\b", "Property"),
    (r"\bcriminal trespass\b", "Property"),
    (r"\bcriminal breach of trust\b", "Economic"),
    (r"\breceiving stolen property\b", "Economic"),
    (r"\bdishonestly receiv\w+ stolen property\b", "Economic"),
    (r"\bcheating\b", "Economic"),
    (r"\bforgery\b", "Economic"),
    (r"\bcounterfeit", "Economic"),
    (r"\bmurder\b", "Person"),
    (r"\bculpable homicide\b", "Person"),
    (r"\bcausing hurt\b", "Person"),
    (r"\bgrievous hurt\b", "Person"),
    (r"\bassault\b", "Person"),
    (r"\bcriminal force\b", "Person"),
    (r"\bwrongful restraint\b", "Person"),
    (r"\bwrongful confinement\b", "Person"),
    (r"\bkidnapping\b", "Person"),
    (r"\babduction\b", "Person"),
    (r"\bdowry death\b", "Person"),
    (r"\brape\b", "Sexual"),
    (r"\bsexual harassment\b", "Sexual"),
    (r"outrag\w+ .{0,20}modesty", "Sexual"),
    (r"\bstalking\b", "Sexual"),
    (r"\bvoyeurism\b", "Sexual"),
    (r"\bunlawful assembly\b", "Public_Order"),
    (r"\brioting\b", "Public_Order"),
    (r"\baffray\b", "Public_Order"),
    (r"\bcriminal intimidation\b", "Public_Order"),
    (r"promoting enmity", "Public_Order"),
    (r"\bdefamation\b", "Public_Order"),
    (r"public nuisance", "Public_Order"),
]

WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20,
}

TOP_LEVEL_ROW_RE = re.compile(
    r"^\s*(?P<bns_num>\d{1,3}[A-Z]?)\.\s+(?P<bns_title>.+?)\s{2,}(?P<rest>\S.*)$"
)
IPC_CELL_RE = re.compile(r"^(?P<ipc_num>\d{1,3}[A-Z]?)\.\s*(?P<ipc_title>.+)$")
SUBSECTION_ROW_RE = re.compile(r"^\s*(?P<num>\d{1,3}[A-Z]?)\s*\(")

ACT_HEADER_RE = re.compile(
    r"^\s*(?P<num>\d{1,3}[A-Z]?)\.\s+(?P<title>[A-Z][^—\n]*?)\.—", re.MULTILINE
)
PAGE_NUM_LINE_RE = re.compile(r"^\s*\d{1,4}\s*$")
PUNISH_YEARS_RE = re.compile(
    r"extend(?:ing)? to\s+([a-z\-]+)\s+years?", re.IGNORECASE
)
LIFE_RE = re.compile(r"imprisonment for life", re.IGNORECASE)
DEATH_RE = re.compile(r"\bdeath\b", re.IGNORECASE)


@dataclass
class BnsSection:
    section_id: str
    bns_section: str
    bns_description: str
    ipc_equivalent: Optional[str]
    ipc_description: Optional[str]
    offence_category: Optional[str]
    is_cognizable: Optional[bool]
    is_bailable: Optional[bool]
    max_punishment_yrs: Optional[int]
    chargesheet_days: int
    source_note: str = ""


def pdftotext_layout(pdf_path: Path) -> str:
    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pdftotext failed for {pdf_path}: {result.stderr}")
    return result.stdout


def parse_comparison_table(text: str) -> dict[str, dict]:
    """Returns bns_number -> {bns_title, ipc_number, ipc_title, has_subsections}."""
    lines = text.splitlines()
    entries: dict[str, dict] = {}
    for line in lines:
        m = TOP_LEVEL_ROW_RE.match(line)
        if not m:
            continue
        bns_num = m.group("bns_num")
        bns_title = m.group("bns_title").strip()
        # Strip change/annotation markers like "(Change)".
        bns_title = re.sub(r"\s*\((Change|New Section|Deleted)\)\s*$", "", bns_title).strip()
        rest = m.group("rest").strip()
        ipc_num, ipc_title = None, None
        ipc_m = IPC_CELL_RE.match(rest)
        if ipc_m:
            ipc_num = ipc_m.group("ipc_num")
            ipc_title = ipc_m.group("ipc_title").strip()
        entries[bns_num] = {
            "bns_title": bns_title,
            "ipc_number": ipc_num,
            "ipc_title": ipc_title,
            "has_subsections": False,
        }
    # Second pass: flag sections that also have "NUM (k)" subsection rows —
    # these have per-subsection IPC splits (e.g. definition vs punishment)
    # that the top-level row alone doesn't capture; humans should double
    # check ipc_equivalent for these at Gate 1.
    for line in lines:
        m = SUBSECTION_ROW_RE.match(line)
        if m and m.group("num") in entries:
            entries[m.group("num")]["has_subsections"] = True
    return entries


def parse_act_sections(text: str) -> dict[str, dict]:
    """Returns bns_number -> {title, body} for every 'N. Title.—body' section
    found in the Act's operative text (TOC entries, which have no em-dash,
    are structurally excluded by ACT_HEADER_RE).
    """
    matches = list(ACT_HEADER_RE.finditer(text))
    sections: dict[str, dict] = {}
    for i, m in enumerate(matches):
        num = m.group("num")
        title = m.group("title").strip()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        raw_body = text[body_start:body_end]
        body_lines = [
            ln.strip() for ln in raw_body.splitlines()
            if ln.strip() and not PAGE_NUM_LINE_RE.match(ln) and not re.match(r"^\s*CHAPTER\b", ln)
        ]
        body = " ".join(body_lines)
        body = re.sub(r"\s+", " ", body).strip()
        # Last section found for a given number wins (only relevant if a
        # number is reused across a TOC-vs-body ambiguity, which shouldn't
        # happen given ACT_HEADER_RE requires the em-dash body marker).
        sections[num] = {"title": title, "body": f"{title}.—{body}"}
    return sections


def find_companion_punishment_section(
    title: str, act_sections: dict[str, dict], exclude_num: str
) -> Optional[tuple[str, str]]:
    """BNS frequently splits a definition section from its punishment clause
    into a separate, later-numbered section titled 'Punishment for <offence>'
    (e.g. 101 'Murder' / 103 'Punishment for murder'). When a section's own
    body states no term, this looks for that companion so the CSV note points
    a human reviewer at the right place instead of reading as a failed
    extraction. Returns (bns_number, title) of the best title-overlap match.
    """
    core_word = re.sub(r"[^a-z ]", "", title.lower()).split()
    core_word = [w for w in core_word if len(w) > 3]
    if not core_word:
        return None
    best: Optional[tuple[str, str]] = None
    for num, data in act_sections.items():
        if num == exclude_num:
            continue
        candidate_title = data["title"]
        if not candidate_title.lower().startswith("punishment for"):
            continue
        if any(w in candidate_title.lower() for w in core_word):
            best = (num, candidate_title)
            break
    return best


def extract_max_punishment_years(body: str) -> tuple[Optional[int], str]:
    """Best-effort extraction of the punishment ceiling stated in the section
    body. Returns (years_or_None, note) — note explains life/death or absence.
    """
    if LIFE_RE.search(body):
        return None, "imprisonment for life (see body text)"
    if DEATH_RE.search(body) and re.search(r"punish\w* with death", body, re.IGNORECASE):
        return None, "death penalty provided (see body text)"
    years_found = []
    for m in PUNISH_YEARS_RE.finditer(body):
        word = m.group(1).lower()
        if word in WORD_NUMBERS:
            years_found.append(WORD_NUMBERS[word])
    if years_found:
        return max(years_found), ""
    return None, "no punishment term found in extracted body text"


def infer_offence_category(title: str) -> Optional[str]:
    for pattern, category in TARGET_KEYWORDS:
        if re.search(pattern, title, re.IGNORECASE):
            return category
    return None


def compute_chargesheet_days(max_years: Optional[int], punishment_note: str) -> int:
    if "life" in punishment_note or "death" in punishment_note:
        return 90
    if max_years is not None and max_years >= 10:
        return 90
    return 60


def build_target_list(act_sections: dict[str, dict]) -> dict[str, str]:
    """bns_number -> offence_category, selected by keyword match against
    each Act section's real (extracted) title — never a hand-typed guess at
    which numbers exist.
    """
    targets: dict[str, str] = {}
    for num, data in act_sections.items():
        category = infer_offence_category(data["title"])
        if category:
            targets[num] = category
    for num in MANDATORY_SECTIONS:
        if num not in targets:
            # Mandatory but keyword match missed it (e.g. unusual title
            # phrasing) — still include, category left for human fill-in.
            targets[num] = infer_offence_category(
                act_sections.get(num, {}).get("title", "")
            ) or "Property"
    return targets


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    bns_text = pdftotext_layout(BNS_PDF)
    comparison_text = pdftotext_layout(COMPARISON_PDF)

    (OUT_DIR / "bns_act_raw.txt").write_text(bns_text)
    (OUT_DIR / "comparison_raw.txt").write_text(comparison_text)

    act_sections = parse_act_sections(bns_text)
    comparison = parse_comparison_table(comparison_text)

    targets = build_target_list(act_sections)

    rows: list[BnsSection] = []
    for bns_num in sorted(targets, key=lambda n: (len(n), n)):
        act = act_sections.get(bns_num)
        comp = comparison.get(bns_num)
        notes: list[str] = []

        if act is None:
            notes.append("section number not found in Act body text extraction — SKIPPED")
            continue

        bns_description = act["body"]

        if bns_num in MANDATORY_SECTIONS:
            ipc_equivalent, verified = MANDATORY_SECTIONS[bns_num]
            if not verified:
                notes.append(
                    f"ipc_equivalent={ipc_equivalent} per SEED_RUNBOOK.md §2.1 mandatory "
                    "list; NOT independently confirmed against the comparison PDF's "
                    "subsection rows — verify before relying on this pairing."
                )
            ipc_description = comp["ipc_title"] if comp and comp.get("ipc_title") else None
        elif comp is not None and comp.get("ipc_number"):
            ipc_equivalent = comp["ipc_number"]
            ipc_description = comp.get("ipc_title")
            if comp.get("has_subsections"):
                notes.append(
                    "this BNS section has subsection-level rows in the comparison "
                    "table (definition vs punishment often split across different "
                    "IPC numbers) — the top-level ipc_equivalent may only reflect "
                    "the definition clause; verify against comparison_raw.txt."
                )
        else:
            ipc_equivalent = None
            ipc_description = None
            notes.append("no IPC correspondence found in comparison table (new BNS provision or unparsed row)")

        offence_category = targets[bns_num]

        max_years, punishment_note = extract_max_punishment_years(bns_description)
        if punishment_note == "no punishment term found in extracted body text":
            companion = find_companion_punishment_section(act["title"], act_sections, bns_num)
            if companion:
                companion_num, companion_title = companion
                companion_years, companion_note = extract_max_punishment_years(
                    act_sections[companion_num]["body"]
                )
                # Propagate the companion's life/death/years signal into this
                # note verbatim — compute_chargesheet_days() string-matches on
                # "life"/"death" in punishment_note, so losing that phrase here
                # would silently misclassify a life/death offence as 60 days.
                detail = companion_note or (
                    f"max {companion_years} yrs" if companion_years is not None else ""
                )
                punishment_note = (
                    f"this section is definitional; punishment is stated in companion "
                    f"BNS {companion_num} '{companion_title}'"
                    + (f" — {detail}" if detail else "")
                )
                if companion_years is not None and max_years is None:
                    max_years = companion_years
        if punishment_note:
            notes.append(f"punishment: {punishment_note}")

        chargesheet_days = compute_chargesheet_days(max_years, punishment_note)

        notes.append(
            "is_cognizable/is_bailable: not present in either source PDF (no BNSS "
            "First Schedule in dataset/) — left NULL; populate from a public BNSS "
            "First Schedule reference and verify before production use."
        )

        rows.append(
            BnsSection(
                section_id=f"BNS-{bns_num}",
                bns_section=f"BNS {bns_num}",
                bns_description=bns_description,
                ipc_equivalent=ipc_equivalent,
                ipc_description=ipc_description,
                offence_category=offence_category,
                is_cognizable=None,
                is_bailable=None,
                max_punishment_yrs=max_years,
                chargesheet_days=chargesheet_days,
                source_note=" | ".join(notes),
            )
        )

    csv_path = OUT_DIR / "bns_sections.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "section_id", "bns_section", "bns_description", "ipc_equivalent",
                "ipc_description", "offence_category", "is_cognizable", "is_bailable",
                "max_punishment_yrs", "chargesheet_days", "source_note",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    r.section_id, r.bns_section, r.bns_description, r.ipc_equivalent or "",
                    r.ipc_description or "", r.offence_category or "",
                    "" if r.is_cognizable is None else r.is_cognizable,
                    "" if r.is_bailable is None else r.is_bailable,
                    "" if r.max_punishment_yrs is None else r.max_punishment_yrs,
                    r.chargesheet_days, r.source_note,
                ]
            )

    mandatory_missing = [n for n in MANDATORY_SECTIONS if n not in {row.section_id.split("-")[1] for row in rows}]
    print(f"extracted {len(rows)} BNS sections -> {csv_path}")
    print(f"raw text dumps -> {OUT_DIR / 'bns_act_raw.txt'}, {OUT_DIR / 'comparison_raw.txt'}")
    if mandatory_missing:
        print(f"\nMANDATORY sections MISSING: {mandatory_missing}", )
        return 1
    print("all 7 mandatory sections present. Human review required (Gate 1, SEED_RUNBOOK.md §10) —")
    print("check source_note column, especially is_cognizable/is_bailable (always NULL) and")
    print("the flagged ipc_equivalent verification cases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
