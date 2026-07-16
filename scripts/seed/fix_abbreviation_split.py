#!/usr/bin/env python3
"""One-off retrofit: clear stale Kannada translations for narrative fields
whose English text contains a "K.R."/"J.P."-style locality abbreviation,
now that narrative_gen.split_sentences() no longer mis-splits on them.

English text is untouched (it was never wrong — only how it got chunked
for per-sentence translation was). This clears each affected row's _kn
cache entry (so a rerun of narrative_gen.generate_narrative() actually
retranslates instead of returning the stale cached text_kn) and its DB
_kn column, then relies on 06_kannada_pass.py's narrative pass (which
already only processes rows where the _kn column IS NULL) to redo them
with the fixed splitter.
"""

from db import connect
from narrative_gen import _cache_path
import json

ABBR_PATTERN = r"K\.R\.|J\.P\."


def clear_kn(table: str, record_id: str, field: str) -> None:
    path = _cache_path(table, record_id, field)
    if path.exists():
        payload = json.loads(path.read_text())
        if payload.get("text_kn") is not None:
            payload["text_kn"] = None
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT fir_id FROM firs WHERE complaint_text ~ %s OR fir_narrative ~ %s OR mo_description_free ~ %s",
                (ABBR_PATTERN, ABBR_PATTERN, ABBR_PATTERN),
            )
            fir_ids = [r[0] for r in cur.fetchall()]
            print(f"{len(fir_ids)} affected FIRs")

            for fir_id in fir_ids:
                cur.execute(
                    "SELECT complaint_text, fir_narrative, mo_description_free FROM firs WHERE fir_id = %s", (fir_id,)
                )
                complaint, narrative, mo_free = cur.fetchone()
                import re
                if complaint and re.search(ABBR_PATTERN, complaint):
                    clear_kn("firs", fir_id, "complaint_text")
                    cur.execute("UPDATE firs SET complaint_text_kn = NULL WHERE fir_id = %s", (fir_id,))
                if narrative and re.search(ABBR_PATTERN, narrative):
                    clear_kn("firs", fir_id, "fir_narrative")
                    # firs has no fir_narrative_kn column — nothing to NULL in DB.
                if mo_free and re.search(ABBR_PATTERN, mo_free):
                    clear_kn("firs", fir_id, "mo_description_free")
                    # firs has no mo_description_free_kn column either.

                cur.execute(
                    "SELECT fir_victim_id, victim_statement FROM fir_victims WHERE fir_id = %s", (fir_id,)
                )
                for fir_victim_id, statement in cur.fetchall():
                    if statement and re.search(ABBR_PATTERN, statement):
                        clear_kn("fir_victims", fir_id, "victim_statement")
                        cur.execute(
                            "UPDATE fir_victims SET victim_statement_kn = NULL WHERE fir_victim_id = %s",
                            (fir_victim_id,),
                        )

                cur.execute(
                    "SELECT entry_id, entry_number, entry_text FROM case_diary_entries WHERE fir_id = %s", (fir_id,)
                )
                for entry_id, entry_number, entry_text in cur.fetchall():
                    if entry_text and re.search(ABBR_PATTERN, entry_text):
                        clear_kn("case_diary_entries", f"{fir_id}:{entry_number}", "entry_text")
                        cur.execute(
                            "UPDATE case_diary_entries SET entry_text_kn = NULL WHERE entry_id = %s", (entry_id,)
                        )
        conn.commit()
    print("Cleared stale _kn cache + DB values for affected rows.")


if __name__ == "__main__":
    main()
