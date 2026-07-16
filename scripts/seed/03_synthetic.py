#!/usr/bin/env python3
"""Stage 5 — synthetic case data (SEED_RUNBOOK.md §6). Golden threads A, B, C
first (§6.1, exactly per DATA_ARCHITECTURE_SCHEMA_V2.md §8), then background
corpus (§6.2). This file currently implements Thread A.

All narrative English text is generated live via Ollama (narrative_gen.py);
Kannada mirrors are deferred to a separate batched pass (HF_TOKEN gate —
IndicTrans2 is a gated HuggingFace repo, see narrative_gen.py docstring).
_kn columns are left NULL here and filled in by that later pass.

Relative dates compute from SEED_DEMO_DATE (backend/.env), not the wall clock.
"""

from __future__ import annotations

import random
import sys
import uuid
from datetime import datetime, timedelta

from db import connect, get_demo_date
from geo_helpers import (
    bearing_distance,
    deterministic_choice,
    deterministic_int,
    deterministic_weighted_choice,
    format_direction_distance,
    resolve_locality,
)
from narrative_facts import build_fact_sheet, build_complaint_prompt, build_diary_entry_prompt, \
    build_fir_narrative_prompt, build_mo_description_free_prompt, build_police_report_prompt, \
    build_victim_statement_prompt
from narrative_gen import generate_narrative

RNG = random.Random(20260714)  # fixed seed: reproducible geo jitter/picks

# get_demo_date() returns a plain date (no time-of-day) — combined with
# midnight here so DEMO_DATE - timedelta(hours=...) arithmetic downstream
# (registration_date, incident_date, etc.) yields real datetimes with a
# valid .hour, not a date silently truncated back to day granularity.
DEMO_DATE = datetime.combine(get_demo_date(), datetime.min.time())


def new_uuid() -> str:
    return str(uuid.uuid4())


def jitter_point(lat: float, lon: float, max_meters: float) -> tuple[float, float]:
    """Small random offset, roughly uniform within max_meters of (lat, lon)."""
    # 1 deg latitude ~= 111_000 m; 1 deg longitude ~= 111_000 * cos(lat) m.
    import math

    r = max_meters * math.sqrt(RNG.random())
    theta = RNG.random() * 2 * math.pi
    dlat = (r * math.cos(theta)) / 111_000
    dlon = (r * math.sin(theta)) / (111_000 * math.cos(math.radians(lat)))
    return round(lat + dlat, 6), round(lon + dlon, 6)


# ============================================================
# Thread A — "The Chain Gang" (DATA_ARCHITECTURE_SCHEMA_V2.md §8)
# ============================================================

# Two real Mysuru Ring Road corridor points, ~2.9km apart (well over the
# 800m DBSCAN eps, so the two clusters can never accidentally merge).
CLUSTER_1_CENTER = (12.3480, 76.6220)  # near Hebbal
CLUSTER_2_CENTER = (12.3360, 76.6460)  # near Metagalli
# Scattered remainder points, each >=1.1km from every cluster centre and
# from each other, so they can't form an unintended 3rd/4th cluster.
SCATTERED_POINTS = [
    (12.3420, 76.6330),  # MYS, along corridor, >1km from both cluster centres
    (12.3550, 76.6180),  # MYS, along corridor
    (12.519478, 76.884467),  # MDY — anchored at KA-MDY-023's own coords (Mandya Rural
    # PS), guaranteeing containment within MDY's district polygon since the
    # station itself is already confirmed inside it (Gate 3 geometry check).
    (12.938034, 77.746920),  # BLR — anchored at KA-BLR-147 (Varthur PS), same reasoning.
]


def thread_a_localities() -> dict[str, str]:
    """Insert the 2 named Ring Road corridor localities Thread A needs.
    Golden-thread locality names are colloquial, not official KGIS ward
    names (verified in Stage 3) — authored here as source='Synthetic' with
    real-world coordinates, per the Stage 3 scoping decision.
    """
    localities = [
        ("Hebbal Ring Road", "MYS", "KA-MYS-005", CLUSTER_1_CENTER),
        ("Metagalli Ring Road", "MYS", "KA-MYS-012", CLUSTER_2_CENTER),
    ]
    ids: dict[str, str] = {}
    with connect() as conn:
        with conn.cursor() as cur:
            for name, district_id, station_id, (lat, lon) in localities:
                locality_id = new_uuid()
                cur.execute(
                    """
                    INSERT INTO localities
                        (locality_id, locality_name, locality_type, district_id,
                         primary_station_id, centroid, source)
                    VALUES (%s, %s, 'Area', %s, %s,
                            ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, 'Synthetic')
                    """,
                    (locality_id, name, district_id, station_id, lon, lat),
                )
                ids[name] = locality_id
        conn.commit()
    print(f"Thread A: inserted {len(ids)} corridor localities")
    return ids


def thread_a_persons() -> dict[str, str]:
    """Ravi's 4-record ER cluster + 7 more gang members + a scattering of
    victims/witnesses used across the 12 FIRs. Returns name -> person_id.
    """
    er_cluster_id = new_uuid()
    people = [
        # (key, full_name, aliases, district_id, er_status, is_history_sheeted)
        ("ravi_canonical", "Ravi Kumara S",
         ["Ravi", "Ravi Kumar N", "ರವಿ ಕುಮಾರ್", "Ravikumar"], "MYS", "Canonical", True),
        ("ravi_dup1", "Ravi Kumar N", None, "MYS", "Duplicate", False),
        ("ravi_dup2", "Ravikumar", None, "MDY", "Duplicate", False),
        ("ravi_dup3", "Ravi", None, "MYS", "Duplicate", False),
        ("member2", "Suresh Gowda", None, "MYS", None, False),
        ("member3", "Manjunath K", None, "MYS", None, False),
        ("member4", "Nagaraj HS", None, "MDY", None, False),
        ("member5", "Basavaraj Naik", None, "MDY", None, False),
        ("member6", "Girish Kumar", None, "MYS", None, False),
        ("member7", "Dinesh Patil", None, "MYS", None, False),
        ("member8", "Yogesh Rao", None, "MDY", None, False),
        # background persons — victims / witnesses / panchas across the 12 FIRs
        ("victim1", "Chandrashekar B", None, "MYS", None, False),
        ("victim2", "Lakshmi Devamma", None, "MYS", None, False),
        ("victim3", "Ganesh Prasad", None, "MYS", None, False),
        ("victim4", "Vasanthi R", None, "MDY", None, False),
        ("victim5", "Srinivas Murthy", None, "MYS", None, False),
        ("victim6", "Anitha Kumari", None, "MYS", None, False),
        ("witness1", "Kumar Swamy", None, "MYS", None, False),
        ("witness2", "Roopa N", None, "MYS", None, False),
    ]

    ids: dict[str, str] = {}
    with connect() as conn:
        with conn.cursor() as cur:
            for key, name, aliases, district_id, er_status, is_hs in people:
                person_id = new_uuid()
                ids[key] = person_id
                cur.execute(
                    """
                    INSERT INTO persons
                        (person_id, full_name, aliases, gender, district_id,
                         is_history_sheeted, er_cluster_id, er_confidence, er_status)
                    VALUES (%s, %s, %s, 'Male', %s, %s, %s, %s, %s)
                    """,
                    (
                        person_id, name, aliases, district_id, is_hs,
                        er_cluster_id if key.startswith("ravi_") else None,
                        0.920 if key.startswith("ravi_") else None,
                        er_status,
                    ),
                )
        conn.commit()
    print(f"Thread A: inserted {len(ids)} persons (er_cluster_id={er_cluster_id})")
    return ids


def thread_a_gang(person_ids: dict[str, str]) -> str:
    gang_id = new_uuid()
    member_keys = ["ravi_canonical", "member2", "member3", "member4", "member5", "member6", "member7", "member8"]
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO gangs
                    (gang_id, gang_name, gang_name_kn, primary_crime_type, operating_district,
                     is_active, formation_approx_year, known_strength, notes)
                VALUES (%s, %s, NULL, 'SNATCHING-CHAIN', 'MYS', TRUE, %s, %s, %s)
                """,
                (
                    gang_id, "Mysuru Chain Gang", DEMO_DATE.year - 4, len(member_keys),
                    "Active chain-snatching gang operating along the Mysuru Ring Road corridor, "
                    "with incidents extending into Mandya and Bengaluru City limits.",
                ),
            )
            roles = ["Leader"] + ["Member"] * (len(member_keys) - 1)
            for key, role in zip(member_keys, roles):
                cur.execute(
                    """
                    INSERT INTO gang_memberships
                        (membership_id, gang_id, person_id, role_in_gang, joined_approx_date, is_active)
                    VALUES (%s, %s, %s, %s, %s, TRUE)
                    """,
                    (new_uuid(), gang_id, person_ids[key], role,
                     DEMO_DATE - timedelta(days=365 * RNG.randint(1, 4))),
                )
        conn.commit()
    print(f"Thread A: gang '{gang_id}' with {len(member_keys)} members")
    return gang_id


def thread_a_phones(person_ids: dict[str, str]) -> None:
    """3+ phone numbers each shared across >=2 gang members."""
    member_keys = ["ravi_canonical", "member2", "member3", "member4", "member5", "member6", "member7", "member8"]
    shared_numbers = ["+919742011001", "+919742011002", "+919742011003"]
    # Each shared number linked to 2-3 members; remaining members get a
    # unique own number too, for realism.
    sharing_map = [
        (shared_numbers[0], ["ravi_canonical", "member2", "member3"]),
        (shared_numbers[1], ["ravi_canonical", "member4"]),
        (shared_numbers[2], ["member5", "member6", "member7"]),
    ]
    with connect() as conn:
        with conn.cursor() as cur:
            for number, keys in sharing_map:
                for key in keys:
                    cur.execute(
                        """
                        INSERT INTO person_phones (phone_record_id, person_id, phone_number, phone_type, is_active)
                        VALUES (%s, %s, %s, 'Mobile', TRUE)
                        """,
                        (new_uuid(), person_ids[key], number),
                    )
            for i, key in enumerate(member_keys):
                cur.execute(
                    """
                    INSERT INTO person_phones (phone_record_id, person_id, phone_number, phone_type, is_active)
                    VALUES (%s, %s, %s, 'Mobile', TRUE)
                    """,
                    (new_uuid(), person_ids[key], f"+91974201{2000 + i}"),
                )
        conn.commit()
    print("Thread A: person_phones with 3 shared numbers across gang members")


def thread_a_known_associates(person_ids: dict[str, str]) -> None:
    member_keys = ["ravi_canonical", "member2", "member3", "member4", "member5", "member6", "member7", "member8"]
    pairs = [(member_keys[i], member_keys[j]) for i in range(len(member_keys)) for j in range(i + 1, len(member_keys))]
    # Confirmed co-accused edges for a representative subset (not exhaustive
    # clique — a real gang's known_associates graph is rarely fully dense).
    chosen = RNG.sample(pairs, k=min(10, len(pairs)))
    with connect() as conn:
        with conn.cursor() as cur:
            for a_key, b_key in chosen:
                pid_a, pid_b = person_ids[a_key], person_ids[b_key]
                if pid_a > pid_b:
                    pid_a, pid_b = pid_b, pid_a
                cur.execute(
                    """
                    INSERT INTO known_associates
                        (association_id, person_id_a, person_id_b, association_type, confidence)
                    VALUES (%s, %s, %s, 'Co_Accused', 'Confirmed')
                    """,
                    (new_uuid(), pid_a, pid_b),
                )
        conn.commit()
    print(f"Thread A: {len(chosen)} known_associates Confirmed edges")


def thread_a_history_sheet(person_ids: dict[str, str]) -> None:
    hs_id = new_uuid()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO history_sheets
                    (history_sheet_id, person_id, hs_number, station_id, opened_date,
                     category, is_active, risk_level, total_cases_count, conviction_count)
                VALUES (%s, %s, %s, 'KA-MYS-012', %s, 'Rowdy', TRUE, 'High', 12, 2)
                """,
                (hs_id, person_ids["ravi_canonical"], "HS-MYS-2022-0341",
                 DEMO_DATE - timedelta(days=730)),
            )
            text = generate_english(
                "Write a 2-sentence police history-sheet entry in English documenting that "
                "rowdy-sheeter Ravi Kumara S continues to be active in chain-snatching offences "
                "along the Mysuru Ring Road corridor and remains under periodic surveillance.",
                temperature=0.7,
            )
            cur.execute(
                """
                INSERT INTO history_sheet_entries (hs_entry_id, history_sheet_id, entry_date, entry_text, officer_id)
                VALUES (%s, %s, %s, %s, 'KSP-23417')
                """,
                (new_uuid(), hs_id, DEMO_DATE - timedelta(days=30), text),
            )
        conn.commit()
    print("Thread A: history_sheet (Rowdy, High risk) for Ravi Kumara S")


