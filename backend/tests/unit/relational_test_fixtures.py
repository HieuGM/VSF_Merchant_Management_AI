from __future__ import annotations

from datetime import datetime, timezone

from database.models import (
    MerchantDimensionCalculation,
    MerchantDimensionEvidence,
    MerchantProfile,
    MerchantRating,
    OperationalMetric,
)


DIMENSIONS = (
    "food_quality",
    "image_quality",
    "delivery_quality",
    "packaging",
    "service",
    "waiting_time",
    "menu_diversity",
    "price_competitiveness",
)


def seed_relational_profile(
    db_session,
    merchant_id: str,
    *,
    scores: dict[str, float],
    bases: dict[str, str] | None = None,
    prep_minutes: float | None = None,
) -> MerchantProfile:
    values = {dimension: float(scores.get(dimension, 0.8)) for dimension in DIMENSIONS}
    profile = MerchantProfile(
        merchant_id=merchant_id,
        tier="hero",
        price_level="trung bình",
        food_quality_score=values["food_quality"],
        image_quality_score=values["image_quality"],
        delivery_quality_score=values["delivery_quality"],
        packaging_score=values["packaging"],
        service_score=values["service"],
        waiting_time_score=values["waiting_time"],
        menu_diversity_score=values["menu_diversity"],
        price_competitiveness_score=values["price_competitiveness"],
        scoring_version="test-v2",
        scored_at=datetime.now(timezone.utc),
    )
    db_session.add(profile)
    db_session.add(
        MerchantRating(
            merchant_id=merchant_id,
            shopeefood_rating=4.8,
            shopeefood_review_count=100,
            foody_rating=8.5,
            foody_review_count=20,
        )
    )
    db_session.add(
        OperationalMetric(
            merchant_id=merchant_id,
            avg_prep_time_min=prep_minutes or 12.0,
            cancel_rate=0.02,
            acceptance_rate=0.95,
            estimated_daily_orders=100,
            peak_hours=["11:00-13:00"],
            avg_delivery_time_min=28.0,
            on_time_rate=0.94,
            driver_rating=4.7,
            packaging_ok_rate=0.9,
            source_kind="development_fixture",
        )
    )
    now = datetime.now(timezone.utc)
    for dimension in DIMENSIONS:
        evidence_id = f"ev_{merchant_id}_{dimension}"
        db_session.add(
            MerchantDimensionCalculation(
                merchant_id=merchant_id,
                dimension=dimension,
                basis=(bases or {}).get(dimension, "test basis"),
                source_kind="development_fixture",
                scoring_version="test-v2",
                calculated_at=now,
            )
        )
        db_session.add(
            MerchantDimensionEvidence(
                evidence_id=evidence_id,
                merchant_id=merchant_id,
                dimension=dimension,
                evidence_type="test_metric",
                value_numeric=values[dimension],
                unit="score",
                source_kind="development_fixture",
                observed_at=now,
            )
        )
    db_session.flush()
    return profile
