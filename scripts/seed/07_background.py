#!/usr/bin/env python3
"""Stage 5.2 — background corpus, filling to DATA_ARCHITECTURE_SCHEMA_V2.md
§7.1 target volumes after the golden threads (SEED_RUNBOOK.md §6.2).

Every stage is count-based and resumable: each function checks how many
rows already exist against its §7.1 target and only generates the delta,
so a crash/interrupt-and-rerun never duplicates work already committed.

Constraints enforced throughout (§6.2):
  - Active units only (10 districts) — zero case rows elsewhere.
  - Never create a reserved-registry entity (§7.5) — none of the random
    name/plate/ID generation below can coincidentally produce one (checked
    once at the end via 05_validate.py, and the generators here don't draw
    from anything close to the reserved literals).
  - No collision with golden-thread entities (names, FIR IDs, plates,
    gang names) — new persons/vehicles/gangs are drawn from disjoint pools
    and FIR IDs use a disjoint numbering scheme (KA-[DIST]-9[NNN]-...).
"""

from __future__ import annotations

import csv
import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from db import connect, get_demo_date
from geo_helpers import bearing_distance, deterministic_int, format_direction_distance
from narrative_facts import (
    build_complaint_prompt,
    build_diary_entry_prompt,
    build_fact_sheet,
    build_fir_narrative_prompt,
    build_mo_description_free_prompt,
    build_victim_statement_prompt,
)
from narrative_gen import KannadaTranslator, generate_narrative

RNG = random.Random(20260716)
DEMO_DATE = datetime.combine(get_demo_date(), datetime.min.time())
CRIME_MIX_PATH = Path(__file__).resolve().parents[2] / "db" / "reference" / "crime_mix.csv"

ACTIVE_DISTRICTS = ["BLR", "MYS", "MDY", "HBL", "MNG", "BGV", "TMK", "KDG", "CKM", "RCH"]
# Rough relative FIR-volume weight per district (urban units get more).
DISTRICT_FIR_WEIGHT = {
    "BLR": 30, "MYS": 16, "HBL": 10, "MNG": 8,
    "MDY": 8, "BGV": 7, "TMK": 7, "KDG": 5, "CKM": 5, "RCH": 4,
}

TARGETS = {
    "persons": 500, "firs": 800, "ncr_petitions": 300, "case_diary_entries": 2000,
    "seizures": 250, "missing_persons": 40, "chargesheets": 200, "court_disposals": 80,
    "gangs": 5, "known_associates": 300, "stolen_property": 150, "vehicles": 80,
    "history_sheeted_persons": 150,
}

FIRST_NAMES_M = [
    "Manjunath", "Ramesh", "Suresh", "Naveen", "Ganesh", "Prakash", "Vinay", "Raghavendra",
    "Shivakumar", "Nataraj", "Puttaswamy", "Chandru", "Somashekar", "Devaraj", "Mahesh",
    "Yathish", "Krishnappa", "Basavaraj", "Girish", "Dinesh", "Anand", "Kiran", "Vijay",
    "Santosh", "Harish", "Mohan", "Rajesh", "Srinivas", "Ravindra", "Nagesh", "Umesh",
    "Prasanna", "Lokesh", "Vasanth", "Channabasappa", "Siddappa", "Halappa", "Mallikarjun",
    "Veeresh", "Iranna", "Shankar", "Gopal", "Ashok", "Ranganath", "Byrappa", "Puttaraju",
    "Nanjundaiah", "Kumar", "Sathish", "Manohar",
]
FIRST_NAMES_F = [
    "Lakshmi", "Vasanthi", "Anitha", "Roopa", "Sowmya", "Deepa", "Kavya", "Jyothi",
    "Sunanda", "Bhagya", "Padma", "Savitri", "Radha", "Shobha", "Geetha", "Nirmala",
    "Manjula", "Rekha", "Suma", "Vidya", "Pushpa", "Kamala", "Yashoda", "Renuka",
    "Chandrika", "Prabha", "Latha", "Vani", "Meena", "Girija",
]
LAST_NAMES = [
    "Gowda", "B", "K", "R", "N", "S", "T", "M", "HS", "Rao", "Naik", "Reddy", "Setty",
    "Patil", "Kumar", "Shetty", "Hegde", "Achar", "Poojary", "Naidu",
]

_STRAY_ALIAS_SUFFIXES = ["Anna", "Bhai", "Master"]


def load_crime_mix() -> dict[str, list[tuple[str, float]]]:
    mix: dict[str, list[tuple[str, float]]] = {}
    with open(CRIME_MIX_PATH) as f:
        # Strip leading '#'-comment lines before DictReader sees the file —
        # otherwise it treats the first comment line as the header row.
        lines = [line for line in f if not line.lstrip().startswith("#")]
    for row in csv.DictReader(lines):
        mix.setdefault(row["district_id"], []).append((row["crime_type_id"], float(row["weight"])))
    return mix


def _weighted_choice(pairs: list[tuple[str, float]]):
    items, weights = zip(*pairs)
    return RNG.choices(items, weights=weights, k=1)[0]


def _random_name(existing: set[str]) -> tuple[str, str]:
    """Returns (full_name, gender)."""
    for _ in range(200):
        gender = "Female" if RNG.random() < 0.35 else "Male"
        first = RNG.choice(FIRST_NAMES_F if gender == "Female" else FIRST_NAMES_M)
        last = RNG.choice(LAST_NAMES)
        name = f"{first} {last}"
        if name not in existing:
            existing.add(name)
            return name, gender
    # Pool exhausted (shouldn't happen at our scale) — add a numeric suffix.
    name = f"{first} {last} {RNG.randint(2, 99)}"
    existing.add(name)
    return name, gender