def _pick_io_pool() -> dict[str, list[str]]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT officer_id, district_id FROM officers "
                "WHERE role = 'IO' AND district_id = ANY(%s) AND officer_id != 'KSP-23417'",
                (["MYS", "MDY", "BLR"],),
            )
            pool: dict[str, list[str]] = {}
            for officer_id, district_id in cur.fetchall():
                pool.setdefault(district_id, []).append(officer_id)
    return pool


# Each row: (serial, station_id, district_id, crime_type_id, mo_code_id,
#            point, days_before_demo_date, investigation_status,
#            use_harish, convicted, gps_exact, near_deadline, fully_dressed,
#            accused_keys, victim_key)
FIR_ROWS = [
    (1, "KA-MYS-012", "MYS", "SNATCHING-CHAIN", "MO-ROB-004", "c1_0", 650, "Chargesheet_Filed", True, True, True, False, False, ["ravi_canonical", "member2"], "victim1"),
    (2, "KA-MYS-012", "MYS", "SNATCHING-CHAIN", "MO-ROB-004", "c1_1", 500, "Chargesheet_Filed", False, False, False, False, False, ["member2", "member3"], "victim2"),
    (3, "KA-MYS-005", "MYS", "SNATCHING-CHAIN", "MO-ROB-004", "c1_2", 620, "Chargesheet_Filed", False, True, True, False, False, ["ravi_dup1", "member3"], "victim3"),
    (4, "KA-MYS-005", "MYS", "SNATCHING-CHAIN", "MO-ROB-004", "c1_3", 400, "Chargesheet_Filed", False, False, False, False, False, ["member4", "member5"], "victim4"),
    (5, "KA-MYS-026", "MYS", "SNATCHING-CHAIN", "MO-ROB-004", "c2_0", 300, "Under_Investigation", False, False, False, False, False, ["member5", "member6"], "victim5"),
    (6, "KA-MDY-023", "MDY", "SNATCHING-CHAIN", "MO-ROB-004", "c2_1", 200, "Under_Investigation", False, False, False, False, False, ["ravi_dup2", "member4"], "victim6"),
    (7, "KA-MYS-012", "MYS", "SNATCHING-GENERAL", None, "c2_2", 58, "Open", True, False, False, True, False, ["member6", "member7"], "victim1"),
    (8, "KA-MYS-005", "MYS", "ROBBERY", None, "c2_3", 120, "Chargesheet_Filed", True, False, False, False, True, ["ravi_canonical", "member7", "member8"], "victim2"),
    (9, "KA-MYS-026", "MYS", "SNATCHING-GENERAL", None, "s_0", 56, "Open", True, False, False, True, False, ["member2", "member8"], "victim3"),
    (10, "KA-MYS-012", "MYS", "SNATCHING-GENERAL", None, "s_1", 54, "Open", True, False, False, True, False, ["member3", "member5"], "victim4"),
    (11, "KA-MDY-023", "MDY", "SNATCHING-GENERAL", None, "s_2", 250, "Under_Investigation", False, False, False, False, False, ["member4", "member6"], "victim5"),
    (12, "KA-BLR-147", "BLR", "ROBBERY", None, "s_3", 180, "Under_Investigation", False, False, False, False, False, ["member7", "member8"], "victim6"),
]

CRIME_TYPE_BNS = {
    "SNATCHING-CHAIN": "BNS-304",
    "SNATCHING-GENERAL": "BNS-304",  # 60-day chargesheet window
    "ROBBERY": "BNS-309",  # 90-day window
}
CHARGESHEET_DAYS = {"BNS-303": 60, "BNS-304": 60, "BNS-309": 90}


def _named_localities_for_thread_a(cur) -> dict[str, tuple[float, float, str]]:
    cur.execute(
        "SELECT locality_name, locality_id FROM localities WHERE locality_name = ANY(%s)",
        (["Hebbal Ring Road", "Metagalli Ring Road"],),
    )
    by_name = dict(cur.fetchall())
    return {
        "Hebbal Ring Road": (*CLUSTER_1_CENTER, by_name["Hebbal Ring Road"]),
        "Metagalli Ring Road": (*CLUSTER_2_CENTER, by_name["Metagalli Ring Road"]),
    }


def _fetch_station(cur, station_id: str) -> tuple[str, float, float]:
    cur.execute(
        "SELECT station_name, latitude, longitude FROM police_stations WHERE station_id = %s", (station_id,)
    )
    name, lat, lon = cur.fetchone()
    # latitude/longitude are DECIMAL columns -> psycopg returns Decimal, not
    # float; bearing_distance()'s math.radians() etc. can't mix Decimal and
    # float, so normalize here once rather than at every call site.
    return name, float(lat), float(lon)


