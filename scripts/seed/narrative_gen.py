"""Local narrative generation + Kannada mirror harness (SEED_RUNBOOK.md §6.4,
DATA_ARCHITECTURE_SCHEMA_V2.md §1.1).

Two-model local pipeline, run entirely offline (no paid API per row):

  1. English generation — a local instruct model served by Ollama
     (OpenAI-compatible endpoint on localhost:11434). Prompted per-record from
     the row's own structured facts so the narrative can't contradict its row.
  2. Kannada mirror — AI4Bharat IndicTrans2, translating the English text
     *sentence-by-sentence*. Translating per-sentence (rather than asking one
     generation call to produce parallel text) makes sentence alignment
     (schema §1.1.2 — sentence i in _kn <-> sentence i in English) a structural
     guarantee instead of something to verify after the fact.

Every (table, record_id, field) result is cached to disk so re-running the
seeder never re-generates or re-translates a row that's already been done.

Setup (once):
    brew install ollama
    ollama pull qwen2.5:7b-instruct
    ollama serve   # or let `brew services start ollama` run it in the background

IndicTrans2 is a gated HuggingFace repo (both indictrans2-en-indic-1B and the
distilled -dist-200M variant) — weights do NOT download anonymously. One-time
setup: create a HuggingFace account, visit
https://huggingface.co/ai4bharat/indictrans2-en-indic-1B and click "Request
access" (usually auto-approved), then generate a read-scoped token at
https://huggingface.co/settings/tokens and add it to backend/.env as
HF_TOKEN=hf_xxx. Never paste the token directly into a prompt/chat — env file
only, loaded the same way as SUPABASE_DB_URL (see db.py).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv

CACHE_DIR = Path(__file__).resolve().parent / "narrative_cache"
BACKEND_ENV = Path(__file__).resolve().parents[2] / "backend" / ".env"
load_dotenv(BACKEND_ENV)

OLLAMA_BASE_URL = "http://localhost:11434/v1"
OLLAMA_MODEL = "qwen2.5:7b-instruct"
PROMPT_VERSION = "v2"  # v2: fact-injecting templates (narrative_facts.py), see Thread A retrofit

INDICTRANS2_MODEL_ID = "ai4bharat/indictrans2-en-indic-1B"
INDICTRANS2_SRC_LANG = "eng_Latn"
INDICTRANS2_TGT_LANG = "kan_Knda"

# Population rates from DATA_ARCHITECTURE_SCHEMA_V2.md §1.1.3. Keys are
# (table, field) pairs; "master_data" covers the 100%-rate label fields
# (districts, stations, crime_types, mo_codes, events_calendar, gangs names).
KN_POPULATION_RATES: dict[str, float] = {
    "master_data": 1.0,
    "firs.complaint_text": 1.0,
    "fir_victims.victim_statement": 0.90,
    "ncr_petitions.petition_text": 0.80,
    "case_diary_entries.entry_text": 0.30,
}
DEFAULT_KN_RATE = 0.50  # "all other _kn narrative fields" per §1.1.3


@dataclass
class NarrativeResult:
    table: str
    record_id: str
    field: str
    text_en: str
    text_kn: Optional[str]
    model: str
    prompt_version: str
    from_cache: bool


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?।])\s+")
# English initials ("K.R.", "J.P.") and the same pattern transliterated into
# Kannada script by IndicTrans2 (e.g. "ಕೆ. ಆರ್." for "K.R.") — both render
# an abbreviation as a short token immediately followed by a period, which
# this naive splitter otherwise mistakes for a sentence end.
_TRAILING_INITIAL_RE = re.compile(r"\b[A-Z]\.$")
_TRAILING_KANNADA_INITIAL_RE = re.compile(r"(?:^|[\s'\"])[ಀ-೿]{1,3}\.$")


def split_sentences(text: str) -> list[str]:
    """Lightweight sentence splitter — good enough for short police narratives.

    Kept dependency-free (no nltk/pysbd) since these fields are 1-8 sentences
    of fairly formulaic prose, not open-domain text.

    One abbreviation guard: locality names like "K.R. Circle" and "J.P.
    Nagar" (real seeded gazetteer entries) contain a period+space inside a
    single-letter-initial pair, which the naive regex above treats as a
    sentence boundary — splitting "...along K.R." from "Circle in the..."
    mid-sentence. Any split fragment ending in a lone capital letter + period
    is almost certainly such an initial, not a real sentence end, so it gets
    re-merged with the following fragment.
    """
    text = text.strip()
    if not text:
        return []
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(text)]
    parts = [p for p in parts if p]
    merged: list[str] = []
    for p in parts:
        if merged and (_TRAILING_INITIAL_RE.search(merged[-1]) or _TRAILING_KANNADA_INITIAL_RE.search(merged[-1])):
            merged[-1] = f"{merged[-1]} {p}"
        else:
            merged.append(p)
    return merged


def _cache_key(table: str, record_id: str, field: str) -> str:
    # PROMPT_VERSION is folded in deliberately: bumping it after a prompt
    # revision must invalidate old cached text, not silently keep serving
    # stale generations for records already processed under the old prompt.
    raw = f"{table}:{record_id}:{field}:{PROMPT_VERSION}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _cache_path(table: str, record_id: str, field: str) -> Path:
    return CACHE_DIR / table / f"{_cache_key(table, record_id, field)}.json"


def _read_cache(table: str, record_id: str, field: str) -> Optional[dict]:
    path = _cache_path(table, record_id, field)
    if path.exists():
        return json.loads(path.read_text())
    return None


def _write_cache(table: str, record_id: str, field: str, payload: dict) -> None:
    path = _cache_path(table, record_id, field)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))


def generate_english(
    prompt: str,
    *,
    temperature: float = 0.8,
    model: str = OLLAMA_MODEL,
    max_tokens: int = 400,
) -> str:
    """Call the local Ollama OpenAI-compatible chat-completions endpoint.

    `temperature` should vary per-record (not a fixed constant) — narratives
    sharing an MO code must not read near-identically (SEED_RUNBOOK.md §6.4).
    """
    with httpx.Client(base_url=OLLAMA_BASE_URL, timeout=120.0) as client:
        resp = client.post(
            "/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


class KannadaTranslator:
    """Thin wrapper around IndicTrans2, loaded lazily (large model, GPU/MPS-heavy).

    Instantiate once per seed run and reuse — loading the model per call would
    be prohibitively slow across hundreds of narrative rows.

    Uses AI4Bharat's own IndicTransToolkit (IndicProcessor) for pre/post
    -processing, not manual "eng_Latn kan_Knda <text>" string prefixing.
    That naive approach (the model card's older documented usage) was tried
    first and produced Devanagari (Hindi) output instead of Kannada script —
    IndicProcessor handles the language-tag formatting, numeral/quote
    normalization, and script-specific postprocessing the raw tokenizer
    needs to actually honor the requested target language.
    """

    def __init__(self, model_id: str = INDICTRANS2_MODEL_ID) -> None:
        self._model_id = model_id
        self._tokenizer = None
        self._model = None
        self._processor = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        # Imported lazily: torch/transformers are heavy and only needed once
        # translation actually starts, not merely to import this module.
        import torch
        from IndicTransToolkit.processor import IndicProcessor
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        hf_token = os.environ.get("HF_TOKEN")
        if not hf_token:
            raise RuntimeError(
                "HF_TOKEN not set in backend/.env — IndicTrans2 is a gated "
                "HuggingFace repo. See narrative_gen.py module docstring for "
                "the one-time access-request + token setup."
            )

        self._tokenizer = AutoTokenizer.from_pretrained(
            self._model_id, trust_remote_code=True, token=hf_token
        )
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        self._model = AutoModelForSeq2SeqLM.from_pretrained(
            self._model_id, trust_remote_code=True, token=hf_token
        ).to(device)
        self._device = device
        self._processor = IndicProcessor(inference=True)

    def translate_sentences(self, sentences: list[str], *, num_beams: int = 5) -> list[str]:
        """Translate English sentences to Kannada, one-to-one, preserving order.

        Per-sentence translation (rather than translating the whole paragraph
        in one call) is what guarantees sentence *i* in the Kannada mirror
        corresponds to sentence *i* in English (schema §1.1.2) — there's no
        re-segmentation step that could drift the alignment.

        `num_beams` is a memory/quality knob: beam search keeps num_beams
        hypotheses live per item, so lowering it (e.g. to 1, greedy) cuts
        peak memory for short reference-label batches where translation
        quality is less sensitive than for case-narrative prose.
        """
        if not sentences:
            return []
        self._ensure_loaded()
        import torch

        batch = self._processor.preprocess_batch(
            sentences, src_lang=INDICTRANS2_SRC_LANG, tgt_lang=INDICTRANS2_TGT_LANG
        )
        inputs = self._tokenizer(
            batch, return_tensors="pt", padding=True, truncation=True
        ).to(self._device)
        with torch.no_grad():
            generated = self._model.generate(
                **inputs, max_length=256, num_beams=num_beams, early_stopping=True
            )
        decoded = self._tokenizer.batch_decode(generated, skip_special_tokens=True)
        return self._processor.postprocess_batch(decoded, lang=INDICTRANS2_TGT_LANG)


def _kn_rate_for(table: str, field: str) -> float:
    key = f"{table}.{field}"
    if key in KN_POPULATION_RATES:
        return KN_POPULATION_RATES[key]
    return DEFAULT_KN_RATE


def _should_populate_kn(table: str, record_id: str, field: str, rate: float) -> bool:
    """Deterministic per-row draw so the same record always gets the same
    include/exclude decision across re-runs (stable hash, not random.random()).
    """
    digest = hashlib.sha256(f"{table}:{record_id}:{field}:kn".encode()).digest()
    draw = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
    return draw < rate


def generate_narrative(
    table: str,
    record_id: str,
    field: str,
    prompt: str,
    *,
    translator: Optional[KannadaTranslator] = None,
    temperature: float = 0.8,
    force_kn: Optional[bool] = None,
) -> NarrativeResult:
    """Top-level entry point used by scripts/seed/03_synthetic.py.

    Checks the disk cache first; on a miss, generates English via Ollama and
    — if this row is selected for Kannada population at the field's §1.1.3
    rate — translates it sentence-by-sentence via IndicTrans2. Every result
    (hit or miss) is returned uniformly so callers don't need to branch.
    """
    cached = _read_cache(table, record_id, field)
    if cached is not None:
        text_kn = cached.get("text_kn")
        # A prior run may have generated English with force_kn=False (Kannada
        # deliberately deferred, e.g. the Thread A/B/C golden-thread builds)
        # — backfill the translation now instead of silently keeping the gap
        # forever, which is what a plain early-return here would do.
        if text_kn is None:
            populate_kn = (
                force_kn
                if force_kn is not None
                else _should_populate_kn(table, record_id, field, _kn_rate_for(table, field))
            )
            if populate_kn and translator is not None:
                en_sentences = split_sentences(cached["text_en"])
                kn_sentences = translator.translate_sentences(en_sentences)
                text_kn = " ".join(kn_sentences)
                cached = {**cached, "text_kn": text_kn}
                _write_cache(table, record_id, field, cached)
        return NarrativeResult(
            table=table,
            record_id=record_id,
            field=field,
            text_en=cached["text_en"],
            text_kn=text_kn,
            model=cached["model"],
            prompt_version=cached["prompt_version"],
            from_cache=True,
        )

    text_en = generate_english(prompt, temperature=temperature)

    populate_kn = (
        force_kn
        if force_kn is not None
        else _should_populate_kn(table, record_id, field, _kn_rate_for(table, field))
    )
    text_kn: Optional[str] = None
    if populate_kn:
        if translator is None:
            raise ValueError(
                f"{table}.{field} for {record_id} is selected for Kannada "
                "population but no KannadaTranslator was provided."
            )
        en_sentences = split_sentences(text_en)
        kn_sentences = translator.translate_sentences(en_sentences)
        text_kn = " ".join(kn_sentences)

    payload = {
        "text_en": text_en,
        "text_kn": text_kn,
        "model": OLLAMA_MODEL,
        "prompt_version": PROMPT_VERSION,
    }
    _write_cache(table, record_id, field, payload)

    return NarrativeResult(
        table=table,
        record_id=record_id,
        field=field,
        text_en=text_en,
        text_kn=text_kn,
        model=OLLAMA_MODEL,
        prompt_version=PROMPT_VERSION,
        from_cache=False,
    )


def assert_sentence_aligned(text_en: str, text_kn: str) -> None:
    """Validation helper (used by scripts/seed/05_validate.py, §8.5): the
    English and Kannada mirror must have the same sentence count.
    """
    en_count = len(split_sentences(text_en))
    kn_count = len(split_sentences(text_kn))
    if en_count != kn_count:
        raise AssertionError(
            f"sentence-count mismatch: en={en_count} kn={kn_count}\n"
            f"en={text_en!r}\nkn={text_kn!r}"
        )
