#!/usr/bin/env python3
"""One-off retrofit: relocating KA-MDY-006 out of the Metagalli-area corridor
(fix_mdy_containment.py, to satisfy real district-boundary containment)
dropped Thread A's second DBSCAN cluster from 4 to 3 members — KA-MDY-006
had been an unintentional border point propping it up to the schema's
"concentrate >=4 points each in 2 corridor localities" requirement.

KA-MYS-009 ("s_0", a MYS-district scattered/noise point per the original
design, station KA-MYS-026) is relocated into the Metagalli cluster's
vicinity instead — legitimate because it's already MYS-district, so this
doesn't reintroduce a cross-district containment violation the way leaving
KA-MDY-006 in place did.
"""

from geo_helpers import bearing_distance, format_direction_distance, resolve_locality
from db import connect

FIR_ID = "KA-MYS-009-2026-0009"
CLUSTER_2_CENTER = (12.3360, 76.6460)  # "near Metagalli" — matches 03_synthetic.py's constant


def jitter_point(lat: float, lon: float, max_meters: float, seed: str) -> tuple[float, float]:
    import math
    import random

    rng = random.Random(seed)
    r = max_meters * math.sqrt(rng.random())
    theta = rng.random() * 2 * math.pi
    dlat = (r * math.cos(theta)) / 111_000
    dlon = (r * math.sin(theta)) / (111_000 * math.cos(math.radians(lat)))
    return round(lat + dlat, 6), round(lon + dlon, 6)


def main() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT station_name, latitude, longitude FROM police_stations WHERE station_id = 'KA-MYS-026'")
            station_name, station_lat, station_lon = cur.fetchone()
            station_lat, station_lon = float(station_lat), float(station_lon)

            lat, lon = jitter_point(*CLUSTER_2_CENTER, 300, seed=f"{FIR_ID}:relocate")

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
    print(f"Relocated {FIR_ID} to ({lat}, {lon}) near Metagalli cluster")


if __name__ == "__main__":
    main()