def _fetch_mo_row(cur, mo_code_id: str | None) -> dict | None:
    if mo_code_id is None:
        return None
    cur.execute(
        "SELECT target_type, tool_used, time_pattern, mo_description FROM mo_codes WHERE mo_code_id = %s",
        (mo_code_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return {"target_type": row[0], "tool_used": row[1], "time_pattern": row[2], "mo_description": row[3]}


def thread_a_firs(person_ids: dict[str, str], gang_id: str) -> list[str]:
    points = {
        "c1_0": jitter_point(*CLUSTER_1_CENTER, 250), "c1_1": jitter_point(*CLUSTER_1_CENTER, 250),
        "c1_2": jitter_point(*CLUSTER_1_CENTER, 250), "c1_3": jitter_point(*CLUSTER_1_CENTER, 250),
        "c2_0": jitter_point(*CLUSTER_2_CENTER, 250), "c2_1": jitter_point(*CLUSTER_2_CENTER, 250),
        "c2_2": jitter_point(*CLUSTER_2_CENTER, 250), "c2_3": jitter_point(*CLUSTER_2_CENTER, 250),
        "s_0": SCATTERED_POINTS[0], "s_1": SCATTERED_POINTS[1],
        "s_2": SCATTERED_POINTS[2], "s_3": SCATTERED_POINTS[3],
    }
    io_pool = _pick_io_pool()
    fir_ids: list[str] = []
    district_names = {"MYS": "Mysuru", "MDY": "Mandya", "BLR": "Bengaluru"}

    with connect() as conn:
        with conn.cursor() as cur:
            named_localities = _named_localities_for_thread_a(cur)

            for (serial, station_id, district_id, crime_type_id, mo_code_id, point_key, days_before,
                 status, use_harish, convicted, gps_exact, near_deadline, fully_dressed,
                 accused_keys, victim_key) in FIR_ROWS:
                fir_id = f"KA-{district_id}-{serial:03d}-{DEMO_DATE.year}-{serial:04d}"
                fir_ids.append(fir_id)
                lat, lon = points[point_key]
                bns_section = CRIME_TYPE_BNS[crime_type_id]
                cs_days = CHARGESHEET_DAYS[bns_section]
                registration_date = DEMO_DATE - timedelta(days=days_before)
                incident_dt = registration_date - timedelta(hours=RNG.randint(2, 30))
                chargesheet_deadline = registration_date + timedelta(days=cs_days)
                io_officer_id = "KSP-23417" if use_harish else RNG.choice(io_pool.get(district_id, ["KSP-23417"]))

                if gps_exact:
                    precision, source, confidence = "exact", "gps", round(RNG.uniform(0.95, 0.999), 3)
                else:
                    precision, source, confidence = "locality", "gazetteer", round(RNG.uniform(0.55, 0.90), 3)

                station_name, station_lat, station_lon = _fetch_station(cur, station_id)
                locality_id, locality_name = resolve_locality(cur, lat, lon, named_localities)
                mo_row = _fetch_mo_row(cur, mo_code_id)
                cur.execute("SELECT full_name FROM persons WHERE person_id = %s", (person_ids[victim_key],))
                victim_name = cur.fetchone()[0]

                facts = build_fact_sheet(
                    fir_id=fir_id, crime_type_id=crime_type_id, station_name=station_name,
                    district_name=district_names[district_id], locality_name=locality_name,
                    victim_name=victim_name, incident_hour=incident_dt.hour, mo_row=mo_row,
                    num_accused=len(accused_keys),
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

                # FORM IF-1 fields — real bearing/distance from the handling
                # station to the incident point, deterministic-but-plausible
                # picks for the rest (see geo_helpers module docstring for why
                # these avoid the module-level RNG).
                distance_km, compass = bearing_distance(station_lat, station_lon, lat, lon)
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
                    INSERT INTO firs
                        (fir_id, station_id, district_id, fir_number, fir_year, registration_date,
                         incident_date, incident_location, crime_type_id, primary_bns_section,
                         is_pre_bns, complaint_text, fir_narrative, mo_code_id, mo_description_free,
                         complainant_id, io_officer_id, investigation_status, chargesheet_deadline,
                         fir_type, is_zero_fir, latitude, longitude, location_precision,
                         geocode_source, geocode_confidence, incident_locality_id,
                         info_received_ts, gd_entry_number, gd_entry_time, information_type,
                         beat_number, direction_distance_from_ps)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, %s, %s, %s, %s,
                            %s, %s, %s, %s, 'Original', FALSE, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        fir_id, station_id, district_id, f"{serial:04d}", DEMO_DATE.year, registration_date,
                        incident_dt, incident_location, crime_type_id, bns_section,
                        complaint, fir_narrative, mo_code_id, mo_description_free,
                        person_ids[victim_key], io_officer_id, status, chargesheet_deadline,
                        lat, lon, precision, source, confidence, locality_id,
                        info_received_ts, gd_entry_number, gd_entry_time, information_type,
                        beat_number, direction_distance,
                    ),
                )

                for i, key in enumerate(accused_keys, start=1):
                    cur.execute(
                        """
                        INSERT INTO fir_accused (fir_accused_id, fir_id, person_id, role, accused_serial, is_arrested)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (new_uuid(), fir_id, person_ids[key],
                         "Main_Accused" if i == 1 else "Co_Accused", i, convicted or fully_dressed),
                    )

                vs_prompt, vs_temp = build_victim_statement_prompt(facts)
                victim_statement = generate_narrative(
                    "fir_victims", fir_id, "victim_statement", vs_prompt, temperature=vs_temp, force_kn=False
                ).text_en
                cur.execute(
                    """
                    INSERT INTO fir_victims (fir_victim_id, fir_id, person_id, victim_serial, victim_statement)
                    VALUES (%s, %s, %s, 1, %s)
                    """,
                    (new_uuid(), fir_id, person_ids[victim_key], victim_statement),
                )

                if gps_exact:
                    spot_prompt, spot_temp, _ = build_diary_entry_prompt(facts, 1)
                    diary_text = generate_narrative(
                        "case_diary_entries", f"{fir_id}:1", "entry_text", spot_prompt,
                        temperature=spot_temp, force_kn=False,
                    ).text_en
                    cur.execute(
                        """
                        INSERT INTO case_diary_entries
                            (entry_id, fir_id, officer_id, entry_date, entry_number, entry_text,
                             action_taken, latitude, longitude, location_precision, geocode_source, geocode_confidence)
                        VALUES (%s, %s, %s, %s, 1, %s, 'Spot_Visit', %s, %s, 'exact', 'gps', %s)
                        """,
                        (new_uuid(), fir_id, io_officer_id, registration_date + timedelta(hours=6),
                         diary_text, lat, lon, round(RNG.uniform(0.95, 0.999), 3)),
                    )

                n_diary = 8 if fully_dressed else RNG.randint(1, 3)
                start_entry = 2 if gps_exact else 1
                for entry_num in range(start_entry, start_entry + n_diary):
                    diary_prompt, diary_temp, action_taken = build_diary_entry_prompt(facts, entry_num)
                    text = generate_narrative(
                        "case_diary_entries", f"{fir_id}:{entry_num}", "entry_text", diary_prompt,
                        temperature=diary_temp, force_kn=False,
                    ).text_en
                    cur.execute(
                        """
                        INSERT INTO case_diary_entries
                            (entry_id, fir_id, officer_id, entry_date, entry_number, entry_text, action_taken)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (new_uuid(), fir_id, io_officer_id,
                         registration_date + timedelta(days=entry_num * 3), entry_num, text, action_taken),
                    )

                if fully_dressed:
                    for wkey in ["witness1", "witness2"]:
                        cur.execute(
                            """
                            INSERT INTO fir_witnesses (fir_witness_id, fir_id, person_id, witness_type, statement_recorded)
                            VALUES (%s, %s, %s, 'Eyewitness', TRUE)
                            """,
                            (new_uuid(), fir_id, person_ids[wkey]),
                        )
                    summary = generate_narrative(
                        "chargesheets", fir_id, "summary_text",
                        f"Write a 3-sentence chargesheet summary in English for a {facts.crime_type_id.replace('-', ' ').lower()} "
                        f"case near {locality_name} with {len(accused_keys)} accused, filed under the Bharatiya "
                        f"Nyaya Sanhita, citing the investigation's key evidence (CCTV, recovered property, "
                        f"witness statements) and requesting trial.",
                        temperature=0.7, force_kn=False,
                    ).text_en
                    despatch_ts = registration_date + timedelta(days=55 + deterministic_int(f"{fir_id}:despatch", 2, 5))
                    cur.execute(
                        """
                        INSERT INTO chargesheets
                            (chargesheet_id, fir_id, filing_officer_id, filing_date, court_name,
                             sections_applied, num_accused, num_witnesses, summary_text, filing_status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'Filed')
                        """,
                        (new_uuid(), fir_id, io_officer_id, registration_date + timedelta(days=55),
                         "JMFC Mysuru", [bns_section], len(accused_keys), 2, summary),
                    )
                    cur.execute("UPDATE firs SET despatch_to_court_ts = %s WHERE fir_id = %s", (despatch_ts, fir_id))

                if convicted:
                    chargesheet_id = new_uuid()
                    cur.execute(
                        """
                        INSERT INTO chargesheets
                            (chargesheet_id, fir_id, filing_officer_id, filing_date, court_name,
                             sections_applied, num_accused, num_witnesses, summary_text, filing_status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'Filed')
                        ON CONFLICT (fir_id) DO NOTHING
                        """,
                        (chargesheet_id, fir_id, io_officer_id, registration_date + timedelta(days=58),
                         "JMFC Mysuru", [bns_section], len(accused_keys), 1,
                         f"Chargesheet filed under {bns_section} against {len(accused_keys)} accused "
                         f"for a {facts.crime_type_id.replace('-', ' ').lower()} case near {locality_name}."),
                    )
                    despatch_ts = registration_date + timedelta(days=58 + deterministic_int(f"{fir_id}:despatch_conv", 2, 5))
                    cur.execute("UPDATE firs SET despatch_to_court_ts = %s WHERE fir_id = %s", (despatch_ts, fir_id))
                    cur.execute(
                        """
                        INSERT INTO court_disposals (disposal_id, chargesheet_id, fir_id, disposal_date, court_name, outcome, sentence_details)
                        VALUES (%s, %s, %s, %s, %s, 'Convicted', %s)
                        """,
                        (new_uuid(), chargesheet_id, fir_id, registration_date + timedelta(days=420),
                         "JMFC Mysuru", f"Rigorous imprisonment as per {bns_section}, with fine."),
                    )
        conn.commit()

    print(f"Thread A: inserted {len(fir_ids)} FIRs (2 convicted, 3 near-deadline open, 1 fully-dressed)")
    return fir_ids


_THREAD_A_KEY_TO_NAME = {
    "ravi_canonical": "Ravi Kumara S", "ravi_dup1": "Ravi Kumar N", "ravi_dup2": "Ravikumar",
    "ravi_dup3": "Ravi", "member2": "Suresh Gowda", "member3": "Manjunath K",
    "member4": "Nagaraj HS", "member5": "Basavaraj Naik", "member6": "Girish Kumar",
    "member7": "Dinesh Patil", "member8": "Yogesh Rao",
    "victim1": "Chandrashekar B", "victim2": "Lakshmi Devamma", "victim3": "Ganesh Prasad",
    "victim4": "Vasanthi R", "victim5": "Srinivas Murthy", "victim6": "Anitha Kumari",
    "witness1": "Kumar Swamy", "witness2": "Roopa N",
}


def fetch_thread_a_person_ids() -> dict[str, str]:
    """Re-fetch the person_id mapping for an already-committed Thread A
    setup run (used when resuming into --thread-a-firs as a separate pass).
    """
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT full_name, person_id FROM persons WHERE full_name = ANY(%s)",
                (list(set(_THREAD_A_KEY_TO_NAME.values())),),
            )
            by_name = dict(cur.fetchall())
    # ER-cluster duplicates share a name with no other disambiguator in this
    # simple lookup only for "Ravi" itself, which is unique among the four —
    # each of the 4 Ravi variants has a distinct full_name, so this is safe.
    return {key: by_name[name] for key, name in _THREAD_A_KEY_TO_NAME.items() if name in by_name}


# ============================================================
# Thread B — "The Repeat Victim" (DATA_ARCHITECTURE_SCHEMA_V2.md §8)
#
# Real station note: the schema doc's illustrative "station KA-BLR-021" for
# Savitha's Jayanagar household doesn't match our actual seeded station_id
# assignment (KA-BLR-021 = Chamarajpet PS here) — station IDs were assigned
# sequentially during Stage 3 reference ingest, not hand-picked to match the
# steering doc's example. What matters is the real station covering
# Jayanagar: KA-BLR-050 "Jayanagar PS", and its J.P. Nagar counterpart
# KA-BLR-051 "Jayaprakash Nagar PS" (~2km apart, confirmed via live query) —
# no DEMO_SCENARIOS.md beat queries by literal station ID, only by area name
# ("Jayanagar station limits"), so this substitution doesn't break anything.
# ============================================================

THREAD_B_JAYANAGAR_CENTER = (12.928575, 77.581388)  # KA-BLR-050
THREAD_B_JPNAGAR_CENTER = (12.911800, 77.587600)  # KA-BLR-051
THREAD_B_RECOVERY_CENTER = (12.982986, 77.638280)  # KA-BLR-046 Indiranagar — different locality, for recovery-point variety


def thread_b_localities() -> dict[str, str]:
    localities = [
        ("Jayanagar 4th Block", "BLR", "KA-BLR-050", THREAD_B_JAYANAGAR_CENTER),
        ("J.P. Nagar 2nd Phase", "BLR", "KA-BLR-051", THREAD_B_JPNAGAR_CENTER),
    ]
    ids: dict[str, str] = {}
    with connect() as conn:
        with conn.cursor() as cur:
            for name, district_id, station_id, (lat, lon) in localities:
                locality_id = new_uuid()
                cur.execute(
                    """
                    INSERT INTO localities
                        (locality_id, locality_name, locality_type, district_id,
                         primary_station_id, centroid, source)
                    VALUES (%s, %s, 'Area', %s, %s,
                            ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, 'Synthetic')
                    """,
                    (locality_id, name, district_id, station_id, lon, lat),
                )
                ids[name] = locality_id
        conn.commit()
    print(f"Thread B: inserted {len(ids)} localities (Jayanagar 4th Block, J.P. Nagar 2nd Phase)")
    return ids


def thread_b_persons() -> dict[str, str]:
    people = [
        ("savitha", "Savitha R", None, "BLR", False),
        ("manja", "Manja", ["Manjunatha D"], "BLR", False),
        ("thief1", "Ashwin Kumar", None, "BLR", False),
        ("thief2", "Ravikiran M", None, "BLR", False),
        ("thief3", "Naveen S", None, "BLR", False),
        ("thief4", "Prashanth Kumar", None, "BLR", False),
        ("thief5", "Manoj Gowda", None, "BLR", False),
        ("pancha1", "Muniraju K", None, "BLR", False),
        ("pancha2", "Lakshmamma", None, "BLR", False),
        ("mp_person", "Deepa Rani", None, "BLR", False),
        ("mp_reporter", "Rangaswamy N", None, "BLR", False),
        ("mys_victim", "Harsha Vardhan", None, "MYS", False),
        ("mys_thief", "Sharath Babu", None, "MYS", False),
    ]
    ids: dict[str, str] = {}
    with connect() as conn:
        with conn.cursor() as cur:
            for key, name, aliases, district_id, is_hs in people:
                person_id = new_uuid()
                ids[key] = person_id
                cur.execute(
                    """
                    INSERT INTO persons (person_id, full_name, aliases, gender, district_id, is_history_sheeted)
                    VALUES (%s, %s, %s, 'Male', %s, %s)
                    """,
                    (person_id, name, aliases, district_id, is_hs),
                )
            # Savitha's household address — Jayanagar 4th Block, real facts,
            # tied to the escalation timeline and eventual FIR.
            cur.execute(
                "SELECT locality_id FROM localities WHERE locality_name = 'Jayanagar 4th Block'"
            )
            jayanagar_locality_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO person_addresses
                    (address_id, person_id, address_text, address_type, station_id,
                     latitude, longitude, location_precision, geocode_source, geocode_confidence, locality_id)
                VALUES (%s, %s, %s, 'Current', 'KA-BLR-050', %s, %s, 'locality', 'gazetteer', 0.85, %s)
                """,
                (new_uuid(), ids["savitha"], "Jayanagar 4th Block, Bengaluru",
                 THREAD_B_JAYANAGAR_CENTER[0], THREAD_B_JAYANAGAR_CENTER[1], jayanagar_locality_id),
            )
        conn.commit()
    print(f"Thread B: inserted {len(ids)} persons")
    return ids


# Savitha's eventual FIR id, precomputed with the same format thread_b_firs()
# uses for serial=1 — needed here because ncr_petitions has
# CHECK (status <> 'Escalated_To_FIR' OR escalated_fir_id IS NOT NULL),
# evaluated at INSERT time (not deferrable), so the Petition row must be
# inserted with its escalated_fir_id already set, not filled in by a later
# UPDATE once thread_b_firs() runs.
THREAD_B_SAVITHA_FIR_ID = f"KA-BLR-101-{DEMO_DATE.year}-1001"


def thread_b_escalation(person_ids: dict[str, str]) -> str:
    """2 NCRs + 1 Petition, escalating over 3 years — the last one is
    inserted already pointing at Savitha's eventual FIR (see
    THREAD_B_SAVITHA_FIR_ID docstring above for why it can't be a later UPDATE).
    """
    records = [
        ("NCR", "NCR-A", "Verbal_Abuse", 3 * 365, "Closed", None),
        ("NCR", "NCR-B", "Threat", 2 * 365, "Closed", None),
        ("Petition", None, "Property_Dispute", 365, "Escalated_To_FIR", THREAD_B_SAVITHA_FIR_ID),
    ]
    petition_id_of_last = None
    with connect() as conn:
        with conn.cursor() as cur:
            for i, (petition_type, ncr_prefix, category, days_before, status, escalated_fir_id) in enumerate(records, start=1):
                petition_id = new_uuid()
                received_date = DEMO_DATE - timedelta(days=days_before)
                ncr_number = f"{ncr_prefix}-{DEMO_DATE.year - (days_before // 365)}-{i:04d}" if ncr_prefix else None
                text = generate_narrative(
                    "ncr_petitions", petition_id, "petition_text",
                    f"Write a 2-sentence police {'NCR' if petition_type == 'NCR' else 'petition'} complaint "
                    f"narrative in English, first-person from a woman complainant, regarding a "
                    f"{category.replace('_', ' ').lower()} dispute with a neighbour near Jayanagar 4th Block, "
                    f"Bengaluru. No names or dates.",
                    temperature=0.8, force_kn=False,
                ).text_en
                cur.execute(
                    """
                    INSERT INTO ncr_petitions
                        (petition_id, petition_type, ncr_number, station_id, district_id,
                         complainant_id, received_date, category, petition_text, address_text, status,
                         escalated_fir_id)
                    VALUES (%s, %s, %s, 'KA-BLR-050', 'BLR', %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (petition_id, petition_type, ncr_number, person_ids["savitha"], received_date,
                     category, text, "Jayanagar 4th Block, Bengaluru", status, escalated_fir_id),
                )
                if i == len(records):
                    petition_id_of_last = petition_id
        conn.commit()
    print("Thread B: inserted 2 NCRs + 1 Petition (escalation timeline)")
    return petition_id_of_last


