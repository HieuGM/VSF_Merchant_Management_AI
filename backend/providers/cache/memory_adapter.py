"""In-memory CachePort adapter (design §8.2 — "tests use an in-memory cache adapter").

Ships in Phase 0 (red-team H4) so both verticals run pytest without Redis. TTL is
honored with a monotonic clock so expiry-related tests are deterministic.
"""
from __future__ import annotations

import time
from typing import Any

from core.cache import CachePort


class InMemoryCache(CachePort):
    def __init__(self) -> None:
        # key -> (value, expires_at_epoch | None)
        self._store: dict[str, tuple[Any, float | None]] = {}

    def _expired(self, key: str) -> bool:
        entry = self._store.get(key)
        if entry is None:
            return True
        _, expires_at = entry
        if expires_at is not None and time.monotonic() >= expires_at:
            self._store.pop(key, None)
            return True
        return False

    def get(self, key: str) -> Any | None:
        if self._expired(key):
            return None
        return self._store[key][0]

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        expires_at = time.monotonic() + ttl_seconds if ttl_seconds else None
        self._store[key] = (value, expires_at)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def exists(self, key: str) -> bool:
        return not self._expired(key)

    def clear(self) -> None:
        self._store.clear()
