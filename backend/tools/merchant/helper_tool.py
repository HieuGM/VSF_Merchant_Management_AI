"""Helper Metadata Catalog Tool — Provides LLMs with valid filter schemas and enums.

Enables agents to query valid cuisines, cities, price levels, 8 dimension names,
and complaint categories to avoid hallucinating parameter values.
"""
from __future__ import annotations

import json
from typing import Any, Type
from pydantic import BaseModel, Field
from crewai.tools import BaseTool

from core.cache import CacheKeys, CachePort

OFFICIAL_8_DIMENSIONS = [
    "food_quality",
    "image_quality",
    "delivery_quality",
    "packaging",
    "service",
    "waiting_time",
    "menu_diversity",
    "price_competitiveness",
]

AVAILABLE_CUISINES = ["Món Việt", "Trà sữa", "Bún đậu", "Cơm tấm", "Lẩu", "Ăn vặt", "Cà phê"]
AVAILABLE_CITIES = ["TP. HCM", "Hà Nội"]
AVAILABLE_PRICE_LEVELS = ["bình dân", "trung bình", "cao cấp"]
COMPLAINT_CATEGORIES = ["service", "packaging", "food_quality", "waiting_time"]
COMPLAINT_SEVERITIES = ["low", "medium", "high", "critical"]

_TTL_CATALOG = 60 * 60


def get_merchant_metadata_catalog(
    topic: str | None = None,
    cache: CachePort | None = None,
) -> dict[str, Any]:
    """Return valid filter values and enums for merchant tool arguments."""
    cache_key = CacheKeys.merchant_catalog() if (cache and not topic) else None

    if cache_key and cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    full_catalog = {
        "official_8_dimensions": OFFICIAL_8_DIMENSIONS,
        "available_cuisines": AVAILABLE_CUISINES,
        "available_cities": AVAILABLE_CITIES,
        "available_price_levels": AVAILABLE_PRICE_LEVELS,
        "complaint_categories": COMPLAINT_CATEGORIES,
        "complaint_severities": COMPLAINT_SEVERITIES,
    }

    if cache_key and cache:
        cache.set(cache_key, full_catalog, ttl_seconds=_TTL_CATALOG)

    if not topic:
        return full_catalog

    topic_lower = topic.strip().lower()
    if "dim" in topic_lower:
        return {"official_8_dimensions": OFFICIAL_8_DIMENSIONS}
    if "cuis" in topic_lower or "city" in topic_lower or "price" in topic_lower:
        return {
            "available_cuisines": AVAILABLE_CUISINES,
            "available_cities": AVAILABLE_CITIES,
            "available_price_levels": AVAILABLE_PRICE_LEVELS,
        }
    if "comp" in topic_lower or "sever" in topic_lower:
        return {
            "complaint_categories": COMPLAINT_CATEGORIES,
            "complaint_severities": COMPLAINT_SEVERITIES,
        }
    return full_catalog


class GetMerchantMetadataCatalogInput(BaseModel):
    topic: str | None = Field(
        None,
        description="Optional topic filter: 'dimensions', 'cuisines', 'complaints', or None for all catalog metadata.",
    )


class GetMerchantMetadataCatalogTool(BaseTool):
    name: str = "get_merchant_metadata_catalog"
    description: str = (
        "Retrieve valid filter enums (cuisines, cities, price levels, 8 dimension names, complaint categories) "
        "to form accurate, valid tool input arguments."
    )
    args_schema: Type[BaseModel] = GetMerchantMetadataCatalogInput

    def _run(self, topic: str | None = None) -> str:
        from core.dependencies import get_cache
        res = get_merchant_metadata_catalog(topic=topic, cache=get_cache())
        return json.dumps(res, ensure_ascii=False)