THREAD_B_FIR_ROWS = [
    # (serial, station_id, point_key, mo_code_id, accused_key, victim_key, days_before, status, convicted)
    (1, "KA-BLR-050", "ja_0", "MO-THEFT-011", "thief1", "savitha", 45, "Under_Investigation", False),
    (2, "KA-BLR-050", "ja_1", "MO-THEFT-011", "thief2", "thief1", 300, "Chargesheet_Filed", True),
    (3, "KA-BLR-050", "ja_2", "MO-THEFT-011", "thief3", "thief2", 250, "Under_Investigation", False),
    (4, "KA-BLR-050", "ja_3", "MO-THEFT-011", "thief1", "thief3", 200, "Chargesheet_Filed", True),
    (5, "KA-BLR-050", "ja_4", None, "thief4", "thief4", 150, "Open", False),
    (6, "KA-BLR-050", "ja_5", None, "thief2", "thief5", 100, "Under_Investigation", False),
    (7, "KA-BLR-051", "jp_0", "MO-THEFT-011", "thief3", "thief4", 320, "Chargesheet_Filed", True),
    (8, "KA-BLR-051", "jp_1", None, "thief5", "thief1", 280, "Open", False),
    (9, "KA-BLR-051", "jp_2", None, "thief1", "thief2", 230, "Under_Investigation", False),
    (10, "KA-BLR-051", "jp_3", None, "thief4", "thief3", 180, "Open", False),
    (11, "KA-BLR-051", "jp_4", None, "thief5", "thief4", 130, "Under_Investigation", False),
    (12, "KA-BLR-051", "jp_5", None, "thief2", "thief5", 80, "Open", False),
]

VEHICLE_ROWS = [
    # (fir_serial, reg_number, make, model, color, owner_key, recovered) — owner_key
    # must match that FIR's victim_key in THREAD_B_FIR_ROWS (the vehicle's owner
    # is whoever reported the theft).
    (1, "KA-05-MJ-4977", "Honda", "Activa", "Grey", "savitha", True),
    (2, "KA-03-HN-2210", "TVS", "Jupiter", "Blue", "thief1", True),
    (3, "KA-04-EQ-8834", "Honda", "Activa", "Black", "thief2", True),
    (7, "KA-05-PL-6612", "Suzuki", "Access", "White", "thief4", True),
]
MYS_VEHICLE = ("KA-09-BX-5541", "TVS", "Ntorq", "Red")


