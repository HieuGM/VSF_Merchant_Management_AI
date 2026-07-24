"""Weather tool (Phase 03) — get_weather_context for preference_reasoning (§5.4).

Reads current weather at the user's location for reasoning (rain → prefer nearby /
delivery). Degrades gracefully: provider failure → `{weather: null, ...}`, never raises,
never fails the crew. No DB session; cache handled inside the provider.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from core.cache import CacheKeys
from core.dependencies import get_cache
from providers.weather import open_meteo_provider
from tools.allow_list import agents_allowed_for
from tools.registry import ToolRegistry, ToolSpec


class GetWeatherArgs(BaseModel):
    lat: float = Field(..., description="Vĩ độ (latitude) vị trí người dùng")
    lng: float = Field(..., description="Kinh độ (longitude) vị trí người dùng")


def get_weather_context(*, lat: float, lng: float) -> dict[str, Any]:
    """Return current weather context; `weather` is null when unavailable (no raise)."""
    # Peek the cache before fetching so `cached` reflects a real hit (share the same
    # cache instance with the provider so the check and the fetch agree).
    cache = get_cache()
    was_cached = cache.get(CacheKeys.weather(lat, lng)) is not None
    weather = open_meteo_provider.get_current(lat, lng, cache=cache)
    return {
        "weather": weather,
        "source": "open-meteo",
        "cached": was_cached,
    }


def register(reg: ToolRegistry) -> None:
    """Auto-discovery entry point (called by registry.auto_discover)."""
    reg.register(
        ToolSpec(
            name="get_weather_context",
            description=(
                "Lấy thời tiết hiện tại tại vị trí người dùng (nhiệt độ, mưa) để suy luận: "
                "trời mưa → ưu tiên quán gần hoặc giao tận nơi."
            ),
            input_schema={"lat": "float (required)", "lng": "float (required)"},
            output_schema={"weather": "dict | None", "source": "str", "cached": "bool"},
            allowed_agents=agents_allowed_for("get_weather_context"),
            cache_policy="weather",
            source_kind="real",
            args_schema=GetWeatherArgs,
        ),
        get_weather_context,
    )