def _maybe_aliases(full_name: str) -> list[str] | None:
    if RNG.random() >= 0.20:
        return None
    parts = full_name.split()
    variants = []
    if len(parts) >= 2:
        variants.append(parts[0])  # first name alone
    variants.append(f"{parts[0]}{RNG.choice(['u', 'a', ''])}")  # spelling variant
    if RNG.random() < 0.5:
        variants.append(f"{parts[0]} {RNG.choice(_STRAY_ALIAS_SUFFIXES)}")
    return variants[:3]


def jitter_point(lat: float, lon: float, max_meters: float) -> tuple[float, float]:
    import math

    r = max_meters * math.sqrt(RNG.random())
    theta = RNG.random() * 2 * math.pi
    dlat = (r * math.cos(theta)) / 111_000
    dlon = (r * math.sin(theta)) / (111_000 * math.cos(math.radians(lat)))
    return round(lat + dlat, 6), round(lon + dlon, 6)


def new_uuid() -> str:
    return str(uuid.uuid4())


# ============================================================
# Stage: persons
# ============================================================

def background_persons() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM persons")
            current = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM persons WHERE is_history_sheeted = TRUE")
            current_hs = cur.fetchone()[0]
            need = TARGETS["persons"] - current
            if need <= 0:
                print(f"background_persons: already at {current}/{TARGETS['persons']}, skipping")
                return
            need_hs = max(0, TARGETS["history_sheeted_persons"] - current_hs)

            cur.execute("SELECT full_name FROM persons")
            existing_names = {r[0] for r in cur.fetchall()}

            cur.execute(
                "SELECT locality_id, district_id, ST_Y(centroid::geometry), ST_X(centroid::geometry) FROM localities WHERE district_id = ANY(%s)",
                (ACTIVE_DISTRICTS,),
            )
            localities_by_district: dict[str, list[tuple[str, float, float]]] = {}
            for locality_id, district_id, lat, lon in cur.fetchall():
                if lat is None or lon is None:
                    continue
                localities_by_district.setdefault(district_id, []).append((locality_id, float(lat), float(lon)))

            cur.execute("SELECT station_id, district_id, latitude, longitude FROM police_stations WHERE district_id = ANY(%s)", (ACTIVE_DISTRICTS,))
            stations_by_district: dict[str, list[tuple[str, float, float]]] = {}
            for station_id, district_id, lat, lon in cur.fetchall():
                stations_by_district.setdefault(district_id, []).append((station_id, float(lat), float(lon)))

            inserted = 0
            for i in range(need):
                district_id = _weighted_choice([(d, DISTRICT_FIR_WEIGHT[d]) for d in ACTIVE_DISTRICTS])
                full_name, gender = _random_name(existing_names)
                aliases = _maybe_aliases(full_name)
                is_hs = need_hs > 0 and RNG.random() < (need_hs / max(need - i, 1))
                if is_hs:
                    need_hs -= 1

                locality_id = None
                if district_id in localities_by_district and localities_by_district[district_id]:
                    locality_id, base_lat, base_lon = RNG.choice(localities_by_district[district_id])
                elif district_id in stations_by_district:
                    _, base_lat, base_lon = RNG.choice(stations_by_district[district_id])
                else:
                    continue
                lat, lon = jitter_point(base_lat, base_lon, 800)

                cur.execute(
                    """
                    INSERT INTO persons
                        (person_id, full_name, aliases, gender, district_id, is_history_sheeted,
                         home_locality_id, latitude, longitude, location_precision, geocode_source, geocode_confidence)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'locality', 'generated', 1.000)
                    """,
                    (new_uuid(), full_name, aliases, gender, district_id, is_hs, locality_id, lat, lon),
                )
                inserted += 1
                if inserted % 100 == 0:
                    conn.commit()
                    print(f"  persons: {inserted}/{need}", flush=True)
        conn.commit()
    print(f"background_persons: inserted {inserted} persons")


# ============================================================
# Stage: gangs
# ============================================================

def background_gangs() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM gangs")
            current = cur.fetchone()[0]
            need = TARGETS["gangs"] - current
            if need <= 0:
                print(f"background_gangs: already at {current}/{TARGETS['gangs']}, skipping")
                return

            cur.execute(
                "SELECT person_id, district_id FROM persons WHERE is_history_sheeted = TRUE "
                "AND person_id NOT IN (SELECT person_id FROM gang_memberships)"
            )
            pool = cur.fetchall()
            RNG.shuffle(pool)

            gang_specs = [
                ("Bengaluru Vehicle Lifters", "THEFT-VEHICLE", "BLR"),
                ("Hubballi Cheating Syndicate", "CHEATING-FRAUD", "HBL"),
                ("Mandya House-Breaking Crew", "HOUSE-BREAKING", "MDY"),
            ]
            created = 0
            for i in range(min(need, len(gang_specs))):
                gang_name, crime_type_id, district_id = gang_specs[i]
                members = [p for p in pool if p[1] == district_id][:5]
                if len(members) < 3:
                    members = pool[:5]
                    pool = pool[5:]
                else:
                    pool = [p for p in pool if p not in members]
                if not members:
                    continue

                gang_id = new_uuid()
                cur.execute(
                    """
                    INSERT INTO gangs (gang_id, gang_name, primary_crime_type, operating_district, is_active, formation_approx_year, known_strength)
                    VALUES (%s, %s, %s, %s, TRUE, %s, %s)
                    """,
                    (gang_id, gang_name, crime_type_id, district_id, DEMO_DATE.year - RNG.randint(1, 6), len(members)),
                )
                for j, (person_id, _) in enumerate(members):
                    cur.execute(
                        """
                        INSERT INTO gang_memberships (membership_id, gang_id, person_id, role_in_gang, joined_approx_date, is_active)
                        VALUES (%s, %s, %s, %s, %s, TRUE)
                        """,
                        (new_uuid(), gang_id, person_id, "Leader" if j == 0 else "Member",
                         DEMO_DATE - timedelta(days=365 * RNG.randint(1, 5))),
                    )
                created += 1
        conn.commit()
    print(f"background_gangs: created {created} gangs")