def thread_b_firs(person_ids: dict[str, str]) -> dict:
    named_localities: dict[str, tuple[float, float, str]] = {}
    district_names = {"BLR": "Bengaluru", "MYS": "Mysuru"}

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT locality_name, locality_id FROM localities WHERE locality_name = ANY(%s)",
                (["Jayanagar 4th Block", "J.P. Nagar 2nd Phase"],),
            )
            by_name = dict(cur.fetchall())
            named_localities = {
                "Jayanagar 4th Block": (*THREAD_B_JAYANAGAR_CENTER, by_name["Jayanagar 4th Block"]),
                "J.P. Nagar 2nd Phase": (*THREAD_B_JPNAGAR_CENTER, by_name["J.P. Nagar 2nd Phase"]),
            }

            points = {}
            for i in range(6):
                points[f"ja_{i}"] = jitter_point(*THREAD_B_JAYANAGAR_CENTER, 200)
                points[f"jp_{i}"] = jitter_point(*THREAD_B_JPNAGAR_CENTER, 200)

            io_pool = _pick_io_pool()
            fir_ids: dict[int, str] = {}

            for (serial, station_id, point_key, mo_code_id, accused_key, victim_key,
                 days_before, status, convicted) in THREAD_B_FIR_ROWS:
                fir_id = f"KA-BLR-{100 + serial:03d}-{DEMO_DATE.year}-{1000 + serial:04d}"
                fir_ids[serial] = fir_id
                lat, lon = points[point_key]
                registration_date = DEMO_DATE - timedelta(days=days_before)
                incident_dt = registration_date - timedelta(hours=RNG.randint(2, 20))
                crime_type_id = "THEFT-VEHICLE" if serial != 1 else "HOUSE-BREAKING"
                bns_section = "BNS-303" if crime_type_id == "THEFT-VEHICLE" else "BNS-330"
                cs_days = 60 if crime_type_id == "THEFT-VEHICLE" else 90
                chargesheet_deadline = registration_date + timedelta(days=cs_days)
                io_officer_id = RNG.choice(io_pool.get("BLR", ["KSP-23417"]))

                station_name, station_lat, station_lon = _fetch_station(cur, station_id)
                locality_id, locality_name = resolve_locality(cur, lat, lon, named_localities)
                mo_row = _fetch_mo_row(cur, mo_code_id)
                cur.execute("SELECT full_name FROM persons WHERE person_id = %s", (person_ids[victim_key],))
                victim_name = cur.fetchone()[0]

                facts = build_fact_sheet(
                    fir_id=fir_id, crime_type_id=crime_type_id, station_name=station_name,
                    district_name=district_names["BLR"], locality_name=locality_name,
                    victim_name=victim_name, incident_hour=incident_dt.hour, mo_row=mo_row, num_accused=1,
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

                distance_km, compass = bearing_distance(station_lat, station_lon, lat, lon)
                direction_distance = format_direction_distance(distance_km, compass)
                information_type = deterministic_weighted_choice(
                    f"{fir_id}:information_type", [("Oral", 0.65), ("Written", 0.35)]
                )
                info_received_ts = registration_date - timedelta(minutes=deterministic_int(f"{fir_id}:info_offset", 5, 90))
                gd_entry_time = info_received_ts + timedelta(minutes=deterministic_int(f"{fir_id}:gd_offset", 2, 20))
                incident_location = f"{locality_name}, {station_name.replace(' PS', '')} jurisdiction"

                cur.execute(
                    """
                    INSERT INTO firs
                        (fir_id, station_id, district_id, fir_number, fir_year, registration_date,
                         incident_date, incident_location, crime_type_id, primary_bns_section,
                         is_pre_bns, complaint_text, fir_narrative, mo_code_id, mo_description_free,
                         complainant_id, io_officer_id, investigation_status, chargesheet_deadline,
                         fir_type, is_zero_fir, latitude, longitude, location_precision,
                         geocode_source, geocode_confidence, incident_locality_id,
                         info_received_ts, gd_entry_number, gd_entry_time, information_type,
                         beat_number, direction_distance_from_ps)
                    VALUES (%s, %s, 'BLR', %s, %s, %s, %s, %s, %s, %s, FALSE, %s, %s, %s, %s,
                            %s, %s, %s, %s, 'Original', FALSE, %s, %s, 'locality', 'gazetteer', %s, %s,
                            %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        fir_id, station_id, f"{1000 + serial:04d}", DEMO_DATE.year, registration_date,
                        incident_dt, incident_location, crime_type_id, bns_section,
                        complaint, fir_narrative, mo_code_id, mo_description_free,
                        person_ids[victim_key], io_officer_id, status, chargesheet_deadline,
                        lat, lon, round(RNG.uniform(0.55, 0.90), 3), locality_id,
                        info_received_ts, str(deterministic_int(f"{fir_id}:gd_number", 1, 999)), gd_entry_time,
                        information_type, f"Beat-{deterministic_int(f'{fir_id}:beat', 1, 6)}", direction_distance,
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO fir_accused (fir_accused_id, fir_id, person_id, role, accused_serial, is_arrested)
                    VALUES (%s, %s, %s, 'Main_Accused', 1, %s)
                    """,
                    (new_uuid(), fir_id, person_ids[accused_key], convicted),
                )
                vs_prompt, vs_temp = build_victim_statement_prompt(facts)
                victim_statement = generate_narrative(
                    "fir_victims", fir_id, "victim_statement", vs_prompt, temperature=vs_temp, force_kn=False
                ).text_en
                cur.execute(
                    "INSERT INTO fir_victims (fir_victim_id, fir_id, person_id, victim_serial, victim_statement) "
                    "VALUES (%s, %s, %s, 1, %s)",
                    (new_uuid(), fir_id, person_ids[victim_key], victim_statement),
                )

                if convicted:
                    chargesheet_id = new_uuid()
                    cur.execute(
                        """
                        INSERT INTO chargesheets
                            (chargesheet_id, fir_id, filing_officer_id, filing_date, court_name,
                             sections_applied, num_accused, num_witnesses, summary_text, filing_status)
                        VALUES (%s, %s, %s, %s, 'JMFC Bengaluru', %s, 1, 1, %s, 'Filed')
                        """,
                        (chargesheet_id, fir_id, io_officer_id, registration_date + timedelta(days=55),
                         [bns_section], f"Chargesheet filed under {bns_section} for a vehicle theft near {locality_name}."),
                    )
                    cur.execute(
                        """
                        INSERT INTO court_disposals (disposal_id, chargesheet_id, fir_id, disposal_date, court_name, outcome, sentence_details)
                        VALUES (%s, %s, %s, %s, 'JMFC Bengaluru', 'Convicted', %s)
                        """,
                        (new_uuid(), chargesheet_id, fir_id, registration_date + timedelta(days=380),
                         f"Rigorous imprisonment as per {bns_section}, with fine."),
                    )

            # Vehicles
            vehicle_ids: dict[int, str] = {}
            for fir_serial, reg_number, make, model, color, owner_key, recovered in VEHICLE_ROWS:
                vehicle_id = new_uuid()
                vehicle_ids[fir_serial] = vehicle_id
                theft_date = DEMO_DATE - timedelta(days=[r[6] for r in THREAD_B_FIR_ROWS if r[0] == fir_serial][0])
                cur.execute(
                    """
                    INSERT INTO vehicles
                        (vehicle_id, registration_number, vehicle_type, make, model, color,
                         owner_person_id, is_stolen, stolen_fir_id, theft_date, is_recovered)
                    VALUES (%s, %s, 'Two-Wheeler', %s, %s, %s, %s, TRUE, %s, %s, FALSE)
                    """,
                    (vehicle_id, reg_number, make, model, color, person_ids[owner_key],
                     fir_ids[fir_serial], theft_date),
                )
                # Savitha's vehicle (serial 1) gets the full mahazar/seizure
                # treatment in thread_b_recovery() — skip it here so that
                # function's UPDATE is the one source of truth for it. The
                # other "field-lookup variety" vehicles just need a plain
                # recovery status/date, no seizure narrative required by spec.
                if recovered and fir_serial != 1:
                    recovery_date = theft_date + timedelta(days=deterministic_int(f"vehicle:{fir_serial}:recovery", 10, 40))
                    cur.execute(
                        "UPDATE vehicles SET is_recovered = TRUE, recovery_date = %s WHERE vehicle_id = %s",
                        (recovery_date, vehicle_id),
                    )

            # MYS unrecovered vehicle — separate district, "field-lookup variety".
            mys_fir_id = f"KA-MYS-999-{DEMO_DATE.year}-9001"
            mys_days_before = 90
            mys_reg_date = DEMO_DATE - timedelta(days=mys_days_before)
            mys_incident_dt = mys_reg_date - timedelta(hours=8)
            mys_station_name, mys_station_lat, mys_station_lon = _fetch_station(cur, "KA-MYS-013")
            mys_lat, mys_lon = jitter_point(mys_station_lat, mys_station_lon, 800)
            mys_locality_id, mys_locality_name = resolve_locality(cur, mys_lat, mys_lon, {})
            mys_facts = build_fact_sheet(
                fir_id=mys_fir_id, crime_type_id="THEFT-VEHICLE", station_name=mys_station_name,
                district_name="Mysuru", locality_name=mys_locality_name, victim_name="Harsha Vardhan",
                incident_hour=mys_incident_dt.hour, mo_row=None, num_accused=1,
            )
            mys_complaint_prompt, mys_temp = build_complaint_prompt(mys_facts)
            mys_complaint = generate_narrative(
                "firs", mys_fir_id, "complaint_text", mys_complaint_prompt, temperature=mys_temp, force_kn=False
            ).text_en
            mys_mo_free_prompt, mys_mo_free_temp = build_mo_description_free_prompt(mys_facts)
            mys_mo_description_free = generate_narrative(
                "firs", mys_fir_id, "mo_description_free", mys_mo_free_prompt, temperature=mys_mo_free_temp, force_kn=False
            ).text_en

            mys_distance_km, mys_compass = bearing_distance(mys_station_lat, mys_station_lon, mys_lat, mys_lon)
            mys_direction_distance = format_direction_distance(mys_distance_km, mys_compass)
            mys_information_type = deterministic_weighted_choice(
                f"{mys_fir_id}:information_type", [("Oral", 0.65), ("Written", 0.35)]
            )
            mys_info_received_ts = mys_reg_date - timedelta(minutes=deterministic_int(f"{mys_fir_id}:info_offset", 5, 90))
            mys_gd_entry_time = mys_info_received_ts + timedelta(minutes=deterministic_int(f"{mys_fir_id}:gd_offset", 2, 20))
            mys_incident_location = f"{mys_locality_name}, {mys_station_name.replace(' PS', '')} jurisdiction"

            cur.execute(
                """
                INSERT INTO firs
                    (fir_id, station_id, district_id, fir_number, fir_year, registration_date, incident_date,
                     incident_location, crime_type_id, primary_bns_section, is_pre_bns, complaint_text,
                     mo_description_free, complainant_id, io_officer_id, investigation_status, chargesheet_deadline,
                     fir_type, is_zero_fir, latitude, longitude, location_precision, geocode_source, geocode_confidence,
                     incident_locality_id, info_received_ts, gd_entry_number, gd_entry_time, information_type,
                     beat_number, direction_distance_from_ps)
                VALUES (%s, 'KA-MYS-013', 'MYS', '9001', %s, %s, %s, %s, 'THEFT-VEHICLE', 'BNS-303', FALSE, %s,
                        %s, %s, %s, 'Under_Investigation', %s, 'Original', FALSE, %s, %s, 'locality', 'gazetteer', 0.7,
                        %s, %s, %s, %s, %s, %s, %s)
                """,
                (mys_fir_id, DEMO_DATE.year, mys_reg_date, mys_incident_dt,
                 mys_incident_location, mys_complaint, mys_mo_description_free, person_ids["mys_victim"],
                 RNG.choice(io_pool.get("MYS", ["KSP-23417"])), mys_reg_date + timedelta(days=60),
                 mys_lat, mys_lon, mys_locality_id, mys_info_received_ts,
                 str(deterministic_int(f"{mys_fir_id}:gd_number", 1, 999)), mys_gd_entry_time,
                 mys_information_type, f"Beat-{deterministic_int(f'{mys_fir_id}:beat', 1, 6)}", mys_direction_distance),
            )
            mys_vs_prompt, mys_vs_temp = build_victim_statement_prompt(mys_facts)
            mys_victim_statement = generate_narrative(
                "fir_victims", mys_fir_id, "victim_statement", mys_vs_prompt, temperature=mys_vs_temp, force_kn=False
            ).text_en
            cur.execute(
                "INSERT INTO fir_victims (fir_victim_id, fir_id, person_id, victim_serial, victim_statement) "
                "VALUES (%s, %s, %s, 1, %s)",
                (new_uuid(), mys_fir_id, person_ids["mys_victim"], mys_victim_statement),
            )
            mys_vehicle_id = new_uuid()
            reg_number, make, model, color = MYS_VEHICLE
            cur.execute(
                """
                INSERT INTO vehicles
                    (vehicle_id, registration_number, vehicle_type, make, model, color,
                     owner_person_id, is_stolen, stolen_fir_id, theft_date, is_recovered)
                VALUES (%s, %s, 'Two-Wheeler', %s, %s, %s, %s, TRUE, %s, %s, FALSE)
                """,
                (mys_vehicle_id, reg_number, make, model, color, person_ids["mys_victim"], mys_fir_id, mys_reg_date),
            )

            # Manja's own receiving-stolen-property FIR (BNS-317) — suo-moto/police-initiated,
            # no victim complainant (the "victim" is the State), so complaint_text uses
            # build_police_report_prompt() rather than the victim-first-person template.
            manja_fir_id = f"KA-BLR-200-{DEMO_DATE.year}-2001"
            manja_days_before = 60
            manja_reg_date = DEMO_DATE - timedelta(days=manja_days_before)
            manja_incident_dt = manja_reg_date - timedelta(hours=4)
            manja_station_name, manja_station_lat, manja_station_lon = _fetch_station(cur, "KA-BLR-050")
            manja_lat, manja_lon = jitter_point(*THREAD_B_JAYANAGAR_CENTER, 150)
            manja_locality_id, manja_locality_name = resolve_locality(cur, manja_lat, manja_lon, named_localities)
            manja_facts = build_fact_sheet(
                fir_id=manja_fir_id, crime_type_id="RECEIVING-STOLEN", station_name=manja_station_name,
                district_name="Bengaluru", locality_name=manja_locality_name, victim_name="the State",
                incident_hour=manja_incident_dt.hour, mo_row=None, num_accused=1,
            )
            manja_narrative_prompt, manja_temp = build_fir_narrative_prompt(manja_facts)
            manja_narrative = generate_narrative(
                "firs", manja_fir_id, "fir_narrative", manja_narrative_prompt, temperature=manja_temp, force_kn=False
            ).text_en
            manja_report_prompt, manja_report_temp = build_police_report_prompt(manja_facts)
            manja_complaint = generate_narrative(
                "firs", manja_fir_id, "complaint_text", manja_report_prompt, temperature=manja_report_temp, force_kn=False
            ).text_en
            manja_mo_free_prompt, manja_mo_free_temp = build_mo_description_free_prompt(manja_facts)
            manja_mo_description_free = generate_narrative(
                "firs", manja_fir_id, "mo_description_free", manja_mo_free_prompt, temperature=manja_mo_free_temp, force_kn=False
            ).text_en

            manja_distance_km, manja_compass = bearing_distance(
                manja_station_lat, manja_station_lon, manja_lat, manja_lon
            )
            manja_direction_distance = format_direction_distance(manja_distance_km, manja_compass)
            manja_info_received_ts = manja_reg_date - timedelta(
                minutes=deterministic_int(f"{manja_fir_id}:info_offset", 5, 90)
            )
            manja_gd_entry_time = manja_info_received_ts + timedelta(
                minutes=deterministic_int(f"{manja_fir_id}:gd_offset", 2, 20)
            )
            manja_incident_location = f"{manja_locality_name}, scrap dealer premises"

            cur.execute(
                """
                INSERT INTO firs
                    (fir_id, station_id, district_id, fir_number, fir_year, registration_date, incident_date,
                     incident_location, crime_type_id, primary_bns_section, is_pre_bns, complaint_text,
                     fir_narrative, mo_description_free, io_officer_id, investigation_status, chargesheet_deadline,
                     fir_type, is_zero_fir, latitude, longitude, location_precision, geocode_source, geocode_confidence,
                     incident_locality_id, info_received_ts, gd_entry_number, gd_entry_time, information_type,
                     beat_number, direction_distance_from_ps)
                VALUES (%s, 'KA-BLR-050', 'BLR', '2001', %s, %s, %s, %s, 'RECEIVING-STOLEN', 'BNS-317', FALSE, %s,
                        %s, %s, %s, 'Chargesheet_Filed', %s, 'Original', FALSE, %s, %s, 'locality', 'gazetteer', 0.75,
                        %s, %s, %s, %s, 'Written', %s, %s)
                """,
                (manja_fir_id, DEMO_DATE.year, manja_reg_date, manja_incident_dt,
                 manja_incident_location, manja_complaint, manja_narrative, manja_mo_description_free,
                 RNG.choice(io_pool.get("BLR", ["KSP-23417"])), manja_reg_date + timedelta(days=90),
                 manja_lat, manja_lon, manja_locality_id, manja_info_received_ts,
                 str(deterministic_int(f"{manja_fir_id}:gd_number", 1, 999)), manja_gd_entry_time,
                 f"Beat-{deterministic_int(f'{manja_fir_id}:beat', 1, 6)}", manja_direction_distance),
            )
            cur.execute(
                """
                INSERT INTO fir_accused (fir_accused_id, fir_id, person_id, role, accused_serial, is_arrested)
                VALUES (%s, %s, %s, 'Main_Accused', 1, TRUE)
                """,
                (new_uuid(), manja_fir_id, person_ids["manja"]),
            )

        conn.commit()

    print(f"Thread B: inserted {len(fir_ids)} BLR vehicle-theft FIRs + 1 MYS FIR + 1 Manja receiving FIR")
    return {"fir_ids": fir_ids, "vehicle_ids": vehicle_ids, "mys_fir_id": mys_fir_id, "manja_fir_id": manja_fir_id}


def thread_b_recovery(person_ids: dict[str, str], build_result: dict) -> None:
    """Recovery 6 weeks after Savitha's theft: mahazar, 2 panchas, GPS-exact
    point in a different locality (Indiranagar) than the theft (Jayanagar).
    """
    fir_id = build_result["fir_ids"][1]
    vehicle_id = build_result["vehicle_ids"][1]

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT registration_date FROM firs WHERE fir_id = %s", (fir_id,))
            reg_date = cur.fetchone()[0]
            recovery_date = reg_date + timedelta(days=42)
            lat, lon = jitter_point(*THREAD_B_RECOVERY_CENTER, 150)

            # Stolen phone, reported in the same FIR, recovered alongside the vehicle.
            property_id = new_uuid()
            desc = generate_narrative(
                "stolen_property", property_id, "description",
                "Write a 1-sentence description in English of a stolen mobile phone reported in a "
                "house-breaking FIR, including a plausible IMEI-style serial number format.",
                temperature=0.6, force_kn=False,
            ).text_en
            cur.execute(
                """
                INSERT INTO stolen_property
                    (property_id, fir_id, property_type, description, estimated_value_inr, serial_number, is_recovered)
                VALUES (%s, %s, 'Electronics', %s, 18000, %s, FALSE)
                """,
                (property_id, fir_id, desc, f"IMEI-{deterministic_int(fir_id + ':imei', 10**14, 10**15 - 1)}"),
            )

            seizure_id = new_uuid()
            items_desc = generate_narrative(
                "seizures", seizure_id, "items_description",
                "Write a 2-sentence mahazar (seizure panchnama) items description in English for the "
                "recovery of a stolen grey Honda Activa scooter and a mobile phone from a suspect's "
                "residence, in the presence of two independent panch witnesses.",
                temperature=0.6, force_kn=False,
            ).text_en
            cur.execute(
                """
                INSERT INTO seizures
                    (seizure_id, fir_id, mahazar_number, seizure_type, seizure_date, seizure_location,
                     latitude, longitude, location_precision, geocode_source, geocode_confidence,
                     pancha_1_person_id, pancha_2_person_id, items_description,
                     linked_property_id, linked_vehicle_id, muddemal_number, custody_status)
                VALUES (%s, %s, %s, 'Vehicle', %s, %s, %s, %s, 'exact', 'gps', %s, %s, %s, %s, %s, %s, %s, 'In_Custody')
                """,
                (seizure_id, fir_id, f"MZR-BLR-{DEMO_DATE.year}-0142", recovery_date,
                 "Indiranagar, Bengaluru", lat, lon, round(RNG.uniform(0.95, 0.999), 3),
                 person_ids["pancha1"], person_ids["pancha2"], items_desc,
                 property_id, vehicle_id, f"MDM-{DEMO_DATE.year}-0088"),
            )

            cur.execute(
                "UPDATE stolen_property SET is_recovered = TRUE, recovery_date = %s, recovery_location = %s, "
                "recovery_seizure_id = %s, latitude = %s, longitude = %s, location_precision = 'exact', "
                "geocode_source = 'gps', geocode_confidence = %s WHERE property_id = %s",
                (recovery_date, "Indiranagar, Bengaluru", seizure_id, lat, lon,
                 round(RNG.uniform(0.95, 0.999), 3), property_id),
            )
            cur.execute(
                "UPDATE vehicles SET is_recovered = TRUE, recovery_date = %s WHERE vehicle_id = %s",
                (recovery_date, vehicle_id),
            )
        conn.commit()

    print("Thread B: recovery seizure recorded (vehicle + phone, 6 weeks after theft)")


def thread_b_receiver_network(person_ids: dict[str, str], build_result: dict) -> None:
    fence_key = "manja"
    thief_keys = ["thief1", "thief2", "thief3"]  # tied to FIRs 1 (Savitha's), 2, 3
    with connect() as conn:
        with conn.cursor() as cur:
            for thief_key, fir_serial in zip(thief_keys, [1, 2, 3]):
                pid_a, pid_b = person_ids[fence_key], person_ids[thief_key]
                if pid_a > pid_b:
                    pid_a, pid_b = pid_b, pid_a
                cur.execute(
                    """
                    INSERT INTO known_associates
                        (association_id, person_id_a, person_id_b, association_type,
                         first_seen_fir_id, confidence)
                    VALUES (%s, %s, %s, 'Known_Receiver', %s, 'Confirmed')
                    """,
                    (new_uuid(), pid_a, pid_b, build_result["fir_ids"][fir_serial]),
                )
        conn.commit()
    print("Thread B: 3 Known_Receiver known_associates edges (fence Manja <-> thieves)")


def thread_b_missing_person(person_ids: dict[str, str]) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT locality_id FROM localities WHERE locality_name = 'Jayanagar 4th Block'"
            )
            locality_id = cur.fetchone()[0]
            report_date = DEMO_DATE - timedelta(days=200)
            traced_date = DEMO_DATE - timedelta(days=170)
            desc = generate_narrative(
                "missing_persons", person_ids["mp_person"], "physical_description",
                "Write a 1-sentence physical description in English for a missing-person report, "
                "generic enough to not identify a real individual (approximate age, height, clothing worn).",
                temperature=0.6, force_kn=False,
            ).text_en
            cur.execute(
                """
                INSERT INTO missing_persons
                    (mp_id, person_id, reported_by_person_id, station_id, report_date, last_seen_date,
                     last_seen_location, locality_id, latitude, longitude, location_precision,
                     geocode_source, geocode_confidence, physical_description, status, traced_date, traced_location)
                VALUES (%s, %s, %s, 'KA-BLR-050', %s, %s, %s, %s, %s, %s, 'locality', 'gazetteer', 0.7,
                        %s, 'Traced', %s, %s)
                """,
                (new_uuid(), person_ids["mp_person"], person_ids["mp_reporter"], report_date,
                 report_date - timedelta(days=1), "Jayanagar 4th Block, Bengaluru", locality_id,
                 THREAD_B_JAYANAGAR_CENTER[0], THREAD_B_JAYANAGAR_CENTER[1], desc, traced_date,
                 "Jayanagar 4th Block, Bengaluru"),
            )
        conn.commit()
    print("Thread B: missing_persons record (Traced) in Jayanagar 4th Block")


