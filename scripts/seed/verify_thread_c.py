#!/usr/bin/env python3
"""Verification for Thread C (Dasara Bandobast)."""

from db import connect

with connect() as conn:
    with conn.cursor() as cur:
        # DBSCAN cluster guarantee: eps 250m, minpoints 3, expect 2 clusters
        cur.execute(
            """
            SELECT cluster_id, count(*) FROM (
                SELECT DISTINCT f.fir_id,
                       ST_ClusterDBSCAN(f.geom::geometry, eps := 250.0/111320, minpoints := 3) OVER () AS cluster_id
                FROM firs f
                WHERE f.station_id IN ('KA-MYS-007', 'KA-MYS-001') AND f.crime_type_id IN ('THEFT-PICKPOCKET', 'SNATCHING-CHAIN')
                  AND f.registration_date < '2026-07-14'
            ) sub GROUP BY cluster_id ORDER BY cluster_id NULLS LAST
            """
        )
        print("Thread C DBSCAN clusters (cluster_id, point count):", cur.fetchall())
        print()

        # Bannimantap year-over-year trend
        cur.execute(
            """
            SELECT extract(year from registration_date) AS yr, l.locality_name, count(*)
            FROM firs f JOIN localities l ON l.locality_id = f.incident_locality_id
            WHERE l.locality_name IN ('K.R. Circle', 'Bannimantap')
            GROUP BY yr, l.locality_name ORDER BY yr, l.locality_name
            """
        )
        print("Per-year, per-locality FIR counts:")
        for row in cur.fetchall():
            print(" ", row)
        print()

        # Ring gang + membership
        cur.execute("SELECT gang_id, gang_name, known_strength FROM gangs WHERE gang_name = 'Bannimantap Pickpocket Ring'")
        gang_row = cur.fetchone()
        print("Gang:", gang_row)
        cur.execute(
            "SELECT p.full_name, gm.role_in_gang FROM gang_memberships gm JOIN persons p ON p.person_id = gm.person_id "
            "WHERE gm.gang_id = %s", (gang_row[0],)
        )
        print("Members:", cur.fetchall())
        print()

        # Ring FIRs / MO-THEFT-021 coverage
        cur.execute(
            """
            SELECT count(DISTINCT f.fir_id) FROM firs f
            JOIN fir_accused fa ON fa.fir_id = f.fir_id
            JOIN gang_memberships gm ON gm.person_id = fa.person_id AND gm.gang_id = %s
            """,
            (gang_row[0],),
        )
        print("FIRs with >=1 ring member as accused:", cur.fetchone())

        cur.execute(
            """
            SELECT count(DISTINCT f.fir_id) FROM firs f
            JOIN fir_accused fa ON fa.fir_id = f.fir_id
            JOIN gang_memberships gm ON gm.person_id = fa.person_id AND gm.gang_id = %s
            WHERE f.mo_code_id != 'MO-THEFT-021' OR f.mo_code_id IS NULL
            """,
            (gang_row[0],),
        )
        print("Ring FIRs NOT carrying MO-THEFT-021 (should be 0):", cur.fetchone())
        print()

        # known_associates Confirmed edges among ring members
        cur.execute(
            """
            SELECT p1.full_name, p2.full_name, ka.first_seen_fir_id FROM known_associates ka
            JOIN persons p1 ON p1.person_id = ka.person_id_a
            JOIN persons p2 ON p2.person_id = ka.person_id_b
            WHERE ka.association_type = 'Co_Accused' AND ka.confidence = 'Confirmed'
              AND p1.full_name IN ('Puttaraju M','Chandregowda K','Nataraj B','Somashekar R')
            """
        )
        print("Ring known_associates edges:")
        for row in cur.fetchall():
            print(" ", row)
        print()

        # events_calendar
        cur.execute(
            "SELECT event_name, event_date_start, historical_incident_count, expected_footfall FROM events_calendar "
            "WHERE event_name = 'Mysuru Dasara Procession' ORDER BY event_date_start"
        )
        print("events_calendar rows:")
        for row in cur.fetchall():
            print(" ", row)
        print()

        # Representative FIR (fully dressed) + seizure
        cur.execute(
            """
            SELECT f.fir_id, count(DISTINCT fa.person_id), count(DISTINCT cde.entry_id), count(DISTINCT fv.fir_victim_id)
            FROM firs f
            LEFT JOIN fir_accused fa ON fa.fir_id = f.fir_id
            LEFT JOIN case_diary_entries cde ON cde.fir_id = f.fir_id
            LEFT JOIN fir_victims fv ON fv.fir_id = f.fir_id
            WHERE f.fir_id = 'KA-MYS-626-2026-6026'
            GROUP BY f.fir_id
            """
        )
        print("Representative FIR (accused, diary entries, victims):", cur.fetchone())
        cur.execute("SELECT seizure_id, items_description FROM seizures WHERE fir_id = 'KA-MYS-626-2026-6026'")
        print("Seizure:", cur.fetchone())
        cur.execute("SELECT count(*) FROM stolen_property WHERE fir_id = 'KA-MYS-626-2026-6026' AND is_recovered = TRUE")
        print("Recovered phones:", cur.fetchone())
        print()

        # Null-field sanity check across all Thread C FIRs
        cur.execute(
            """
            SELECT count(*) FILTER (WHERE mo_description_free IS NULL) AS null_mo,
                   count(*) FILTER (WHERE complaint_text IS NULL) AS null_complaint,
                   count(*) FILTER (WHERE incident_locality_id IS NULL) AS null_locality,
                   count(*) FILTER (WHERE direction_distance_from_ps IS NULL) AS null_dist,
                   count(*) AS total
            FROM firs WHERE station_id IN ('KA-MYS-007','KA-MYS-001') AND crime_type_id IN ('THEFT-PICKPOCKET','SNATCHING-CHAIN')
              AND registration_date < '2026-07-14'
            """
        )
        print("Null-field check (should be 0,0,0,0,27):", cur.fetchone())
