"""ThreadStore (ORCHESTRATOR_STEERING.md O-13, §6.3).

Holds up to ASK_THREAD_TTL_S worth of per-thread turn summaries (query,
specialist, one-line answer summary, entity IDs — §6.1's '## Conversation
context' prompt section pulls the last 6). Process-global with a per-thread
asyncio lock; the memory backend is why the backend must run
`uvicorn --workers 1` (O-13) until THREAD_STORE_BACKEND=catalyst lands (P4,
Catalyst Cache — durable, multi-worker safe. Not implemented yet; selecting it
now raises rather than silently falling back, so a misconfiguration is loud).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Protocol

from app.config import Settings


@dataclass
class TurnSummary:
    query: str
    specialist: str
    answer_summary: str
    entity_ids: list[str] = field(default_factory=list)
    ts: float = field(default_factory=time.time)


class ThreadStore(Protocol):
    async def append(self, thread_id: str, turn: TurnSummary) -> None: ...
    async def get_recent(self, thread_id: str, limit: int = 6) -> list[TurnSummary]: ...


class InMemoryThreadStore:
    def __init__(self, ttl_s: int) -> None:
        self._ttl_s = ttl_s
        self._threads: dict[str, list[TurnSummary]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._locks_guard = asyncio.Lock()

    async def _lock_for(self, thread_id: str) -> asyncio.Lock:
        async with self._locks_guard:
            lock = self._locks.get(thread_id)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[thread_id] = lock
            return lock

    def _evict_expired(self, thread_id: str) -> None:
        cutoff = time.time() - self._ttl_s
        turns = self._threads.get(thread_id)
        if not turns:
            return
        self._threads[thread_id] = [t for t in turns if t.ts >= cutoff]

    async def append(self, thread_id: str, turn: TurnSummary) -> None:
        lock = await self._lock_for(thread_id)
        async with lock:
            self._evict_expired(thread_id)
            self._threads.setdefault(thread_id, []).append(turn)

    async def get_recent(self, thread_id: str, limit: int = 6) -> list[TurnSummary]:
        lock = await self._lock_for(thread_id)
        async with lock:
            self._evict_expired(thread_id)
            return self._threads.get(thread_id, [])[-limit:]


_memory_store: InMemoryThreadStore | None = None


def get_thread_store(settings: Settings) -> ThreadStore:
    """Process-global singleton (O-13) — never construct a store per-request."""
    global _memory_store
    if settings.thread_store_backend == "catalyst":
        raise NotImplementedError(
            "THREAD_STORE_BACKEND=catalyst is not implemented yet (lands in P4). "
            "Set THREAD_STORE_BACKEND=memory for now."
        )
    if _memory_store is None:
        _memory_store = InMemoryThreadStore(settings.ask_thread_ttl_s)
    return _memory_store
