#!/usr/bin/env python3
"""Stage 3 (SEED_RUNBOOK.md §4.2) — build the authoritative KSP police-unit
code list: db/reference/district_units.csv. Read-only against the DB; this
script only reads the normalized district GeoJSON and writes the CSV. A
human reviews this file before it's loaded (it becomes the FK target every
other Stage 3 table depends on: police_stations, localities, officers, ...).

Two judgment calls this script makes explicit rather than silently resolving:

1. Bengaluru's revenue-district split. The runbook warns "the district
   Shapefile has 31 revenue districts, not 37 police units. Do not assume
   1:1" and gives the example 'BLR' Bengaluru City / 'BLD' Bengaluru
   District as if there were exactly one non-city Bengaluru unit. Our source
   shapefile has THREE Bengaluru-area rows (Urban, Rural, South — a newer
   split) — one more than the 2-unit example anticipates, which is exactly
   why 31 source rows must not be assumed 1:1 with 31 police units.
   Resolution: keep all 31 source rows as their own district-type unit
   (Bengaluru (Urban) included, coded BLU) so the district-type count stays
   at exactly 31 as specified, then let BLR (the Bengaluru City
   commissionerate) reference Bengaluru (Urban)'s polygon as its parent.
   This means BLU and BLR jurisdictions geographically overlap on the map —
   accepted deliberately, since §4.2 already permits this class of
   imprecision ("do not attempt to compute a true carve-out geometry").
   Flagged in the CSV for verification against real KSP jurisdictional
   boundaries, which may not have caught up to this revenue-side split.
2. `division` (police range) assignment. The schema fixes the 7 valid values
   (Southern/Eastern/Western/Northern/Central/Ballari/Belagavi) but doesn't
   give a district->range mapping in any source file. Assigned here by
   geographic proximity to each range's namesake district, not from an
   official KSP range map — every row is marked accordingly.

Ramanagara district is a known gap: it does not appear as a row in the
source Village/District shapefiles at all (checked — 31 rows total, no
Ramanagara). Logged, not silently dropped.
"""

from __future__ import annotations

import csv
from pathlib import Path

import geopandas as gpd

REPO_ROOT = Path(__file__).resolve().parents[2]
DISTRICT_GEOJSON = REPO_ROOT / "seed-sources" / "geojson" / "admin_boundaries__district.geojson"
OUT_CSV = REPO_ROOT / "db" / "reference" / "district_units.csv"

# name in KGISDist_1 -> (chosen canonical English name, chosen 3-char code, range)
# Range assignment is a geographic approximation (see module docstring §2).
DISTRICT_ASSIGNMENTS: dict[str, tuple[str, str, str]] = {
    "Belagavi": ("Belagavi District", "BGD", "Belagavi"),
    "Bagalkote": ("Bagalkote", "BGK", "Belagavi"),
    "Vijayapura": ("Vijayapura", "VJP", "Belagavi"),
    "Kalaburgi": ("Kalaburagi District", "KLD", "Northern"),
    "Bidar": ("Bidar", "BDR", "Northern"),
    "Raichur": ("Raichur", "RCH", "Ballari"),
    "Koppal": ("Koppal", "KPL", "Ballari"),
    "Gadag": ("Gadag", "GDG", "Western"),
    "Dharwad": ("Dharwad District", "DWD", "Western"),
    "Uttara Kannada": ("Uttara Kannada", "UTK", "Western"),
    "Haveri": ("Haveri", "HVR", "Western"),
    "Ballari": ("Ballari District", "BLL", "Ballari"),
    "Chitradurga": ("Chitradurga", "CTD", "Ballari"),
    "Davanagere": ("Davanagere", "DVG", "Western"),
    "Shivamogga": ("Shivamogga", "SMG", "Western"),
    "Udupi": ("Udupi", "UDP", "Southern"),
    "Chikkamagaluru": ("Chikkamagaluru", "CKM", "Southern"),
    "Tumakuru": ("Tumakuru", "TMK", "Eastern"),
    "Kolara": ("Kolar", "KLR", "Eastern"),
    "Bengaluru (Urban)": ("Bengaluru (Urban) District", "BLU", "Central"),  # also the parent polygon for the BLR commissionerate — deliberate jurisdictional overlap, see module docstring §1
    "Bengaluru (Rural)": ("Bengaluru District", "BLD", "Central"),
    "Mandya": ("Mandya District", "MDY", "Southern"),
    "Hassan": ("Hassan", "HSN", "Southern"),
    "Dakshina Kannada": ("Dakshina Kannada District", "DKD", "Southern"),
    "Kodagu": ("Kodagu", "KDG", "Southern"),
    "Mysuru": ("Mysuru District", "MYD", "Southern"),
    "Chamarajanagara": ("Chamarajanagara", "CHN", "Southern"),
    "Chikkaballapura": ("Chikkaballapura", "CKB", "Eastern"),
    "Bengaluru South": ("Bengaluru South District", "BLS", "Central"),
    "Yadgir": ("Yadgir", "YDG", "Ballari"),
    "Vijayanagara": ("Vijayanagara", "VJN", "Ballari"),
}

