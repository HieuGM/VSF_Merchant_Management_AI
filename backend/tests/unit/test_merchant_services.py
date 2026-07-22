"""Unit tests for Merchant Services (Task 3).

Ensures:
- `MerchantProfileService` returns clean profile views obeying C2.
- `RecommendationService` generates actionable steps backed by evidence refs.
- `CompetitorService` analyzes competitor profiles effectively.
"""
from __future__ import annotations

import pytest
from database.models import Merchant, MerchantProfile, Review, OperationalMetric
from services.merchant_profile_service import MerchantProfileService
from services.recommendation_service import RecommendationService
from services.competitor_service import CompetitorService


@pytest.fixture
def sample_merchant_for_services(db_session):
    """Seed test merchant data for service layer testing."""
    merchant = Merchant(
        merchant_id="m_svc_test_01",
        name="Bún Chả Hương Liên",
        cuisine="Món Việt",
        city="Hà Nội",
        city_slug="ha-noi",
        address="24 Le Van Huu",
        lat=21.018,
        lng=105.853,
    )
    db_session.add(merchant)

    competitor = Merchant(
        merchant_id="m_svc_comp_02",
        name="Bún Chả Đắc Kim",
        cuisine="Món Việt",
        city="Hà Nội",
        city_slug="ha-noi",
        address="1 Hang Manh",
        lat=21.033,
        lng=105.847,
    )
    db_session.add(competitor)

    profile_data = {
        "merchant_id": "m_svc_test_01",
        "tier": "gold",
        "overall_score": 0.62,  # Must be stripped per C2
        "dimensions": {
            "food_quality": {"score": 8.5, "basis": "Chả nướng thơm", "evidence_refs": ["REV-301"]},
            "waiting_time": {
                "score": 4.8,  # Weak dimension < 6.0
                "basis": "Quá tải giờ cao điểm",
                "evidence_refs": ["METRIC-m_svc_test_01"],
            },
            "packaging": {
                "score": 5.2,  # Weak dimension < 6.0
                "basis": "Nước chấm bị đổ",
                "evidence_refs": ["REV-302"],
            },
            "image_quality": {"score": 7.5, "basis": "Ảnh chụp nét", "evidence_refs": []},
            "delivery_quality": {"score": 7.0, "basis": "Tương đối", "evidence_refs": []},
            "service": {"score": 8.0, "basis": "Nhiệt tình", "evidence_refs": []},
            "menu_diversity": {"score": 7.0, "basis": "Đủ món", "evidence_refs": []},
            "price_level": {"score": 8.0, "basis": "Hợp lý", "evidence_refs": []},
        },
    }

    profile = MerchantProfile(
        merchant_id="m_svc_test_01",
        dimensions_json=profile_data["dimensions"],
        profile_json=profile_data,
        schema_version="1.0",
        source_kind="development_fixture",
    )
    db_session.add(profile)

    metric = OperationalMetric(
        merchant_id="m_svc_test_01",
        avg_prep_time_min=17.0,
    )
    db_session.add(metric)

    db_session.flush()
    return merchant


def test_merchant_profile_service_get_view(db_session, sample_merchant_for_services):
    svc = MerchantProfileService(db_session)
    view = svc.get_profile_view("m_svc_test_01")

    assert view is not None
    assert view["merchant_id"] == "m_svc_test_01"
    assert "dimensions" in view
    assert "overall_score" not in view  # Security C2 check


def test_recommendation_service_generate_actions(db_session, sample_merchant_for_services):
    svc = RecommendationService(db_session)
    result = svc.generate_recommendations("m_svc_test_01")

    assert result["merchant_id"] == "m_svc_test_01"
    assert "actions" in result
    assert len(result["actions"]) == 2  # waiting_time (4.8) and packaging (5.2)

    for action in result["actions"]:
        assert "action_title" in action
        assert "dimension" in action
        assert "evidence_refs" in action
        assert len(action["evidence_refs"]) >= 1


def test_competitor_service_analyze(db_session, sample_merchant_for_services):
    svc = CompetitorService(db_session)
    analysis = svc.analyze_competitors("m_svc_test_01", radius_km=5.0)

    assert analysis["target_merchant_id"] == "m_svc_test_01"
    assert "competitors" in analysis
    assert len(analysis["competitors"]) >= 1
