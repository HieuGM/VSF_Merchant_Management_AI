"""In-memory CachePort adapter (§8.2 + red-team H4)."""
from __future__ import annotations

from core.cache import CacheKeys
from providers.cache.memory_adapter import InMemoryCache


def test_set_get_delete_exists():
    cache = InMemoryCache()
    key = CacheKeys.profile_snapshot("user_demo_01")
    assert cache.get(key) is None
    cache.set(key, {"a": 1})
    assert cache.exists(key)
    assert cache.get(key) == {"a": 1}
    cache.delete(key)
    assert not cache.exists(key)


def test_ttl_expiry(monkeypatch):
    cache = InMemoryCache()
    clock = {"t": 1000.0}
    monkeypatch.setattr("providers.cache.memory_adapter.time.monotonic", lambda: clock["t"])
    cache.set("k", "v", ttl_seconds=10)
    assert cache.get("k") == "v"
    clock["t"] += 11
    assert cache.get("k") is None


def test_cache_keys_shape():
    assert CacheKeys.session_context("s1") == "agent:session:s1:context:v1"
    assert CacheKeys.weather(10.79, 106.66) == "agent:weather:10.79:106.66"
    assert CacheKeys.geocode("q1").startswith("agent:geocode:")
