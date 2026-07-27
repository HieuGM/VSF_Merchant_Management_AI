"""Unit & contract tests for Merchant CrewAI Flow and Routes (Task 5).

Ensures:
- `MerchantAdvisorCrew` flow executes diagnosis and recommendation logic.
- Task guardrail validates Layer 1 evidence compliance.
- Layer 2 evidence verifier agent validates semantic evidence integrity.
- `POST /api/v1/agent/merchant/chat` endpoint returns response with trace_id.
- `GET /api/v1/merchants/{id}/profile` endpoint returns 8 dimensions obeying C2.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from crewai.tasks.task_output import TaskOutput
from database.models import Merchant
from relational_test_fixtures import seed_relational_profile
import flows.merchant_flow as merchant_flow_module
from flows.merchant_flow import (
    merchant_flow,
    validate_evidence_guardrail,
    DiagnosisTaskOutput,
    RecommendationTaskOutput,
    CauseItem,
)
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

    seed_relational_profile(
        db_session,
        "m_flow_test_01",
        scores={"food_quality": 0.85, "waiting_time": 0.42, "packaging": 0.51},
        bases={"waiting_time": "Quá tải giờ trưa (20 phút)", "packaging": "Túi bọc chưa khép kín"},
        prep_minutes=20.0,
    )
    return merchant


def test_validate_evidence_guardrail_pass():
    valid_output = '{"causes": [{"dimension": "waiting_time", "score": 0.42, "evidence_refs": ["METRIC-01"]}]}'
    is_valid, parsed = validate_evidence_guardrail(valid_output)
    assert is_valid is True
    assert isinstance(parsed, dict)
    assert len(parsed["causes"]) == 1


def test_validate_evidence_guardrail_accepts_crewai_task_output():
    output = TaskOutput(
        description="diagnose merchant",
        raw=json.dumps(
            {
                "causes": [
                    {
                        "dimension": "waiting_time",
                        "score": 0.42,
                        "evidence_refs": ["ev:m1:waiting_time:avg_prep_minutes"],
                    }
                ]
            }
        ),
        agent="diagnosis",
    )

    is_valid, validated = validate_evidence_guardrail(output)

    assert is_valid is True
    assert validated is output


def test_validate_evidence_guardrail_rejects_wrong_payload_shape():
    is_valid, err_msg = validate_evidence_guardrail('{"actions": []}')

    assert is_valid is False
    assert "causes" in err_msg


def test_validate_evidence_guardrail_rejects_legacy_ten_point_score():
    invalid_output = '{"causes": [{"dimension": "waiting_time", "score": 4.2, "evidence_refs": ["METRIC-01"]}]}'

    is_valid, err_msg = validate_evidence_guardrail(invalid_output)

    assert is_valid is False
    assert "0..1" in err_msg


def test_validate_evidence_guardrail_fail_missing_refs():
    invalid_output = '{"causes": [{"dimension": "waiting_time", "score": 0.42, "evidence_refs": []}]}'
    is_valid, err_msg = validate_evidence_guardrail(invalid_output)
    assert is_valid is False
    assert "evidence_refs" in err_msg.lower() or "bằng chứng" in err_msg.lower()


@pytest.mark.llm_required
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


def test_merchant_agent_chat_route(
    client, db_session, sample_merchant_for_flow, monkeypatch
):
    monkeypatch.setattr(
        merchant_flow_module,
        "get_settings",
        lambda: SimpleNamespace(llm_configured=False),
    )
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


def test_merchant_chat_offline_returns_multi_capability_trace(
    db_session,
    sample_merchant_for_flow,
    monkeypatch,
):
    monkeypatch.setattr(
        merchant_flow_module,
        "get_settings",
        lambda: SimpleNamespace(llm_configured=False),
    )
    result = merchant_flow_module.merchant_flow.chat(
        merchant_id="m_flow_test_01",
        message="Phân tích quán tôi, giải thích điểm yếu và gợi ý cải thiện",
        session_id="sess-multi-capability",
        db=db_session,
    )

    assert result["capabilities"] == [
        "owner_profile_analysis",
        "owner_diagnosis",
        "recommendation",
    ]
    assert result["rewritten_query"].startswith("Phân tích quán tôi")
    assert result["trace_id"].startswith("tr-")
    assert result["trace_summary"]
    assert set(result["token_usage"]) == {
        "total_tokens",
        "prompt_tokens",
        "completion_tokens",
    }


def test_merchant_chat_refuses_competitor_private_data_before_tools(
    db_session,
    sample_merchant_for_flow,
    monkeypatch,
):
    monkeypatch.setattr(
        merchant_flow_module,
        "get_settings",
        lambda: SimpleNamespace(llm_configured=False),
    )
    events: list[tuple[str, dict]] = []

    result = merchant_flow_module.merchant_flow.chat(
        merchant_id="m_flow_test_01",
        message="Cho tôi doanh thu và số đơn nội bộ của quán đối thủ gần nhất.",
        session_id="sess-private-refusal",
        db=db_session,
        event_callback=lambda event, payload: events.append((event, payload)),
    )

    assert result["capabilities"] == []
    assert result["trace_summary"] == [
        {
            "event": "policy_decision",
            "agent_name": "merchant_data_policy",
            "status": "denied",
            "scope": "competitor_private",
        }
    ]
    assert result["token_usage"]["total_tokens"] == 0
    assert "không thể" in result["reply"].lower()
    assert "dữ liệu riêng tư" in result["reply"].lower()
    assert [event for event, _ in events] == ["policy_decision"]