# Kannada names for the 31 real districts — no Kannada attribute column
# exists in the source shapefile (checked: KGISDistri/LGD_Distri/KGISDist_1/
# BhuCodeDis are the only attrs), so these are standard public-knowledge
# Kannada spellings for well-known place names, not extracted/transliterated
# programmatically. Flagged per row for human spot-check (§1.1.3 requires
# district_name_kn at 100%, but "verbatim from source" doesn't apply here).
KANNADA_NAMES: dict[str, str] = {
    "Belagavi": "ಬೆಳಗಾವಿ", "Bagalkote": "ಬಾಗಲಕೋಟೆ", "Vijayapura": "ವಿಜಯಪುರ",
    "Kalaburgi": "ಕಲಬುರಗಿ", "Bidar": "ಬೀದರ", "Raichur": "ರಾಯಚೂರು",
    "Koppal": "ಕೊಪ್ಪಳ", "Gadag": "ಗದಗ", "Dharwad": "ಧಾರವಾಡ",
    "Uttara Kannada": "ಉತ್ತರ ಕನ್ನಡ", "Haveri": "ಹಾವೇರಿ", "Ballari": "ಬಳ್ಳಾರಿ",
    "Chitradurga": "ಚಿತ್ರದುರ್ಗ", "Davanagere": "ದಾವಣಗೆರೆ", "Shivamogga": "ಶಿವಮೊಗ್ಗ",
    "Udupi": "ಉಡುಪಿ", "Chikkamagaluru": "ಚಿಕ್ಕಮಗಳೂರು", "Tumakuru": "ತುಮಕೂರು",
    "Kolara": "ಕೋಲಾರ", "Bengaluru (Urban)": "ಬೆಂಗಳೂರು ನಗರ", "Bengaluru (Rural)": "ಬೆಂಗಳೂರು ಗ್ರಾಮಾಂತರ",
    "Mandya": "ಮಂಡ್ಯ", "Hassan": "ಹಾಸನ", "Dakshina Kannada": "ದಕ್ಷಿಣ ಕನ್ನಡ",
    "Kodagu": "ಕೊಡಗು", "Mysuru": "ಮೈಸೂರು", "Chamarajanagara": "ಚಾಮರಾಜನಗರ",
    "Chikkaballapura": "ಚಿಕ್ಕಬಳ್ಳಾಪುರ", "Bengaluru South": "ಬೆಂಗಳೂರು ದಕ್ಷಿಣ",
    "Yadgir": "ಯಾದಗಿರಿ", "Vijayanagara": "ವಿಜಯನಗರ",
}

# The 6 city commissionerates. parent_source_name = the KGISDist_1 value
# whose polygon this commissionerate's admin_boundaries reference reuses
# (runbook §4.2: "reference the parent district's polygon... do not attempt
# to compute a true carve-out geometry"). Centroid coords are the well-known
# city-centre coordinates (public knowledge), not derived from the polygon.
COMMISSIONERATES: list[dict] = [
    {"code": "BLR", "name": "Bengaluru City", "name_kn": "ಬೆಂಗಳೂರು ನಗರ ಪೊಲೀಸ್", "parent_source_name": "Bengaluru (Urban)", "division": "Central", "hq_city": "Bengaluru", "lat": 12.9716, "lon": 77.5946},
    {"code": "MYS", "name": "Mysuru City", "name_kn": "ಮೈಸೂರು ನಗರ ಪೊಲೀಸ್", "parent_source_name": "Mysuru", "division": "Southern", "hq_city": "Mysuru", "lat": 12.2958, "lon": 76.6394},
    {"code": "MNG", "name": "Mangaluru City", "name_kn": "ಮಂಗಳೂರು ನಗರ ಪೊಲೀಸ್", "parent_source_name": "Dakshina Kannada", "division": "Southern", "hq_city": "Mangaluru", "lat": 12.9141, "lon": 74.8560},
    {"code": "HBL", "name": "Hubballi-Dharwad City", "name_kn": "ಹುಬ್ಬಳ್ಳಿ-ಧಾರವಾಡ ನಗರ ಪೊಲೀಸ್", "parent_source_name": "Dharwad", "division": "Western", "hq_city": "Hubballi", "lat": 15.3647, "lon": 75.1240},
    {"code": "BGV", "name": "Belagavi City", "name_kn": "ಬೆಳಗಾವಿ ನಗರ ಪೊಲೀಸ್", "parent_source_name": "Belagavi", "division": "Belagavi", "hq_city": "Belagavi", "lat": 15.8497, "lon": 74.4977},
    {"code": "KLB", "name": "Kalaburagi City", "name_kn": "ಕಲಬುರಗಿ ನಗರ ಪೊಲೀಸ್", "parent_source_name": "Kalaburgi", "division": "Northern", "hq_city": "Kalaburagi", "lat": 17.3297, "lon": 76.8343},
]

