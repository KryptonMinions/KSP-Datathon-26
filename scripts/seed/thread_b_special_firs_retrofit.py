#!/usr/bin/env python3
"""Targeted UPDATE retrofit for Thread B's two special-case FIRs (the MYS
unrecovered-vehicle FIR and Manja's own RECEIVING-STOLEN FIR), which were
written before 03_synthetic.py's thread_b_firs() main loop pattern (facts +
FORM IF-1 fields + mo_description_free) was applied to them. Mirrors
thread_a_retrofit.py's targeted-UPDATE strategy: these FIRs' PKs and FK
references are already correct and already committed, so only the weak/empty
narrative and FORM IF-1 columns need fixing.
"""

import math
import random
from datetime import timedelta

from db import connect
from geo_helpers import (
    bearing_distance,
    deterministic_int,
    deterministic_weighted_choice,
    format_direction_distance,
    resolve_locality,
)
from narrative_facts import build_fact_sheet, build_fir_narrative_prompt, \
    build_mo_description_free_prompt, build_police_report_prompt, build_victim_statement_prompt
from narrative_gen import generate_narrative

MYS_FIR_ID = "KA-MYS-999-2026-9001"
MANJA_FIR_ID = "KA-BLR-200-2026-2001"
THREAD_B_JAYANAGAR_CENTER = (12.928575, 77.581388)

_JITTER_RNG = random.Random(1729)


def jitter_point(lat: float, lon: float, max_meters: float) -> tuple[float, float]:
    """Small random offset, roughly uniform within max_meters of (lat, lon).
    Mirrors 03_synthetic.py's jitter_point() but with its own seeded RNG
    instance, since this is a standalone retrofit script, not part of the
    original generation run.
    """
    r = max_meters * math.sqrt(_JITTER_RNG.random())
    theta = _JITTER_RNG.random() * 2 * math.pi
    dlat = (r * math.cos(theta)) / 111_000
    dlon = (r * math.sin(theta)) / (111_000 * math.cos(math.radians(lat)))
    return round(lat + dlat, 6), round(lon + dlon, 6)


def _fetch_station(cur, station_id: str) -> tuple[str, float, float]:
    cur.execute("SELECT station_name, latitude, longitude FROM police_stations WHERE station_id = %s", (station_id,))
    name, lat, lon = cur.fetchone()
    return name, float(lat), float(lon)


