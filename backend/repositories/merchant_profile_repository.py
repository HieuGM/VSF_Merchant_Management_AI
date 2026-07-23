"""Relational repository for the current eight-dimension merchant profile."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.errors import NotFoundError
from database.models import (
    MarketTrendingDish,
    Merchant,
    MerchantDimensionCalculation,
    MerchantDimensionEvidence,
    MerchantProfile,
    MerchantRating,
    OperationalMetric,
)


SCORE_COLUMNS: dict[str, str] = {
    "food_quality": "food_quality_score",
    "image_quality": "image_quality_score",
    "delivery_quality": "delivery_quality_score",
    "packaging": "packaging_score",
    "service": "service_score",
    "waiting_time": "waiting_time_score",
    "menu_diversity": "menu_diversity_score",
    "price_competitiveness": "price_competitiveness_score",
}


def _number(value: Any) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


def _evidence_dict(row: MerchantDimensionEvidence) -> dict[str, Any]:
    if row.value_numeric is not None:
        value: Any = _number(row.value_numeric)
    elif row.value_text is not None:
        value = row.value_text
    else:
        value = row.value_boolean
    return {
        "evidence_id": row.evidence_id,
        "type": row.evidence_type,
        "value": value,
        "unit": row.unit,
        "ref_type": row.reference_type,
        "ref_ids": list(row.reference_ids or []),
        "source_kind": row.source_kind,
    }


class MerchantProfileRepository:
    """Read the current merchant profile from typed relational facts."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def _base_row(
        self, merchant_id: str
    ) -> tuple[MerchantProfile, Merchant, MerchantRating | None, OperationalMetric | None] | None:
        stmt = (
            select(MerchantProfile, Merchant, MerchantRating, OperationalMetric)
            .join(Merchant, Merchant.merchant_id == MerchantProfile.merchant_id)
            .outerjoin(
                MerchantRating,
                MerchantRating.merchant_id == MerchantProfile.merchant_id,
            )
            .outerjoin(
                OperationalMetric,
                OperationalMetric.merchant_id == MerchantProfile.merchant_id,
            )
            .where(MerchantProfile.merchant_id == merchant_id)
        )
        row = self._db.execute(stmt).first()
        if row is None:
            return None
        return row[0], row[1], row[2], row[3]

    def _calculations(
        self, merchant_id: str
    ) -> dict[str, MerchantDimensionCalculation]:
        rows = self._db.execute(
            select(MerchantDimensionCalculation).where(
                MerchantDimensionCalculation.merchant_id == merchant_id
            )
        ).scalars()
        return {row.dimension: row for row in rows}

    def _evidence(
        self, merchant_id: str, dimension: str | None = None
    ) -> list[MerchantDimensionEvidence]:
        stmt = select(MerchantDimensionEvidence).where(
            MerchantDimensionEvidence.merchant_id == merchant_id
        )
        if dimension is not None:
            stmt = stmt.where(MerchantDimensionEvidence.dimension == dimension)
        stmt = stmt.order_by(
            MerchantDimensionEvidence.dimension,
            MerchantDimensionEvidence.evidence_id,
        )
        return list(self._db.execute(stmt).scalars())

    def get_profile(self, merchant_id: str) -> dict[str, Any] | None:
        base = self._base_row(merchant_id)
        if base is None:
            return None
        profile, merchant, rating, operations = base
        calculations = self._calculations(merchant_id)
        evidence_by_dimension: dict[str, list[dict[str, Any]]] = {
            dimension: [] for dimension in SCORE_COLUMNS
        }
        for row in self._evidence(merchant_id):
            evidence_by_dimension[row.dimension].append(_evidence_dict(row))

        dimensions: dict[str, dict[str, Any]] = {}
        for dimension, column in SCORE_COLUMNS.items():
            calculation = calculations.get(dimension)
            evidence = evidence_by_dimension[dimension]
            dimensions[dimension] = {
                "score": float(getattr(profile, column)),
                "basis": calculation.basis if calculation else "unspecified",
                "evidence": evidence,
                "evidence_refs": [item["evidence_id"] for item in evidence],
            }

        trend_rows = self._db.execute(
            select(MarketTrendingDish)
            .where(
                MarketTrendingDish.city_slug == merchant.city_slug,
                MarketTrendingDish.cuisine == merchant.cuisine,
            )
            .order_by(MarketTrendingDish.rank)
            .limit(8)
        ).scalars()

        operation_kpis = {}
        delivery_stats = {}
        if operations is not None:
            operation_kpis = {
                "avg_prep_minutes": _number(operations.avg_prep_time_min),
                "cancel_rate": _number(operations.cancel_rate),
                "acceptance_rate": _number(operations.acceptance_rate),
                "estimated_daily_orders": operations.estimated_daily_orders,
                "peak_hours": list(operations.peak_hours or []),
            }
            delivery_stats = {
                "avg_delivery_minutes": _number(operations.avg_delivery_time_min),
                "on_time_rate": _number(operations.on_time_rate),
                "driver_rating": _number(operations.driver_rating),
                "packaging_ok_rate": _number(operations.packaging_ok_rate),
            }

        ratings = {}
        if rating is not None:
            ratings = {
                "shopeefood_avg": _number(rating.shopeefood_rating),
                "shopeefood_total_review": rating.shopeefood_review_count,
                "foody_rating": _number(rating.foody_rating),
                "foody_review_count": rating.foody_review_count,
            }

        return {
            "merchant_id": merchant_id,
            "tier": profile.tier,
            "metadata": {
                "name": merchant.name,
                "cuisine": merchant.cuisine,
                "category": merchant.category,
                "location": {
                    "address": merchant.address,
                    "city": merchant.city,
                    "lat": merchant.lat,
                    "lng": merchant.lng,
                },
                "open_hours": {
                    "open": merchant.opens_at.isoformat() if merchant.opens_at else None,
                    "close": merchant.closes_at.isoformat() if merchant.closes_at else None,
                },
                "taste_tags": list(merchant.taste_tags or []),
                "diet_tags": list(merchant.diet_tags or []),
                "ingredient_tags": list(merchant.ingredient_tags or []),
            },
            "price_level": profile.price_level,
            "dimensions": dimensions,
            "attributes": {
                "customer_segments": list(merchant.customer_segments or []),
                "peak_time": list(operations.peak_hours or []) if operations else [],
                "trending_dishes": [
                    {
                        "dish": row.dish_name,
                        "trend_score": _number(row.trend_score),
                        "rank": row.rank,
                    }
                    for row in trend_rows
                ],
                "operation_kpis": operation_kpis,
                "delivery_stats": delivery_stats,
            },
            "ratings": ratings,
            "schema_version": "2.0",
            "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
        }

    def get_dimension_evidence(
        self, merchant_id: str, dimension: str
    ) -> dict[str, Any]:
        if dimension not in SCORE_COLUMNS:
            return {
                "merchant_id": merchant_id,
                "dimension": dimension,
                "status": "dimension_not_found",
                "available_dimensions": list(SCORE_COLUMNS),
            }

        base = self._base_row(merchant_id)
        if base is None:
            return {
                "merchant_id": merchant_id,
                "dimension": dimension,
                "status": "not_found",
                "evidence": [],
            }
        profile = base[0]
        calculation = self._calculations(merchant_id).get(dimension)
        return {
            "merchant_id": merchant_id,
            "dimension": dimension,
            "score": float(getattr(profile, SCORE_COLUMNS[dimension])),
            "basis": calculation.basis if calculation else "unspecified",
            "evidence": [
                _evidence_dict(row)
                for row in self._evidence(merchant_id, dimension=dimension)
            ],
        }

    def get_profile_or_raise(self, merchant_id: str) -> dict[str, Any]:
        profile = self.get_profile(merchant_id)
        if profile is None:
            raise NotFoundError(
                f"Không tìm thấy hồ sơ merchant '{merchant_id}'.",
                details={"merchant_id": merchant_id},
            )
        return profile