# ============================================================
# Stage: FIRs (+ vehicles, stolen_property, seizures, chargesheets, disposals, diary entries)
# ============================================================

def _fetch_station(cur, station_id: str) -> tuple[str, float, float]:
    cur.execute("SELECT station_name, latitude, longitude FROM police_stations WHERE station_id = %s", (station_id,))
    name, lat, lon = cur.fetchone()
    return name, float(lat), float(lon)


def background_firs() -> None:
    crime_mix = load_crime_mix()
    translator = KannadaTranslator()

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM firs")
            current = cur.fetchone()[0]
            need = TARGETS["firs"] - current
            if need <= 0:
                print(f"background_firs: already at {current}/{TARGETS['firs']}, skipping")
                return

            cur.execute(
                "SELECT station_id, district_id FROM police_stations WHERE district_id = ANY(%s)", (ACTIVE_DISTRICTS,)
            )
            stations_by_district: dict[str, list[str]] = {}
            for station_id, district_id in cur.fetchall():
                stations_by_district.setdefault(district_id, []).append(station_id)

            cur.execute(
                "SELECT locality_id, district_id, ST_Y(centroid::geometry), ST_X(centroid::geometry), boundary IS NOT NULL FROM localities WHERE district_id = ANY(%s)",
                (ACTIVE_DISTRICTS,),
            )
            localities_by_district: dict[str, list[tuple[str, float, float]]] = {}
            for locality_id, district_id, lat, lon, _has_boundary in cur.fetchall():
                if lat is None or lon is None:
                    continue
                localities_by_district.setdefault(district_id, []).append((locality_id, float(lat), float(lon)))

            cur.execute("SELECT person_id, district_id FROM persons")
            persons_by_district: dict[str, list[str]] = {}
            for person_id, district_id in cur.fetchall():
                persons_by_district.setdefault(district_id, []).append(person_id)

            cur.execute("SELECT person_id, district_id FROM persons WHERE is_history_sheeted = TRUE")
            accused_pool: dict[str, list[str]] = {}
            for person_id, district_id in cur.fetchall():
                accused_pool.setdefault(district_id, []).append(person_id)

            cur.execute("SELECT bns_section, ipc_equivalent, chargesheet_days FROM bns_sections")
            bns_meta = {row[0].replace(" ", "-"): (row[1], row[2]) for row in cur.fetchall()}

            cur.execute("SELECT crime_type_id, primary_bns_section FROM crime_types")
            crime_bns = dict(cur.fetchall())

            cur.execute(
                "SELECT officer_id, district_id FROM officers WHERE role = 'IO' AND district_id = ANY(%s)",
                (ACTIVE_DISTRICTS,),
            )
            io_pool: dict[str, list[str]] = {}
            for officer_id, district_id in cur.fetchall():
                io_pool.setdefault(district_id, []).append(officer_id)

            cur.execute("SELECT registration_number FROM vehicles")
            used_plates = {r[0] for r in cur.fetchall()}

            # Resume-safe: derive the next serial from the highest one already used in this
            # scheme (the trailing 4 digits), not a hardcoded 9000 — a rerun after a partial
            # crash must not reissue fir_ids that already exist.
            cur.execute(r"SELECT fir_id FROM firs WHERE fir_id ~ '-9[0-9]{3}$'")
            existing_serials = [int(r[0][-4:]) for r in cur.fetchall()]
            fir_counter = max(existing_serials, default=9000)
            inserted = 0
            for i in range(need):
                fir_counter += 1
                serial = fir_counter
                district_id = _weighted_choice([(d, DISTRICT_FIR_WEIGHT[d]) for d in ACTIVE_DISTRICTS])
                if district_id not in crime_mix or district_id not in stations_by_district:
                    continue
                crime_type_id = _weighted_choice(crime_mix[district_id])
                station_id = RNG.choice(stations_by_district[district_id])
                station_name, station_lat, station_lon = _fetch_station(cur, station_id)

                days_before = RNG.randint(30, 1800)  # spans back into 2021-2025
                registration_date = DEMO_DATE - timedelta(days=days_before)
                incident_dt = registration_date - timedelta(hours=RNG.randint(1, 30))
                is_pre_bns = incident_dt < datetime(2024, 7, 1)

                # geocode: real locality if the district has one, else station-jitter fallback (covers MNG's gap)
                if district_id in localities_by_district and localities_by_district[district_id]:
                    locality_id, loc_lat, loc_lon = RNG.choice(localities_by_district[district_id])
                    precision = "locality"
                    if not is_pre_bns and RNG.random() < 0.15:
                        precision = "exact"
                    lat, lon = jitter_point(loc_lat, loc_lon, 300 if precision == "exact" else 900)
                    confidence = round(RNG.uniform(0.95, 0.999) if precision == "exact" else RNG.uniform(0.55, 0.90), 3)
                    source = "gps" if precision == "exact" else "gazetteer"
                    cur.execute("SELECT locality_name FROM localities WHERE locality_id = %s", (locality_id,))
                    locality_name = cur.fetchone()[0]
                else:
                    locality_id = None
                    precision, source = "station", "gazetteer"
                    lat, lon = jitter_point(station_lat, station_lon, 1500)
                    confidence = round(RNG.uniform(0.55, 0.75), 3)
                    locality_name = f"{station_name.replace(' PS', '')} jurisdiction"

                # fir_id is VARCHAR(20): "KA-" + 3-char district + "-" + 3 digits + "-" + 4-digit
                # year + "-" + 4 digits = exactly 20 chars. serial is globally unique via
                # fir_counter, so the 4-digit tail alone already guarantees uniqueness.
                fir_id = f"KA-{district_id}-{serial % 1000:03d}-{registration_date.year}-{serial:04d}"

                victims = persons_by_district.get(district_id) or persons_by_district.get("BLR")
                victim_id = RNG.choice(victims)
                cur.execute("SELECT full_name FROM persons WHERE person_id = %s", (victim_id,))
                victim_name = cur.fetchone()[0]

                num_accused = 0 if RNG.random() < 0.35 else RNG.choice([1, 1, 1, 2, 2, 3])
                accused_ids: list[str] = []
                pool = accused_pool.get(district_id) or accused_pool.get("BLR") or []
                if pool and num_accused:
                    accused_ids = RNG.sample(pool, min(num_accused, len(pool)))

                mo_row = None
                mo_code_id = None
                if RNG.random() < 0.55:
                    cur.execute("SELECT mo_code_id, target_type, tool_used, time_pattern, mo_description FROM mo_codes WHERE crime_type_id = %s", (crime_type_id,))
                    mo_candidates = cur.fetchall()
                    if mo_candidates:
                        row = RNG.choice(mo_candidates)
                        mo_code_id = row[0]
                        mo_row = {"target_type": row[1], "tool_used": row[2], "time_pattern": row[3], "mo_description": row[4]}

                bns_section = crime_bns.get(crime_type_id, "BNS-303")
                ipc_equiv, cs_days = bns_meta.get(bns_section, (None, 60))
                cs_days = cs_days or 60
                # primary_bns_section is an FK to bns_sections and must always hold a
                # valid BNS section id, even for is_pre_bns FIRs — the historical IPC
                # citation is free text and belongs in ipc_sections, not this column.
                primary_section = bns_section
                ipc_sections = [ipc_equiv] if (is_pre_bns and ipc_equiv) else None

                district_name_map = {
                    "BLR": "Bengaluru", "MYS": "Mysuru", "MDY": "Mandya", "HBL": "Hubballi",
                    "MNG": "Mangaluru", "BGV": "Belagavi", "TMK": "Tumakuru", "KDG": "Kodagu",
                    "CKM": "Chikkamagaluru", "RCH": "Kalaburagi",
                }
                facts = build_fact_sheet(
                    fir_id=fir_id, crime_type_id=crime_type_id, station_name=station_name,
                    district_name=district_name_map.get(district_id, district_id), locality_name=locality_name,
                    victim_name=victim_name, incident_hour=incident_dt.hour, mo_row=mo_row,
                    num_accused=max(1, len(accused_ids)),
                )
                complaint_prompt, complaint_temp = build_complaint_prompt(facts)
                complaint = generate_narrative("firs", fir_id, "complaint_text", complaint_prompt, translator=translator, temperature=complaint_temp, force_kn=None).text_en
                narrative_prompt, narrative_temp = build_fir_narrative_prompt(facts)
                fir_narrative = generate_narrative("firs", fir_id, "fir_narrative", narrative_prompt, temperature=narrative_temp, force_kn=False).text_en
                mo_free_prompt, mo_free_temp = build_mo_description_free_prompt(facts)
                mo_description_free = generate_narrative("firs", fir_id, "mo_description_free", mo_free_prompt, temperature=mo_free_temp, force_kn=False).text_en

                distance_km, compass = bearing_distance(station_lat, station_lon, lat, lon)
                direction_distance = format_direction_distance(distance_km, compass)
                information_type = RNG.choices(["Oral", "Written"], weights=[0.65, 0.35])[0]
                info_received_ts = registration_date - timedelta(minutes=RNG.randint(5, 90))
                gd_entry_time = info_received_ts + timedelta(minutes=RNG.randint(2, 20))
                incident_location = f"{locality_name}, {station_name.replace(' PS', '')} jurisdiction"

                status_weights = [("Open", 0.30), ("Under_Investigation", 0.35), ("Chargesheet_Filed", 0.30), ("Closed", 0.05)]
                investigation_status = RNG.choices([s for s, _ in status_weights], weights=[w for _, w in status_weights])[0]
                chargesheet_deadline = registration_date + timedelta(days=cs_days)
                io_officer_id = RNG.choice(io_pool.get(district_id, ["KSP-23417"]))

                cur.execute(
                    """
                    INSERT INTO firs
                        (fir_id, station_id, district_id, fir_number, fir_year, registration_date,
                         incident_date, incident_location, crime_type_id, primary_bns_section, ipc_sections,
                         is_pre_bns, complaint_text, fir_narrative, mo_code_id, mo_description_free,
                         complainant_id, io_officer_id, investigation_status, chargesheet_deadline,
                         fir_type, is_zero_fir, latitude, longitude, location_precision,
                         geocode_source, geocode_confidence, incident_locality_id,
                         info_received_ts, gd_entry_number, gd_entry_time, information_type,
                         beat_number, direction_distance_from_ps)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, 'Original', FALSE, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s)
                    """,
                    (
                        fir_id, station_id, district_id, f"{serial:04d}", registration_date.year, registration_date,
                        incident_dt, incident_location, crime_type_id, primary_section, ipc_sections,
                        is_pre_bns, complaint, fir_narrative, mo_code_id, mo_description_free,
                        victim_id, io_officer_id, investigation_status, chargesheet_deadline,
                        lat, lon, precision, source, confidence, locality_id,
                        info_received_ts, str(RNG.randint(1, 999)), gd_entry_time,
                        information_type, f"Beat-{RNG.randint(1, 6)}", direction_distance,
                    ),
                )

                for k, person_id in enumerate(accused_ids, start=1):
                    cur.execute(
                        "INSERT INTO fir_accused (fir_accused_id, fir_id, person_id, role, accused_serial, is_arrested) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        (new_uuid(), fir_id, person_id, "Main_Accused" if k == 1 else "Co_Accused", k, RNG.random() < 0.5),
                    )

                vs_prompt, vs_temp = build_victim_statement_prompt(facts)
                victim_statement = generate_narrative("fir_victims", fir_id, "victim_statement", vs_prompt, translator=translator, temperature=vs_temp, force_kn=None).text_en
                cur.execute(
                    "INSERT INTO fir_victims (fir_victim_id, fir_id, person_id, victim_serial, victim_statement) VALUES (%s, %s, %s, 1, %s)",
                    (new_uuid(), fir_id, victim_id, victim_statement),
                )

                n_diary = RNG.choices([1, 2, 3, 4], weights=[0.35, 0.35, 0.20, 0.10])[0]
                for entry_num in range(1, n_diary + 1):
                    diary_prompt, diary_temp, action_taken = build_diary_entry_prompt(facts, entry_num)
                    record_id = f"{fir_id}:{entry_num}"
                    is_spot_visit = entry_num == 1 and RNG.random() < 0.15
                    text = generate_narrative(
                        "case_diary_entries", record_id, "entry_text", diary_prompt, translator=translator,
                        temperature=diary_temp, force_kn=None,
                    ).text_en
                    entry_date = registration_date + timedelta(days=entry_num * RNG.randint(2, 5))
                    if is_spot_visit:
                        spot_lat, spot_lon = jitter_point(lat, lon, 50)
                        cur.execute(
                            "INSERT INTO case_diary_entries (entry_id, fir_id, officer_id, entry_date, entry_number, entry_text, "
                            "action_taken, latitude, longitude, location_precision, geocode_source, geocode_confidence) "
                            "VALUES (%s, %s, %s, %s, %s, %s, 'Spot_Visit', %s, %s, 'exact', 'gps', %s)",
                            (new_uuid(), fir_id, io_officer_id, entry_date, entry_num, text, spot_lat, spot_lon, round(RNG.uniform(0.95, 0.999), 3)),
                        )
                    else:
                        cur.execute(
                            "INSERT INTO case_diary_entries (entry_id, fir_id, officer_id, entry_date, entry_number, entry_text, action_taken) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                            (new_uuid(), fir_id, io_officer_id, entry_date, entry_num, text, action_taken),
                        )

                chargesheet_id = None
                if investigation_status == "Chargesheet_Filed":
                    chargesheet_id = new_uuid()
                    filing_date = registration_date + timedelta(days=max(5, cs_days - RNG.randint(2, 10)))
                    summary = (
                        f"Chargesheet filed under {primary_section} against {max(1, len(accused_ids))} accused "
                        f"for a {crime_type_id.replace('-', ' ').lower()} case near {locality_name}."
                    )
                    cur.execute(
                        "INSERT INTO chargesheets (chargesheet_id, fir_id, filing_officer_id, filing_date, court_name, "
                        "sections_applied, num_accused, num_witnesses, summary_text, filing_status) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'Filed')",
                        (chargesheet_id, fir_id, io_officer_id, filing_date, f"JMFC {district_name_map.get(district_id, district_id)}",
                         [primary_section], max(1, len(accused_ids)), RNG.randint(0, 2), summary),
                    )
                    despatch_ts = filing_date + timedelta(days=RNG.randint(2, 6))
                    cur.execute("UPDATE firs SET despatch_to_court_ts = %s WHERE fir_id = %s", (despatch_ts, fir_id))

                    if RNG.random() < 0.45:
                        outcome = RNG.choices(
                            ["Convicted", "Acquitted", "Compounded", "Pending"], weights=[0.4, 0.25, 0.15, 0.2]
                        )[0]
                        cur.execute(
                            "INSERT INTO court_disposals (disposal_id, chargesheet_id, fir_id, disposal_date, court_name, outcome, sentence_details) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                            (new_uuid(), chargesheet_id, fir_id, filing_date + timedelta(days=RNG.randint(120, 500)),
                             f"JMFC {district_name_map.get(district_id, district_id)}", outcome,
                             f"Disposed under {primary_section}." if outcome != "Pending" else None),
                        )

                # Vehicle theft / property crime -> vehicle + stolen_property + possible seizure
                is_vehicle_crime = crime_type_id == "THEFT-VEHICLE"
                is_property_crime = crime_type_id in ("THEFT-GENERAL", "THEFT-DWELLING", "HOUSE-BREAKING", "HOUSE-BREAKING-NIGHT", "ROBBERY", "SNATCHING-CHAIN")
                recovered = RNG.random() < 0.35

                if is_vehicle_crime:
                    plate = None
                    for _ in range(20):
                        candidate = f"KA-{RNG.randint(1, 65):02d}-{RNG.choice('ABCDEFGHJKLMNPQRSTUVWXYZ')}{RNG.choice('ABCDEFGHJKLMNPQRSTUVWXYZ')}-{RNG.randint(1000, 9999)}"
                        if candidate not in used_plates:
                            used_plates.add(candidate)
                            plate = candidate
                            break
                    if plate:
                        vehicle_id = new_uuid()
                        make_model = RNG.choice([
                            ("Honda", "Activa"), ("TVS", "Jupiter"), ("Bajaj", "Pulsar"), ("Hero", "Splendor"),
                            ("Suzuki", "Access"), ("Yamaha", "FZ"), ("Maruti", "Swift"), ("Hyundai", "i10"),
                        ])
                        color = RNG.choice(["Black", "White", "Red", "Blue", "Grey", "Silver"])
                        cur.execute(
                            "INSERT INTO vehicles (vehicle_id, registration_number, vehicle_type, make, model, color, "
                            "owner_person_id, is_stolen, stolen_fir_id, theft_date, is_recovered, recovery_date) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s, %s, %s)",
                            (vehicle_id, plate, "Two-Wheeler" if make_model[0] != "Maruti" and make_model[0] != "Hyundai" else "Four-Wheeler",
                             make_model[0], make_model[1], color, victim_id, fir_id, incident_dt.date(),
                             recovered, incident_dt.date() + timedelta(days=RNG.randint(10, 45)) if recovered else None),
                        )
                        if recovered and RNG.random() < 0.4:
                            _insert_recovery_seizure(cur, fir_id, district_id, station_name, lat, lon, locality_id,
                                                       io_officer_id, incident_dt, linked_vehicle_id=vehicle_id,
                                                       translator=translator, persons_by_district=persons_by_district)

                elif is_property_crime and RNG.random() < 0.5:
                    property_id = new_uuid()
                    prop_type = RNG.choice(["Electronics", "Jewellery", "Cash", "Documents", "Other"])
                    desc = generate_narrative(
                        "stolen_property", property_id, "description",
                        f"Write a 1-sentence description in English of stolen {prop_type.lower()} reported in a "
                        f"{crime_type_id.replace('-', ' ').lower()} FIR near {locality_name}.",
                        translator=translator, temperature=0.6, force_kn=None,
                    ).text_en
                    cur.execute(
                        "INSERT INTO stolen_property (property_id, fir_id, property_type, description, estimated_value_inr, is_recovered) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        (property_id, fir_id, prop_type, desc, RNG.randint(3000, 80000), recovered),
                    )
                    if recovered:
                        _insert_recovery_seizure(cur, fir_id, district_id, station_name, lat, lon, locality_id,
                                                   io_officer_id, incident_dt, linked_property_id=property_id,
                                                   translator=translator, persons_by_district=persons_by_district)

                inserted += 1
                if inserted % 25 == 0:
                    conn.commit()
                    print(f"  firs: {inserted}/{need}", flush=True)
        conn.commit()
    print(f"background_firs: inserted {inserted} FIRs")


