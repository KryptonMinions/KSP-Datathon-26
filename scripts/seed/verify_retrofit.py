#!/usr/bin/env python3
"""Verification for the Thread A narrative retrofit."""

from db import connect

with connect() as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT cluster_id, count(*) FROM (
                SELECT DISTINCT f.fir_id,
                       ST_ClusterDBSCAN(f.geom::geometry, eps := 800.0/111320, minpoints := 3) OVER () AS cluster_id
                FROM firs f
                JOIN fir_accused fa ON fa.fir_id = f.fir_id
                JOIN gang_memberships gm ON gm.person_id = fa.person_id
                JOIN gangs g ON g.gang_id = gm.gang_id AND g.gang_name = 'Mysuru Chain Gang'
            ) sub GROUP BY cluster_id ORDER BY cluster_id NULLS LAST
            """
        )
        print("DBSCAN clusters (cluster_id, point count):", cur.fetchall())
        print()

        cur.execute("SELECT count(*) FROM firs WHERE mo_description_free IS NOT NULL")
        print("mo_description_free populated:", cur.fetchone())

        cur.execute(
            "SELECT count(*) FROM firs WHERE incident_locality_id IS NOT NULL "
            "AND info_received_ts IS NOT NULL AND gd_entry_number IS NOT NULL "
            "AND direction_distance_from_ps IS NOT NULL"
        )
        print("FORM IF-1 fields populated (all 4 checked):", cur.fetchone())

        cur.execute(
            "SELECT fir_id, direction_distance_from_ps, information_type, beat_number "
            "FROM firs ORDER BY fir_id LIMIT 3"
        )
        print("sample FORM IF-1 values:")
        for row in cur.fetchall():
            print(" ", row)

        print()
        cur.execute("SELECT fir_id, complaint_text FROM firs WHERE mo_code_id = 'MO-ROB-004' ORDER BY fir_id")
        print("complaint_text for the 6 MO-ROB-004 FIRs:")
        for fir_id, text in cur.fetchall():
            print(f"  {fir_id}: {text[:100]}...")
