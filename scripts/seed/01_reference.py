#!/usr/bin/env python3
"""Stage 3 — real reference data ingest (SEED_RUNBOOK.md §4). FK dependency
order: districts -> admin_boundaries -> police_stations -> localities ->
sub_divisions/circles -> jurisdiction_boundary -> bns_sections.

Run functions individually via the CLI flags below rather than always doing
a full run — each step is inspected before the next runs.

Usage:
    python 01_reference.py --districts
    python 01_reference.py --admin-boundaries
    python 01_reference.py --all
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

from db import connect

REPO_ROOT = Path(__file__).resolve().parents[2]
GEOJSON_DIR = REPO_ROOT / "seed-sources" / "geojson"
DISTRICT_UNITS_CSV = REPO_ROOT / "db" / "reference" / "district_units.csv"

# Commissionerate city-extent polygons, used to reclassify stations that
# fall inside the actual city limits from their parent district-type unit to
# the commissionerate. We don't have a true carve-out polygon for any of
# these (per §4.2, not attempted), so this uses the best available proxy:
# BBMP wards (very precise) for Bengaluru, and the matching town_boundaries
# source (real KGIS municipal-limit polygon) for the other 4 where one
# exists. Mangaluru has no town_boundaries or ward_boundaries file among our
# sources at all — no polygon proxy exists, so it falls back to a plain
# radius circle around the known city-centre coordinate (courser than the
# polygon-based approach, but MNG is one of the 10 §7.1 active units and
# needs *some* directly-assigned stations for background case data, so an
# approximation beats leaving it with zero).
COMMISSIONERATE_CITY_SOURCES: dict[str, str | None] = {
    "BLR": "__BBMP_UNION__",
    "MYS": "town_boundaries__2605_Mysuru.geojson",
    "HBL": "town_boundaries__0903_Hubli Dharwad.geojson",
    "BGV": "town_boundaries__0105_Belagavi.geojson",
    "KLB": "town_boundaries__0406_Kalaburagi.geojson",
    "MNG": "__RADIUS_FALLBACK__",
}

# (lat, lon, radius_km) for the __RADIUS_FALLBACK__ case.
RADIUS_FALLBACK_CENTERS: dict[str, tuple[float, float, float]] = {
    "MNG": (12.9141, 74.8560, 12.0),
}

STATION_TYPE_KEYWORDS: list[tuple[str, str]] = [
    (r"\bwomen\b", "Women"),
    (r"\bcyber\b", "Cyber"),
    (r"\brural\b", "Rural"),
    (r"\btown\b", "Town"),
]


def _normalize_station_name(name: str) -> str:
    n = name.strip().lower()
    n = re.sub(r"\bp\.?\s*s\.?\b", "", n)  # "PS", "P.S", "P S"
    n = re.sub(r"\bpolice\s*station\b", "", n)
    n = re.sub(r"\bout\s*post\b|\boutpost\b", "", n)
    n = re.sub(r"[^a-z0-9 ]", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _infer_station_type(name: str, category: str) -> str:
    if category == "Traffic":
        return "Traffic"
    lname = name.lower()
    for pattern, station_type in STATION_TYPE_KEYWORDS:
        if re.search(pattern, lname):
            return station_type
    return "City"


def _to_multipolygon_wkt(geom) -> str:
    if isinstance(geom, Polygon):
        geom = MultiPolygon([geom])
    return geom.wkt


def _is_polygonal(geom) -> bool:
    return geom is not None and geom.geom_type in ("Polygon", "MultiPolygon")


# ============================================================
# districts
# ============================================================

def load_districts() -> None:
    with DISTRICT_UNITS_CSV.open() as f:
        rows = list(csv.DictReader(f))

    with connect() as conn:
        with conn.cursor() as cur:
            for r in rows:
                cur.execute(
                    """
                    INSERT INTO districts
                        (district_id, district_name, district_name_kn, unit_type,
                         division, hq_city, centroid_latitude, centroid_longitude)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (district_id) DO NOTHING
                    """,
                    (
                        r["district_id"], r["district_name"], r["district_name_kn"] or None,
                        r["unit_type"], r["division"] or None, r["hq_city"] or None,
                        float(r["centroid_latitude"]), float(r["centroid_longitude"]),
                    ),
                )
        conn.commit()

    print(f"loaded {len(rows)} districts")


# ============================================================
# admin_boundaries (State / District / Taluk / Hobli)
# ============================================================

def load_admin_boundaries() -> None:
    with DISTRICT_UNITS_CSV.open() as f:
        district_rows = list(csv.DictReader(f))
    # KGISDist_1 (source_polygon_name) -> KSP district_id, for District-type rows only.
    poly_name_to_district_id = {
        r["source_polygon_name"]: r["district_id"] for r in district_rows if r["unit_type"] == "District"
    }

    district_gdf = gpd.read_file(GEOJSON_DIR / "admin_boundaries__district.geojson")
    # KGISDistri (2-digit code) -> district_id, for the taluk join.
    kgis_code_to_district_id = {
        row["KGISDistri"]: poly_name_to_district_id[row["KGISDist_1"]]
        for _, row in district_gdf.iterrows()
        if row["KGISDist_1"] in poly_name_to_district_id
    }

    taluk_gdf = gpd.read_file(GEOJSON_DIR / "admin_boundaries__taluk.geojson")
    # KGISTalukC -> KGISDistri, for the hobli join (hobli only carries taluk code).
    taluk_code_to_kgis_district = dict(zip(taluk_gdf["KGISTalukC"], taluk_gdf["KGISDistri"]))

    inserted = 0
    with connect() as conn:
        with conn.cursor() as cur:
            # --- State ---
            state_gdf = gpd.read_file(GEOJSON_DIR / "admin_boundaries__state.geojson")
            for _, row in state_gdf.iterrows():
                cur.execute(
                    """
                    INSERT INTO admin_boundaries (boundary_type, name, name_kn, ref_district_id, geom, source)
                    VALUES ('State', %s, %s, NULL, ST_GeomFromText(%s, 4326)::geography, 'KGIS')
                    """,
                    ("Karnataka", "ಕರ್ನಾಟಕ", _to_multipolygon_wkt(row.geometry)),
                )
                inserted += 1

            # --- District ---
            for _, row in district_gdf.iterrows():
                district_id = poly_name_to_district_id.get(row["KGISDist_1"])
                if district_id is None:
                    print(f"  SKIP district polygon with no mapped unit: {row['KGISDist_1']}", file=sys.stderr)
                    continue
                name_kn = next(
                    (r["district_name_kn"] for r in district_rows if r["district_id"] == district_id), None
                )
                cur.execute(
                    """
                    INSERT INTO admin_boundaries (boundary_type, name, name_kn, ref_district_id, geom, source)
                    VALUES ('District', %s, %s, %s, ST_GeomFromText(%s, 4326)::geography, 'KGIS')
                    """,
                    (row["KGISDist_1"], name_kn, district_id, _to_multipolygon_wkt(row.geometry)),
                )
                inserted += 1

            # --- Taluk ---
            taluk_missing = 0
            for _, row in taluk_gdf.iterrows():
                district_id = kgis_code_to_district_id.get(row["KGISDistri"])
                if district_id is None:
                    taluk_missing += 1
                    continue
                cur.execute(
                    """
                    INSERT INTO admin_boundaries (boundary_type, name, name_kn, ref_district_id, geom, source)
                    VALUES ('Taluk', %s, NULL, %s, ST_GeomFromText(%s, 4326)::geography, 'KGIS')
                    """,
                    (row["KGISTalukN"], district_id, _to_multipolygon_wkt(row.geometry)),
                )
                inserted += 1
            if taluk_missing:
                print(f"  {taluk_missing} taluk polygons skipped (no district mapping)", file=sys.stderr)

            # --- Hobli (per-district source files) ---
            hobli_files = sorted((GEOJSON_DIR).glob("hobli_boundaries__*.geojson"))
            hobli_missing = 0
            hobli_non_polygon = 0
            hobli_non_polygon_files: set[str] = set()
            for path in hobli_files:
                hobli_gdf = gpd.read_file(path)
                for _, row in hobli_gdf.iterrows():
                    if not _is_polygonal(row.geometry):
                        # 3 source files (Uttara Kannada, Dakshina Kannada,
                        # Bengaluru South) are entirely LineString, not
                        # Polygon — a genuine source data quality issue
                        # (wrong export format), not an invalid-but-fixable
                        # geometry. Not load-bearing for any FK downstream
                        # (no table references hobli-level admin_boundaries),
                        # so skipped with a loud count rather than attempting
                        # line-to-polygon reconstruction.
                        hobli_non_polygon += 1
                        hobli_non_polygon_files.add(path.name)
                        continue
                    kgis_district = taluk_code_to_kgis_district.get(row["KGISTalukC"])
                    district_id = kgis_code_to_district_id.get(kgis_district) if kgis_district else None
                    if district_id is None:
                        hobli_missing += 1
                        continue
                    cur.execute(
                        """
                        INSERT INTO admin_boundaries (boundary_type, name, name_kn, ref_district_id, geom, source)
                        VALUES ('Hobli', %s, NULL, %s, ST_GeomFromText(%s, 4326)::geography, 'KGIS')
                        """,
                        (row["KGISHobliN"], district_id, _to_multipolygon_wkt(row.geometry)),
                    )
                    inserted += 1
            if hobli_missing:
                print(f"  {hobli_missing} hobli polygons skipped (no district mapping)", file=sys.stderr)
            if hobli_non_polygon:
                print(
                    f"  {hobli_non_polygon} hobli features skipped (non-polygon geometry) "
                    f"in files: {sorted(hobli_non_polygon_files)}",
                    file=sys.stderr,
                )

        conn.commit()

    print(f"loaded {inserted} admin_boundaries rows")


# ============================================================
# police_stations
# ============================================================

STATION_SOURCES: list[tuple[str, str, str]] = [
    # (filename, name_column, category)
    ("police_stations__Karnataka_Police_Station_Locations_Map.geojson", "POL_STAName", "Station"),
    ("police_stations__Bengaluru_Urban_Police_Station_Locations.geojson", "POL_STAName", "Station"),
    ("police_stations__Karnatak_Police_Outpost_Locations_Map.geojson", "POL_OPSTName", "Outpost"),
    ("police_stations__Bengaluru_Urban_Police_Outpost_Locations.geojson", "POL_OPSTName", "Outpost"),
    ("traffic_police_stations__Karnataka_Traffic_Police_Station_Locations_Map.geojson", "TRF_POL_STAName", "Traffic"),
    ("traffic_police_stations__Bengaluru_Urban_Traffic_Police_Stations_Map.geojson", "TRF_POL_STAName", "Traffic"),
]


def _load_raw_station_points() -> gpd.GeoDataFrame:
    frames = []
    for filename, name_col, category in STATION_SOURCES:
        gdf = gpd.read_file(GEOJSON_DIR / filename)
        # KML Point/MultiPoint mixed within a file (seen in Stage 1 report)
        # — normalize MultiPoint to its first point (KML placemarks are
        # single points; MultiPoint only appears from an OGR quirk on a
        # handful of features, never genuinely multi-location stations).
        gdf["geometry"] = gdf.geometry.apply(
            lambda g: g.geoms[0] if g.geom_type == "MultiPoint" else g
        )
        frames.append(
            gpd.GeoDataFrame(
                {
                    "name": gdf[name_col].astype(str).str.strip(),
                    "category": category,
                    "source_file": filename,
                    "is_statewide_source": "Bengaluru" not in filename,
                },
                geometry=gdf.geometry,
                crs=gdf.crs,
            )
        )
    combined = pd.concat(frames, ignore_index=True)
    combined = combined[combined["name"] != ""]
    return gpd.GeoDataFrame(combined, geometry="geometry", crs=frames[0].crs)


def _dedupe_stations(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Dedupe on normalized name + <150m proximity (SEED_RUNBOOK.md §4.3).
    Prefers the statewide source over a Bengaluru-specific subset file when
    both cover the same real station.
    """
    gdf = gdf.copy()
    gdf["norm_name"] = gdf["name"].apply(_normalize_station_name)
    # Sort BEFORE reprojecting/reindexing, so gdf and gdf_metric are built
    # from the exact same row order and stay aligned after both get their
    # index reset. (Reprojecting first and re-selecting via .loc[gdf.index]
    # after a prior reset_index(drop=True) silently scrambles the pairing —
    # gdf.index is by then just a fresh 0..n-1 RangeIndex that no longer
    # identifies the original rows, so distance() ends up comparing
    # essentially random pairs instead of true candidate duplicates.)
    gdf = gdf.sort_values("is_statewide_source", ascending=False)
    # Project to a metric CRS (UTM 43N, matches the source data's native
    # projection) for real distance comparisons.
    gdf_metric = gdf.to_crs(epsg=32643)
    gdf = gdf.reset_index(drop=True)
    gdf_metric = gdf_metric.reset_index(drop=True)

    keep = [True] * len(gdf)
    by_name: dict[str, list[int]] = {}
    for i, norm_name in enumerate(gdf["norm_name"]):
        by_name.setdefault(norm_name, []).append(i)

    for indices in by_name.values():
        if len(indices) < 2:
            continue
        for a in range(len(indices)):
            i = indices[a]
            if not keep[i]:
                continue
            for b in range(a + 1, len(indices)):
                j = indices[b]
                if not keep[j]:
                    continue
                if gdf_metric.geometry.iloc[i].distance(gdf_metric.geometry.iloc[j]) < 150:
                    keep[j] = False  # j comes later in the statewide-first sort -> drop it

    deduped = gdf[keep].reset_index(drop=True)
    print(f"  dedup: {len(gdf)} raw -> {len(deduped)} after name+150m dedup")
    return deduped


