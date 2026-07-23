"""Unit tests for Merchant Profile and Evidence Repositories (Task 1).

Ensures:
- 8-dimension profile lookup works.
- `overall_score` is strictly stripped per security rule C2.
- Evidence references are properly fetched by ID prefix.
"""
from __future__ import annotations

from datetime import datetime, timezone
import pytest
from database.models import (
    Merchant,
    MerchantDimensionCalculation,
    MerchantDimensionEvidence,
    MerchantProfile,
    MerchantRating,
    OperationalMetric,
    Review,
)
from repositories.merchant_profile_repository import MerchantProfileRepository
from repositories.evidence_repository import EvidenceRepository


@pytest.fixture
def sample_merchant_data(db_session):
    """Seed test merchant data in test DB session."""
    merchant = Merchant(
        merchant_id="test_merchant_001",
        name="Quán Cơm Tấm Sài Gòn",
        cuisine="Món Việt",
        city="TP. HCM",
        city_slug="tp-hcm",
        address="123 Nguyễn Trãi, Q1",
        lat=10.77,
        lng=106.69,
    )
    db_session.add(merchant)

    profile = MerchantProfile(
        merchant_id="test_merchant_001",
        tier="hero",
        price_level="trung bình",
        food_quality_score=0.85,
        image_quality_score=0.70,
        delivery_quality_score=0.90,
        packaging_score=0.80,
        service_score=0.85,
        waiting_time_score=0.75,
        menu_diversity_score=0.80,
        price_competitiveness_score=0.70,
        scoring_version="2.0",
        scored_at=datetime.now(timezone.utc),
    )
    db_session.add(profile)
    db_session.add(
        MerchantRating(
            merchant_id="test_merchant_001",
            shopeefood_rating=4.8,
            shopeefood_review_count=1000,
            foody_rating=8.5,
            foody_review_count=20,
        )
    )

    dimensions = (
        "food_quality",
        "image_quality",
        "delivery_quality",
        "packaging",
        "service",
        "waiting_time",
        "menu_diversity",
        "price_competitiveness",
    )
    for dimension in dimensions:
        db_session.add(
            MerchantDimensionCalculation(
                merchant_id="test_merchant_001",
                dimension=dimension,
                basis=(
                    "preparation_time"
                    if dimension == "waiting_time"
                    else f"{dimension} basis"
                ),
                source_kind="development_fixture",
                scoring_version="2.0",
                calculated_at=datetime.now(timezone.utc),
            )
        )

    db_session.add(
        MerchantDimensionEvidence(
            evidence_id="ev:test:waiting",
            merchant_id="test_merchant_001",
            dimension="waiting_time",
            evidence_type="avg_prep_minutes",
            value_numeric=12.5,
            unit="minutes",
            reference_type="operational_metric",
            reference_ids=["test_merchant_001"],
            source_kind="development_fixture",
        )
    )

    review = Review(
        review_id="REV-101",
        merchant_id="test_merchant_001",
        rating=4.5,
        text="Cơm tấm rất ngon, sườn mềm đậm đà!",
        sentiment="positive",
        source_kind="real",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(review)

    metric = OperationalMetric(
        merchant_id="test_merchant_001",
        avg_prep_time_min=12.5,
        peak_hours=["11:00-13:00"],
        source_kind="development_fixture",
    )
    db_session.add(metric)

    db_session.flush()
    return merchant


def test_get_profile_returns_valid_schema(db_session, sample_merchant_data):
    repo = MerchantProfileRepository(db_session)
    profile = repo.get_profile("test_merchant_001")

    assert profile is not None
    assert profile["merchant_id"] == "test_merchant_001"
    assert "dimensions" in profile
    assert len(profile["dimensions"]) == 8


def test_get_profile_strips_overall_score_security_c2(db_session, sample_merchant_data):
    repo = MerchantProfileRepository(db_session)
    profile = repo.get_profile("test_merchant_001")

    assert profile is not None
    # C2 Rule: overall_score must NOT be in top-level or dimensions
    assert "overall_score" not in profile
    assert "overall_score" not in profile["dimensions"]
    assert "overall_score_internal" not in profile


def test_get_dimension_evidence_is_bounded(db_session, sample_merchant_data):
    repo = MerchantProfileRepository(db_session)

    result = repo.get_dimension_evidence("test_merchant_001", "waiting_time")

    assert result["dimension"] == "waiting_time"
    assert result["score"] == 0.75
    assert result["basis"] == "preparation_time"
    assert result["evidence"] == [
        {
            "evidence_id": "ev:test:waiting",
            "type": "avg_prep_minutes",
            "value": 12.5,
            "unit": "minutes",
            "ref_type": "operational_metric",
            "ref_ids": ["test_merchant_001"],
            "source_kind": "development_fixture",
        }
    ]


def test_unknown_dimension_does_not_fall_back_to_full_profile(
    db_session, sample_merchant_data
):
    repo = MerchantProfileRepository(db_session)

    result = repo.get_dimension_evidence("test_merchant_001", "unknown")

    assert result == {
        "merchant_id": "test_merchant_001",
        "dimension": "unknown",
        "status": "dimension_not_found",
        "available_dimensions": [
            "food_quality",
            "image_quality",
            "delivery_quality",
            "packaging",
            "service",
            "waiting_time",
            "menu_diversity",
            "price_competitiveness",
        ],
    }


def test_get_profile_not_found(db_session):
    repo = MerchantProfileRepository(db_session)
    profile = repo.get_profile("non_existent_merchant")
    assert profile is None


def test_get_evidence_by_refs(db_session, sample_merchant_data):
    repo = EvidenceRepository(db_session)
    evidences = repo.get_evidence_by_refs(["REV-101", "METRIC-test_merchant_001"])

    assert len(evidences) == 2
    ref_map = {e["ref"]: e for e in evidences}

    assert "REV-101" in ref_map
    assert ref_map["REV-101"]["type"] == "review"
    assert "Cơm tấm rất ngon" in ref_map["REV-101"]["content"]

    assert "METRIC-test_merchant_001" in ref_map
    assert ref_map["METRIC-test_merchant_001"]["type"] == "operational_metric"
    assert ref_map["METRIC-test_merchant_001"]["avg_prep_time_min"] == 12.5
