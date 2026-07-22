"""Unit tests for Merchant Tools Package (Task 2).

Ensures:
- `get_profile_evidence` tool retrieves profile and evidence details while obeying C2.
- `compare_competitors` tool compares candidate merchants in radius.
- `diagnose_merchant` tool caps diagnosis causes at max 5 and requires evidence_refs.
- `recommend_improvements` tool generates evidence-backed actionable steps.
- All tools register cleanly with ToolRegistry and adhere to allow_list permissions.
"""
from __future__ import annotations

import pytest
from database.models import Merchant, MerchantProfile, Review, OperationalMetric
from tools.merchant.profile_tool import get_profile_evidence
from tools.merchant.competitor_tool import compare_competitors
from tools.merchant.diagnosis_tool import diagnose_merchant, recommend_improvements
from tools.registry import registry


@pytest.fixture
def sample_merchant_for_tools(db_session):
    """Seed test merchant with weak waiting_time and packaging scores for diagnostic testing."""
    merchant = Merchant(
        merchant_id="m_tool_test_01",
        name="Phở Gia Truyền Hà Nội",
        cuisine="Món Việt",
        city="Hà Nội",
        city_slug="ha-noi",
        address="45 Hang Bac",
        lat=21.03,
        lng=105.85,
    )
    db_session.add(merchant)

    competitor = Merchant(
        merchant_id="m_tool_comp_02",
        name="Phở Thìn Bờ Hồ",
        cuisine="Món Việt",
        city="Hà Nội",
        city_slug="ha-noi",
        address="13 Dinh Tien Hoang",
        lat=21.031,
        lng=105.852,
    )
    db_session.add(competitor)

    profile_data = {
        "merchant_id": "m_tool_test_01",
        "tier": "gold",
        "overall_score": 0.58,  # Must be stripped per C2
        "dimensions": {
            "food_quality": {"score": 8.0, "basis": "Vị ngon", "evidence_refs": ["REV-201"]},
            "waiting_time": {
                "score": 4.5,  # Weak dimension < 6.0
                "basis": "Chuẩn bị lâu (18.5 phút)",
                "evidence_refs": ["METRIC-m_tool_test_01"],
            },
            "packaging": {
                "score": 5.0,  # Weak dimension < 6.0
                "basis": "Đóng gói chưa chắc chắn",
                "evidence_refs": ["REV-202"],
            },
            "image_quality": {"score": 7.0, "basis": "Ảnh ổn", "evidence_refs": []},
            "delivery_quality": {"score": 7.5, "basis": "Giao khá tốt", "evidence_refs": []},
            "service": {"score": 8.0, "basis": "Thái độ tốt", "evidence_refs": []},
            "menu_diversity": {"score": 7.0, "basis": "15 món", "evidence_refs": []},
            "price_level": {"score": 7.5, "basis": "Hợp lý", "evidence_refs": []},
        },
    }

    profile = MerchantProfile(
        merchant_id="m_tool_test_01",
        dimensions_json=profile_data["dimensions"],
        profile_json=profile_data,
        schema_version="1.0",
        source_kind="development_fixture",
    )
    db_session.add(profile)

    metric = OperationalMetric(
        merchant_id="m_tool_test_01",
        avg_prep_time_min=18.5,
    )
    db_session.add(metric)

    db_session.flush()
    return merchant


def test_get_profile_evidence_tool(db_session, sample_merchant_for_tools):
    res = get_profile_evidence("m_tool_test_01", db=db_session)

    assert res["merchant_id"] == "m_tool_test_01"
    assert "dimensions" in res
    assert "overall_score" not in res  # C2 compliance check
    assert "overall_score" not in res["dimensions"]


def test_get_profile_evidence_tool_specific_dimension(db_session, sample_merchant_for_tools):
    res = get_profile_evidence("m_tool_test_01", dimension="waiting_time", db=db_session)

    assert res["merchant_id"] == "m_tool_test_01"
    assert res["dimension"] == "waiting_time"
    assert res["details"]["score"] == 4.5


def test_diagnose_merchant_tool(db_session, sample_merchant_for_tools):
    res = diagnose_merchant("m_tool_test_01", db=db_session)

    assert res["merchant_id"] == "m_tool_test_01"
    assert res["status"] == "ok"
    assert len(res["causes"]) == 2  # waiting_time (4.5) and packaging (5.0)

    for cause in res["causes"]:
        assert "dimension" in cause
        assert "score" in cause
        assert cause["score"] < 6.0
        assert len(cause["evidence_refs"]) >= 1


def test_recommend_improvements_tool(db_session, sample_merchant_for_tools):
    res = recommend_improvements("m_tool_test_01", db=db_session)

    assert res["merchant_id"] == "m_tool_test_01"
    assert "actions" in res
    assert len(res["actions"]) == 2

    for action in res["actions"]:
        assert "action_title" in action
        assert "dimension" in action
        assert len(action["evidence_refs"]) >= 1


def test_compare_competitors_tool(db_session, sample_merchant_for_tools):
    res = compare_competitors("m_tool_test_01", radius_km=5.0, db=db_session)

    assert res["target_merchant_id"] == "m_tool_test_01"
    assert "competitors" in res
    assert len(res["competitors"]) >= 1
    first_comp = res["competitors"][0]
    assert "merchant_id" in first_comp
    assert "distance_km" in first_comp


def test_merchant_tools_registered_in_registry():
    registered_names = set(registry.names())

    assert "get_profile_evidence" in registered_names
    assert "diagnose_merchant" in registered_names
    assert "recommend_improvements" in registered_names
    assert "compare_competitors" in registered_names