def _insert_recovery_seizure(cur, fir_id, district_id, station_name, lat, lon, locality_id, io_officer_id,
                              incident_dt, translator, persons_by_district, linked_vehicle_id=None, linked_property_id=None) -> None:
    pool = persons_by_district.get(district_id) or []
    if len(pool) < 2:
        return
    pancha1, pancha2 = RNG.sample(pool, 2)
    seizure_id = new_uuid()
    recovery_date = incident_dt + timedelta(days=RNG.randint(5, 60))
    slat, slon = jitter_point(lat, lon, 500)
    items_desc = generate_narrative(
        "seizures", seizure_id, "items_description",
        "Write a 2-sentence mahazar (seizure panchnama) items description in English for a property recovery, "
        "in the presence of two independent panch witnesses.",
        translator=translator, temperature=0.6, force_kn=None,
    ).text_en
    cur.execute(
        "INSERT INTO seizures (seizure_id, fir_id, mahazar_number, seizure_type, seizure_date, seizure_location, "
        "locality_id, latitude, longitude, location_precision, geocode_source, geocode_confidence, "
        "pancha_1_person_id, pancha_2_person_id, items_description, linked_vehicle_id, linked_property_id, custody_status) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'locality', 'gazetteer', %s, %s, %s, %s, %s, %s, 'In_Custody')",
        (seizure_id, fir_id, f"MZR-{district_id}-{recovery_date.year}-{RNG.randint(1, 9999):04d}",
         "Vehicle" if linked_vehicle_id else "Property", recovery_date, f"{station_name} jurisdiction",
         locality_id, slat, slon, round(RNG.uniform(0.55, 0.90), 3), pancha1, pancha2, items_desc,
         linked_vehicle_id, linked_property_id),
    )
    if linked_property_id:
        cur.execute(
            "UPDATE stolen_property SET recovery_date = %s, recovery_seizure_id = %s WHERE property_id = %s",
            (recovery_date, seizure_id, linked_property_id),
        )


