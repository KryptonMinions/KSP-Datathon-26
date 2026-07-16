#!/usr/bin/env python3
"""Stage 6 — batched Kannada mirror pass (DATA_ARCHITECTURE_SCHEMA_V2.md §1.1).

Two independent passes:

1. Master-data labels (§1.1.3: districts, stations, crime types, MO codes,
   events, gangs — 100% population), plus localities and taluk/hobli
   admin_boundaries. These are short reference-table labels with no LLM
   generation step — just a direct IndicTrans2 translation of the existing
   English value, batched for throughput.

2. Golden-thread narrative fields (complaint_text, victim_statement,
   entry_text, petition_text, stolen_property.description,
   seizures.items_description) that were generated during the Thread A/B/C
   builds with force_kn=False (Kannada deliberately deferred). Re-invokes
   narrative_gen.generate_narrative() with the same (table, record_id, field)
   keys used originally so it hits the disk cache and backfills the missing
   translation in place (see the cache-hit fix in narrative_gen.py), then
   writes the result to the DB row's _kn column. Population rates per
   §1.1.3 are applied automatically by generate_narrative().

Scoped to the current dataset (golden threads only, no background corpus
yet) — safe to re-run once the background corpus exists, since already-kn'd
rows are skipped by the `col_kn IS NULL` filters throughout.
"""

from __future__ import annotations

from db import connect
from narrative_gen import KannadaTranslator, generate_narrative

# Small batch + greedy decoding for master-data labels: this machine is
# memory-constrained and beam-search-5 over larger batches was thrashing
# (swap-bound, not compute-bound) on mo_codes' longer paragraphs. Labels
# are short enough that greedy decoding costs little in quality.
BATCH_SIZE = 8
MASTER_DATA_NUM_BEAMS = 1


def translate_column(
    conn, cur, *, table: str, pk_col: str, text_col: str, kn_col: str,
    translator: KannadaTranslator, where_extra: str = "",
) -> int:
    cur.execute(
        f"SELECT {pk_col}, {text_col} FROM {table} "
        f"WHERE {kn_col} IS NULL AND {text_col} IS NOT NULL {where_extra}"
    )
    rows = cur.fetchall()
    if not rows:
        return 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        pks = [r[0] for r in batch]
        texts = [r[1] for r in batch]
        translated = translator.translate_sentences(texts, num_beams=MASTER_DATA_NUM_BEAMS)
        for pk, kn_text in zip(pks, translated):
            cur.execute(f"UPDATE {table} SET {kn_col} = %s WHERE {pk_col} = %s", (kn_text, pk))
        conn.commit()  # per-batch commit — a kill mid-table keeps completed batches
        print(f"  ...{table}.{kn_col}: {min(i + BATCH_SIZE, len(rows))}/{len(rows)}", flush=True)
    return len(rows)


def run_master_data_pass(translator: KannadaTranslator) -> None:
    jobs = [
        dict(table="police_stations", pk_col="station_id", text_col="station_name", kn_col="station_name_kn"),
        dict(
            table="admin_boundaries", pk_col="boundary_id", text_col="name", kn_col="name_kn",
            where_extra="AND boundary_type IN ('Taluk', 'Hobli')",
        ),
        dict(table="crime_types", pk_col="crime_type_id", text_col="crime_type_name", kn_col="crime_type_name_kn"),
        dict(table="mo_codes", pk_col="mo_code_id", text_col="mo_description", kn_col="mo_description_kn"),
        dict(table="localities", pk_col="locality_id", text_col="locality_name", kn_col="locality_name_kn"),
        dict(table="gangs", pk_col="gang_id", text_col="gang_name", kn_col="gang_name_kn"),
        dict(table="events_calendar", pk_col="event_id", text_col="event_name", kn_col="event_name_kn"),
    ]
    with connect() as conn:
        with conn.cursor() as cur:
            for job in jobs:
                n = translate_column(conn, cur, translator=translator, **job)
                print(f"Kannada pass: {job['table']}.{job['kn_col']} — {n} rows translated", flush=True)


