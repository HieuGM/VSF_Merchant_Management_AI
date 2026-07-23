"""Pure mapping tests for the legacy JSON -> relational backfill."""

from decimal import Decimal

import pytest

from services.merchant_relational_mapping import map_legacy_profile


def _legacy_profile() -> dict:
    dimensions = {
        "food_quality": {
            "score": 0.7,
            "basis": "rating + reviews",
            "evidence": [{"type": "rating", "value": 4.8}],
        },
        "image_quality": {
            "score": 0.6,
            "basis": "photo coverage",
            "evidence": [{"type": "has_photo_ratio", "value": 0.6}],
        },
        "delivery_quality": {
            "score": 0.75,
            "basis": "delivery stats",
            "evidence": [{"type": "on_time_rate", "value": 0.91}],
        },
        "packaging": {
            "score": 0.8,
            "basis": "packaging feedback",
            "evidence": [{"type": "packaging_ok_rate", "value": 0.95}],
        },
        "service": {
            "score": 0.9,
            "basis": "rating",
            "evidence": [{"type": "service_complaint_count", "value": 0}],
        },
        "waiting_time": {
            "score": 0.8,
            "basis": "prep time + complaints",
            "evidence": [
                {"type": "avg_prep_minutes", "value": 13},
                {"type": "late_complaint_count", "value": 0},
            ],
        },
        "menu_diversity": {
            "score": 0.65,
            "basis": "dish count",
            "evidence": [{"type": "dish_count", "value": 32}],
        },
        "price_level": {
            "score": 0.72,
            "basis": "peer price",
            "evidence": [{"type": "price_ratio", "value": 0.9}],
        },
    }
    return {
        "tier": "background",
        "price_level": "trung bình",
        "dimensions": dimensions,
        "ratings": {
            "shopeefood_avg": 4.8,
            "shopeefood_total_review": 1000,
            "foody_rating": 6.7,
            "foody_review_count": 190,
        },
        "attributes": {
            "customer_segments": ["văn phòng"],
            "operation_kpis": {
                "avg_prep_minutes": 13,
                "cancel_rate": 0.02,
                "acceptance_rate": 0.97,
                "estimated_daily_orders": 84,
                "peak_hours": ["11:00-13:00"],
            },
            "delivery_stats": {
                "avg_delivery_minutes": 25,
                "on_time_rate": 0.91,
                "driver_rating": 4.7,
                "packaging_ok_rate": 0.95,
            },
        },
    }


def test_maps_complete_legacy_profile_to_typed_relational_rows():
    mapped = map_legacy_profile("94", _legacy_profile())

    assert mapped.profile["waiting_time_score"] == Decimal("0.800")
    assert mapped.profile["price_competitiveness_score"] == Decimal("0.720")
    assert mapped.operations["avg_prep_time_min"] == Decimal("13.00")
    assert mapped.ratings["shopeefood_rating"] == Decimal("4.80")
    assert len(mapped.calculations) == 8
    assert {row["dimension"] for row in mapped.calculations} == {
        "food_quality",
        "image_quality",
        "delivery_quality",
        "packaging",
        "service",
        "waiting_time",
        "menu_diversity",
        "price_competitiveness",
    }


def test_waiting_time_drops_late_delivery_complaint_evidence():
    legacy = _legacy_profile()
    legacy["dimensions"]["waiting_time"]["score"] = 0.4
    mapped = map_legacy_profile("94", legacy)

    waiting_evidence = [
        row for row in mapped.evidence if row["dimension"] == "waiting_time"
    ]
    assert [row["evidence_type"] for row in waiting_evidence] == [
        "avg_prep_minutes"
    ]
    assert mapped.profile["waiting_time_score"] == Decimal("0.800")
    waiting_calculation = next(
        row for row in mapped.calculations if row["dimension"] == "waiting_time"
    )
    assert waiting_calculation["basis"] == "avg_prep_time_min only"


def test_evidence_ids_are_deterministic():
    first = map_legacy_profile("94", _legacy_profile())
    second = map_legacy_profile("94", _legacy_profile())

    assert [row["evidence_id"] for row in first.evidence] == [
        row["evidence_id"] for row in second.evidence
    ]


def test_rejects_profile_with_missing_dimension():
    legacy = _legacy_profile()
    del legacy["dimensions"]["service"]

    with pytest.raises(ValueError, match="missing dimensions: service"):
        map_legacy_profile("94", legacy)


def test_rejects_score_outside_zero_to_one():
    legacy = _legacy_profile()
    legacy["dimensions"]["service"]["score"] = 8.0

    with pytest.raises(ValueError, match="service score must be between 0 and 1"):
        map_legacy_profile("94", legacy)
