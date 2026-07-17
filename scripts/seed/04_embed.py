#!/usr/bin/env python3
"""Stage 6 — embeddings (SEED_RUNBOOK.md §7). Chunks every RAG-marked field
(DATA_ARCHITECTURE_SCHEMA_V2.md §2/§Group J) into document_chunks and embeds
each chunk with intfloat/multilingual-e5-base (768-dim).

Chunking (§7 / J1): whole field if <=6 sentences, else 4-sentence windows
with 1-sentence overlap (stride 3). English canonical text only — _kn
fields are never embedded. sentence_start/sentence_end are 0-based indices
into the field's own English sentence list (citation anchoring).

e5 usage convention: embed with a "passage: " prefix (query-time retrieval
code applies "query: " on its own side — not this script's concern). The
prefix is only used for the embedding computation; chunk_text is stored
without it, since it's meant for citation display too.

Resumable: skips any (source_table, source_id, source_field) that already
has chunks in the table (matches document_chunks' own UNIQUE constraint),
so a rerun after a partial failure only fills the gap.
"""

from __future__ import annotations

import sys
import uuid

from db import connect
from narrative_gen import split_sentences

EMBED_MODEL_ID = "intfloat/multilingual-e5-base"
EMBED_DIM = 768
BATCH_SIZE = 16

# (source_table, source_field, select_sql) — select_sql must return
# (source_id, text, district_id, station_id) in that order. source_id is
# cast to text explicitly since document_chunks.source_id is VARCHAR.
RAG_FIELDS: list[tuple[str, str, str]] = [
    ("mo_codes", "mo_description",
     "SELECT mo_code_id::text, mo_description, NULL, NULL FROM mo_codes WHERE mo_description IS NOT NULL"),
    ("firs", "incident_location",
     "SELECT fir_id::text, incident_location, district_id, station_id FROM firs WHERE incident_location IS NOT NULL"),
    ("firs", "complaint_text",
     "SELECT fir_id::text, complaint_text, district_id, station_id FROM firs WHERE complaint_text IS NOT NULL"),
    ("firs", "fir_narrative",
     "SELECT fir_id::text, fir_narrative, district_id, station_id FROM firs WHERE fir_narrative IS NOT NULL"),
    ("firs", "mo_description_free",
     "SELECT fir_id::text, mo_description_free, district_id, station_id FROM firs WHERE mo_description_free IS NOT NULL"),
    ("fir_victims", "victim_statement",
     "SELECT fv.fir_victim_id::text, fv.victim_statement, f.district_id, f.station_id "
     "FROM fir_victims fv JOIN firs f ON f.fir_id = fv.fir_id WHERE fv.victim_statement IS NOT NULL"),
    ("case_diary_entries", "entry_text",
     "SELECT cde.entry_id::text, cde.entry_text, f.district_id, f.station_id "
     "FROM case_diary_entries cde JOIN firs f ON f.fir_id = cde.fir_id WHERE cde.entry_text IS NOT NULL"),
    ("chargesheets", "summary_text",
     "SELECT cs.chargesheet_id::text, cs.summary_text, f.district_id, f.station_id "
     "FROM chargesheets cs JOIN firs f ON f.fir_id = cs.fir_id WHERE cs.summary_text IS NOT NULL"),
    ("ncr_petitions", "petition_text",
     "SELECT petition_id::text, petition_text, district_id, station_id FROM ncr_petitions WHERE petition_text IS NOT NULL"),
    ("seizures", "items_description",
     "SELECT s.seizure_id::text, s.items_description, f.district_id, f.station_id "
     "FROM seizures s JOIN firs f ON f.fir_id = s.fir_id WHERE s.items_description IS NOT NULL"),
    ("missing_persons", "physical_description",
     "SELECT mp.mp_id::text, mp.physical_description, ps.district_id, mp.station_id "
     "FROM missing_persons mp JOIN police_stations ps ON ps.station_id = mp.station_id "
     "WHERE mp.physical_description IS NOT NULL"),
    ("history_sheet_entries", "entry_text",
     "SELECT hse.hs_entry_id::text, hse.entry_text, ps.district_id, hs.station_id "
     "FROM history_sheet_entries hse "
     "JOIN history_sheets hs ON hs.history_sheet_id = hse.history_sheet_id "
     "JOIN police_stations ps ON ps.station_id = hs.station_id "
     "WHERE hse.entry_text IS NOT NULL"),
    ("gangs", "notes",
     "SELECT gang_id::text, notes, operating_district, NULL FROM gangs WHERE notes IS NOT NULL"),
    ("stolen_property", "description",
     "SELECT sp.property_id::text, sp.description, f.district_id, f.station_id "
     "FROM stolen_property sp JOIN firs f ON f.fir_id = sp.fir_id WHERE sp.description IS NOT NULL"),
    ("events_calendar", "notes",
     "SELECT event_id::text, notes, district_id, station_id FROM events_calendar WHERE notes IS NOT NULL"),
]


