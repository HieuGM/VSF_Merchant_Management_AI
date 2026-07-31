from __future__ import annotations

import json

from database.models import Merchant
from relational_test_fixtures import seed_relational_profile
from services.merchant_data_policy import PUBLIC_DIMENSIONS
from tools.merchant.cohort_tool import (
    aggregate_public_merchant_cohort,
    compare_owner_to_public_cohort,
)


def _merchant(db_session, merchant_id: str, name: str) -> None:
    db_session.add(
        Merchant(
            merchant_id=merchant_id,
            name=name,
            cuisine="Món Việt Cohort Test",
            category="Quán ăn",
            city="Hà Nội",
            city_slug="ha_noi",
            lat=21.028,
            lng=105.854,
            is_active=True,
        )
    )
def test_cohort_contains_public_aggregates_and_no_private_kpis(db_session):
    for merchant_id, food_score in (("m_cohort_01", 0.7), ("m_cohort_02", 0.9)):
        _merchant(db_session, merchant_id, f"Quán {merchant_id}")
        seed_relational_profile(
            db_session,
            merchant_id,
            scores={
                "food_quality": food_score,
                "waiting_time": 0.2,
                "packaging": 0.3,
            },
        )
    db_session.commit()

    result = aggregate_public_merchant_cohort(
        ["m_cohort_01", "m_cohort_02"],
        step_id="market-1",
        db=db_session,
    )

    assert result["status"] == "ok"
    assert result["cohort_count"] == 2
    assert result["aggregates"]["dimensions"]["food_quality"]["mean"] == 0.8
    assert set(result["aggregates"]["dimensions"]) <= PUBLIC_DIMENSIONS
    serialized = json.dumps(result, ensure_ascii=False)
    assert "estimated_daily_orders" not in serialized
    assert "cancel_rate" not in serialized
    assert "waiting_time" not in serialized
    assert "packaging" not in serialized
    assert "aggregate:market-1:dimensions.food_quality.mean" in result["evidence_refs"]


def test_owner_comparison_uses_only_public_dimensions(db_session):
    _merchant(db_session, "m_cohort_owner", "Quán Owner")
    seed_relational_profile(
        db_session,
        "m_cohort_owner",
        scores={
            "food_quality": 0.6,
            "image_quality": 0.7,
            "waiting_time": 0.1,
        },
    )
    _merchant(db_session, "m_cohort_comp", "Quán Competitor")
    seed_relational_profile(
        db_session,
        "m_cohort_comp",
        scores={
            "food_quality": 0.8,
            "image_quality": 0.9,
            "waiting_time": 0.95,
        },
    )
    db_session.commit()
    cohort = aggregate_public_merchant_cohort(
        ["m_cohort_comp"],
        step_id="market-compare",
        db=db_session,
    )

    result = compare_owner_to_public_cohort(
        "m_cohort_owner",
        cohort,
        db=db_session,
    )

    assert result["status"] == "ok"
    assert set(result["dimensions"]) <= PUBLIC_DIMENSIONS
    assert result["dimensions"]["food_quality"]["owner_value"] == 0.6
    assert result["dimensions"]["food_quality"]["cohort_mean"] == 0.8
    assert result["dimensions"]["food_quality"]["delta"] == -0.2
    assert "waiting_time" not in result["dimensions"]