# ============================================================
# Stage: NCRs / petitions
# ============================================================

def background_ncrs() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM ncr_petitions")
            current = cur.fetchone()[0]
            need = TARGETS["ncr_petitions"] - current
            if need <= 0:
                print(f"background_ncrs: already at {current}/{TARGETS['ncr_petitions']}, skipping")
                return

            cur.execute("SELECT station_id, district_id FROM police_stations WHERE district_id = ANY(%s)", (ACTIVE_DISTRICTS,))
            stations_by_district: dict[str, list[str]] = {}
            for station_id, district_id in cur.fetchall():
                stations_by_district.setdefault(district_id, []).append(station_id)

            cur.execute("SELECT person_id, district_id FROM persons")
            persons_by_district: dict[str, list[str]] = {}
            for person_id, district_id in cur.fetchall():
                persons_by_district.setdefault(district_id, []).append(person_id)

            cur.execute("SELECT officer_id, district_id FROM officers WHERE district_id = ANY(%s)", (ACTIVE_DISTRICTS,))
            io_pool: dict[str, list[str]] = {}
            for officer_id, district_id in cur.fetchall():
                io_pool.setdefault(district_id, []).append(officer_id)

            categories = ["Verbal_Abuse", "Simple_Hurt", "Property_Dispute", "Noise", "Threat", "Neighbour_Dispute"]
            translator = KannadaTranslator()
            inserted = 0
            for i in range(need):
                district_id = _weighted_choice([(d, DISTRICT_FIR_WEIGHT[d]) for d in ACTIVE_DISTRICTS])
                if district_id not in stations_by_district or district_id not in persons_by_district:
                    continue
                station_id = RNG.choice(stations_by_district[district_id])
                complainant_id = RNG.choice(persons_by_district[district_id])
                category = RNG.choice(categories)
                petition_type = RNG.choices(["NCR", "Petition"], weights=[0.6, 0.4])[0]
                days_before = RNG.randint(10, 1500)
                received_date = DEMO_DATE - timedelta(days=days_before)
                will_escalate = RNG.random() < 0.08
                status = "Escalated_To_FIR" if will_escalate else RNG.choices(["Open", "Closed", "Referred"], weights=[0.15, 0.75, 0.10])[0]

                petition_id = new_uuid()
                text = generate_narrative(
                    "ncr_petitions", petition_id, "petition_text",
                    f"Write a 2-sentence police {'NCR' if petition_type == 'NCR' else 'petition'} complaint narrative "
                    f"in English, first-person, regarding a {category.replace('_', ' ').lower()} dispute. No names or dates.",
                    translator=translator, temperature=0.8, force_kn=None,
                ).text_en

                escalated_fir_id = None
                if status == "Escalated_To_FIR":
                    # Escalating requires a real FIR to point at — skip escalation if none convenient;
                    # background NCRs are mostly standalone per §7.1 (only ~8% escalate).
                    cur.execute(
                        "SELECT fir_id FROM firs WHERE district_id = %s AND complainant_id = %s ORDER BY registration_date DESC LIMIT 1",
                        (district_id, complainant_id),
                    )
                    row = cur.fetchone()
                    if row:
                        escalated_fir_id = row[0]
                    else:
                        status = "Closed"

                cur.execute(
                    "INSERT INTO ncr_petitions (petition_id, petition_type, station_id, district_id, complainant_id, "
                    "received_date, category, petition_text, status, escalated_fir_id, assigned_officer_id) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (petition_id, petition_type, station_id, district_id, complainant_id, received_date,
                     category, text, status, escalated_fir_id, RNG.choice(io_pool.get(district_id, ["KSP-23417"]))),
                )
                inserted += 1
                if inserted % 50 == 0:
                    conn.commit()
                    print(f"  ncr_petitions: {inserted}/{need}", flush=True)
        conn.commit()
    print(f"background_ncrs: inserted {inserted} NCR/petition rows")