def _assign_district_and_city(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    with DISTRICT_UNITS_CSV.open() as f:
        district_rows = list(csv.DictReader(f))
    poly_name_to_district_id = {
        r["source_polygon_name"]: r["district_id"] for r in district_rows if r["unit_type"] == "District"
    }

    district_gdf = gpd.read_file(GEOJSON_DIR / "admin_boundaries__district.geojson")
    district_gdf["district_id"] = district_gdf["KGISDist_1"].map(poly_name_to_district_id)
    district_gdf = district_gdf.dropna(subset=["district_id"])[["district_id", "geometry"]]

    joined = gpd.sjoin(gdf, district_gdf, how="left", predicate="within")
    joined = joined.drop(columns=["index_right"])
    unmatched = joined["district_id"].isna().sum()
    if unmatched:
        # Points exactly on a boundary edge or just outside due to
        # source-precision mismatch between layers — nearest-district
        # fallback rather than dropping real stations.
        missing_mask = joined["district_id"].isna()
        nearest = gpd.sjoin_nearest(
            joined.loc[missing_mask, ["geometry"]], district_gdf, how="left"
        )
        joined.loc[missing_mask, "district_id"] = nearest["district_id"].values
        print(f"  {unmatched} stations fell outside all district polygons; assigned via nearest-district fallback")

    # Commissionerate city remap.
    joined["district_id"] = joined["district_id"].astype(str)
    for code, source in COMMISSIONERATE_CITY_SOURCES.items():
        if source is None:
            continue
        if source == "__RADIUS_FALLBACK__":
            lat, lon, radius_km = RADIUS_FALLBACK_CENTERS[code]
            center = gpd.GeoSeries(gpd.points_from_xy([lon], [lat]), crs=district_gdf.crs).to_crs(epsg=32643)
            joined_metric = joined.to_crs(epsg=32643)
            within_city = joined_metric.geometry.distance(center.iloc[0]) <= radius_km * 1000
        else:
            if source == "__BBMP_UNION__":
                city_gdf = gpd.read_file(GEOJSON_DIR / "bbmp_ward_boundaries.geojson")
            else:
                city_gdf = gpd.read_file(GEOJSON_DIR / source)
            city_poly = unary_union(city_gdf.geometry)
            city_series = gpd.GeoSeries([city_poly], crs=district_gdf.crs)
            within_city = joined.geometry.within(city_series.iloc[0])
        n_remapped = within_city.sum()
        joined.loc[within_city, "district_id"] = code
        print(f"  remapped {n_remapped} stations into commissionerate {code}")

    return joined


def load_police_stations() -> None:
    raw = _load_raw_station_points()
    print(f"loaded {len(raw)} raw station/outpost/traffic points from 6 sources")
    deduped = _dedupe_stations(raw)
    # Outposts excluded: not a valid police_stations.station_type value in
    # the schema (City/Rural/Town/Traffic/Women/Cyber only — no Outpost),
    # and real FIRs are registered at stations, not outposts. Including all
    # 182 would also roughly double the source-manifest's "~906 stations
    # statewide" target for no schema-supported benefit.
    n_outposts = (deduped["category"] == "Outpost").sum()
    deduped = deduped[deduped["category"] != "Outpost"].reset_index(drop=True)
    print(f"  excluded {n_outposts} outposts (no station_type slot in schema)")
    assigned = _assign_district_and_city(deduped)

    assigned["station_type"] = [
        _infer_station_type(name, category) for name, category in zip(assigned["name"], assigned["category"])
    ]

    # Sequential station_id per district: 'KA-{district_id}-{seq:03d}' = 10 chars.
    assigned = assigned.sort_values(["district_id", "name"]).reset_index(drop=True)
    seq_counters: dict[str, int] = {}
    station_ids = []
    for district_id in assigned["district_id"]:
        seq_counters[district_id] = seq_counters.get(district_id, 0) + 1
        station_ids.append(f"KA-{district_id}-{seq_counters[district_id]:03d}")
    assigned["station_id"] = station_ids

    inserted = 0
    skipped_no_district = 0
    with connect() as conn:
        with conn.cursor() as cur:
            # Only insert stations whose district_id actually exists in the
            # districts table (guards against any remaining sjoin_nearest
            # edge case landing on a code outside our 37).
            cur.execute("SELECT district_id FROM districts")
            valid_districts = {r[0] for r in cur.fetchall()}

            for _, row in assigned.iterrows():
                if row["district_id"] not in valid_districts:
                    skipped_no_district += 1
                    continue
                cur.execute(
                    """
                    INSERT INTO police_stations
                        (station_id, station_name, district_id, station_type,
                         latitude, longitude, location_precision, geocode_source, geocode_confidence)
                    VALUES (%s, %s, %s, %s, %s, %s, 'exact', 'manual', 1.000)
                    ON CONFLICT (station_id) DO NOTHING
                    """,
                    (
                        row["station_id"], row["name"][:150], row["district_id"], row["station_type"],
                        row.geometry.y, row.geometry.x,
                    ),
                )
                inserted += 1
        conn.commit()

    if skipped_no_district:
        print(f"  {skipped_no_district} stations skipped (district_id not in districts table)", file=sys.stderr)
    print(f"loaded {inserted} police_stations rows")
    print("NOTE: station_name_kn left NULL (spec requires 100% population at master-data rate — "
          "run a follow-up IndicTrans2 transliteration pass over station_name before Gate 3 sign-off).")


# ============================================================
# localities (SEED_RUNBOOK.md §4.4)
# ============================================================

# §7.1 targets 150-200 localities total, "concentrated in active units."
# Ward-level files alone across the 7 active units that have one (348) plus
# BBMP (243) sum to 591 — well over target — so each source is sampled down
# to a representative, evenly-spaced subset (gdf.iloc[::step], not random,
# for reproducibility) rather than loaded in full. Kodagu and Mangaluru have
# no ward_boundaries file at all; they fall back to a small village sample.
#
# Golden-thread-specific colloquial locality names (Jayanagar 4th Block,
# K.R. Circle, Bannimantap, etc.) are deliberately NOT sourced here — they
# don't match official KGIS ward names (verified: BBMP wards are named
# things like "Kempegowda Ward", not "Jayanagar 4th Block") and belong to
# Stage 5 (SEED_RUNBOOK.md §6.1, golden threads), authored as
# source='Synthetic' rows with real-world coordinates when Threads A/B/C
# are built — not part of this general gazetteer pass.
LOCALITY_WARD_SOURCES: list[tuple[str, str, int]] = [
    # (district_id, filename, sample_step)
    ("MYS", "ward_boundaries__2605_Mysuru.geojson", 3),
    ("MDY", "ward_boundaries__2204_Mandya.geojson", 2),
    ("TMK", "ward_boundaries__1810_Tumakuru.geojson", 2),
    ("CKM", "ward_boundaries__1702_Chickamagaluru.geojson", 2),
    # BGV, HBL, RCH deliberately absent here — checked directly: their ward
    # files have KGISWardNa null on effectively every row (Belagavi 1/59
    # named, Raichur 0/35, Hubballi-Dharwad 0/83 — a genuine source gap, not
    # a filter bug), so they're sourced from village_boundaries instead,
    # below. For BGV/HBL specifically (commissionerate cities) this trades
    # precision for coverage: village polygons span the whole parent
    # district, not just the city core, so some resulting localities will
    # sit outside the true city limits — same class of approximation
    # already accepted for jurisdiction geometry per §4.2.
]
LOCALITY_TOWN_SOURCES: list[tuple[str, str]] = [
    ("MYS", "town_boundaries__2605_Mysuru.geojson"),
    ("BGV", "town_boundaries__0105_Belagavi.geojson"),
    ("HBL", "town_boundaries__0903_Hubli Dharwad.geojson"),
    ("MDY", "town_boundaries__2204_Mandya.geojson"),
    ("TMK", "town_boundaries__1810_Tumakuru.geojson"),
]
LOCALITY_VILLAGE_FALLBACK_SOURCES: list[tuple[str, str, int]] = [
    ("KDG", "village_boundaries__25_Kodagu.geojson", 100),
    # MNG's village file is entirely LineString (2745/2745 features) — the
    # same export defect found in 3 of the hobli_boundaries files at Gate 1.
    # Kept here (rather than silently omitted) so the zero-row outcome is
    # visible in the run log via _is_polygonal filtering, not hidden.
    ("MNG", "village_boundaries__24_Dakshina Kannada.geojson", 100),
    ("BGV", "village_boundaries__01_Belagavi.geojson", 65),
    ("RCH", "village_boundaries__06_Raichur.geojson", 45),
    ("HBL", "village_boundaries__09_Dharwad.geojson", 25),
]
BBMP_SAMPLE_STEP = 6


def _safe_centroid(geom):
    c = geom.centroid
    if not geom.contains(c):
        return geom.representative_point()  # ST_PointOnSurface equivalent
    return c


def _mechanical_aliases(name: str) -> list[str]:
    """Cheap mechanical alias variants (SEED_RUNBOOK.md §4.4) — abbreviation
    contractions and punctuation-stripped forms. No romanization variant:
    every source name here is already Latin-script (KGIS attribute tables
    carry no Kannada-script name column for wards/towns/villages).
    """
    aliases = set()
    stripped = re.sub(r"[^\w\s]", "", name).strip()
    if stripped and stripped != name:
        aliases.add(stripped)
    abbreviated = (
        name.replace("Nagar", "Ngr").replace("Layout", "Lyt")
        .replace("Extension", "Ext").replace("Block", "Blk")
    )
    if abbreviated != name:
        aliases.add(abbreviated)
    return sorted(aliases)


def load_localities() -> None:
    with DISTRICT_UNITS_CSV.open() as f:
        district_rows = list(csv.DictReader(f))
    valid_district_ids = {r["district_id"] for r in district_rows}

    records = []  # (locality_name, locality_type, district_id, geometry)
    skipped_no_name = 0

    def _clean_name(raw) -> str | None:
        nonlocal skipped_no_name
        if raw is None or (isinstance(raw, float)):  # NaN reads as float
            skipped_no_name += 1
            return None
        s = str(raw).strip()
        if not s:
            skipped_no_name += 1
            return None
        return s

    for district_id, filename, step in LOCALITY_WARD_SOURCES:
        # Filter to named rows BEFORE sampling, not after — several of these
        # sources (Belagavi, Raichur, Hubballi-Dharwad: checked directly)
        # have KGISWardNa null on most rows, so step-sampling the raw file
        # first would mostly select unusable unnamed wards.
        gdf = gpd.read_file(GEOJSON_DIR / filename)
        gdf = gdf[gdf["KGISWardNa"].notna()].iloc[::step]
        for _, row in gdf.iterrows():
            name = _clean_name(row["KGISWardNa"])
            if name and _is_polygonal(row.geometry):
                records.append((name, "Ward", district_id, row.geometry))

    bbmp = gpd.read_file(GEOJSON_DIR / "bbmp_ward_boundaries.geojson").iloc[::BBMP_SAMPLE_STEP]
    for _, row in bbmp.iterrows():
        name = _clean_name(row["KGISWardName"])
        if name and _is_polygonal(row.geometry):
            records.append((name, "Ward", "BLR", row.geometry))

    for district_id, filename in LOCALITY_TOWN_SOURCES:
        gdf = gpd.read_file(GEOJSON_DIR / filename)
        for _, row in gdf.iterrows():
            name = _clean_name(row["KGISTownNa"])
            if name and _is_polygonal(row.geometry):
                records.append((name.title(), "Town", district_id, row.geometry))

    for district_id, filename, step in LOCALITY_VILLAGE_FALLBACK_SOURCES:
        path = GEOJSON_DIR / filename
        if not path.exists():
            print(f"  WARNING: {filename} not found, skipping village fallback for {district_id}", file=sys.stderr)
            continue
        gdf = gpd.read_file(path).iloc[::step]
        for _, row in gdf.iterrows():
            name = _clean_name(row["KGISVill_2"])
            if name and _is_polygonal(row.geometry):
                records.append((name, "Village", district_id, row.geometry))

    if skipped_no_name:
        print(f"  {skipped_no_name} source features skipped (missing/blank name)", file=sys.stderr)

    inserted = 0
    skipped_bad_district = 0
    with connect() as conn:
        with conn.cursor() as cur:
            for name, locality_type, district_id, geom in records:
                if district_id not in valid_district_ids:
                    skipped_bad_district += 1
                    continue
                centroid = _safe_centroid(geom)
                aliases = _mechanical_aliases(name)
                cur.execute(
                    """
                    INSERT INTO localities
                        (locality_name, locality_type, district_id, aliases,
                         centroid, boundary, source)
                    VALUES (%s, %s, %s, %s,
                            ST_GeomFromText(%s, 4326)::geography,
                            ST_GeomFromText(%s, 4326)::geography, 'KGIS')
                    """,
                    (
                        name, locality_type, district_id, aliases or None,
                        centroid.wkt, _to_multipolygon_wkt(geom),
                    ),
                )
                inserted += 1
        conn.commit()

    if skipped_bad_district:
        print(f"  {skipped_bad_district} localities skipped (bad district_id)", file=sys.stderr)
    print(f"loaded {inserted} localities rows")

    # primary_station_id: nearest station in the same district (jurisdiction
    # Voronoi polygons don't exist yet at this point in §4's own ordering —
    # §4.6 runs after §4.4 — so this uses the simpler "nearest station in
    # unit" fallback path directly rather than the two-step
    # jurisdiction-boundary-aware version).
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE localities l
                SET primary_station_id = (
                    SELECT ps.station_id
                    FROM police_stations ps
                    WHERE ps.district_id = l.district_id
                    ORDER BY ps.geom <-> l.centroid
                    LIMIT 1
                )
                WHERE l.primary_station_id IS NULL
                """
            )
            updated = cur.rowcount
        conn.commit()
    print(f"assigned primary_station_id for {updated} localities")


# ============================================================
# sub_divisions / circles (SEED_RUNBOOK.md §4.5) — synthesized, no open
# dataset exists. Stations grouped into circles of 3-6, circles grouped into
# sub_divisions of 2-4, calibrated (not exactly matched) to the real
# statewide totals (~230 circles / ~91 sub-divisions).
#
# Grouping method: sort each district's stations by a latitude-banded key
# (round(lat, 1) then longitude) so sequential chunks are spatially
# contiguous-ish, then chunk into fixed-size groups. This is a simpler
# stand-in for the runbook's suggested k-means/taluk-based grouping — no new
# heavy dependency (scikit-learn) for what is synthesized administrative
# scaffolding, not demo-critical geometry. Voronoi jurisdiction generation
# (next function) is what actually needs to be spatially sound, and that
# uses real PostGIS ST_VoronoiPolygons, not this grouping.
# ============================================================

CIRCLE_TARGET_SIZE = 4.5  # stations per circle, within the 3-6 spec range
SUBDIVISION_TARGET_SIZE = 3  # circles per sub_division, within the 2-4 spec range


def _chunk(seq: list, size: int) -> list[list]:
    size = max(1, size)
    return [seq[i:i + size] for i in range(0, len(seq), size)]


def synthesize_sub_divisions_and_circles() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT district_id FROM districts ORDER BY district_id")
            all_districts = [r[0] for r in cur.fetchall()]

            total_circles = 0
            total_subdivisions = 0
            for district_id in all_districts:
                cur.execute(
                    "SELECT station_id, latitude, longitude FROM police_stations "
                    "WHERE district_id = %s ORDER BY round(latitude::numeric, 1), longitude",
                    (district_id,),
                )
                stations = cur.fetchall()
                if not stations:
                    continue

                n_circles = max(1, round(len(stations) / CIRCLE_TARGET_SIZE))
                circle_chunks = _chunk(stations, max(1, round(len(stations) / n_circles)))

                circle_ids = []
                for i, chunk in enumerate(circle_chunks, start=1):
                    circle_id = f"{district_id}-C{i:03d}"
                    circle_ids.append((circle_id, chunk))

                n_subdivisions = max(1, round(len(circle_ids) / SUBDIVISION_TARGET_SIZE))
                subdivision_chunks = _chunk(circle_ids, max(1, round(len(circle_ids) / n_subdivisions)))

                for i, sub_chunk in enumerate(subdivision_chunks, start=1):
                    subdivision_id = f"{district_id}-{i:02d}"
                    cur.execute(
                        "INSERT INTO sub_divisions (subdivision_id, subdivision_name, district_id) "
                        "VALUES (%s, %s, %s) ON CONFLICT (subdivision_id) DO NOTHING",
                        (subdivision_id, f"{district_id} Sub-Division {i}", district_id),
                    )
                    total_subdivisions += 1
                    for circle_id, station_rows in sub_chunk:
                        cur.execute(
                            "INSERT INTO circles (circle_id, circle_name, subdivision_id) "
                            "VALUES (%s, %s, %s) ON CONFLICT (circle_id) DO NOTHING",
                            (circle_id, f"{circle_id} Circle", subdivision_id),
                        )
                        total_circles += 1
                        station_ids = [s[0] for s in station_rows]
                        cur.execute(
                            "UPDATE police_stations SET circle_id = %s WHERE station_id = ANY(%s)",
                            (circle_id, station_ids),
                        )
        conn.commit()

    print(f"synthesized {total_subdivisions} sub_divisions, {total_circles} circles "
          f"(calibration targets: ~91 / ~230 statewide)")


# ============================================================
# jurisdiction_boundary (SEED_RUNBOOK.md §4.6) — Voronoi partition of each
# unit's station points, clipped to that unit's district polygon. Real
# PostGIS geometry, unlike the sub_division/circle scaffolding above.
# Commissionerate + parent-district stations are partitioned TOGETHER
# against the parent revenue-district polygon (per §4.6) to avoid
# gaps/overlaps between e.g. BLR and BLU, then the resulting cells are
# assigned back to whichever station they belong to (each station keeps its
# own already-assigned district_id in police_stations — this only touches
# jurisdiction_boundary, never district_id).
# ============================================================

# unit code -> the real district polygon (by source_polygon_name) whose
# extent its stations should be Voronoi-clipped against. Commissionerates
# share their parent's polygon (no true carve-out, per §4.2); their
# stations are pooled into the SAME Voronoi run as the parent so the two
# unit's cells tile one shared area without overlap.
def _voronoi_polygon_groups() -> dict[str, list[str]]:
    """Returns {source_polygon_name: [unit_codes sharing that polygon]}."""
    with DISTRICT_UNITS_CSV.open() as f:
        rows = list(csv.DictReader(f))
    groups: dict[str, list[str]] = {}
    for r in rows:
        groups.setdefault(r["source_polygon_name"], []).append(r["district_id"])
    return groups


def generate_jurisdiction_boundaries() -> None:
    groups = _voronoi_polygon_groups()
    district_gdf = gpd.read_file(GEOJSON_DIR / "admin_boundaries__district.geojson")
    poly_by_name = dict(zip(district_gdf["KGISDist_1"], district_gdf.geometry))

    total_updated = 0
    with connect() as conn:
        with conn.cursor() as cur:
            # Default statement_timeout is too short for ST_VoronoiPolygons
            # over the larger station groups (e.g. Bengaluru's combined
            # BLR+BLU+BLD+BLS pool, ~330+ points) — raise it for this
            # session only.
            cur.execute("SET statement_timeout = '300s';")
            for source_name, unit_codes in groups.items():
                clip_poly = poly_by_name.get(source_name)
                if clip_poly is None:
                    continue
                cur.execute(
                    "SELECT station_id FROM police_stations WHERE district_id = ANY(%s)",
                    (unit_codes,),
                )
                station_ids = [r[0] for r in cur.fetchall()]
                if len(station_ids) < 2:
                    # ST_VoronoiPolygons needs >=2 points to produce a
                    # partition; a single-station unit just gets the whole
                    # clip polygon as its one jurisdiction cell.
                    if len(station_ids) == 1:
                        cur.execute(
                            """
                            UPDATE police_stations
                            SET jurisdiction_boundary = ST_Multi(ST_GeomFromText(%s, 4326))::geography
                            WHERE station_id = %s
                            """,
                            (clip_poly.wkt, station_ids[0]),
                        )
                        total_updated += 1
                    continue

                # ST_VoronoiPolygons + ST_Intersection with the clip polygon,
                # then match each resulting cell back to its generating
                # station via ST_Contains on the station's own point.
                cur.execute(
                    """
                    WITH pts AS (
                        SELECT station_id, ST_SetSRID(ST_MakePoint(longitude, latitude), 4326) AS pt
                        FROM police_stations WHERE station_id = ANY(%s)
                    ),
                    collected AS (
                        SELECT ST_Collect(pt) AS geom FROM pts
                    ),
                    voronoi AS (
                        SELECT (ST_Dump(ST_VoronoiPolygons(geom))).geom AS cell FROM collected
                    ),
                    clipped AS (
                        SELECT ST_Intersection(cell, ST_GeomFromText(%s, 4326)) AS cell
                        FROM voronoi
                    )
                    SELECT pts.station_id, ST_AsText(ST_Multi(clipped.cell))
                    FROM clipped
                    JOIN pts ON ST_Contains(clipped.cell, pts.pt)
                    """,
                    (station_ids, clip_poly.wkt),
                )
                results = cur.fetchall()
                for station_id, cell_wkt in results:
                    cur.execute(
                        """
                        UPDATE police_stations
                        SET jurisdiction_boundary = ST_GeomFromText(%s, 4326)::geography
                        WHERE station_id = %s
                        """,
                        (cell_wkt, station_id),
                    )
                    total_updated += 1
        conn.commit()

    print(f"generated jurisdiction_boundary for {total_updated} stations")


if __name__ == "__main__":
    if "--districts" in sys.argv or "--all" in sys.argv:
        load_districts()
    if "--admin-boundaries" in sys.argv or "--all" in sys.argv:
        load_admin_boundaries()
    if "--police-stations" in sys.argv or "--all" in sys.argv:
        load_police_stations()
    if "--localities" in sys.argv or "--all" in sys.argv:
        load_localities()
    if "--sub-divisions-circles" in sys.argv or "--all" in sys.argv:
        synthesize_sub_divisions_and_circles()
    if "--jurisdiction" in sys.argv or "--all" in sys.argv:
        generate_jurisdiction_boundaries()
