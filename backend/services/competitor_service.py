"""Competitor Analysis Service (C-05) — Business logic layer for merchant competitor analysis.
"""
from __future__ import annotations

import math
from typing import Any
from sqlalchemy.orm import Session
from repositories.merchant_repository import MerchantRepository
from repositories.merchant_profile_repository import MerchantProfileRepository


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlng / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class CompetitorService:
    """Service layer for competitor benchmarking and comparison."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._merchant_repo = MerchantRepository(db)
        self._profile_repo = MerchantProfileRepository(db)

    def analyze_competitors(
        self, merchant_id: str, radius_km: float = 5.0, limit: int = 5
    ) -> dict[str, Any]:
        """Perform comprehensive competitor analysis for a merchant within radius_km."""
        target = self._merchant_repo.get_by_id(merchant_id)
        if not target or target.lat is None or target.lng is None:
            return {
                "target_merchant_id": merchant_id,
                "status": "target_not_found_or_no_location",
                "competitors": [],
            }

        target_profile = self._profile_repo.get_profile(merchant_id) or {}
        candidates = self._merchant_repo.search_merchants(
            cuisine=target.cuisine, city=target.city, limit=50
        )

        competitors: list[dict[str, Any]] = []
        for c in candidates:
            if c.merchant_id == merchant_id or c.lat is None or c.lng is None:
                continue

            dist = _haversine(target.lat, target.lng, c.lat, c.lng)
            if dist <= radius_km:
                comp_profile = self._profile_repo.get_profile(c.merchant_id) or {}
                competitors.append({
                    "merchant_id": c.merchant_id,
                    "name": c.name,
                    "cuisine": c.cuisine,
                    "address": c.address,
                    "distance_km": round(dist, 2),
                    "dimensions": comp_profile.get("dimensions", {}),
                })

        competitors.sort(key=lambda x: x["distance_km"])
        competitors = competitors[:limit]

        return {
            "target_merchant_id": merchant_id,
            "target_name": target.name,
            "cuisine": target.cuisine,
            "target_dimensions": target_profile.get("dimensions", {}),
            "radius_km": radius_km,
            "competitor_count": len(competitors),
            "competitors": competitors,
        }
