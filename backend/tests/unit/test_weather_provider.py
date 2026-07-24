"""Open-Meteo weather provider — cache hit/miss + graceful degrade (Phase 07 test 3)."""
from __future__ import annotations

import providers.weather.open_meteo_provider as omp
from providers.cache.memory_adapter import InMemoryCache


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_cache_hit_avoids_second_http_call(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, params=None, timeout=None):
        calls["n"] += 1
        return _FakeResp({"current": {"temperature_2m": 30.0, "precipitation": 0.0, "weather_code": 0}})

    monkeypatch.setattr(omp.httpx, "get", fake_get)
    cache = InMemoryCache()

    first = omp.get_current(10.77, 106.70, cache=cache)
    second = omp.get_current(10.77, 106.70, cache=cache)

    assert calls["n"] == 1, "second call must be served from cache"
    assert first == second
    assert first["condition"] == "clear" and first["is_rain"] is False


def test_rain_code_flags_is_rain(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        return _FakeResp({"current": {"temperature_2m": 25.0, "precipitation": 4.2, "weather_code": 61}})

    monkeypatch.setattr(omp.httpx, "get", fake_get)
    out = omp.get_current(1.0, 2.0, cache=InMemoryCache())
    assert out["is_rain"] is True and out["condition"] == "rain"


def test_http_failure_degrades_to_none(monkeypatch):
    def boom(url, params=None, timeout=None):
        raise RuntimeError("network down")

    monkeypatch.setattr(omp.httpx, "get", boom)
    assert omp.get_current(1.0, 2.0, cache=InMemoryCache()) is None
