"""Competitor Analysis Service (C-05) — Business logic layer for merchant competitor analysis.
"""
from __future__ import annotations

from typing import Any
from sqlalchemy.orm import Session
from repositories.merchant_repository import MerchantRepository
from repositories.merchant_profile_repository import MerchantProfileRepository

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
        competitors: list[dict[str, Any]] = []
        candidates = self._merchant_repo.find_nearby_competitors(
            merchant_id=merchant_id,
            lat=target.lat,
            lng=target.lng,
            radius_km=radius_km,
            cuisine=target.cuisine,
            city=target.city,
            limit=limit,
        )
        for c, distance_km in candidates:
            comp_profile = self._profile_repo.get_profile(c.merchant_id) or {}
            competitors.append({
                "merchant_id": c.merchant_id,
                "name": c.name,
                "cuisine": c.cuisine,
                "address": c.address,
                "distance_km": round(distance_km, 2),
                "dimensions": comp_profile.get("dimensions", {}),
            })

        return {
            "target_merchant_id": merchant_id,
            "target_name": target.name,
            "cuisine": target.cuisine,
            "target_dimensions": target_profile.get("dimensions", {}),
            "radius_km": radius_km,
            "competitor_count": len(competitors),
            "competitors": competitors,
        }