# ============================================================
# Thread C — "Dasara Bandobast" (preventive analytics; DATA_ARCHITECTURE_SCHEMA_V2.md §8)
# ============================================================

# Real-world Mysuru coordinates. K.R. Circle sits along Sayyaji Rao Road near
# the Palace; Bannimantap (the Dasara exhibition/wrestling grounds) is ~2km
# south along the same road — comfortably outside each other's DBSCAN eps
# (250m) while each cluster's own jitter radius stays well inside it.
THREAD_C_KR_CIRCLE_CENTER = (12.307200, 76.655300)  # near KA-MYS-007 Krishnaraja PS
THREAD_C_BANNIMANTAP_CENTER = (12.291900, 76.635500)  # near KA-MYS-001 Ashokpuram PS

CRIME_TYPE_BNS["THEFT-PICKPOCKET"] = "BNS-303"

# (year_label, days_before_demo_date for the window start, kr_count, ban_count, ring_pairs)
# Bannimantap count rises 3 -> 4 -> 5 year over year (the "discoverable pattern" C3
# queries against); ring FIRs are a subset of that year's Bannimantap count, 2 per
# year, each pair drawn from the 4 ring members so co-accused edges span all 6
# unordered pairs at least once across the 3 years.
THREAD_C_YEARS = [
    ("Y-3", 1005, 5, 3, [("ring1", "ring2"), ("ring3", "ring4")]),
    ("Y-2", 640, 5, 4, [("ring1", "ring3"), ("ring2", "ring4")]),
    ("Y-1", 285, 5, 5, [("ring1", "ring4"), ("ring2", "ring3")]),
]

_C_FIRST_NAMES_M = [
    "Manjunath", "Ramesh", "Suresh", "Naveen", "Ganesh", "Prakash", "Vinay",
    "Raghavendra", "Shivakumar", "Nataraj", "Puttaswamy", "Chandru", "Somashekar",
    "Devaraj", "Mahesh", "Yathish", "Krishnappa", "Basavaraj", "Girish", "Dinesh",
]
_C_FIRST_NAMES_F = [
    "Lakshmi", "Vasanthi", "Anitha", "Roopa", "Sowmya", "Deepa", "Kavya",
]
_C_LAST_NAMES = ["Gowda", "B", "K", "R", "N", "S", "T", "M", "HS", "Rao", "Naik", "Reddy", "Setty"]


