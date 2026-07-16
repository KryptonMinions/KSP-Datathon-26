#!/usr/bin/env python3
"""One-off retrofit: 3 Thread B vehicles (Ashwin Kumar's, Ravikiran M's,
Prashanth Kumar's) were marked is_recovered=TRUE via a plain UPDATE during
the original thread_b_firs() build, without the full seizure/mahazar
treatment given to Savitha's vehicle in thread_b_recovery(). Found by
05_validate.py check 1 ("every recovered vehicle has a linked seizures
row"). Backfills a minimal seizures row for each, reusing the same 2
panch witnesses (Muniraju K / Lakshmamma) already seeded for Savitha's
recovery.
"""

import uuid

from db import connect
from narrative_gen import generate_narrative

VEHICLES = [
    # (vehicle_id, fir_id, reg_number, make, model, color, station_id, locality_id, lat, lon)
    ("49ee14cc-f939-4875-b9a2-6dd408b6ba61", "KA-BLR-102-2026-1002", "KA-03-HN-2210", "TVS", "Jupiter", "Blue",
     "KA-BLR-050", "4238c93d-fe13-44f7-9138-a5f304b4a711", 12.929312, 77.581648),
    ("1cfa2ebe-40b9-4861-a22e-cb415c5041a7", "KA-BLR-103-2026-1003", "KA-04-EQ-8834", "Honda", "Activa", "Black",
     "KA-BLR-050", "4238c93d-fe13-44f7-9138-a5f304b4a711", 12.929926, 77.582369),
    ("e88acfa2-76ed-4f45-bf20-3edac132bf79", "KA-BLR-107-2026-1007", "KA-05-PL-6612", "Suzuki", "Access", "White",
     "KA-BLR-051", "c01341a7-2053-4fe0-af3c-4ec4711c43fe", 12.912889, 77.586515),
]


def main() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT person_id FROM persons WHERE full_name = 'Muniraju K'")
            pancha1 = cur.fetchone()[0]
            cur.execute("SELECT person_id FROM persons WHERE full_name = 'Lakshmamma'")
            pancha2 = cur.fetchone()[0]

            for i, (vehicle_id, fir_id, reg, make, model, color, station_id, locality_id, lat, lon) in enumerate(VEHICLES):
                cur.execute("SELECT recovery_date FROM vehicles WHERE vehicle_id = %s", (vehicle_id,))
                recovery_date = cur.fetchone()[0]

                seizure_id = str(uuid.uuid4())
                items_desc = generate_narrative(
                    "seizures", seizure_id, "items_description",
                    f"Write a 2-sentence mahazar (seizure panchnama) items description in English for the "
                    f"recovery of a stolen {color.lower()} {make} {model} scooter, registration {reg}, from a "
                    f"suspect's residence, in the presence of two independent panch witnesses.",
                    temperature=0.6, force_kn=False,
                ).text_en
                cur.execute(
                    """
                    INSERT INTO seizures
                        (seizure_id, fir_id, mahazar_number, seizure_type, seizure_date, seizure_location,
                         locality_id, latitude, longitude, location_precision, geocode_source, geocode_confidence,
                         pancha_1_person_id, pancha_2_person_id, items_description, linked_vehicle_id,
                         muddemal_number, custody_status)
                    VALUES (%s, %s, %s, 'Vehicle', %s, %s, %s, %s, %s, 'locality', 'gazetteer', 0.75, %s, %s, %s, %s, %s, 'In_Custody')
                    """,
                    (seizure_id, fir_id, f"MZR-BLR-2026-{200 + i:04d}", recovery_date, "recovered from suspect residence",
                     locality_id, lat, lon, pancha1, pancha2, items_desc, vehicle_id, f"MDM-2026-{100 + i:04d}"),
                )
                print(f"  seizure created for {reg} ({fir_id})")
        conn.commit()
    print("Missing vehicle seizures retrofit: done")


if __name__ == "__main__":
    main()
