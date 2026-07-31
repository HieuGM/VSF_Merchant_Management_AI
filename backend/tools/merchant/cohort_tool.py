"""Privacy-safe aggregation and owner comparison for public merchant cohorts."""
from __future__ import annotations

import statistics
from collections import Counter
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import (
    FoodImage,
    MenuItem,
    Merchant,
    MerchantProfile,
    MerchantRating,
    Review,
)
from services.merchant_data_policy import PUBLIC_DIMENSIONS


_DIMENSION_COLUMNS = {
    "food_quality": "food_quality_score",
    "image_quality": "image_quality_score",
    "menu_diversity": "menu_diversity_score",
    "price_competitiveness": "price_competitiveness_score",
}


def _stats(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    return {
        "mean": round(statistics.fmean(values), 3),
        "median": round(statistics.median(values), 3),
        "min": round(min(values), 3),
        "max": round(max(values), 3),
    }


def _platform_rating(rating: MerchantRating | None) -> float | None:
    if rating is None:
        return None
    if rating.shopeefood_rating is not None:
        return float(rating.shopeefood_rating)
    if rating.foody_rating is not None:
        return round(float(rating.foody_rating) / 2, 3)
    return None


def aggregate_public_merchant_cohort(
    merchant_ids: list[str],
    step_id: str,
    db: Session | None = None,
) -> dict[str, Any]:
    session = db or SessionLocal()
    try:
        unique_ids = list(dict.fromkeys(str(item) for item in merchant_ids if item))
        if not unique_ids:
            return {
                "status": "insufficient_data",
                "cohort_count": 0,
                "aggregates": {},
                "evidence_refs": [],
                "provenance": {},
            }

        rows = (
            session.query(Merchant, MerchantProfile, MerchantRating)
            .outerjoin(
                MerchantProfile,
                Merchant.merchant_id == MerchantProfile.merchant_id,
            )
            .outerjoin(
                MerchantRating,
                Merchant.merchant_id == MerchantRating.merchant_id,
            )
            .filter(Merchant.merchant_id.in_(unique_ids), Merchant.is_active == True)
            .all()
        )
        actual_ids = [merchant.merchant_id for merchant, _, _ in rows]
        ratings = [
            value
            for _, _, rating in rows
            if (value := _platform_rating(rating)) is not None
        ]

        dimension_values: dict[str, list[float]] = {
            dimension: [] for dimension in PUBLIC_DIMENSIONS
        }
        for _, profile, _ in rows:
            if profile is None:
                continue
            for dimension, column in _DIMENSION_COLUMNS.items():
                value = getattr(profile, column, None)
                if value is not None:
                    dimension_values[dimension].append(float(value))

        prices = [
            float(row[0])
            for row in (
                session.query(MenuItem.price)
                .filter(
                    MenuItem.merchant_id.in_(actual_ids),
                    MenuItem.is_available == True,
                )
                .all()
            )
        ]
        images = [
            (row[0], row[1])
            for row in (
                session.query(FoodImage.dish_image_quality, FoodImage.blur_score)
                .filter(FoodImage.merchant_id.in_(actual_ids))
                .all()
            )
        ]
        image_quality_values = [
            float(quality) for quality, _ in images if quality is not None
        ]
        blur_values = [float(blur) for _, blur in images if blur is not None]

        review_rows = (
            session.query(Review.sentiment, Review.text)
            .filter(Review.merchant_id.in_(actual_ids))
            .all()
        )
        sentiment_counts: Counter[str] = Counter(
            sentiment for sentiment, _ in review_rows if sentiment
        )
        theme_counts: Counter[str] = Counter()
        theme_keywords = {
            "food_quality": ("ngon", "dở", "nguội", "nhạt", "mặn"),
            "delivery": ("giao", "ship", "chậm", "trễ"),
            "packaging": ("đóng gói", "hộp", "bao bì"),
            "service": ("phục vụ", "nhân viên", "thái độ"),
            "price": ("giá", "đắt", "rẻ"),
            "image": ("ảnh", "hình"),
        }
        for _, text in review_rows:
            lowered = text.lower()
            for theme, keywords in theme_keywords.items():
                if any(keyword in lowered for keyword in keywords):
                    theme_counts[theme] += 1

        aggregates: dict[str, Any] = {
            "rating": _stats(ratings),
            "menu_price": _stats(prices),
            "dimensions": {
                dimension: stats
                for dimension, values in dimension_values.items()
                if (stats := _stats(values)) is not None
            },
            "review_sentiment": dict(sentiment_counts),
            "review_themes": dict(theme_counts.most_common()),
            "image_quality": {
                "quality": _stats(image_quality_values),
                "blur": _stats(blur_values),
                "image_count": len(images),
            },
        }
        evidence_refs: list[str] = []
        if aggregates["rating"]:
            evidence_refs.append(f"aggregate:{step_id}:rating.mean")
        if aggregates["menu_price"]:
            evidence_refs.append(f"aggregate:{step_id}:menu_price.median")
        for dimension in aggregates["dimensions"]:
            evidence_refs.append(
                f"aggregate:{step_id}:dimensions.{dimension}.mean"
            )
        if images:
            evidence_refs.append(f"aggregate:{step_id}:image_quality.quality.mean")

        return {
            "status": "ok" if rows else "insufficient_data",
            "cohort_count": len(rows),
            "cohort_definition": {
                "candidate_count": len(unique_ids),
                "included_count": len(rows),
            },
            "aggregates": aggregates,
            "evidence_refs": evidence_refs,
            "provenance": {
                "step_id": step_id,
                "public_only": True,
                "merchant_count": len(rows),
                "review_count": len(review_rows),
                "image_count": len(images),
            },
        }
    finally:
        if db is None:
            session.close()


def compare_owner_to_public_cohort(
    owner_merchant_id: str,
    cohort: dict[str, Any],
    db: Session | None = None,
) -> dict[str, Any]:
    session = db or SessionLocal()
    try:
        profile = session.get(MerchantProfile, owner_merchant_id)
        if profile is None:
            return {
                "status": "not_found",
                "owner_merchant_id": owner_merchant_id,
                "dimensions": {},
                "evidence_refs": [],
            }
        cohort_dimensions = cohort.get("aggregates", {}).get("dimensions", {})
        comparisons: dict[str, Any] = {}
        evidence_refs: list[str] = []
        for dimension, column in _DIMENSION_COLUMNS.items():
            if dimension not in PUBLIC_DIMENSIONS:
                continue
            stats = cohort_dimensions.get(dimension)
            if not stats or stats.get("mean") is None:
                continue
            owner_value = round(float(getattr(profile, column)), 3)
            cohort_mean = round(float(stats["mean"]), 3)
            comparisons[dimension] = {
                "owner_value": owner_value,
                "cohort_mean": cohort_mean,
                "cohort_median": round(float(stats["median"]), 3),
                "delta": round(owner_value - cohort_mean, 3),
                "owner_evidence_ref": (
                    f"profile:{owner_merchant_id}:{dimension}"
                ),
                "cohort_evidence_ref": next(
                    (
                        ref
                        for ref in cohort.get("evidence_refs", [])
                        if ref.endswith(f"dimensions.{dimension}.mean")
                    ),
                    None,
                ),
            }
            evidence_refs.append(f"profile:{owner_merchant_id}:{dimension}")
            if comparisons[dimension]["cohort_evidence_ref"]:
                evidence_refs.append(comparisons[dimension]["cohort_evidence_ref"])

        return {
            "status": "ok" if comparisons else "insufficient_data",
            "owner_merchant_id": owner_merchant_id,
            "cohort_count": cohort.get("cohort_count", 0),
            "dimensions": comparisons,
            "evidence_refs": list(dict.fromkeys(evidence_refs)),
        }
    finally:
        if db is None:
            session.close()


class CompareOwnerToPublicCohortInput(BaseModel):
    owner_merchant_id: str
    cohort: dict[str, Any] = Field(description="Public cohort aggregate payload.")
