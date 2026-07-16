#!/usr/bin/env python3
"""Stage 1 — normalize dataset/ into seed-sources/ (SEED_RUNBOOK.md §2).

Converts every spatial source (Shapefile ZIPs, extension-less KML files,
existing GeoJSON) into seed-sources/geojson/*.geojson, always forcing
EPSG:4326 reprojection. Never hand-parses KML/Shapefile — ogr2ogr only.

Read-only with respect to dataset/ — never mutates the source tree. Emits
seed-sources/report.json and stops (Gate 1 in SEED_RUNBOOK.md §10); does not
touch the database. A human reviews the report before Stage 2 runs.

Usage:
    python 00_normalize_sources.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import geopandas as gpd
from shapely import make_valid

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO_ROOT / "dataset"
OUT_DIR = REPO_ROOT / "seed-sources"
GEOJSON_DIR = OUT_DIR / "geojson"
TARGET_CRS = "EPSG:4326"


@dataclass
class SourceReport:
    name: str
    input_path: str
    input_format: str
    input_crs: Optional[str]
    output_path: str
    feature_count: int
    geometry_types: list[str]
    attribute_columns: list[str]
    invalid_geometry_count: int
    fixed_geometry_count: int
    ok: bool
    error: Optional[str] = None


def _missing_report(name: str, path: Path, fmt: str, error: str) -> SourceReport:
    return SourceReport(
        name=name,
        input_path=str(path),
        input_format=fmt,
        input_crs=None,
        output_path="",
        feature_count=0,
        geometry_types=[],
        attribute_columns=[],
        invalid_geometry_count=0,
        fixed_geometry_count=0,
        ok=False,
        error=error,
    )


def _run_ogr2ogr(args: list[str]) -> None:
    result = subprocess.run(["ogr2ogr", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ogr2ogr failed: {' '.join(args)}\n{result.stderr}")


def _shapefile_crs(shp_path: Path) -> Optional[str]:
    """Lightweight CRS read (metadata only, no geometry load) via pyogrio."""
    try:
        import pyogrio

        info = pyogrio.read_info(str(shp_path))
        crs = info.get("crs")
        return str(crs) if crs else None
    except Exception:
        return None


def _fix_geometries(geojson_path: Path) -> int:
    """Run shapely.make_valid() over every invalid feature; rewrite if any fixed.

    ST_MakeValid also runs again at DB-load time (Stage 3) per runbook §2.4 —
    "do both, cheaply". Returns the invalid-geometry count found (pre-fix).
    """
    gdf = gpd.read_file(geojson_path)
    if gdf.geometry.isna().all():
        return 0
    invalid_mask = ~gdf.geometry.is_valid & gdf.geometry.notna()
    invalid_count = int(invalid_mask.sum())
    if invalid_count > 0:
        gdf.loc[invalid_mask, gdf.geometry.name] = gdf.loc[
            invalid_mask, gdf.geometry.name
        ].apply(make_valid)
        gdf.to_file(geojson_path, driver="GeoJSON")
    return invalid_count


def _report_from_output(
    name: str, src_path: Path, input_format: str, input_crs: Optional[str], out_path: Path
) -> SourceReport:
    gdf = gpd.read_file(out_path)
    feature_count = len(gdf)
    geom_col = gdf.geometry.name if "geometry" in gdf.columns or gdf.geometry is not None else None
    geometry_types = (
        sorted(set(gdf.geometry.geom_type.dropna().unique().tolist())) if geom_col else []
    )
    attribute_columns = [c for c in gdf.columns if c != geom_col]
    invalid_count = _fix_geometries(out_path)
    ok = feature_count > 0 and (len(geometry_types) > 0 or geom_col is None)
    error = None if ok else "0 features or no geometry present"
    return SourceReport(
        name=name,
        input_path=str(src_path),
        input_format=input_format,
        input_crs=input_crs,
        output_path=str(out_path),
        feature_count=feature_count,
        geometry_types=geometry_types,
        attribute_columns=attribute_columns,
        invalid_geometry_count=invalid_count,
        fixed_geometry_count=invalid_count,
        ok=ok,
        error=error,
    )


def convert_shapefile_zip(zip_path: Path, out_name: str) -> SourceReport:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp_path)
        shp_files = list(tmp_path.rglob("*.shp"))
        if not shp_files:
            return _missing_report(out_name, zip_path, "shapefile", "no .shp found in zip")
        shp_path = shp_files[0]
        input_crs = _shapefile_crs(shp_path)
        if input_crs is None:
            # Runbook §2.6: fail loudly if a CRS could not be determined at all —
            # rather than let ogr2ogr's -t_srs silently reinterpret raw coordinates.
            return _missing_report(
                out_name, zip_path, "shapefile", "could not determine input CRS (.prj missing?)"
            )
        out_path = GEOJSON_DIR / f"{out_name}.geojson"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        _run_ogr2ogr(["-f", "GeoJSON", "-t_srs", TARGET_CRS, str(out_path), str(shp_path)])
        return _report_from_output(out_name, zip_path, "shapefile", input_crs, out_path)


def is_kml_content(path: Path) -> bool:
    try:
        head = path.read_bytes()[:2000]
    except Exception:
        return False
    return b"<kml" in head.lower()


def convert_kml_content(src_path: Path, out_name: str) -> SourceReport:
    """src_path has no .kml extension but is KML content — force -if so
    ogr2ogr's driver auto-detection (which relies on file extension) doesn't
    silently skip it. KML is defined to always be WGS84 (EPSG:4326) per spec.

    Uses the LIBKML driver, not the classic KML driver: these sources carry
    their real attributes (e.g. station name) inside
    <ExtendedData><SchemaData><SimpleData> per-placemark, which the classic
    KML driver does not surface as fields at all (it only reads the plain
    <name>/<description> tags, both empty in this dataset) — LIBKML is
    schema-aware and maps SimpleData fields to real attribute columns.
    """
    out_path = GEOJSON_DIR / f"{out_name}.geojson"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run_ogr2ogr(
        ["-f", "GeoJSON", "-t_srs", TARGET_CRS, "-if", "LIBKML", str(out_path), str(src_path)]
    )
    return _report_from_output(out_name, src_path, "kml", "EPSG:4326", out_path)


def convert_geojson(src_path: Path, out_name: str) -> SourceReport:
    """GeoJSON is defined to always be WGS84 (RFC 7946) — still routed through
    ogr2ogr for consistency with the other sources and to normalize output shape.
    """
    out_path = GEOJSON_DIR / f"{out_name}.geojson"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run_ogr2ogr(["-f", "GeoJSON", "-t_srs", TARGET_CRS, str(out_path), str(src_path)])
    return _report_from_output(out_name, src_path, "geojson", "EPSG:4326", out_path)


def main() -> int:
    GEOJSON_DIR.mkdir(parents=True, exist_ok=True)
    reports: list[SourceReport] = []

    # 1. administrative_boundaries — top-level single zips (State/District/Taluk)
    admin_dir = DATASET_DIR / "administrative_boundaries"
    for zip_name, out_name in [
        ("State.zip", "admin_boundaries__state"),
        ("District.zip", "admin_boundaries__district"),
        ("Taluk.zip", "admin_boundaries__taluk"),
    ]:
        zip_path = admin_dir / zip_name
        if zip_path.exists():
            reports.append(convert_shapefile_zip(zip_path, out_name))
        else:
            reports.append(_missing_report(out_name, zip_path, "shapefile", "file not found"))

    # 2. administrative_boundaries — per-district subdirs (Village/Hobli/Town/Ward)
    for subdir_name, prefix in [
        ("Village_boundaries", "village_boundaries"),
        ("hobli_boundaries", "hobli_boundaries"),
        ("Town_boundaries", "town_boundaries"),
        ("ward_boundaries", "ward_boundaries"),
    ]:
        subdir = admin_dir / subdir_name
        if not subdir.exists():
            continue
        for zip_path in sorted(subdir.glob("*.zip")):
            out_name = f"{prefix}__{zip_path.stem}"
            reports.append(convert_shapefile_zip(zip_path, out_name))

    # 3. police station / traffic police KML (files carry no extension)
    for subdir_name, prefix in [
        ("police_station_locations", "police_stations"),
        ("traffic_police_stations", "traffic_police_stations"),
    ]:
        subdir = DATASET_DIR / subdir_name
        if not subdir.exists():
            continue
        for src_path in sorted(subdir.iterdir()):
            if not src_path.is_file() or not is_kml_content(src_path):
                continue
            out_name = f"{prefix}__{src_path.stem or src_path.name}"
            reports.append(convert_kml_content(src_path, out_name))

    # 4. BBMP ward boundaries geojson
    bbmp_path = DATASET_DIR / "BBMP_ward_boundaries.geojson"
    if bbmp_path.exists():
        reports.append(convert_geojson(bbmp_path, "bbmp_ward_boundaries"))
    else:
        reports.append(_missing_report("bbmp_ward_boundaries", bbmp_path, "geojson", "file not found"))

    report = {"target_crs": TARGET_CRS, "sources": [asdict(r) for r in reports]}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUT_DIR / "report.json"
    report_path.write_text(json.dumps(report, indent=2))

    failures = [r for r in reports if not r.ok]
    print(f"normalized {len(reports)} sources -> {GEOJSON_DIR}")
    print(f"report written to {report_path}")
    if failures:
        print(f"\n{len(failures)} source(s) FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f.name}: {f.error}", file=sys.stderr)
        return 1
    print("all sources OK. Human review required before Stage 2 (Gate 1, SEED_RUNBOOK.md §10).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
