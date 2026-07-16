#!/usr/bin/env python3
"""Retrofit for the 12 Thread A FIRs committed before the narrative-quality
fix (see the plan file's "Addendum: Thread A Narrative Quality Retrofit").

Targeted UPDATE, not delete+regenerate — fir_accused/fir_witnesses/
chargesheets/court_disposals and non-text case_diary_entries columns are
already correct; only firs' own narrative/FORM-IF1 columns and
fir_victims.victim_statement / case_diary_entries.entry_text are wrong.

Fetches facts from the LIVE DB (not by replaying jitter_point()/RNG) — geo
and PKs don't change, only the empty/weak columns are computed. Naturally
resumable: generate_narrative() caches by (table, record_id, field,
PROMPT_VERSION), so a second run after a crash just re-issues the same
UPDATEs with cached text.

Usage:
    python thread_a_retrofit.py
"""

from __future__ import annotations

from datetime import timedelta

from db import connect
from geo_helpers import (
    bearing_distance,
    deterministic_int,
    deterministic_weighted_choice,
    format_direction_distance,
    resolve_locality,
)
from narrative_facts import (
    build_complaint_prompt,
    build_diary_entry_prompt,
    build_fact_sheet,
    build_fir_narrative_prompt,
    build_mo_description_free_prompt,
    build_victim_statement_prompt,
)
from narrative_gen import generate_narrative

DISTRICT_NAMES = {"MYS": "Mysuru", "MDY": "Mandya", "BLR": "Bengaluru"}

# Pure string reconstruction of the 12 fir_ids — matches
# thread_a_firs()'s `f"KA-{district_id}-{serial:03d}-{year}-{serial:04d}"`
# format exactly. No RNG needed since fir_id is deterministic from serial+district.
_FIR_ID_DISTRICTS = [
    (1, "MYS"), (2, "MYS"), (3, "MYS"), (4, "MYS"), (5, "MYS"), (6, "MDY"),
    (7, "MYS"), (8, "MYS"), (9, "MYS"), (10, "MYS"), (11, "MDY"), (12, "BLR"),
]


def _named_localities(cur) -> dict[str, tuple[float, float, str]]:
    from importlib import import_module

    synth = import_module("03_synthetic")
    cur.execute(
        "SELECT locality_name, locality_id FROM localities WHERE locality_name = ANY(%s)",
        (["Hebbal Ring Road", "Metagalli Ring Road"],),
    )
    by_name = dict(cur.fetchall())
    return {
        "Hebbal Ring Road": (*synth.CLUSTER_1_CENTER, by_name["Hebbal Ring Road"]),
        "Metagalli Ring Road": (*synth.CLUSTER_2_CENTER, by_name["Metagalli Ring Road"]),
    }