def run_narrative_pass(translator: KannadaTranslator) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            # (select_sql, id_cols_for_update, table_for_cache, field_for_cache,
            #  record_id_fn(row) -> str, update_sql)
            cur.execute("SELECT fir_id FROM firs WHERE complaint_text_kn IS NULL AND complaint_text IS NOT NULL")
            fir_rows = cur.fetchall()
            for (fir_id,) in fir_rows:
                result = generate_narrative("firs", fir_id, "complaint_text", "", translator=translator, force_kn=None)
                if result.text_kn:
                    cur.execute("UPDATE firs SET complaint_text_kn = %s WHERE fir_id = %s", (result.text_kn, fir_id))
            conn.commit()
            print(f"Kannada pass: firs.complaint_text_kn — {len(fir_rows)} candidate rows (rate 100%)", flush=True)

            cur.execute(
                "SELECT fir_victim_id, fir_id FROM fir_victims "
                "WHERE victim_statement_kn IS NULL AND victim_statement IS NOT NULL"
            )
            fv_rows = cur.fetchall()
            for fir_victim_id, fir_id in fv_rows:
                result = generate_narrative("fir_victims", fir_id, "victim_statement", "", translator=translator, force_kn=None)
                if result.text_kn:
                    cur.execute(
                        "UPDATE fir_victims SET victim_statement_kn = %s WHERE fir_victim_id = %s",
                        (result.text_kn, fir_victim_id),
                    )
            conn.commit()
            print(f"Kannada pass: fir_victims.victim_statement_kn — {len(fv_rows)} candidate rows (rate 90%)", flush=True)

            cur.execute(
                "SELECT entry_id, fir_id, entry_number FROM case_diary_entries "
                "WHERE entry_text_kn IS NULL AND entry_text IS NOT NULL"
            )
            diary_rows = cur.fetchall()
            for entry_id, fir_id, entry_number in diary_rows:
                record_id = f"{fir_id}:{entry_number}"
                result = generate_narrative("case_diary_entries", record_id, "entry_text", "", translator=translator, force_kn=None)
                if result.text_kn:
                    cur.execute(
                        "UPDATE case_diary_entries SET entry_text_kn = %s WHERE entry_id = %s",
                        (result.text_kn, entry_id),
                    )
            conn.commit()
            print(f"Kannada pass: case_diary_entries.entry_text_kn — {len(diary_rows)} candidate rows (rate 30%)", flush=True)

            cur.execute(
                "SELECT petition_id FROM ncr_petitions WHERE petition_text_kn IS NULL AND petition_text IS NOT NULL"
            )
            petition_rows = cur.fetchall()
            for (petition_id,) in petition_rows:
                result = generate_narrative("ncr_petitions", petition_id, "petition_text", "", translator=translator, force_kn=None)
                if result.text_kn:
                    cur.execute(
                        "UPDATE ncr_petitions SET petition_text_kn = %s WHERE petition_id = %s",
                        (result.text_kn, petition_id),
                    )
            conn.commit()
            print(f"Kannada pass: ncr_petitions.petition_text_kn — {len(petition_rows)} candidate rows (rate 80%)", flush=True)

            cur.execute(
                "SELECT property_id FROM stolen_property WHERE description_kn IS NULL AND description IS NOT NULL"
            )
            property_rows = cur.fetchall()
            for (property_id,) in property_rows:
                result = generate_narrative("stolen_property", property_id, "description", "", translator=translator, force_kn=None)
                if result.text_kn:
                    cur.execute(
                        "UPDATE stolen_property SET description_kn = %s WHERE property_id = %s",
                        (result.text_kn, property_id),
                    )
            conn.commit()
            print(f"Kannada pass: stolen_property.description_kn — {len(property_rows)} candidate rows (rate 50%)", flush=True)

            cur.execute(
                "SELECT seizure_id FROM seizures WHERE items_description_kn IS NULL AND items_description IS NOT NULL"
            )
            seizure_rows = cur.fetchall()
            for (seizure_id,) in seizure_rows:
                result = generate_narrative("seizures", seizure_id, "items_description", "", translator=translator, force_kn=None)
                if result.text_kn:
                    cur.execute(
                        "UPDATE seizures SET items_description_kn = %s WHERE seizure_id = %s",
                        (result.text_kn, seizure_id),
                    )
            conn.commit()
            print(f"Kannada pass: seizures.items_description_kn — {len(seizure_rows)} candidate rows (rate 50%)", flush=True)


if __name__ == "__main__":
    translator = KannadaTranslator()
    run_master_data_pass(translator)
    run_narrative_pass(translator)
    print("Kannada pass complete.")
