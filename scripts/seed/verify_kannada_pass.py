#!/usr/bin/env python3
from db import connect

with connect() as conn:
    with conn.cursor() as cur:
        checks = [
            ("police_stations", "station_name_kn"), ("admin_boundaries", "name_kn"),
            ("crime_types", "crime_type_name_kn"), ("mo_codes", "mo_description_kn"),
            ("localities", "locality_name_kn"), ("gangs", "gang_name_kn"),
            ("events_calendar", "event_name_kn"), ("firs", "complaint_text_kn"),
            ("fir_victims", "victim_statement_kn"), ("case_diary_entries", "entry_text_kn"),
            ("ncr_petitions", "petition_text_kn"), ("stolen_property", "description_kn"),
            ("seizures", "items_description_kn"),
        ]
        for tbl, col in checks:
            cur.execute(f"SELECT count(*), count({col}) FROM {tbl}")
            total, pop = cur.fetchone()
            print(f"{tbl}.{col}: {pop}/{total} = {pop/total*100:.0f}%")
        print()
        cur.execute("SELECT station_name, station_name_kn FROM police_stations LIMIT 5")
        for r in cur.fetchall():
            print(r)
        print()
        cur.execute("SELECT crime_type_name, crime_type_name_kn FROM crime_types LIMIT 5")
        for r in cur.fetchall():
            print(r)
        print()
        cur.execute("SELECT fir_id, complaint_text, complaint_text_kn FROM firs LIMIT 1")
        print(cur.fetchone())
