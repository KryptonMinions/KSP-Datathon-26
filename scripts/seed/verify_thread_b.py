#!/usr/bin/env python3
"""Verification for Thread B (The Repeat Victim)."""

from db import connect

with connect() as conn:
    with conn.cursor() as cur:
        # DBSCAN cluster guarantee: eps 600m, minpoints 4, expect 2 clusters (Jayanagar + J.P. Nagar)
        cur.execute(
            """
            SELECT cluster_id, count(*) FROM (
                SELECT DISTINCT f.fir_id,
                       ST_ClusterDBSCAN(f.geom::geometry, eps := 600.0/111320, minpoints := 4) OVER () AS cluster_id
                FROM firs f
                WHERE f.station_id IN ('KA-BLR-050', 'KA-BLR-051')
            ) sub GROUP BY cluster_id ORDER BY cluster_id NULLS LAST
            """
        )
        print("Thread B DBSCAN clusters (cluster_id, point count):", cur.fetchall())
        print()

        # MO-THEFT-011 count
        cur.execute("SELECT count(*) FROM firs WHERE mo_code_id = 'MO-THEFT-011'")
        print("MO-THEFT-011 FIR count:", cur.fetchone())

        cur.execute("SELECT fir_id, station_id, crime_type_id FROM firs WHERE mo_code_id = 'MO-THEFT-011' ORDER BY fir_id")
        for row in cur.fetchall():
            print(" ", row)
        print()

        # Savitha escalation timeline
        cur.execute(
            """
            SELECT p.person_id, p.full_name FROM persons p WHERE p.full_name ILIKE '%Savitha%'
            """
        )
        print("Savitha person row:", cur.fetchall())

        cur.execute(
            """
            SELECT petition_id, petition_type, received_date, status, escalated_fir_id FROM ncr_petitions
            ORDER BY received_date
            """
        )
        print("NCR/Petition timeline:")
        for row in cur.fetchall():
            print(" ", row)
        print()

        # Vehicle recovery
        cur.execute(
            "SELECT registration_number, is_recovered, recovery_date FROM vehicles ORDER BY registration_number"
        )
        print("Vehicles:")
        for row in cur.fetchall():
            print(" ", row)
        print()

        # Receiver network
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='known_associates' ORDER BY ordinal_position")
        print("known_associates columns:", [r[0] for r in cur.fetchall()])
        cur.execute(
            """
            SELECT ka.association_type, p1.full_name, p2.full_name, ka.first_seen_fir_id
            FROM known_associates ka
            JOIN persons p1 ON p1.person_id = ka.person_id_a
            JOIN persons p2 ON p2.person_id = ka.person_id_b
            WHERE ka.association_type = 'Known_Receiver'
            """
        )
        print("Known_Receiver edges:")
        for row in cur.fetchall():
            print(" ", row)
        print()

        # Missing person
        cur.execute(
            """
            SELECT p.full_name, mp.status, mp.locality_id, mp.last_seen_date, mp.traced_date
            FROM missing_persons mp JOIN persons p ON p.person_id = mp.person_id
            """
        )
        print("Missing persons:", cur.fetchall())
        print()

        # complaint_text diversity spot-check for Thread B FIRs
        cur.execute(
            "SELECT fir_id, complaint_text FROM firs WHERE station_id IN ('KA-BLR-050','KA-BLR-051') ORDER BY fir_id"
        )
        print("Thread B complaint_text samples:")
        for fir_id, text in cur.fetchall():
            print(f"  {fir_id}: {text[:90]}...")
