"""Unit tests for Merchant Services (Task 3).

Ensures:
- `MerchantProfileService` returns clean profile views obeying C2.
- `RecommendationService` generates actionable steps backed by evidence refs.
- `CompetitorService` analyzes competitor profiles effectively.
"""
from __future__ import annotations

import pytest
from database.models import Merchant
from relational_test_fixtures import seed_relational_profile
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

    seed_relational_profile(
        db_session,
        "m_svc_test_01",
        scores={"food_quality": 0.85, "waiting_time": 0.48, "packaging": 0.52},
        bases={"waiting_time": "Quá tải giờ cao điểm", "packaging": "Nước chấm bị đổ"},
        prep_minutes=17.0,
    )
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
    assert len(result["actions"]) == 2

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
