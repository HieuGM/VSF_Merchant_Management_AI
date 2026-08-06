from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from providers.cache.redis_adapter import RedisCache


def test_redis_cache_serializes_json_and_honors_ttl():
    client = MagicMock()
    cache = RedisCache("redis://unused", client=client)

    cache.set("merchant:1", {"name": "Xôi", "prices": [20_000]}, ttl_seconds=300)

    key, payload = client.set.call_args.args
    assert key == "merchant:1"
    assert client.set.call_args.kwargs == {"ex": 300}
    assert json.loads(payload) == {"name": "Xôi", "prices": [20_000]}


def test_redis_cache_reads_bytes_and_supports_basic_operations():
    client = MagicMock()
    client.get.return_value = b'{"status":"ok","count":1}'
    client.exists.return_value = 1
    cache = RedisCache("redis://unused", client=client)

    assert cache.get("search:1") == {"status": "ok", "count": 1}
    assert cache.exists("search:1") is True
    cache.set("plain", "value")
    cache.delete("search:1")

    client.set.assert_called_once_with("plain", '"value"')
    client.delete.assert_called_once_with("search:1")


def test_get_cache_selects_redis_adapter_when_url_is_configured(monkeypatch):
    import core.dependencies as dependencies
    import providers.cache.redis_adapter as redis_adapter

    sentinel = MagicMock()
    sentinel.ping.return_value = True
    monkeypatch.setattr(
        dependencies,
        "get_settings",
        lambda: SimpleNamespace(cache_backend="redis", redis_url="redis://cache:6379/0"),
    )
    monkeypatch.setattr(redis_adapter, "RedisCache", lambda url: sentinel if url else None)
    dependencies.get_cache.cache_clear()
    try:
        assert dependencies.get_cache() is sentinel
    finally:
        dependencies.get_cache.cache_clear()


def test_get_cache_falls_back_when_redis_is_unreachable(monkeypatch):
    import core.dependencies as dependencies
    import providers.cache.redis_adapter as redis_adapter
    from providers.cache.memory_adapter import InMemoryCache

    broken = MagicMock()
    broken.ping.side_effect = ConnectionError("redis unavailable")
    monkeypatch.setattr(
        dependencies,
        "get_settings",
        lambda: SimpleNamespace(cache_backend="redis", redis_url="redis://cache:6379/0"),
    )
    monkeypatch.setattr(redis_adapter, "RedisCache", lambda _url: broken)
    dependencies.get_cache.cache_clear()
    try:
        assert isinstance(dependencies.get_cache(), InMemoryCache)
    finally:
        dependencies.get_cache.cache_clear()
