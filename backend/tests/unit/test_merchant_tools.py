"""Unit tests for Merchant Tools Package (Task 2).

Ensures active pure tool functions preserve evidence and privacy contracts.
"""
from __future__ import annotations

import pytest
from database.models import Merchant
from relational_test_fixtures import seed_relational_profile
from tools.merchant.profile_tool import get_merchant_profile_summary
from tools.merchant.competitor_tool import compare_merchant_benchmark
from tools.merchant.diagnosis_tool import diagnose_merchant, recommend_improvements


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

    seed_relational_profile(
        db_session,
        "m_tool_test_01",
        scores={"food_quality": 0.8, "waiting_time": 0.45, "packaging": 0.5},
        bases={"waiting_time": "Chuẩn bị lâu (18.5 phút)", "packaging": "Đóng gói chưa chắc chắn"},
        prep_minutes=18.5,
    )
    return merchant


def test_get_profile_evidence_tool(db_session, sample_merchant_for_tools):
    res = get_merchant_profile_summary("m_tool_test_01", db=db_session)

    assert res["merchant_id"] == "m_tool_test_01"
    assert "dimensions" in res
    assert "overall_score" not in res  # C2 compliance check
    assert "overall_score_internal" not in res


def test_get_profile_evidence_tool_specific_dimension(db_session, sample_merchant_for_tools):
    res = get_merchant_profile_summary("m_tool_test_01", dimensions=["waiting_time"], db=db_session)

    assert res["merchant_id"] == "m_tool_test_01"
    assert "waiting_time" in res["dimensions"]
    assert res["dimensions"]["waiting_time"] == pytest.approx(0.45, abs=0.001)
    # Only requested dimension should be present
    assert "food_quality" not in res["dimensions"]


def test_diagnose_merchant_tool(db_session, sample_merchant_for_tools):
    res = diagnose_merchant("m_tool_test_01", db=db_session)

    assert res["merchant_id"] == "m_tool_test_01"
    assert res["status"] == "ok"
    assert len(res["causes"]) == 2  # waiting_time (4.5) and packaging (5.0)

    for cause in res["causes"]:
        assert "dimension" in cause
        assert "score" in cause
        assert cause["score"] < 0.6
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


def test_compare_merchant_benchmark_tool(db_session, sample_merchant_for_tools):
    res = compare_merchant_benchmark(
        "m_tool_test_01",
        radius_km=5.0,
        db=db_session,
    )

    assert res["target_merchant_id"] == "m_tool_test_01"
    assert "competitors" in res
    assert len(res["competitors"]) >= 1
    first_comp = res["competitors"][0]
    assert "merchant_id" in first_comp
    assert "distance_km" in first_comp
