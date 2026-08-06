"""Synchronous Redis implementation of the shared CachePort contract."""
from __future__ import annotations

import json
from typing import Any

from redis import Redis

from core.cache import CachePort


class RedisCache(CachePort):
    """Store bounded application cache values as UTF-8 JSON."""

    def __init__(self, url: str, *, client: Any | None = None) -> None:
        if not url:
            raise ValueError("Redis URL is required")
        self._client = client or Redis.from_url(url, decode_responses=True)

    def get(self, key: str) -> Any | None:
        value = self._client.get(key)
        if value is None:
            return None
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        return json.loads(value)

    def ping(self) -> bool:
        return bool(self._client.ping())

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
        if ttl_seconds is not None and ttl_seconds > 0:
            self._client.set(key, payload, ex=int(ttl_seconds))
        else:
            self._client.set(key, payload)

    def delete(self, key: str) -> None:
        self._client.delete(key)

    def exists(self, key: str) -> bool:
        return bool(self._client.exists(key))
