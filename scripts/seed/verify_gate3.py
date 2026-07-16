#!/usr/bin/env python3
"""Stage 3 (SEED_RUNBOOK.md §10 Gate 3) verification — row counts and
spot-checks. Read-only; prints a summary for human review.
"""

from __future__ import annotations

from db import connect

ACTIVE_UNITS = ["BLR", "MYS", "MDY", "HBL", "MNG", "BGV", "TMK", "KDG", "CKM", "RCH"]


def main() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            for table in [
                "districts", "admin_boundaries", "police_stations", "localities",
                "sub_divisions", "circles", "bns_sections", "district_socioeconomic",
            ]:
                cur.execute(f"SELECT count(*) FROM {table}")
                print(f"{table}: {cur.fetchone()[0]}")

            print()
            cur.execute(
                "SELECT count(*) FROM police_stations WHERE jurisdiction_boundary IS NOT NULL"
            )
            print(f"police_stations with jurisdiction_boundary: {cur.fetchone()[0]}")
            cur.execute("SELECT count(*) FROM police_stations WHERE circle_id IS NOT NULL")
            print(f"police_stations with circle_id: {cur.fetchone()[0]}")

            print()
            print("--- active unit station counts ---")
            cur.execute(
                "SELECT district_id, count(*) FROM police_stations "
                "WHERE district_id = ANY(%s) GROUP BY district_id ORDER BY district_id",
                (ACTIVE_UNITS,),
            )
            for row in cur.fetchall():
                print(" ", row)

            print()
            print("--- Thread A required station ---")
            cur.execute(
                "SELECT station_id, station_name, district_id FROM police_stations "
                "WHERE station_id = 'KA-MYS-012'"
            )
            print(" ", cur.fetchone())

            print()
            print("--- geometry sanity: any FIR-eligible station outside its district polygon? ---")
            cur.execute(
                """
                SELECT count(*) FROM police_stations ps
                JOIN admin_boundaries ab ON ab.boundary_type = 'District'
                    AND ab.ref_district_id = ps.district_id
                WHERE NOT ST_Contains(ab.geom::geometry, ps.geom::geometry)
                """
            )
            print(f"  stations outside their own district polygon: {cur.fetchone()[0]}")

            print()
            print("--- spot-check 5 stations (name, coords, type, district) ---")
            cur.execute(
                "SELECT station_name, latitude, longitude, station_type, district_id "
                "FROM police_stations ORDER BY random() LIMIT 5"
            )
            for row in cur.fetchall():
                print(" ", row)


if __name__ == "__main__":
    main()