def _thread_c_victim_names(n: int) -> list[str]:
    names: list[str] = []
    for i in range(n):
        if i % 4 == 3 and _C_FIRST_NAMES_F:
            first = _C_FIRST_NAMES_F[(i // 4) % len(_C_FIRST_NAMES_F)]
        else:
            first = _C_FIRST_NAMES_M[i % len(_C_FIRST_NAMES_M)]
        last = _C_LAST_NAMES[i % len(_C_LAST_NAMES)]
        names.append(f"{first} {last}")
    return names


def thread_c_localities() -> dict[str, str]:
    localities = [
        ("K.R. Circle", "MYS", "KA-MYS-007", THREAD_C_KR_CIRCLE_CENTER),
        ("Bannimantap", "MYS", "KA-MYS-001", THREAD_C_BANNIMANTAP_CENTER),
    ]
    ids: dict[str, str] = {}
    with connect() as conn:
        with conn.cursor() as cur:
            for name, district_id, station_id, (lat, lon) in localities:
                locality_id = new_uuid()
                cur.execute(
                    """
                    INSERT INTO localities
                        (locality_id, locality_name, locality_type, district_id,
                         primary_station_id, centroid, source)
                    VALUES (%s, %s, 'Area', %s, %s,
                            ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, 'Synthetic')
                    """,
                    (locality_id, name, district_id, station_id, lon, lat),
                )
                ids[name] = locality_id
        conn.commit()
    print(f"Thread C: inserted {len(ids)} localities (K.R. Circle, Bannimantap)")
    return ids


def thread_c_persons() -> dict[str, str]:
    total_firs = sum(kr + ban for _, _, kr, ban, _ in THREAD_C_YEARS)
    people: list[tuple[str, str, str]] = [
        ("ring1", "Puttaraju M", "MYS"),
        ("ring2", "Chandregowda K", "MYS"),
        ("ring3", "Nataraj B", "MYS"),
        ("ring4", "Somashekar R", "MYS"),
        ("casual1", "Manjunath Gowda", "MYS"),
        ("casual2", "Raghavendra Setty", "MYS"),
        ("casual3", "Vinay Kumar T", "MYS"),
        ("casual4", "Shivakumar B", "MYS"),
        ("casual5", "Prakash Naik", "MYS"),
        ("pancha1", "Basavaraju N", "MYS"),
        ("pancha2", "Jayamma", "MYS"),
    ]
    victim_names = _thread_c_victim_names(total_firs)
    for i, name in enumerate(victim_names, start=1):
        people.append((f"cvictim{i}", name, "MYS"))

    ids: dict[str, str] = {}
    with connect() as conn:
        with conn.cursor() as cur:
            for key, name, district_id in people:
                person_id = new_uuid()
                ids[key] = person_id
                cur.execute(
                    "INSERT INTO persons (person_id, full_name, gender, district_id) VALUES (%s, %s, 'Male', %s)",
                    (person_id, name, district_id),
                )
        conn.commit()
    print(f"Thread C: inserted {len(ids)} persons (4 ring + 5 casual accused + 2 panchas + {total_firs} victims)")
    return ids


def thread_c_gang(person_ids: dict[str, str]) -> str:
    gang_id = new_uuid()
    member_keys = ["ring1", "ring2", "ring3", "ring4"]
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO gangs
                    (gang_id, gang_name, primary_crime_type, operating_district,
                     is_active, formation_approx_year, known_strength, notes)
                VALUES (%s, %s, 'THEFT-PICKPOCKET', 'MYS', TRUE, %s, %s, %s)
                """,
                (
                    gang_id, "Bannimantap Pickpocket Ring", DEMO_DATE.year - 3, len(member_keys),
                    "Crowd-press pickpocketing crew active during Mysuru Dasara at the Bannimantap "
                    "exhibition grounds, operating in shifting sub-pairs to avoid detection.",
                ),
            )
            roles = ["Leader", "Member", "Member", "Member"]
            for key, role in zip(member_keys, roles):
                cur.execute(
                    """
                    INSERT INTO gang_memberships
                        (membership_id, gang_id, person_id, role_in_gang, joined_approx_date, is_active)
                    VALUES (%s, %s, %s, %s, %s, TRUE)
                    """,
                    (new_uuid(), gang_id, person_ids[key], role, DEMO_DATE - timedelta(days=365 * 3)),
                )
        conn.commit()
    print(f"Thread C: gang '{gang_id}' (Bannimantap Pickpocket Ring) with {len(member_keys)} members")
    return gang_id


def thread_c_events(locality_ids: dict[str, str]) -> dict[str, str]:
    """3 past Mysuru Dasara Procession windows + 1 upcoming edition (DEMO_DATE
    + 21 days per SEED_RUNBOOK.md §7.4 — demo-date-relative, not the real
    lunar-calendar Dasara date). historical_incident_count mirrors the
    kr_count+ban_count planned for that year in THREAD_C_YEARS.
    """
    route_wkt = (
        "LINESTRING(76.6551 12.3052, 76.6553 12.3072, 76.6450 12.2990, 76.6355 12.2919)"
    )
    ids: dict[str, str] = {}
    with connect() as conn:
        with conn.cursor() as cur:
            for year_label, days_before, kr_count, ban_count, _ in THREAD_C_YEARS:
                event_id = new_uuid()
                start = DEMO_DATE - timedelta(days=days_before)
                notes = generate_narrative(
                    "events_calendar", event_id, "notes",
                    "Write a 2-sentence bandobast planning note in English for the Mysuru Dasara "
                    "Procession, covering crowd-control staffing along Sayyaji Rao Road through K.R. "
                    "Circle to Bannimantap, and known pickpocketing/chain-snatching risk in the crowd.",
                    temperature=0.6, force_kn=False,
                ).text_en
                cur.execute(
                    """
                    INSERT INTO events_calendar
                        (event_id, event_name, event_type, district_id, station_id,
                         event_date_start, event_date_end, expected_footfall, historical_incident_count,
                         notes, latitude, longitude, location_precision, geocode_source, geocode_confidence,
                         venue_locality_id, route_geom)
                    VALUES (%s, %s, 'Festival', 'MYS', 'KA-MYS-001', %s, %s, 400000, %s, %s, %s, %s,
                            'exact', 'gazetteer', 0.9, %s,
                            ST_SetSRID(ST_GeomFromText(%s), 4326)::geography)
                    """,
                    (
                        event_id, "Mysuru Dasara Procession", start, start + timedelta(days=9),
                        kr_count + ban_count, notes,
                        THREAD_C_BANNIMANTAP_CENTER[0], THREAD_C_BANNIMANTAP_CENTER[1],
                        locality_ids["Bannimantap"], route_wkt,
                    ),
                )
                ids[year_label] = event_id

            upcoming_id = new_uuid()
            upcoming_start = DEMO_DATE + timedelta(days=21)
            upcoming_notes = generate_narrative(
                "events_calendar", upcoming_id, "notes",
                "Write a 2-sentence bandobast planning note in English for the upcoming Mysuru Dasara "
                "Procession, referencing the rising pickpocketing trend at Bannimantap in recent years "
                "and recommending additional plainclothes coverage there.",
                temperature=0.6, force_kn=False,
            ).text_en
            cur.execute(
                """
                INSERT INTO events_calendar
                    (event_id, event_name, event_type, district_id, station_id,
                     event_date_start, event_date_end, expected_footfall, notes,
                     latitude, longitude, location_precision, geocode_source, geocode_confidence,
                     venue_locality_id, route_geom)
                VALUES (%s, %s, 'Festival', 'MYS', 'KA-MYS-001', %s, %s, 400000, %s, %s, %s,
                        'exact', 'gazetteer', 0.9, %s,
                        ST_SetSRID(ST_GeomFromText(%s), 4326)::geography)
                """,
                (
                    upcoming_id, "Mysuru Dasara Procession", upcoming_start, upcoming_start + timedelta(days=9),
                    upcoming_notes, THREAD_C_BANNIMANTAP_CENTER[0], THREAD_C_BANNIMANTAP_CENTER[1],
                    locality_ids["Bannimantap"], route_wkt,
                ),
            )
            ids["upcoming"] = upcoming_id
        conn.commit()
    print(f"Thread C: inserted {len(ids)} events_calendar rows (3 past Dasara + 1 upcoming)")
    return ids


def thread_c_firs(person_ids: dict[str, str], locality_ids: dict[str, str]) -> dict:
    named_localities = {
        "K.R. Circle": (*THREAD_C_KR_CIRCLE_CENTER, locality_ids["K.R. Circle"]),
        "Bannimantap": (*THREAD_C_BANNIMANTAP_CENTER, locality_ids["Bannimantap"]),
    }
    io_pool = _pick_io_pool()
    casual_keys = ["casual1", "casual2", "casual3", "casual4", "casual5"]
    victim_counter = 0
    ring_fir_ids: list[str] = []
    ring_pair_first_fir: dict[tuple[str, str], str] = {}
    representative_fir_id: str | None = None
    serial = 0

    with connect() as conn:
        with conn.cursor() as cur:
            kr_station_name, kr_station_lat, kr_station_lon = _fetch_station(cur, "KA-MYS-007")
            ban_station_name, ban_station_lat, ban_station_lon = _fetch_station(cur, "KA-MYS-001")

            for year_idx, (year_label, days_before, kr_count, ban_count, ring_pairs) in enumerate(THREAD_C_YEARS):
                window_start = DEMO_DATE - timedelta(days=days_before)
                n_ring = len(ring_pairs)
                n_ban_casual = ban_count - n_ring

                # --- K.R. Circle: all non-ring, mixed pickpocketing/chain-snatching ---
                for i in range(kr_count):
                    serial += 1
                    victim_counter += 1
                    fir_id = f"KA-MYS-{600 + serial:03d}-{DEMO_DATE.year}-{6000 + serial:04d}"
                    crime_type_id = "THEFT-PICKPOCKET" if i % 2 == 0 else "SNATCHING-CHAIN"
                    mo_code_id = "MO-ROB-004" if crime_type_id == "SNATCHING-CHAIN" else None
                    day_offset = deterministic_int(f"{fir_id}:day", 0, 8)
                    hour = deterministic_int(f"{fir_id}:hour", 17, 20)
                    incident_dt = window_start + timedelta(days=day_offset, hours=hour)
                    registration_date = incident_dt + timedelta(hours=deterministic_int(f"{fir_id}:reg_offset", 1, 6))
                    lat, lon = jitter_point(*THREAD_C_KR_CIRCLE_CENTER, 100)
                    accused_key = casual_keys[serial % len(casual_keys)]
                    _thread_c_insert_fir(
                        cur, fir_id=fir_id, station_id="KA-MYS-007", station_name=kr_station_name,
                        station_lat=kr_station_lat, station_lon=kr_station_lon,
                        lat=lat, lon=lon, locality_name="K.R. Circle",
                        locality_id=locality_ids["K.R. Circle"], named_localities=named_localities,
                        crime_type_id=crime_type_id, mo_code_id=mo_code_id,
                        registration_date=registration_date, incident_dt=incident_dt,
                        accused_keys=[accused_key], victim_key=f"cvictim{victim_counter}",
                        person_ids=person_ids, io_pool=io_pool, fully_dressed=False,
                    )

                # --- Bannimantap: n_ban_casual non-ring + ring FIRs ---
                for i in range(n_ban_casual):
                    serial += 1
                    victim_counter += 1
                    fir_id = f"KA-MYS-{600 + serial:03d}-{DEMO_DATE.year}-{6000 + serial:04d}"
                    crime_type_id = "THEFT-PICKPOCKET" if i % 2 == 0 else "SNATCHING-CHAIN"
                    mo_code_id = "MO-ROB-004" if crime_type_id == "SNATCHING-CHAIN" else None
                    day_offset = deterministic_int(f"{fir_id}:day", 0, 8)
                    hour = deterministic_int(f"{fir_id}:hour", 17, 20)
                    incident_dt = window_start + timedelta(days=day_offset, hours=hour)
                    registration_date = incident_dt + timedelta(hours=deterministic_int(f"{fir_id}:reg_offset", 1, 6))
                    lat, lon = jitter_point(*THREAD_C_BANNIMANTAP_CENTER, 100)
                    accused_key = casual_keys[serial % len(casual_keys)]
                    _thread_c_insert_fir(
                        cur, fir_id=fir_id, station_id="KA-MYS-001", station_name=ban_station_name,
                        station_lat=ban_station_lat, station_lon=ban_station_lon,
                        lat=lat, lon=lon, locality_name="Bannimantap",
                        locality_id=locality_ids["Bannimantap"], named_localities=named_localities,
                        crime_type_id=crime_type_id, mo_code_id=mo_code_id,
                        registration_date=registration_date, incident_dt=incident_dt,
                        accused_keys=[accused_key], victim_key=f"cvictim{victim_counter}",
                        person_ids=person_ids, io_pool=io_pool, fully_dressed=False,
                    )

                for ring_idx, pair in enumerate(ring_pairs):
                    serial += 1
                    victim_counter += 1
                    fir_id = f"KA-MYS-{600 + serial:03d}-{DEMO_DATE.year}-{6000 + serial:04d}"
                    day_offset = deterministic_int(f"{fir_id}:day", 0, 8)
                    hour = deterministic_int(f"{fir_id}:hour", 17, 20)
                    incident_dt = window_start + timedelta(days=day_offset, hours=hour)
                    registration_date = incident_dt + timedelta(hours=deterministic_int(f"{fir_id}:reg_offset", 1, 6))
                    lat, lon = jitter_point(*THREAD_C_BANNIMANTAP_CENTER, 100)
                    # Most recent past Dasara (Y-1)'s first ring FIR is the
                    # representative "fully dressed" case-card FIR.
                    is_representative = year_label == "Y-1" and ring_idx == 0
                    _thread_c_insert_fir(
                        cur, fir_id=fir_id, station_id="KA-MYS-001", station_name=ban_station_name,
                        station_lat=ban_station_lat, station_lon=ban_station_lon,
                        lat=lat, lon=lon, locality_name="Bannimantap",
                        locality_id=locality_ids["Bannimantap"], named_localities=named_localities,
                        crime_type_id="THEFT-PICKPOCKET", mo_code_id="MO-THEFT-021",
                        registration_date=registration_date, incident_dt=incident_dt,
                        accused_keys=list(pair), victim_key=f"cvictim{victim_counter}",
                        person_ids=person_ids, io_pool=io_pool, fully_dressed=is_representative,
                    )
                    ring_fir_ids.append(fir_id)
                    pair_key = tuple(sorted(pair))
                    ring_pair_first_fir.setdefault(pair_key, fir_id)
                    if is_representative:
                        representative_fir_id = fir_id

        conn.commit()

    print(f"Thread C: inserted {serial} FIRs ({len(ring_fir_ids)} ring FIRs across 3 years)")
    return {
        "ring_fir_ids": ring_fir_ids,
        "ring_pair_first_fir": ring_pair_first_fir,
        "representative_fir_id": representative_fir_id,
    }


def _thread_c_insert_fir(
    cur, *, fir_id, station_id, station_name, station_lat, station_lon, lat, lon,
    locality_name, locality_id, named_localities, crime_type_id, mo_code_id,
    registration_date, incident_dt, accused_keys, victim_key, person_ids, io_pool, fully_dressed,
):
    mo_row = _fetch_mo_row(cur, mo_code_id)
    resolved_locality_id, resolved_locality_name = resolve_locality(cur, lat, lon, named_localities)
    cur.execute("SELECT full_name FROM persons WHERE person_id = %s", (person_ids[victim_key],))
    victim_name = cur.fetchone()[0]
    bns_section = CRIME_TYPE_BNS[crime_type_id]
    cs_days = CHARGESHEET_DAYS[bns_section]
    io_officer_id = RNG.choice(io_pool.get("MYS", ["KSP-23417"]))

    facts = build_fact_sheet(
        fir_id=fir_id, crime_type_id=crime_type_id, station_name=station_name,
        district_name="Mysuru", locality_name=resolved_locality_name, victim_name=victim_name,
        incident_hour=incident_dt.hour, mo_row=mo_row, num_accused=len(accused_keys),
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

    distance_km, compass = bearing_distance(station_lat, station_lon, lat, lon)
    direction_distance = format_direction_distance(distance_km, compass)
    information_type = deterministic_weighted_choice(f"{fir_id}:information_type", [("Oral", 0.65), ("Written", 0.35)])
    info_received_ts = registration_date - timedelta(minutes=deterministic_int(f"{fir_id}:info_offset", 5, 90))
    gd_entry_time = info_received_ts + timedelta(minutes=deterministic_int(f"{fir_id}:gd_offset", 2, 20))
    incident_location = f"{resolved_locality_name}, {station_name.replace(' PS', '')} jurisdiction"
    chargesheet_deadline = registration_date + timedelta(days=cs_days)

    cur.execute(
        """
        INSERT INTO firs
            (fir_id, station_id, district_id, fir_number, fir_year, registration_date,
             incident_date, incident_location, crime_type_id, primary_bns_section,
             is_pre_bns, complaint_text, fir_narrative, mo_code_id, mo_description_free,
             complainant_id, io_officer_id, investigation_status, chargesheet_deadline,
             fir_type, is_zero_fir, latitude, longitude, location_precision,
             geocode_source, geocode_confidence, incident_locality_id,
             info_received_ts, gd_entry_number, gd_entry_time, information_type,
             beat_number, direction_distance_from_ps)
        VALUES (%s, %s, 'MYS', %s, %s, %s, %s, %s, %s, %s, FALSE, %s, %s, %s, %s,
                %s, %s, 'Chargesheet_Filed', %s, 'Original', FALSE, %s, %s, 'locality',
                'gazetteer', 0.75, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            fir_id, station_id, fir_id.split("-")[-1], DEMO_DATE.year, registration_date,
            incident_dt, incident_location, crime_type_id, bns_section,
            complaint, fir_narrative, mo_code_id, mo_description_free,
            person_ids[victim_key], io_officer_id, chargesheet_deadline,
            lat, lon, resolved_locality_id,
            info_received_ts, str(deterministic_int(f"{fir_id}:gd_number", 1, 999)), gd_entry_time,
            information_type, f"Beat-{deterministic_int(f'{fir_id}:beat', 1, 6)}", direction_distance,
        ),
    )
    for i, key in enumerate(accused_keys, start=1):
        cur.execute(
            """
            INSERT INTO fir_accused (fir_accused_id, fir_id, person_id, role, accused_serial, is_arrested)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (new_uuid(), fir_id, person_ids[key], "Main_Accused" if i == 1 else "Co_Accused", i, fully_dressed),
        )

    vs_prompt, vs_temp = build_victim_statement_prompt(facts)
    victim_statement = generate_narrative(
        "fir_victims", fir_id, "victim_statement", vs_prompt, temperature=vs_temp, force_kn=False
    ).text_en
    cur.execute(
        "INSERT INTO fir_victims (fir_victim_id, fir_id, person_id, victim_serial, victim_statement) "
        "VALUES (%s, %s, %s, 1, %s)",
        (new_uuid(), fir_id, person_ids[victim_key], victim_statement),
    )

    n_diary = 4 if fully_dressed else deterministic_int(f"{fir_id}:n_diary", 1, 3)
    for entry_num in range(1, n_diary + 1):
        diary_prompt, diary_temp, action_taken = build_diary_entry_prompt(facts, entry_num)
        text = generate_narrative(
            "case_diary_entries", f"{fir_id}:{entry_num}", "entry_text", diary_prompt,
            temperature=diary_temp, force_kn=False,
        ).text_en
        cur.execute(
            """
            INSERT INTO case_diary_entries (entry_id, fir_id, officer_id, entry_date, entry_number, entry_text, action_taken)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (new_uuid(), fir_id, io_officer_id, registration_date + timedelta(days=entry_num), entry_num, text, action_taken),
        )

    chargesheet_id = new_uuid()
    summary = f"Chargesheet filed under {bns_section} against {len(accused_keys)} accused for a {crime_type_id.replace('-', ' ').lower()} case near {resolved_locality_name}."
    cur.execute(
        """
        INSERT INTO chargesheets
            (chargesheet_id, fir_id, filing_officer_id, filing_date, court_name,
             sections_applied, num_accused, num_witnesses, summary_text, filing_status)
        VALUES (%s, %s, %s, %s, 'JMFC Mysuru', %s, %s, 0, %s, 'Filed')
        """,
        (chargesheet_id, fir_id, io_officer_id, registration_date + timedelta(days=cs_days - 5),
         [bns_section], len(accused_keys), summary),
    )
    despatch_ts = registration_date + timedelta(days=cs_days - 5 + deterministic_int(f"{fir_id}:despatch", 2, 5))
    cur.execute("UPDATE firs SET despatch_to_court_ts = %s WHERE fir_id = %s", (despatch_ts, fir_id))


def thread_c_known_associates(person_ids: dict[str, str], build_result: dict) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            for pair_key, first_fir_id in build_result["ring_pair_first_fir"].items():
                a_key, b_key = pair_key
                pid_a, pid_b = person_ids[a_key], person_ids[b_key]
                if pid_a > pid_b:
                    pid_a, pid_b = pid_b, pid_a
                cur.execute(
                    """
                    INSERT INTO known_associates
                        (association_id, person_id_a, person_id_b, association_type, first_seen_fir_id, confidence)
                    VALUES (%s, %s, %s, 'Co_Accused', %s, 'Confirmed')
                    """,
                    (new_uuid(), pid_a, pid_b, first_fir_id),
                )
        conn.commit()
    print(f"Thread C: {len(build_result['ring_pair_first_fir'])} known_associates Confirmed edges (ring co-accused)")


def thread_c_seizure(person_ids: dict[str, str], build_result: dict, locality_ids: dict[str, str]) -> None:
    """Seizure of recovered phones for the representative fully-dressed
    ring FIR (Y-1's first ring FIR) — 2 stolen_property phone rows sharing
    one seizure/mahazar.
    """
    fir_id = build_result["representative_fir_id"]
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT registration_date FROM firs WHERE fir_id = %s", (fir_id,))
            reg_date = cur.fetchone()[0]
            seizure_date = reg_date + timedelta(hours=deterministic_int(f"{fir_id}:seizure_offset", 3, 20))
            lat, lon = jitter_point(*THREAD_C_BANNIMANTAP_CENTER, 100)

            seizure_id = new_uuid()
            property_ids = []
            for i in range(2):
                property_id = new_uuid()
                property_ids.append(property_id)
                desc = generate_narrative(
                    "stolen_property", property_id, "description",
                    "Write a 1-sentence description in English of a mobile phone recovered from a "
                    "pickpocketing suspect during a Dasara-crowd crackdown, including a plausible "
                    "IMEI-style serial number format.",
                    temperature=0.6, force_kn=False,
                ).text_en
                # recovery_seizure_id is a real FK to seizures, which doesn't
                # exist yet at this point in the function (inserted below) —
                # insert without recovery fields, UPDATE after the seizures
                # row commits, same ordering as thread_b_recovery().
                cur.execute(
                    """
                    INSERT INTO stolen_property
                        (property_id, fir_id, property_type, description, estimated_value_inr, serial_number)
                    VALUES (%s, %s, 'Electronics', %s, %s, %s)
                    """,
                    (property_id, fir_id, desc, 12000 + i * 3000,
                     f"IMEI-{deterministic_int(fir_id + f':imei{i}', 10**14, 10**15 - 1)}"),
                )

            items_desc = generate_narrative(
                "seizures", seizure_id, "items_description",
                "Write a 2-sentence mahazar (seizure panchnama) items description in English for the "
                "recovery of two mobile phones from a pickpocketing suspect apprehended in the Dasara "
                "procession crowd, in the presence of two independent panch witnesses.",
                temperature=0.6, force_kn=False,
            ).text_en
            cur.execute(
                """
                INSERT INTO seizures
                    (seizure_id, fir_id, mahazar_number, seizure_type, seizure_date, seizure_location,
                     locality_id, latitude, longitude, location_precision, geocode_source, geocode_confidence,
                     pancha_1_person_id, pancha_2_person_id, items_description,
                     linked_property_id, muddemal_number, custody_status)
                VALUES (%s, %s, %s, 'Property', %s, %s, %s, %s, %s, 'exact', 'gps', %s, %s, %s, %s, %s, %s, 'In_Custody')
                """,
                (seizure_id, fir_id, f"MZR-MYS-{DEMO_DATE.year}-0091", seizure_date, "Bannimantap, Mysuru",
                 locality_ids["Bannimantap"], lat, lon, round(RNG.uniform(0.95, 0.999), 3),
                 person_ids["pancha1"], person_ids["pancha2"], items_desc,
                 property_ids[0], f"MDM-{DEMO_DATE.year}-0067"),
            )
            for property_id in property_ids:
                cur.execute(
                    "UPDATE stolen_property SET is_recovered = TRUE, recovery_date = %s, "
                    "recovery_location = %s, recovery_seizure_id = %s WHERE property_id = %s",
                    (seizure_date, "Bannimantap, Mysuru", seizure_id, property_id),
                )
        conn.commit()
    print("Thread C: seizure of 2 recovered phones for the representative ring FIR")


if __name__ == "__main__":
    if "--thread-a-setup" in sys.argv or "--all" in sys.argv:
        loc_ids = thread_a_localities()
        person_ids = thread_a_persons()
        gang_id = thread_a_gang(person_ids)
        thread_a_phones(person_ids)
        thread_a_known_associates(person_ids)
        thread_a_history_sheet(person_ids)
        print("Thread A setup (localities/persons/gang/phones/associates/history) complete.")

    if "--thread-a-firs" in sys.argv or "--all" in sys.argv:
        person_ids = fetch_thread_a_person_ids()
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT gang_id FROM gangs WHERE gang_name = 'Mysuru Chain Gang'")
                gang_id = cur.fetchone()[0]
        thread_a_firs(person_ids, gang_id)

    if "--thread-b" in sys.argv or "--all" in sys.argv:
        thread_b_localities()
        b_person_ids = thread_b_persons()
        # FIRs before escalation: ncr_petitions.escalated_fir_id is a real FK
        # (plus a CHECK requiring it non-NULL when status='Escalated_To_FIR'),
        # so Savitha's FIR must exist before the Petition row can reference it.
        b_result = thread_b_firs(b_person_ids)
        thread_b_escalation(b_person_ids)
        thread_b_recovery(b_person_ids, b_result)
        thread_b_receiver_network(b_person_ids, b_result)
        thread_b_missing_person(b_person_ids)
        print("Thread B complete.")

    if "--thread-c" in sys.argv or "--all" in sys.argv:
        c_locality_ids = thread_c_localities()
        c_person_ids = thread_c_persons()
        thread_c_gang(c_person_ids)
        thread_c_events(c_locality_ids)
        c_result = thread_c_firs(c_person_ids, c_locality_ids)
        thread_c_known_associates(c_person_ids, c_result)
        thread_c_seizure(c_person_ids, c_result, c_locality_ids)
        print("Thread C complete.")
