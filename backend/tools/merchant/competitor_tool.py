"""Merchant competitor analysis tool (F-02 Merchant) — Compares merchant with nearby competitors.
"""
from __future__ import annotations

from typing import Any
from sqlalchemy.orm import Session
from database.connection import SessionLocal
from repositories.merchant_repository import MerchantRepository
from repositories.merchant_profile_repository import MerchantProfileRepository
from tools.allow_list import agents_allowed_for
from tools.registry import ToolRegistry, ToolSpec

def compare_competitors(
    merchant_id: str,
    radius_km: float = 5.0,
    limit: int = 5,
    db: Session | None = None,
) -> dict[str, Any]:
    """Compare a target merchant with nearby competitor merchants within radius_km.

    Returns:
        Target merchant details vs list of competitor profiles.
    """
    session = db or SessionLocal()
    try:
        merchant_repo = MerchantRepository(session)
        profile_repo = MerchantProfileRepository(session)

        target = merchant_repo.get_by_id(merchant_id)
        if not target or target.lat is None or target.lng is None:
            return {
                "target_merchant_id": merchant_id,
                "status": "target_not_found_or_no_location",
                "competitors": [],
            }

        target_profile = profile_repo.get_profile(merchant_id) or {}

        candidates = merchant_repo.find_nearby_competitors(
            merchant_id=merchant_id,
            lat=target.lat,
            lng=target.lng,
            radius_km=radius_km,
            cuisine=target.cuisine,
            city=target.city,
            limit=limit,
        )

        competitors = []
        for c, distance_km in candidates:
            comp_profile = profile_repo.get_profile(c.merchant_id) or {}
            competitors.append({
                "merchant_id": c.merchant_id,
                "name": c.name,
                "cuisine": c.cuisine,
                "distance_km": round(distance_km, 2),
                "dimensions": comp_profile.get("dimensions", {}),
            })

        return {
            "target_merchant_id": merchant_id,
            "target_name": target.name,
            "cuisine": target.cuisine,
            "target_dimensions": target_profile.get("dimensions", {}),
            "radius_km": radius_km,
            "competitors": competitors,
        }
    finally:
        if db is None:
            session.close()


def register(reg: ToolRegistry) -> None:
    """Auto-discovery entry point for competitor comparison tool."""
    reg.register(
        ToolSpec(
            name="compare_competitors",
            description="Compare a merchant's 8 dimensions with nearby competitor merchants.",
            input_schema={"merchant_id": "str", "radius_km": "float?", "limit": "int?"},
            output_schema={"target_merchant_id": "str", "competitors": "list"},
            allowed_agents=agents_allowed_for("compare_competitors"),
            cache_policy="profile_snapshot",
            source_kind="real",
        ),
        compare_competitors,
    )
