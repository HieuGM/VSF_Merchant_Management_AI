"""CachePort interface + Redis key builder (design §8.1/§8.2).

FROZEN SEAM (Feature D-01, red-team H4): the interface AND an in-memory adapter ship
in Phase 0 so both verticals test without Redis. Dev A owns the Redis adapter (D-02);
Dev B consumes the profile snapshot through this port — depend on the interface, never
edit provider files across ownership boundaries.
"""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from typing import Any

# --- Redis TTLs (seconds) — design §8.2 ---
TTL_SESSION_CONTEXT = 30 * 60
TTL_CANDIDATES = 5 * 60
TTL_PROFILE_SNAPSHOT = 15 * 60
TTL_WEATHER = 10 * 60
TTL_GEOCODE = 24 * 60 * 60
TTL_RUN = 24 * 60 * 60


def _hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


class CacheKeys:
    """Canonical key builders (design §8.2). Both verticals MUST build keys here to
    avoid the cross-dev collision called out in plan.md §[H6]."""

    @staticmethod
    def session_context(session_id: str) -> str:
        return f"agent:session:{session_id}:context:v1"

    @staticmethod
    def session_candidates(session_id: str, constraint_hash: str) -> str:
        return f"agent:session:{session_id}:candidates:{constraint_hash}"

    @staticmethod
    def profile_snapshot(user_id: str) -> str:
        return f"agent:user:{user_id}:profile_snapshot:v1"

    @staticmethod
    def weather(lat: float, lng: float) -> str:
        return f"agent:weather:{lat}:{lng}"

    @staticmethod
    def geocode(query: str) -> str:
        return f"agent:geocode:{_hash(query)}"

    @staticmethod
    def run(trace_id: str) -> str:
        return f"agent:run:{trace_id}"


class CachePort(ABC):
    """Replaceable cache backend. Implementations: memory (Phase 0), redis (D-02)."""

    @abstractmethod
    def get(self, key: str) -> Any | None: ...

    @abstractmethod
    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...
