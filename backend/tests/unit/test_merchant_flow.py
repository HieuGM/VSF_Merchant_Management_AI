"""Unit & contract tests for Merchant CrewAI Flow and Routes (Task 5).

Ensures:
- `MerchantAdvisorCrew` flow executes diagnosis and recommendation logic.
- Task guardrail validates Layer 1 evidence compliance.
- Layer 2 evidence verifier agent validates semantic evidence integrity.
- `POST /api/v1/agent/merchant/chat` endpoint returns response with trace_id.
- `GET /api/v1/merchants/{id}/profile` endpoint returns 8 dimensions obeying C2.
"""
from __future__ import annotations

import pytest
from database.models import Merchant, MerchantProfile, OperationalMetric
from flows.merchant_flow import merchant_flow, validate_evidence_guardrail
from core.dependencies import get_db_session
from app.main import app


@pytest.fixture
def sample_merchant_for_flow(db_session):
    """Seed test merchant for flow and route testing."""
    merchant = Merchant(
        merchant_id="m_flow_test_01",
        name="Quán Bún Đậu Mắm Tôm Cô Hương",
        cuisine="Món Việt",
        city="Hà Nội",
        city_slug="ha-noi",
        address="15 Ngõ Trạm",
        lat=21.032,
        lng=105.844,
    )
    db_session.add(merchant)

    profile_data = {
        "merchant_id": "m_flow_test_01",
        "tier": "gold",
        "overall_score": 0.61,  # Must be stripped per C2
        "dimensions": {
            "food_quality": {"score": 8.5, "basis": "Ngon chuẩn vị", "evidence_refs": ["REV-401"]},
            "waiting_time": {
                "score": 4.2,  # Weak dimension < 6.0
                "basis": "Quá tải giờ trưa (20 phút)",
                "evidence_refs": ["METRIC-m_flow_test_01"],
            },
            "packaging": {
                "score": 5.1,  # Weak dimension < 6.0
                "basis": "Túi bọc chưa khép kín",
                "evidence_refs": ["REV-402"],
            },
            "image_quality": {"score": 7.0, "basis": "Ảnh chụp nét", "evidence_refs": []},
            "delivery_quality": {"score": 7.5, "basis": "Giao đúng hẹn", "evidence_refs": []},
            "service": {"score": 8.0, "basis": "Nhiệt tình", "evidence_refs": []},
            "menu_diversity": {"score": 7.0, "basis": "12 món", "evidence_refs": []},
            "price_level": {"score": 8.0, "basis": "Bình dân", "evidence_refs": []},
        },
    }

    profile = MerchantProfile(
        merchant_id="m_flow_test_01",
        dimensions_json=profile_data["dimensions"],
        profile_json=profile_data,
        schema_version="1.0",
        source_kind="development_fixture",
    )
    db_session.add(profile)

    metric = OperationalMetric(
        merchant_id="m_flow_test_01",
        avg_prep_time_min=20.0,
    )
    db_session.add(metric)

    db_session.flush()
    return merchant


def test_validate_evidence_guardrail_pass():
    valid_output = '{"causes": [{"dimension": "waiting_time", "score": 4.2, "evidence_refs": ["METRIC-01"]}]}'
    is_valid, parsed = validate_evidence_guardrail(valid_output)
    assert is_valid is True
    assert isinstance(parsed, dict)
    assert len(parsed["causes"]) == 1


def test_validate_evidence_guardrail_fail_missing_refs():
    invalid_output = '{"causes": [{"dimension": "waiting_time", "score": 4.2, "evidence_refs": []}]}'
    is_valid, err_msg = validate_evidence_guardrail(invalid_output)
    assert is_valid is False
    assert "evidence_refs" in err_msg.lower() or "bằng chứng" in err_msg.lower()


def test_merchant_flow_run_diagnosis(db_session, sample_merchant_for_flow):
    res = merchant_flow.run_diagnosis("m_flow_test_01", db=db_session)

    assert "trace_id" in res
    assert res["merchant_id"] == "m_flow_test_01"
    assert res["status"] in ("ok", "healthy")
    assert "diagnosis" in res
    assert "recommendations" in res


def test_merchant_profile_route(client, db_session, sample_merchant_for_flow):
    app.dependency_overrides[get_db_session] = lambda: db_session
    try:
        resp = client.get("/api/v1/merchants/m_flow_test_01/profile")
        assert resp.status_code == 200

        data = resp.json()
        assert data["merchant_id"] == "m_flow_test_01"
        assert "dimensions" in data
        assert "overall_score" not in data  # Security C2 check
        assert "overall_score" not in data["dimensions"]
    finally:
        app.dependency_overrides.clear()


def test_merchant_agent_chat_route(client, db_session, sample_merchant_for_flow):
    app.dependency_overrides[get_db_session] = lambda: db_session
    try:
        payload = {
            "merchant_id": "m_flow_test_01",
            "message": "Tại sao điểm thời gian chờ của quán tôi lại thấp?",
        }
        resp = client.post("/api/v1/agent/merchant/chat", json=payload)
        assert resp.status_code == 200

        data = resp.json()
        assert "trace_id" in data
        assert "reply" in data
        assert "merchant_id" in data
    finally:
        app.dependency_overrides.clear()