def main() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            # ---------------- MYS FIR ----------------
            mys_station_name, mys_station_lat, mys_station_lon = _fetch_station(cur, "KA-MYS-013")
            mys_lat, mys_lon = jitter_point(mys_station_lat, mys_station_lon, 800)
            mys_locality_id, mys_locality_name = resolve_locality(cur, mys_lat, mys_lon, {})

            cur.execute("SELECT registration_date, incident_date FROM firs WHERE fir_id = %s", (MYS_FIR_ID,))
            mys_reg_date, mys_incident_dt = cur.fetchone()

            mys_facts = build_fact_sheet(
                fir_id=MYS_FIR_ID, crime_type_id="THEFT-VEHICLE", station_name=mys_station_name,
                district_name="Mysuru", locality_name=mys_locality_name, victim_name="Harsha Vardhan",
                incident_hour=mys_incident_dt.hour, mo_row=None, num_accused=1,
            )
            mys_mo_free_prompt, mys_mo_free_temp = build_mo_description_free_prompt(mys_facts)
            mys_mo_description_free = generate_narrative(
                "firs", MYS_FIR_ID, "mo_description_free", mys_mo_free_prompt, temperature=mys_mo_free_temp, force_kn=False
            ).text_en

            mys_distance_km, mys_compass = bearing_distance(mys_station_lat, mys_station_lon, mys_lat, mys_lon)
            mys_direction_distance = format_direction_distance(mys_distance_km, mys_compass)
            mys_information_type = deterministic_weighted_choice(
                f"{MYS_FIR_ID}:information_type", [("Oral", 0.65), ("Written", 0.35)]
            )
            mys_info_received_ts = mys_reg_date - timedelta(minutes=deterministic_int(f"{MYS_FIR_ID}:info_offset", 5, 90))
            mys_gd_entry_time = mys_info_received_ts + timedelta(minutes=deterministic_int(f"{MYS_FIR_ID}:gd_offset", 2, 20))
            mys_incident_location = f"{mys_locality_name}, {mys_station_name.replace(' PS', '')} jurisdiction"

            cur.execute(
                """
                UPDATE firs SET
                    latitude = %s, longitude = %s, incident_location = %s,
                    mo_description_free = %s, incident_locality_id = %s,
                    info_received_ts = %s, gd_entry_number = %s, gd_entry_time = %s,
                    information_type = %s, beat_number = %s, direction_distance_from_ps = %s
                WHERE fir_id = %s
                """,
                (
                    mys_lat, mys_lon, mys_incident_location,
                    mys_mo_description_free, mys_locality_id,
                    mys_info_received_ts, str(deterministic_int(f"{MYS_FIR_ID}:gd_number", 1, 999)), mys_gd_entry_time,
                    mys_information_type, f"Beat-{deterministic_int(f'{MYS_FIR_ID}:beat', 1, 6)}", mys_direction_distance,
                    MYS_FIR_ID,
                ),
            )

            cur.execute("SELECT 1 FROM fir_victims WHERE fir_id = %s", (MYS_FIR_ID,))
            if cur.fetchone() is None:
                cur.execute("SELECT complainant_id FROM firs WHERE fir_id = %s", (MYS_FIR_ID,))
                (mys_victim_id,) = cur.fetchone()
                mys_vs_prompt, mys_vs_temp = build_victim_statement_prompt(mys_facts)
                mys_victim_statement = generate_narrative(
                    "fir_victims", MYS_FIR_ID, "victim_statement", mys_vs_prompt, temperature=mys_vs_temp, force_kn=False
                ).text_en
                cur.execute(
                    "INSERT INTO fir_victims (fir_victim_id, fir_id, person_id, victim_serial, victim_statement) "
                    "VALUES (gen_random_uuid(), %s, %s, 1, %s)",
                    (MYS_FIR_ID, mys_victim_id, mys_victim_statement),
                )
            print(f"  retrofit complete: {MYS_FIR_ID}")

            # ---------------- Manja FIR ----------------
            manja_station_name, manja_station_lat, manja_station_lon = _fetch_station(cur, "KA-BLR-050")
            manja_lat, manja_lon = jitter_point(*THREAD_B_JAYANAGAR_CENTER, 150)

            cur.execute("SELECT locality_name, locality_id FROM localities WHERE locality_name = ANY(%s)",
                        (["Jayanagar 4th Block", "J.P. Nagar 2nd Phase"],))
            by_name = dict(cur.fetchall())
            named_localities = {
                "Jayanagar 4th Block": (THREAD_B_JAYANAGAR_CENTER[0], THREAD_B_JAYANAGAR_CENTER[1], by_name["Jayanagar 4th Block"]),
            }
            manja_locality_id, manja_locality_name = resolve_locality(cur, manja_lat, manja_lon, named_localities)

            cur.execute("SELECT registration_date, incident_date FROM firs WHERE fir_id = %s", (MANJA_FIR_ID,))
            manja_reg_date, manja_incident_dt = cur.fetchone()

            manja_facts = build_fact_sheet(
                fir_id=MANJA_FIR_ID, crime_type_id="RECEIVING-STOLEN", station_name=manja_station_name,
                district_name="Bengaluru", locality_name=manja_locality_name, victim_name="the State",
                incident_hour=manja_incident_dt.hour, mo_row=None, num_accused=1,
            )
            manja_narrative_prompt, manja_temp = build_fir_narrative_prompt(manja_facts)
            manja_narrative = generate_narrative(
                "firs", MANJA_FIR_ID, "fir_narrative", manja_narrative_prompt, temperature=manja_temp, force_kn=False
            ).text_en
            manja_report_prompt, manja_report_temp = build_police_report_prompt(manja_facts)
            manja_complaint = generate_narrative(
                "firs", MANJA_FIR_ID, "complaint_text", manja_report_prompt, temperature=manja_report_temp, force_kn=False
            ).text_en
            manja_mo_free_prompt, manja_mo_free_temp = build_mo_description_free_prompt(manja_facts)
            manja_mo_description_free = generate_narrative(
                "firs", MANJA_FIR_ID, "mo_description_free", manja_mo_free_prompt, temperature=manja_mo_free_temp, force_kn=False
            ).text_en

            manja_distance_km, manja_compass = bearing_distance(
                manja_station_lat, manja_station_lon, manja_lat, manja_lon
            )
            manja_direction_distance = format_direction_distance(manja_distance_km, manja_compass)
            manja_info_received_ts = manja_reg_date - timedelta(
                minutes=deterministic_int(f"{MANJA_FIR_ID}:info_offset", 5, 90)
            )
            manja_gd_entry_time = manja_info_received_ts + timedelta(
                minutes=deterministic_int(f"{MANJA_FIR_ID}:gd_offset", 2, 20)
            )
            manja_incident_location = f"{manja_locality_name}, scrap dealer premises"

            cur.execute(
                """
                UPDATE firs SET
                    latitude = %s, longitude = %s, incident_location = %s,
                    complaint_text = %s, fir_narrative = %s, mo_description_free = %s,
                    incident_locality_id = %s, info_received_ts = %s, gd_entry_number = %s,
                    gd_entry_time = %s, information_type = 'Written', beat_number = %s,
                    direction_distance_from_ps = %s
                WHERE fir_id = %s
                """,
                (
                    manja_lat, manja_lon, manja_incident_location,
                    manja_complaint, manja_narrative, manja_mo_description_free,
                    manja_locality_id, manja_info_received_ts,
                    str(deterministic_int(f"{MANJA_FIR_ID}:gd_number", 1, 999)),
                    manja_gd_entry_time, f"Beat-{deterministic_int(f'{MANJA_FIR_ID}:beat', 1, 6)}",
                    manja_direction_distance,
                    MANJA_FIR_ID,
                ),
            )
            print(f"  retrofit complete: {MANJA_FIR_ID}")

        conn.commit()
    print("Thread B special-case FIR retrofit: done")


if __name__ == "__main__":
    main()
