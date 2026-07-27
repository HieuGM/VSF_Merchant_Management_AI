"""Merchant Profile Summary Tool (Task 2).

Retrieves the 8-dimension quality profile for a merchant.
Security Rule C2: `overall_score` / `overall_score_internal` MUST be stripped.
"""
from __future__ import annotations

import json
from typing import Any, List, Optional, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.cache import CacheKeys, TTL_PROFILE_SNAPSHOT, CachePort
from database.connection import SessionLocal
from database.models import Merchant, MerchantProfile, MerchantRating

# Official 8 dimension column map: short_key -> column attribute name
_DIMENSION_COLUMNS: dict[str, str] = {
    "food_quality": "food_quality_score",
    "image_quality": "image_quality_score",
    "delivery_quality": "delivery_quality_score",
    "packaging": "packaging_score",
    "service": "service_score",
    "waiting_time": "waiting_time_score",
    "menu_diversity": "menu_diversity_score",
    "price_competitiveness": "price_competitiveness_score",
}

_ALL_DIMENSIONS = list(_DIMENSION_COLUMNS.keys())


def get_merchant_profile_summary(
    merchant_id: str,
    dimensions: list[str] | None = None,
    db: Session | None = None,
    cache: CachePort | None = None,
) -> dict[str, Any]:
    """Return compact profile summary for a merchant.

    Args:
        merchant_id: Target merchant ID.
        dimensions: Optional list of dimension keys to include (e.g. ["food_quality", "service"]).
                    If None, returns all 8 dimensions.
        db: Optional injected DB session (for testing).
        cache: Optional CachePort for read-through caching (TTL 15 min).

    Returns:
        dict with status, merchant_id, name, tier, price_level, ratings, dimensions.
        overall_score_internal is NEVER included (Security Rule C2).
    """
    # Cache only for full-profile requests (no dimension filter) to keep keys simple
    cache_key = CacheKeys.merchant_profile(merchant_id) if (cache and not dimensions) else None

    if cache_key and cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    session = db or SessionLocal()
    try:
        row = (
            session.query(Merchant, MerchantProfile, MerchantRating)
            .outerjoin(MerchantProfile, Merchant.merchant_id == MerchantProfile.merchant_id)
            .outerjoin(MerchantRating, Merchant.merchant_id == MerchantRating.merchant_id)
            .filter(Merchant.merchant_id == merchant_id)
            .first()
        )
        if not row:
            return {"status": "not_found", "merchant_id": merchant_id}

        m, p, r = row
        target_dims = [d for d in (dimensions or _ALL_DIMENSIONS) if d in _DIMENSION_COLUMNS]

        dim_data: dict[str, float | None] = {}
        if p:
            for dim in target_dims:
                col = _DIMENSION_COLUMNS[dim]
                val = getattr(p, col, None)
                dim_data[dim] = float(val) if val is not None else None
        else:
            dim_data = {d: None for d in target_dims}

        ratings: dict[str, Any] = {}
        if r:
            if r.shopeefood_rating is not None:
                ratings["shopeefood"] = {
                    "rating": float(r.shopeefood_rating),
                    "review_count": r.shopeefood_review_count,
                }
            if r.foody_rating is not None:
                ratings["foody"] = {
                    "rating": float(r.foody_rating),
                    "review_count": r.foody_review_count,
                }

        result = {
            "status": "ok",
            "merchant_id": m.merchant_id,
            "name": m.name,
            "cuisine": m.cuisine,
            "city": m.city,
            "tier": p.tier if p else None,
            "price_level": p.price_level if p else None,
            "dimensions": dim_data,
            "ratings": ratings,
        }

        if cache_key and cache:
            cache.set(cache_key, result, ttl_seconds=TTL_PROFILE_SNAPSHOT)

        return result
    finally:
        if db is None:
            session.close()


# --- CrewAI Tool Class ---

from typing import Literal

DimensionKey = Literal[
    "food_quality",
    "image_quality",
    "delivery_quality",
    "packaging",
    "service",
    "waiting_time",
    "menu_diversity",
    "price_competitiveness",
]


class GetMerchantProfileSummaryInput(BaseModel):
    merchant_id: str = Field(..., description="Target merchant ID to look up.")
    dimensions: Optional[List[DimensionKey]] = Field(
        None,
        description=(
            "Optional subset of 8 quality dimension keys to filter. "
            "Leave empty/None to retrieve all 8 quality dimensions."
        ),
    )


class GetMerchantProfileSummaryTool(BaseTool):
    name: str = "get_merchant_profile_summary"
    description: str = (
        "Retrieve a merchant's quality profile: 8-dimension scores (food_quality, "
        "image_quality, delivery_quality, packaging, service, waiting_time, "
        "menu_diversity, price_competitiveness), tier, price_level, and platform ratings. "
        "Does NOT return overall_score. Use `dimensions` to request only what you need."
    )
    args_schema: Type[BaseModel] = GetMerchantProfileSummaryInput

    def _run(
        self,
        merchant_id: str,
        dimensions: list[str] | None = None,
    ) -> str:
        from core.dependencies import get_cache
        res = get_merchant_profile_summary(
            merchant_id=merchant_id,
            dimensions=dimensions,
            cache=get_cache(),
        )
        return json.dumps(res, ensure_ascii=False)