def retrofit() -> None:
    fir_ids = [
        f"KA-{district_id}-{serial:03d}-2026-{serial:04d}" for serial, district_id in _FIR_ID_DISTRICTS
    ]

    with connect() as conn:
        with conn.cursor() as cur:
            named_localities = _named_localities(cur)

            for fir_id in fir_ids:
                cur.execute(
                    """
                    SELECT station_id, district_id, crime_type_id, mo_code_id, complainant_id,
                           registration_date, incident_date, latitude, longitude
                    FROM firs WHERE fir_id = %s
                    """,
                    (fir_id,),
                )
                row = cur.fetchone()
                if row is None:
                    print(f"  SKIP {fir_id}: not found")
                    continue
                (station_id, district_id, crime_type_id, mo_code_id, complainant_id,
                 registration_date, incident_date, lat, lon) = row

                cur.execute(
                    "SELECT station_name, latitude, longitude FROM police_stations WHERE station_id = %s",
                    (station_id,),
                )
                station_name, station_lat, station_lon = cur.fetchone()

                mo_row = None
                if mo_code_id:
                    cur.execute(
                        "SELECT target_type, tool_used, time_pattern, mo_description FROM mo_codes WHERE mo_code_id = %s",
                        (mo_code_id,),
                    )
                    r = cur.fetchone()
                    if r:
                        mo_row = {"target_type": r[0], "tool_used": r[1], "time_pattern": r[2], "mo_description": r[3]}

                cur.execute("SELECT full_name FROM persons WHERE person_id = %s", (complainant_id,))
                victim_name = cur.fetchone()[0]

                cur.execute("SELECT count(*) FROM fir_accused WHERE fir_id = %s", (fir_id,))
                num_accused = cur.fetchone()[0]

                locality_id, locality_name = resolve_locality(cur, float(lat), float(lon), named_localities)

                facts = build_fact_sheet(
                    fir_id=fir_id, crime_type_id=crime_type_id, station_name=station_name,
                    district_name=DISTRICT_NAMES[district_id], locality_name=locality_name,
                    victim_name=victim_name, incident_hour=incident_date.hour, mo_row=mo_row,
                    num_accused=num_accused,
                )

                complaint_prompt, complaint_temp = build_complaint_prompt(facts)
                complaint = generate_narrative(
                    "firs", fir_id, "complaint_text", complaint_prompt, temperature=complaint_temp, force_kn=False
                ).text_en

                narrative_prompt, narrative_temp = build_fir_narrative_prompt(facts)
                fir_narrative = generate_narrative(
                    "firs", fir_id, "fir_narrative", narrative_prompt, temperature=narrative_temp, force_kn=False
                ).text_en

                mo_free_prompt, mo_free_temp = build_mo_description_free_prompt(facts)
                mo_description_free = generate_narrative(
                    "firs", fir_id, "mo_description_free", mo_free_prompt, temperature=mo_free_temp, force_kn=False
                ).text_en

                distance_km, compass = bearing_distance(float(station_lat), float(station_lon), float(lat), float(lon))
                direction_distance = format_direction_distance(distance_km, compass)
                information_type = deterministic_weighted_choice(
                    f"{fir_id}:information_type", [("Oral", 0.65), ("Written", 0.35)]
                )
                info_received_ts = registration_date - timedelta(
                    minutes=deterministic_int(f"{fir_id}:info_offset", 5, 90)
                )
                gd_entry_time = info_received_ts + timedelta(
                    minutes=deterministic_int(f"{fir_id}:gd_offset", 2, 20)
                )
                gd_entry_number = str(deterministic_int(f"{fir_id}:gd_number", 1, 999))
                beat_number = f"Beat-{deterministic_int(f'{fir_id}:beat', 1, 6)}"
                incident_location = f"{locality_name}, {station_name.replace(' PS', '')} jurisdiction"

                cur.execute(
                    """
                    UPDATE firs SET
                        complaint_text = %s, fir_narrative = %s, mo_description_free = %s,
                        incident_location = %s, incident_locality_id = %s,
                        info_received_ts = %s, gd_entry_number = %s, gd_entry_time = %s,
                        information_type = %s, beat_number = %s, direction_distance_from_ps = %s
                    WHERE fir_id = %s
                    """,
                    (
                        complaint, fir_narrative, mo_description_free,
                        incident_location, locality_id,
                        info_received_ts, gd_entry_number, gd_entry_time,
                        information_type, beat_number, direction_distance,
                        fir_id,
                    ),
                )

                # despatch_to_court_ts, only where a chargesheet already exists
                cur.execute("SELECT filing_date FROM chargesheets WHERE fir_id = %s", (fir_id,))
                cs_row = cur.fetchone()
                if cs_row is not None:
                    despatch_ts = cs_row[0] + timedelta(days=deterministic_int(f"{fir_id}:despatch", 2, 5))
                    cur.execute("UPDATE firs SET despatch_to_court_ts = %s WHERE fir_id = %s", (despatch_ts, fir_id))

                vs_prompt, vs_temp = build_victim_statement_prompt(facts)
                victim_statement = generate_narrative(
                    "fir_victims", fir_id, "victim_statement", vs_prompt, temperature=vs_temp, force_kn=False
                ).text_en
                cur.execute(
                    "UPDATE fir_victims SET victim_statement = %s WHERE fir_id = %s AND victim_serial = 1",
                    (victim_statement, fir_id),
                )

                cur.execute(
                    "SELECT entry_id, entry_number FROM case_diary_entries WHERE fir_id = %s ORDER BY entry_number",
                    (fir_id,),
                )
                for entry_id, entry_number in cur.fetchall():
                    diary_prompt, diary_temp, _ = build_diary_entry_prompt(facts, entry_number)
                    text = generate_narrative(
                        "case_diary_entries", f"{fir_id}:{entry_number}", "entry_text", diary_prompt,
                        temperature=diary_temp, force_kn=False,
                    ).text_en
                    cur.execute(
                        "UPDATE case_diary_entries SET entry_text = %s WHERE entry_id = %s",
                        (text, entry_id),
                    )

                conn.commit()
                print(f"  retrofit complete: {fir_id}")

    print(f"Thread A retrofit: updated {len(fir_ids)} FIRs")


if __name__ == "__main__":
    retrofit()