# ============================================================
# Stage: missing persons
# ============================================================

def background_missing_persons() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM missing_persons")
            current = cur.fetchone()[0]
            need = TARGETS["missing_persons"] - current
            if need <= 0:
                print(f"background_missing_persons: already at {current}/{TARGETS['missing_persons']}, skipping")
                return

            cur.execute(
                "SELECT locality_id, district_id, ST_Y(centroid::geometry), ST_X(centroid::geometry) FROM localities WHERE district_id = ANY(%s)",
                (ACTIVE_DISTRICTS,),
            )
            localities_by_district: dict[str, list[tuple[str, float, float]]] = {}
            for locality_id, district_id, lat, lon in cur.fetchall():
                if lat is not None and lon is not None:
                    localities_by_district.setdefault(district_id, []).append((locality_id, float(lat), float(lon)))

            cur.execute("SELECT station_id, district_id FROM police_stations WHERE district_id = ANY(%s)", (ACTIVE_DISTRICTS,))
            stations_by_district: dict[str, list[str]] = {}
            for station_id, district_id in cur.fetchall():
                stations_by_district.setdefault(district_id, []).append(station_id)

            cur.execute("SELECT person_id, district_id FROM persons")
            persons_by_district: dict[str, list[str]] = {}
            for person_id, district_id in cur.fetchall():
                persons_by_district.setdefault(district_id, []).append(person_id)

            translator = KannadaTranslator()
            inserted = 0
            for i in range(need):
                district_id = _weighted_choice([(d, DISTRICT_FIR_WEIGHT[d]) for d in ACTIVE_DISTRICTS])
                if district_id not in stations_by_district or district_id not in persons_by_district:
                    continue
                pool = persons_by_district[district_id]
                if len(pool) < 2:
                    continue
                mp_person_id, reporter_id = RNG.sample(pool, 2)
                station_id = RNG.choice(stations_by_district[district_id])

                if district_id in localities_by_district and localities_by_district[district_id]:
                    locality_id, base_lat, base_lon = RNG.choice(localities_by_district[district_id])
                else:
                    locality_id = None
                    _, station_lat, station_lon = _fetch_station(cur, station_id)
                    base_lat, base_lon = station_lat, station_lon
                lat, lon = jitter_point(base_lat, base_lon, 800)

                report_date = DEMO_DATE - timedelta(days=RNG.randint(10, 700))
                is_traced = RNG.random() < 0.60
                status = "Traced" if is_traced else RNG.choices(["Missing", "Matched_UDB"], weights=[0.85, 0.15])[0]

                mp_id = new_uuid()
                desc = generate_narrative(
                    "missing_persons", mp_id, "physical_description",
                    "Write a 1-sentence generic physical description in English for a missing-person report "
                    "(approximate age, height, clothing worn).",
                    translator=translator, temperature=0.6, force_kn=None,
                ).text_en

                cur.execute(
                    "INSERT INTO missing_persons (mp_id, person_id, reported_by_person_id, station_id, report_date, "
                    "last_seen_date, last_seen_location, locality_id, latitude, longitude, location_precision, "
                    "geocode_source, geocode_confidence, physical_description, status, traced_date) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'locality', 'gazetteer', %s, %s, %s, %s)",
                    (mp_id, mp_person_id, reporter_id, station_id, report_date, report_date - timedelta(days=1),
                     "reported locality", locality_id, lat, lon, round(RNG.uniform(0.55, 0.90), 3), desc, status,
                     (report_date + timedelta(days=RNG.randint(5, 90))).date() if is_traced else None),
                )
                inserted += 1
        conn.commit()
    print(f"background_missing_persons: inserted {inserted} missing_persons rows")