class E5Embedder:
    """Lazy-loaded intfloat/multilingual-e5-base, embedded directly via
    transformers (mean-pool + L2-normalize) rather than adding a
    sentence-transformers dependency for a single model.
    """

    def __init__(self, model_id: str = EMBED_MODEL_ID) -> None:
        self._model_id = model_id
        self._tokenizer = None
        self._model = None
        self._device = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        import torch
        from transformers import AutoModel, AutoTokenizer

        self._tokenizer = AutoTokenizer.from_pretrained(self._model_id)
        self._device = "mps" if torch.backends.mps.is_available() else "cpu"
        self._model = AutoModel.from_pretrained(self._model_id).to(self._device)
        self._model.eval()

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        self._ensure_loaded()
        import torch
        import torch.nn.functional as F

        prefixed = [f"passage: {t}" for t in texts]
        batch = self._tokenizer(prefixed, max_length=512, padding=True, truncation=True, return_tensors="pt").to(self._device)
        with torch.no_grad():
            out = self._model(**batch)
        last_hidden = out.last_hidden_state.masked_fill(~batch["attention_mask"][..., None].bool(), 0.0)
        pooled = last_hidden.sum(dim=1) / batch["attention_mask"].sum(dim=1)[..., None]
        normalized = F.normalize(pooled, p=2, dim=1)
        return normalized.cpu().tolist()


def chunk_sentences(sentences: list[str]) -> list[tuple[int, int, str]]:
    """Returns [(sentence_start, sentence_end, chunk_text), ...], 0-based
    inclusive sentence indices. Whole field if <=6 sentences; else
    4-sentence windows with 1-sentence overlap (stride 3).
    """
    n = len(sentences)
    if n == 0:
        return []
    if n <= 6:
        return [(0, n - 1, " ".join(sentences))]
    chunks = []
    start = 0
    while start < n:
        end = min(start + 4, n)
        chunks.append((start, end - 1, " ".join(sentences[start:end])))
        if end >= n:
            break
        start += 3
    return chunks


def already_chunked(cur, source_table: str, source_id: str, source_field: str) -> bool:
    cur.execute(
        "SELECT 1 FROM document_chunks WHERE source_table = %s AND source_id = %s AND source_field = %s LIMIT 1",
        (source_table, source_id, source_field),
    )
    return cur.fetchone() is not None


def main() -> None:
    embedder = E5Embedder()
    total_chunks = 0
    total_rows = 0

    with connect() as conn:
        with conn.cursor() as cur:
            for source_table, source_field, select_sql in RAG_FIELDS:
                cur.execute(select_sql)
                rows = cur.fetchall()
                field_chunks = 0
                pending_meta: list[tuple] = []  # (source_id, chunk_index, sent_start, sent_end, chunk_text, district_id, station_id)
                pending_texts: list[str] = []

                def flush():
                    nonlocal field_chunks, total_chunks
                    if not pending_texts:
                        return
                    vectors = embedder.embed_passages(pending_texts)
                    for meta, vec in zip(pending_meta, vectors):
                        source_id, chunk_index, sent_start, sent_end, chunk_text, district_id, station_id = meta
                        cur.execute(
                            "INSERT INTO document_chunks "
                            "(chunk_id, source_table, source_id, source_field, chunk_index, "
                            " sentence_start, sentence_end, chunk_text, embedding, district_id, station_id) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                            (str(uuid.uuid4()), source_table, source_id, source_field, chunk_index,
                             sent_start, sent_end, chunk_text, str(vec), district_id, station_id),
                        )
                        field_chunks += 1
                        total_chunks += 1
                    pending_meta.clear()
                    pending_texts.clear()

                for source_id, text, district_id, station_id in rows:
                    if not text or already_chunked(cur, source_table, source_id, source_field):
                        continue
                    total_rows += 1
                    sentences = split_sentences(text)
                    for chunk_index, (sent_start, sent_end, chunk_text) in enumerate(chunk_sentences(sentences)):
                        pending_meta.append((source_id, chunk_index, sent_start, sent_end, chunk_text, district_id, station_id))
                        pending_texts.append(chunk_text)
                        if len(pending_texts) >= BATCH_SIZE:
                            flush()
                flush()
                conn.commit()
                print(f"  {source_table}.{source_field}: {field_chunks} chunks", flush=True)
        conn.commit()

    print(f"04_embed: {total_rows} rows chunked into {total_chunks} document_chunks rows")


if __name__ == "__main__":
    sys.exit(main())
