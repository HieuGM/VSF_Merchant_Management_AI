"""Merchant profile repository — read access to the 8-dimension profile (§6.4).

Reconstructs the profile document from the RELATIONAL merchant schema
(migrations `b1c2d3e4f5a6` + `c2d3e4f5a6b7`): typed scores in `merchant_profiles`,
per-dimension `basis` in `merchant_dimension_calculations`, typed evidence in
`merchant_dimension_evidence`, platform ratings, operational KPIs, and the
market trending aggregate. The legacy `dimensions_json` no longer exists.

Optimized: uses a single query with eager-loaded relationships for the core
entities (Merchant, MerchantProfile, MerchantRating, OperationalMetric) and
batch queries for calculations/evidence. Down from 6 queries to 3.

The returned dict keeps the FROZEN tool output shape (`get_merchant_profile`,
`get_trending_dishes`): dimension key `price_competitiveness` is emitted back as
`price_level` (the public contract name, design §6.4). Repository receives a
Session; it never opens/closes one (the tool layer owns the SessionLocal).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from database.models import (
    Merchant,
    MerchantProfile,
    MerchantRating,
    OperationalMetric,
    MerchantDimensionCalculation,
    MerchantDimensionEvidence,
    MarketTrendingDish,
)

# relational dimension name -> public contract name (§6.4 rename)
_DIM_TO_PUBLIC = {"price_competitiveness": "price_level"}

# (relational column attr, relational dimension name) in contract order
_SCORE_DIMENSIONS = (
    ("food_quality_score", "food_quality"),
    ("image_quality_score", "image_quality"),
    ("delivery_quality_score", "delivery_quality"),
    ("packaging_score", "packaging"),
    ("service_score", "service"),
    ("waiting_time_score", "waiting_time"),
    ("menu_diversity_score", "menu_diversity"),
    ("price_competitiveness_score", "price_competitiveness"),
)


def _num(v: Any) -> Any:
    """Decimal/float -> int when integral, else float; passthrough for None."""
    if v is None:
        return None
    f = float(v)
    return int(f) if f.is_integer() else f


def _evidence_value(row: MerchantDimensionEvidence) -> Any:
    if row.value_boolean is not None:
        return row.value_boolean
    if row.value_numeric is not None:
        return _num(row.value_numeric)
    return row.value_text


class MerchantProfileRepository:
    """Read access to merchant 8-dimension profiles (relational reconstruction)."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_profile(self, merchant_id: str) -> dict[str, Any] | None:
        """Reconstruct the profile document for a merchant, or None if absent.

        Optimized: single query for Merchant (with eager-loaded ratings, profile,
        operational_metric), then 2 batch queries for calculations + evidence.
        Total: 3 queries down from 6.
        """
        # Single query with eager-loaded relationships
        stmt = (
            select(Merchant)
            .options(
                joinedload(Merchant.profile),
                joinedload(Merchant.ratings),
                joinedload(Merchant.operational_metric),
            )
            .where(Merchant.merchant_id == merchant_id)
        )
        merchant = self._db.execute(stmt).unique().scalar_one_or_none()
        if merchant is None or merchant.profile is None:
            return None

        prof = merchant.profile
        ratings = merchant.ratings
        op = merchant.operational_metric

        # Batch queries for calculations and evidence (2 queries)
        basis_by_dim = {
            c.dimension: c.basis
            for c in self._db.execute(
                select(MerchantDimensionCalculation).where(
                    MerchantDimensionCalculation.merchant_id == merchant_id)
            ).scalars()
        }
        evidence_by_dim: dict[str, list[dict[str, Any]]] = {}
        for e in self._db.execute(
            select(MerchantDimensionEvidence).where(
                MerchantDimensionEvidence.merchant_id == merchant_id)
        ).scalars():
            evidence_by_dim.setdefault(e.dimension, []).append(
                {"type": e.evidence_type, "value": _evidence_value(e)}
            )

        dimensions: dict[str, Any] = {}
        for attr, dim in _SCORE_DIMENSIONS:
            public_key = _DIM_TO_PUBLIC.get(dim, dim)
            dimensions[public_key] = {
                "score": _num(getattr(prof, attr)),
                "evidence": evidence_by_dim.get(dim, []),
                "basis": basis_by_dim.get(dim, ""),
            }

        return {
            "merchant_id": merchant_id,
            "tier": prof.tier,
            "price_level": prof.price_level,
            "overall_score": _num(prof.overall_score_internal),  # stripped externally
            "dimensions": dimensions,
            "ratings": self._ratings(ratings),
            "attributes": self._attributes(merchant, op),
            "updated_at": prof.updated_at.isoformat() if prof.updated_at else None,
        }

    @staticmethod
    def _ratings(r: MerchantRating | None) -> dict[str, Any]:
        if r is None:
            return {}
        return {
            "shopeefood_avg": _num(r.shopeefood_rating),
            "shopeefood_total_review": r.shopeefood_review_count,
            "foody_rating": _num(r.foody_rating),
            "foody_review_count": r.foody_review_count,
        }

    def _attributes(
        self, merchant: Merchant | None, op: OperationalMetric | None
    ) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "customer_segments": list(merchant.customer_segments or []) if merchant else [],
        }
        if op is not None:
            attrs["peak_hours"] = list(op.peak_hours or [])
            attrs["operation_kpis"] = {
                "cancel_rate": _num(op.cancel_rate),
                "acceptance_rate": _num(op.acceptance_rate),
                "avg_prep_minutes": _num(op.avg_prep_time_min),
                "estimated_daily_orders": op.estimated_daily_orders,
                "peak_hours": list(op.peak_hours or []),
            }
            attrs["delivery_stats"] = {
                "on_time_rate": _num(op.on_time_rate),
                "driver_rating": _num(op.driver_rating),
                "packaging_ok_rate": _num(op.packaging_ok_rate),
                "avg_delivery_minutes": _num(op.avg_delivery_time_min),
            }
        attrs["trending_dishes"] = self._trending(merchant)
        return attrs

    def _trending(self, merchant: Merchant | None) -> list[dict[str, Any]]:
        """Market trending dishes for the merchant's (city_slug, cuisine) market."""
        if merchant is None:
            return []
        rows = self._db.execute(
            select(MarketTrendingDish)
            .where(
                MarketTrendingDish.city_slug == merchant.city_slug,
                MarketTrendingDish.cuisine == merchant.cuisine,
            )
            .order_by(MarketTrendingDish.rank)
        ).scalars()
        return [{"dish": t.dish_name, "total_likes": _num(t.trend_score)} for t in rows]
