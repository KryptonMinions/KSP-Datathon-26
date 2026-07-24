"""Per-turn LLM usage + latency logging (Python `logging`, JSON lines, one
record per completed turn in backend/logs/llm_usage.log).

Separate from the audit DB writer (agent/audit.py) — this is local ops/cost
telemetry (tokens, turnaround time), not part of the product's audit trail,
and stays out of Supabase entirely.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

_LOGS_DIR = Path(__file__).resolve().parents[2] / "logs"
_LOGS_DIR.mkdir(parents=True, exist_ok=True)

_logger = logging.getLogger("ksp.agent.usage")
_logger.setLevel(logging.INFO)
if not _logger.handlers:  # guard against duplicate handlers on module re-import (e.g. --reload)
    _handler = logging.FileHandler(_LOGS_DIR / "llm_usage.log")
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(_handler)
    _logger.propagate = False  # keep this off the root/uvicorn console logger


def log_turn_usage(
    *,
    request_id: str,
    thread_id: str,
    role: str,
    query_class: str,
    specialist: str | None,
    fast_model: str,
    smart_model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    turnaround_ms: int,
    status: str,
    reason: str | None,
) -> None:
    record: dict[str, Any] = {
        "request_id": request_id,
        "thread_id": thread_id,
        "role": role,
        "query_class": query_class,
        "specialist": specialist,
        "profile_models": {"fast": fast_model, "smart": smart_model},
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "turnaround_ms": turnaround_ms,
        "status": status,
        "reason": reason,
    }
    _logger.info(json.dumps(record, default=str))
