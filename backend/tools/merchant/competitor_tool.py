"""Benchmark Comparison Tool (Task 4).

Compares target merchant's 8-dimension profile scores against nearby competitors
of the same cuisine type. Returns compact token-efficient diff.
"""
from __future__ import annotations

import json
import math
from typing import Any, List, Optional, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import Merchant, MerchantProfile

_DIMENSION_COLUMNS = {
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


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Approximate haversine distance in km."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _profile_scores(p: MerchantProfile | None, dimensions: list[str]) -> dict[str, float | None]:
    if not p:
        return {d: None for d in dimensions}
    return {d: float(getattr(p, _DIMENSION_COLUMNS[d])) for d in dimensions}


def compare_merchant_benchmark(
    merchant_id: str,
    radius_km: float = 5.0,
    limit: int = 5,
    dimensions: list[str] | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    """Compare a merchant's dimension scores against same-cuisine competitors nearby.

    Args:
        merchant_id: Target merchant ID.
        radius_km: Geographic search radius (default 5 km).
        limit: Max competitors to return (1..10).
        dimensions: Subset of dimension keys to compare. Defaults to all 8.
        db: Optional injected DB session.

    Returns:
        dict with target scores, competitor benchmarks, and per-dimension delta.
        overall_score_internal is NEVER included (Security Rule C2).
    """
    session = db or SessionLocal()
    try:
        target_dims = [d for d in (dimensions or _ALL_DIMENSIONS) if d in _DIMENSION_COLUMNS]

        # Load target
        row = (
            session.query(Merchant, MerchantProfile)
            .outerjoin(MerchantProfile, Merchant.merchant_id == MerchantProfile.merchant_id)
            .filter(Merchant.merchant_id == merchant_id)
            .first()
        )
        if not row:
            return {"status": "not_found", "merchant_id": merchant_id}
        target_m, target_p = row

        if target_m.lat is None or target_m.lng is None:
            return {
                "status": "no_location",
                "merchant_id": merchant_id,
                "message": "Target merchant has no lat/lng for geo comparison.",
            }

        target_scores = _profile_scores(target_p, target_dims)

        # Load competitor candidates (same city, same cuisine, different ID)
        candidates = (
            session.query(Merchant, MerchantProfile)
            .outerjoin(MerchantProfile, Merchant.merchant_id == MerchantProfile.merchant_id)
            .filter(
                Merchant.merchant_id != merchant_id,
                Merchant.cuisine == target_m.cuisine,
                Merchant.city == target_m.city,
                Merchant.is_active == True,
                Merchant.lat.isnot(None),
            )
            .limit(50)  # Pre-filter; haversine applied below
            .all()
        )

        # Apply haversine radius filter and sort
        nearby: list[tuple[float, Merchant, MerchantProfile | None]] = []
        for comp_m, comp_p in candidates:
            if comp_m.lat is None:
                continue
            dist = _haversine_km(target_m.lat, target_m.lng, comp_m.lat, comp_m.lng)
            if dist <= radius_km:
                nearby.append((dist, comp_m, comp_p))

        nearby.sort(key=lambda x: x[0])
        nearby = nearby[: min(limit, 10)]

        competitors: list[dict[str, Any]] = []
        for dist, comp_m, comp_p in nearby:
            comp_scores = _profile_scores(comp_p, target_dims)
            delta = {
                d: round(comp_scores[d] - (target_scores[d] or 0), 3)
                if comp_scores[d] is not None and target_scores[d] is not None
                else None
                for d in target_dims
            }
            competitors.append({
                "merchant_id": comp_m.merchant_id,
                "name": comp_m.name,
                "distance_km": round(dist, 2),
                "scores": comp_scores,
                "delta_vs_target": delta,
            })

        return {
            "status": "ok",
            "target_merchant_id": merchant_id,
            "target_name": target_m.name,
            "cuisine": target_m.cuisine,
            "radius_km": radius_km,
            "dimensions_compared": target_dims,
            "target_scores": target_scores,
            "competitors": competitors,
        }
    finally:
        if db is None:
            session.close()


# Backward-compat stub for old compare_competitors callers
def compare_competitors(
    merchant_id: str,
    radius_km: float = 5.0,
    limit: int = 5,
    db: Session | None = None,
) -> dict[str, Any]:
    """Backward-compatible wrapper around compare_merchant_benchmark."""
    return compare_merchant_benchmark(
        merchant_id=merchant_id,
        radius_km=radius_km,
        limit=limit,
        db=db,
    )


def register(reg: Any) -> None:
    """Auto-discovery entry point (legacy registry). No-op — tools now registered via CrewAI tool classes."""
    pass


# --- CrewAI Tool Class ---

class CompareMerchantBenchmarkInput(BaseModel):
    merchant_id: str = Field(..., description="Target merchant ID to benchmark.")
    radius_km: float = Field(5.0, description="Search radius for competitors in km (1..20).")
    limit: int = Field(5, description="Max competitors to compare (1..10).")
    dimensions: Optional[List[str]] = Field(
        None,
        description=(
            "Subset of dimension keys to compare. "
            "Valid: food_quality, image_quality, delivery_quality, packaging, "
            "service, waiting_time, menu_diversity, price_competitiveness."
        ),
    )


class CompareMerchantBenchmarkTool(BaseTool):
    name: str = "compare_merchant_benchmark"
    description: str = (
        "Compare a merchant's quality dimension scores against nearby competitors "
        "of the same cuisine. Returns target scores, competitor scores, and "
        "per-dimension delta (positive = competitor is better). "
        "Use `dimensions` to focus on specific areas of interest."
    )
    args_schema: Type[BaseModel] = CompareMerchantBenchmarkInput

    def _run(
        self,
        merchant_id: str,
        radius_km: float = 5.0,
        limit: int = 5,
        dimensions: list[str] | None = None,
    ) -> str:
        res = compare_merchant_benchmark(
            merchant_id=merchant_id,
            radius_km=min(max(0.5, radius_km), 20.0),
            limit=min(max(1, limit), 10),
            dimensions=dimensions,
        )
        return json.dumps(res, ensure_ascii=False)
