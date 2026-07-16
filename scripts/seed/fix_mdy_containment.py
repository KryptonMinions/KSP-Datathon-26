#!/usr/bin/env python3
"""One-off retrofit: FIR KA-MDY-006-2026-0006 (Thread A, station KA-MDY-023
"Mandya Rural PS") was seeded with an incident point jittered around the
Mysuru-side "Metagalli Ring Road" cluster center — 33km from its own
station and 4.35km outside the Mandya district polygon. Found by
05_validate.py check "firs.geom contained within its district boundary".

This FIR was one of Thread A's "remainder scattered along the corridor"
points (not part of either of the 2 required 4+-point DBSCAN clusters), so
relocating it doesn't affect the hotspot guarantee — verified by re-running
the cluster check after this UPDATE.

Relocates the point to a small jitter around the station's own (real,
already-verified-inside-Mandya) coordinates, and recomputes the
locality/direction-distance fields that depend on position.
"""

from datetime import timedelta

from db import connect
from geo_helpers import bearing_distance, format_direction_distance, resolve_locality

FIR_ID = "KA-MDY-006-2026-0006"
STATION_ID = "KA-MDY-023"


def jitter_point(lat: float, lon: float, max_meters: float, seed: str) -> tuple[float, float]:
    import math
    import random

    rng = random.Random(seed)
    r = max_meters * math.sqrt(rng.random())
    theta = rng.random() * 2 * math.pi
    dlat = (r * math.cos(theta)) / 111_000
    dlon = (r * math.sin(theta)) / (111_000 * math.cos(math.radians(lat)))
    return round(lat + dlat, 6), round(lon + dlon, 6)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math

    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def main() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT station_name, latitude, longitude FROM police_stations WHERE station_id = %s", (STATION_ID,))
            station_name, station_lat, station_lon = cur.fetchone()
            station_lat, station_lon = float(station_lat), float(station_lon)

            # KA-MDY-011 (the thread's other MDY FIR) sits essentially at the
            # station's own exact coordinates — the first relocation attempt
            # jittered too close to it (within DBSCAN's 800m eps), turning
            # two intended "noise" points into an unintended micro-cluster.
            # Require >2km separation from it, not just "inside Mandya".
            cur.execute("SELECT latitude, longitude FROM firs WHERE fir_id = 'KA-MDY-011-2026-0011'")
            other_lat, other_lon = (float(v) for v in cur.fetchone())

            for attempt in range(20):
                lat, lon = jitter_point(station_lat, station_lon, 4000, seed=f"{FIR_ID}:relocate:{attempt}")
                cur.execute(
                    "SELECT ST_Contains(ab.geom::geometry, ST_SetSRID(ST_MakePoint(%s, %s), 4326)) "
                    "FROM admin_boundaries ab WHERE ab.ref_district_id = 'MDY' AND ab.boundary_type = 'District'",
                    (lon, lat),
                )
                (inside,) = cur.fetchone()
                far_enough = haversine_m(lat, lon, other_lat, other_lon) > 2000
                if inside and far_enough:
                    break
            else:
                raise RuntimeError("could not find a point inside MDY, >2km from KA-MDY-011, after 20 attempts")

            locality_id, locality_name = resolve_locality(cur, lat, lon, {})
            distance_km, compass = bearing_distance(station_lat, station_lon, lat, lon)
            direction_distance = format_direction_distance(distance_km, compass)
            incident_location = f"{locality_name}, {station_name.replace(' PS', '')} jurisdiction"

            cur.execute(
                """
                UPDATE firs SET
                    latitude = %s, longitude = %s, incident_location = %s,
                    incident_locality_id = %s, direction_distance_from_ps = %s
                WHERE fir_id = %s
                """,
                (lat, lon, incident_location, locality_id, direction_distance, FIR_ID),
            )
        conn.commit()
    print(f"Relocated {FIR_ID} to ({lat}, {lon}) near {station_name} — now inside MDY boundary")


if __name__ == "__main__":
    main()
