"""E5 embedder — mean-pool + L2-normalize, ported verbatim from
scripts/seed/04_embed.py's E5Embedder so runtime query vectors land in the
exact same space as the passage vectors already seeded into document_chunks.

Deliberately prefix-agnostic: 04_embed.py's own docstring states "query-time
retrieval code applies 'query: ' on its own side — not this script's
concern." This service preserves that split — it embeds exactly the text it's
given; the e5 "query: "/"passage: " prefix convention is the CALLER's
responsibility (mirrors OpenAI's own /v1/embeddings, which never injects
prefixes either).
"""

from __future__ import annotations

import threading

from .config import Settings


class E5Embedder:
    def __init__(self, settings: Settings) -> None:
        self._model_id = settings.embed_model_id
        self._max_length = settings.embed_max_length
        self._tokenizer = None
        self._model = None
        self._device = None
        self._lock = threading.Lock()

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            import torch
            from transformers import AutoModel, AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained(self._model_id)
            self._device = "mps" if torch.backends.mps.is_available() else "cpu"
            self._model = AutoModel.from_pretrained(self._model_id).to(self._device)
            self._model.eval()

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Mean-pool (attention-mask-aware) + L2-normalize. Identical math to
        scripts/seed/04_embed.py's E5Embedder.embed_passages — do not change
        this without re-embedding every row in document_chunks."""
        if not texts:
            return []
        self._ensure_loaded()
        import torch
        import torch.nn.functional as F

        batch = self._tokenizer(
            texts, max_length=self._max_length, padding=True,
            truncation=True, return_tensors="pt",
        ).to(self._device)
        with torch.no_grad():
            out = self._model(**batch)
        last_hidden = out.last_hidden_state.masked_fill(
            ~batch["attention_mask"][..., None].bool(), 0.0
        )
        pooled = last_hidden.sum(dim=1) / batch["attention_mask"].sum(dim=1)[..., None]
        normalized = F.normalize(pooled, p=2, dim=1)
        return normalized.cpu().tolist()


_embedder: E5Embedder | None = None
_embedder_lock = threading.Lock()


def get_embedder(settings: Settings) -> E5Embedder:
    global _embedder
    if _embedder is None:
        with _embedder_lock:
            if _embedder is None:
                _embedder = E5Embedder(settings)
    return _embedder