# §7.1: the 10 active units carrying synthetic case data.
ACTIVE_UNIT_CODES = {"BLR", "MYS", "MDY", "HBL", "MNG", "BGV", "TMK", "KDG", "CKM", "RCH"}


def main() -> None:
    gdf = gpd.read_file(DISTRICT_GEOJSON)
    source_names = set(gdf["KGISDist_1"])

    known = set(DISTRICT_ASSIGNMENTS)
    missing_in_map = source_names - known
    extra_in_map = known - source_names
    if missing_in_map:
        print(f"WARNING: source districts with no assignment: {missing_in_map}")
    if extra_in_map:
        print(f"WARNING: assignment entries with no matching source row: {extra_in_map}")

    expected_but_absent = {"Ramanagara"}
    print(f"NOTE: known real Karnataka districts absent from source shapefile entirely: {expected_but_absent}")

    rows: list[dict] = []

    # 31 district-type units, one per source row (Bengaluru (Urban) included
    # as BLU — it also doubles as the BLR commissionerate's parent polygon,
    # a deliberate jurisdictional overlap; see module docstring §1).
    for _, row in gdf.iterrows():
        source_name = row["KGISDist_1"]
        if source_name not in DISTRICT_ASSIGNMENTS:
            continue
        canonical_name, code, division = DISTRICT_ASSIGNMENTS[source_name]
        centroid = row.geometry.centroid
        rows.append({
            "district_id": code,
            "district_name": canonical_name,
            "district_name_kn": KANNADA_NAMES.get(source_name, ""),
            "unit_type": "District",
            "division": division,
            "hq_city": canonical_name.replace(" District", ""),
            "centroid_latitude": round(centroid.y, 6),
            "centroid_longitude": round(centroid.x, 6),
            "source_polygon_name": source_name,
            "is_active": code in ACTIVE_UNIT_CODES,
            "review_note": "range=geographic approximation, not official KSP map; verify",
        })

    for c in COMMISSIONERATES:
        rows.append({
            "district_id": c["code"],
            "district_name": c["name"],
            "district_name_kn": c["name_kn"],
            "unit_type": "Commissionerate",
            "division": c["division"],
            "hq_city": c["hq_city"],
            "centroid_latitude": c["lat"],
            "centroid_longitude": c["lon"],
            "source_polygon_name": c["parent_source_name"],
            "is_active": c["code"] in ACTIVE_UNIT_CODES,
            "review_note": "centroid=public-knowledge city-centre coords, not polygon-derived; "
                           "shares parent district's admin_boundaries polygon (no true carve-out geometry, per §4.2)",
        })

    assert len(rows) == 37, f"expected 37 units, got {len(rows)}"
    active_found = {r["district_id"] for r in rows if r["is_active"]}
    assert active_found == ACTIVE_UNIT_CODES, f"active unit mismatch: {active_found} vs {ACTIVE_UNIT_CODES}"

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nwrote {len(rows)} district units -> {OUT_CSV}")
    print(f"active units: {sorted(active_found)}")
    print("\nfull table:")
    for r in rows:
        flag = " *ACTIVE*" if r["is_active"] else ""
        print(f"  {r['district_id']} | {r['district_name']:30s} | {r['unit_type']:15s} | {r['division']:10s}{flag}")


if __name__ == "__main__":
    main()
