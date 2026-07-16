#!/usr/bin/env python3
"""One-off retrofit: the local Ollama model (qwen2.5:7b-instruct) occasionally
code-switches into Chinese mid-generation — found via 05_validate.py's
sentence-alignment check surfacing a stray "牌照" in one victim_statement,
which led to a broader scan turning up 7 affected rows across
firs.fir_narrative, fir_victims.victim_statement, and
case_diary_entries.entry_text. English text with embedded Chinese isn't
usable narrative content regardless of the Kannada-alignment angle that
found it, so each affected row is regenerated from scratch (fresh cache
entry, fresh English + Kannada where the field has a _kn mirror).
"""

import re

from db import connect
from narrative_facts import build_diary_entry_prompt, build_fir_narrative_prompt, build_victim_statement_prompt
from narrative_gen import KannadaTranslator, _cache_path, generate_narrative

CJK_PATTERN = r"[一-鿿぀-ヿ]"


def fetch_fir_facts(cur, fir_id: str):
    cur.execute(
        """
        SELECT f.crime_type_id, f.mo_code_id, f.incident_date, l.locality_name, ps.station_name,
               f.district_id
        FROM firs f
        JOIN localities l ON l.locality_id = f.incident_locality_id
        JOIN police_stations ps ON ps.station_id = f.station_id
        WHERE f.fir_id = %s
        """,
        (fir_id,),
    )
    crime_type_id, mo_code_id, incident_date, locality_name, station_name, district_id = cur.fetchone()
    mo_row = None
    if mo_code_id:
        cur.execute("SELECT target_type, tool_used, time_pattern, mo_description FROM mo_codes WHERE mo_code_id = %s", (mo_code_id,))
        row = cur.fetchone()
        if row:
            mo_row = {"target_type": row[0], "tool_used": row[1], "time_pattern": row[2], "mo_description": row[3]}
    cur.execute("SELECT count(*) FROM fir_accused WHERE fir_id = %s", (fir_id,))
    num_accused = cur.fetchone()[0]
    district_name = {"MYS": "Mysuru", "MDY": "Mandya", "BLR": "Bengaluru"}.get(district_id, district_id)
    return dict(
        crime_type_id=crime_type_id, station_name=station_name, district_name=district_name,
        locality_name=locality_name, incident_hour=incident_date.hour, mo_row=mo_row, num_accused=num_accused,
    )


def clear_cache(table: str, record_id: str, field: str) -> None:
    path = _cache_path(table, record_id, field)
    if path.exists():
        path.unlink()


def main() -> None:
    from narrative_facts import build_fact_sheet

    translator = KannadaTranslator()
    with connect() as conn:
        with conn.cursor() as cur:
            # --- firs.fir_narrative ---
            cur.execute("SELECT fir_id FROM firs WHERE fir_narrative ~ %s", (CJK_PATTERN,))
            for (fir_id,) in cur.fetchall():
                f = fetch_fir_facts(cur, fir_id)
                facts = build_fact_sheet(fir_id=fir_id, victim_name="the complainant", **f)
                prompt, temp = build_fir_narrative_prompt(facts)
                clear_cache("firs", fir_id, "fir_narrative")
                result = generate_narrative("firs", fir_id, "fir_narrative", prompt, temperature=temp, force_kn=False)
                cur.execute("UPDATE firs SET fir_narrative = %s WHERE fir_id = %s", (result.text_en, fir_id))
                print(f"  fixed firs.fir_narrative for {fir_id}")

            # --- fir_victims.victim_statement ---
            cur.execute(
                "SELECT fv.fir_victim_id, fv.fir_id, fv.victim_statement_kn IS NOT NULL, p.full_name "
                "FROM fir_victims fv JOIN persons p ON p.person_id = fv.person_id WHERE fv.victim_statement ~ %s",
                (CJK_PATTERN,),
            )
            for fir_victim_id, fir_id, had_kn, victim_name in cur.fetchall():
                f = fetch_fir_facts(cur, fir_id)
                facts = build_fact_sheet(fir_id=fir_id, victim_name=victim_name, **f)
                prompt, temp = build_victim_statement_prompt(facts)
                clear_cache("fir_victims", fir_id, "victim_statement")
                result = generate_narrative(
                    "fir_victims", fir_id, "victim_statement", prompt, translator=translator,
                    temperature=temp, force_kn=bool(had_kn),
                )
                cur.execute(
                    "UPDATE fir_victims SET victim_statement = %s, victim_statement_kn = %s WHERE fir_victim_id = %s",
                    (result.text_en, result.text_kn, fir_victim_id),
                )
                print(f"  fixed fir_victims.victim_statement for {fir_id}")

            # --- case_diary_entries.entry_text ---
            cur.execute(
                "SELECT entry_id, fir_id, entry_number, entry_text_kn IS NOT NULL FROM case_diary_entries WHERE entry_text ~ %s",
                (CJK_PATTERN,),
            )
            for entry_id, fir_id, entry_number, had_kn in cur.fetchall():
                f = fetch_fir_facts(cur, fir_id)
                facts = build_fact_sheet(fir_id=fir_id, victim_name="the complainant", **f)
                prompt, temp, _action = build_diary_entry_prompt(facts, entry_number)
                record_id = f"{fir_id}:{entry_number}"
                clear_cache("case_diary_entries", record_id, "entry_text")
                result = generate_narrative(
                    "case_diary_entries", record_id, "entry_text", prompt, translator=translator,
                    temperature=temp, force_kn=bool(had_kn),
                )
                cur.execute(
                    "UPDATE case_diary_entries SET entry_text = %s, entry_text_kn = %s WHERE entry_id = %s",
                    (result.text_en, result.text_kn, entry_id),
                )
                print(f"  fixed case_diary_entries.entry_text for {fir_id}:{entry_number}")

        conn.commit()
    print("Stray-CJK retrofit: done")


if __name__ == "__main__":
    main()