# ============================================================
# Stage: known_associates
# ============================================================

def background_known_associates() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM known_associates")
            current = cur.fetchone()[0]
            need = TARGETS["known_associates"] - current
            if need <= 0:
                print(f"background_known_associates: already at {current}/{TARGETS['known_associates']}, skipping")
                return

            cur.execute("SELECT DISTINCT fir_id FROM fir_accused GROUP BY fir_id HAVING count(*) >= 2")
            multi_accused_firs = [r[0] for r in cur.fetchall()]

            pairs_created = 0
            existing_pairs = set()
            cur.execute("SELECT person_id_a, person_id_b FROM known_associates")
            for a, b in cur.fetchall():
                existing_pairs.add((a, b))

            for fir_id in multi_accused_firs:
                if pairs_created >= need:
                    break
                cur.execute("SELECT person_id FROM fir_accused WHERE fir_id = %s", (fir_id,))
                accused = [r[0] for r in cur.fetchall()]
                for i in range(len(accused)):
                    for j in range(i + 1, len(accused)):
                        a, b = accused[i], accused[j]
                        if a > b:
                            a, b = b, a
                        if (a, b) in existing_pairs:
                            continue
                        cur.execute(
                            "INSERT INTO known_associates (association_id, person_id_a, person_id_b, association_type, first_seen_fir_id, confidence) "
                            "VALUES (%s, %s, %s, 'Co_Accused', %s, %s)",
                            (new_uuid(), a, b, fir_id, RNG.choices(["Confirmed", "Suspected"], weights=[0.7, 0.3])[0]),
                        )
                        existing_pairs.add((a, b))
                        pairs_created += 1
                        if pairs_created >= need:
                            break
                    if pairs_created >= need:
                        break

            # Fill any remainder with random same-district non-accused pairs (Family/Neighbour/Phone_Contact flavor).
            if pairs_created < need:
                cur.execute("SELECT person_id, district_id FROM persons")
                by_district: dict[str, list[str]] = {}
                for person_id, district_id in cur.fetchall():
                    by_district.setdefault(district_id, []).append(person_id)
                rel_types = ["Family", "Neighbour", "Phone_Contact", "Employer_Employee"]
                attempts = 0
                while pairs_created < need and attempts < need * 5:
                    attempts += 1
                    district_id = RNG.choice(list(by_district.keys()))
                    pool = by_district[district_id]
                    if len(pool) < 2:
                        continue
                    a, b = RNG.sample(pool, 2)
                    if a > b:
                        a, b = b, a
                    if (a, b) in existing_pairs:
                        continue
                    cur.execute(
                        "INSERT INTO known_associates (association_id, person_id_a, person_id_b, association_type, confidence) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (new_uuid(), a, b, RNG.choice(rel_types), RNG.choices(["Confirmed", "Suspected"], weights=[0.5, 0.5])[0]),
                    )
                    existing_pairs.add((a, b))
                    pairs_created += 1

        conn.commit()
    print(f"background_known_associates: inserted {pairs_created} pairs")


if __name__ == "__main__":
    stages = {
        "--persons": background_persons,
        "--gangs": background_gangs,
        "--firs": background_firs,
        "--ncrs": background_ncrs,
        "--missing-persons": background_missing_persons,
        "--known-associates": background_known_associates,
    }
    ran_any = False
    for flag, fn in stages.items():
        if flag in sys.argv or "--all" in sys.argv:
            fn()
            ran_any = True
    if not ran_any:
        print("usage: 07_background.py [--persons|--gangs|--firs|--ncrs|--missing-persons|--known-associates|--all]")
    else:
        print("Background corpus stage(s) complete.")
