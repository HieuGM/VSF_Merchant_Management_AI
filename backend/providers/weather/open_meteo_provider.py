"""Open-Meteo weather provider (Phase 02) — free, no API key.

Fetches current weather for reasoning (rain → prefer nearby/delivery). Result is cached
through the CachePort (`CacheKeys.weather`, TTL_WEATHER). Any network/timeout/parse error
degrades gracefully to `None` — the crew must never fail because weather is unavailable.
"""
from __future__ import annotations

from typing import Any

import httpx

from core.cache import TTL_WEATHER, CacheKeys, CachePort
from core.dependencies import get_cache

_BASE_URL = "https://api.open-meteo.com/v1/forecast"
_TIMEOUT_S = 3.0

# Open-Meteo WMO weather codes that indicate rain/drizzle/thunderstorm.
_RAIN_CODES = set(range(51, 68)) | set(range(80, 100))


def _condition(weather_code: int | None) -> str:
    if weather_code is None:
        return "unknown"
    if weather_code == 0:
        return "clear"
    if weather_code in _RAIN_CODES:
        return "rain"
    if weather_code in (1, 2, 3):
        return "cloudy"
    return "other"


def get_current(lat: float, lng: float, cache: CachePort | None = None) -> dict[str, Any] | None:
    """Return current weather dict for a coordinate, or None on any failure.

    Output shape: `{temperature_c, precipitation_mm, condition, is_rain, weather_code}`.
    Cached per (lat, lng) for TTL_WEATHER seconds."""
    cache = cache or get_cache()
    key = CacheKeys.weather(lat, lng)

    cached = cache.get(key)
    if cached is not None:
        return cached

    try:
        params = {
            "latitude": lat,
            "longitude": lng,
            "current": "temperature_2m,precipitation,weather_code",
        }
        resp = httpx.get(_BASE_URL, params=params, timeout=_TIMEOUT_S)
        resp.raise_for_status()
        current = resp.json().get("current", {})
    except Exception:  # noqa: BLE001 - degrade gracefully to None
        return None

    weather_code = current.get("weather_code")
    result = {
        "temperature_c": current.get("temperature_2m"),
        "precipitation_mm": current.get("precipitation"),
        "weather_code": weather_code,
        "condition": _condition(weather_code),
        "is_rain": weather_code in _RAIN_CODES if weather_code is not None else False,
    }
    cache.set(key, result, ttl_seconds=TTL_WEATHER)
    return result
