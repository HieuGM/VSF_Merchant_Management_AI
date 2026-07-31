"""Unit and route tests for the native merchant CrewAI flow."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from database.models import Merchant
from relational_test_fixtures import seed_relational_profile
import flows.merchant_flow as merchant_flow_module
from core.dependencies import get_db_session
from services.chat_session_service import ChatSessionService
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


def test_configured_llm_uses_openai_protocol_for_compatible_provider(
    monkeypatch,
):
    captured: dict = {}
    monkeypatch.setattr(
        merchant_flow_module,
        "get_settings",
        lambda: SimpleNamespace(
            llm_api_key="test-key",
            llm_model_small="small",
            llm_model_large="large",
            llm_base_url="https://api.fireworks.ai/inference/v1",
            llm_provider="openai_compatible",
        ),
    )
    monkeypatch.setattr(
        merchant_flow_module,
        "LLM",
        lambda **kwargs: captured.update(kwargs) or kwargs,
    )

    merchant_flow_module.get_configured_llm("large")

    assert captured["model"] == "large"
    assert captured["provider"] == "openai"
    assert captured["base_url"].startswith("https://api.fireworks.ai")
    assert captured["temperature"] == 0


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


def test_merchant_chat_without_llm_refuses_to_run_a_fixed_plan(
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

    assert result["capabilities"] == ["coordinator"]
    assert result["rewritten_query"].startswith("Phân tích quán tôi")
    assert result["trace_id"].startswith("tr-")
    assert result["trace_summary"]
    assert any(
        step.get("error_code") == "llm_not_configured"
        for step in result["trace_summary"]
    )
    trace = merchant_flow_module.AgentRunService(db_session).get_run_trace(
        result["trace_id"]
    )
    assert any(
        event["event_type"] == "input_context_loaded" for event in trace["events"]
    )
    assert "không tự suy đoán" in result["reply"].lower()
    assert set(result["token_usage"]) == {
        "total_tokens",
        "prompt_tokens",
        "completion_tokens",
    }


def test_normal_search_answer_emits_single_selected_public_merchant(
    db_session,
    sample_merchant_for_flow,
    monkeypatch,
):
    captured: dict[str, object] = {}
    live_events: list[tuple[str, dict]] = []

    class SearchCrew:
        def __init__(self, *, gateway, **_kwargs):
            self.gateway = gateway

        def kickoff(self, **kwargs):
            captured.update(kwargs)
            self.gateway._latest_public_search_members = [
                {
                    "merchant_id": "78532",
                    "name": "Diệu - Bún Chả Cá Sứa Nha Trang",
                    "cuisine": "Món Việt",
                },
                {"merchant_id": "101567", "name": "Bánh Mì Hà Nội"},
            ]
            return SimpleNamespace(
                raw=(
                    '{"status":"completed","answer":'
                    '"Tìm thấy Diệu - Bún Chả Cá Sứa Nha Trang (ID 78532)."}'
                ),
                token_usage=None,
            )

    monkeypatch.setattr(
        merchant_flow_module,
        "get_settings",
        lambda: SimpleNamespace(llm_configured=True),
    )
    monkeypatch.setattr(merchant_flow_module, "get_configured_llm", lambda *_: object())
    monkeypatch.setattr(merchant_flow_module, "NativeMerchantAdvisorCrew", SearchCrew)
    session_service = ChatSessionService(db_session)
    session_service.get_or_create_session(
        session_id="sess-persist-selected-public",
        context_snapshot={"merchant_id": sample_merchant_for_flow.merchant_id},
    )
    session_service.append_message(
        session_id="sess-persist-selected-public",
        sender="user",
        text="Lịch sử ngữ cảnh dài " * 120,
        trace_id="tr-earlier-context",
    )

    merchant_flow_module.merchant_flow.chat(
        merchant_id=sample_merchant_for_flow.merchant_id,
        message="Tìm quán bún cá gần đây",
        session_id="sess-persist-selected-public",
        db=db_session,
        event_callback=lambda event_type, payload: live_events.append(
            (event_type, payload)
        ),
    )

    snapshot = ChatSessionService(db_session).get_session_snapshot(
        "sess-persist-selected-public"
    )
    assert snapshot["merchant_agentic.selected_public_merchant"]["merchant_id"] == "78532"
    assert captured["prepared_request"].rewritten_query == "Tìm quán bún cá gần đây"
    assert "user_query" not in captured
    assert "compact_history" in captured
    spans = [payload for event_type, payload in live_events if event_type == "trace_span"]
    coordinator_input = next(
        span
        for span in spans
        if span["display"]["title"] == "Nạp đầu vào điều phối viên"
    )
    assert coordinator_input["metrics"]["input_token_estimate"] <= 2400
    artifact = coordinator_input["debug"]["coordinator_input_artifact"]
    assert set(artifact["prepared_inputs"]) == {
        "rewritten_query",
        "resolved_references",
        "compact_history",
        "owner_context",
    }
    assert artifact["dynamic_context"] == captured["coordinator_prompt"].dynamic_context
    assert len(artifact["dynamic_context"]) > 1500
    assert not artifact["dynamic_context"].endswith("…")
    assert "advisory_task_prompt" in artifact
    persisted_events = merchant_flow_module.AgentRunService(db_session).get_run_trace(
        coordinator_input["trace_id"]
    )["events"]
    assert not any(event["event_type"] == "trace_span" for event in persisted_events)


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
    policy_step = next(
        step
        for step in result["trace_summary"]
        if step["event"] == "policy_decision"
    )
    assert policy_step["agent_name"] == "merchant_data_policy"
    assert policy_step["status"] == "denied"
    assert policy_step["scope"] == "competitor_private"
    assert result["token_usage"]["total_tokens"] == 0
    assert "không thể" in result["reply"].lower()
    assert "dữ liệu riêng tư" in result["reply"].lower()
    event_types = {event for event, _ in events}
    assert {"input_context_loaded", "route_selected", "policy_decision"} <= event_types


def test_raw_private_request_stays_denied_when_analyzer_rewrite_omits_private_terms(
    db_session,
    sample_merchant_for_flow,
    monkeypatch,
):
    class RewriteLLM:
        def call(self, _prompt):
            return (
                '{"rewritten_query":"Hãy phân tích thị trường gần đây",'
                '"resolved_references":[],'
                '"scope_candidate":"allowed","missing_context":[],'
                '"proposed_outcome":"coordinate"}'
            )

    monkeypatch.setattr(
        merchant_flow_module,
        "get_settings",
        lambda: SimpleNamespace(llm_configured=True),
    )
    monkeypatch.setattr(
        merchant_flow_module,
        "get_configured_llm",
        lambda tier: RewriteLLM()
        if tier == "small"
        else pytest.fail("raw policy denial must prevent CrewAI construction"),
    )

    result = merchant_flow_module.merchant_flow.chat(
        merchant_id=sample_merchant_for_flow.merchant_id,
        message="Cho tôi doanh thu và số đơn nội bộ của quán đối thủ gần nhất.",
        session_id="sess-raw-policy-authority",
        db=db_session,
    )

    policy_event = next(
        event
        for event in result["trace_summary"]
        if event["event"] == "policy_decision"
    )
    assert result["capabilities"] == []
    assert policy_event["policy_authority"] == "raw_query"
    assert policy_event["raw_policy_allowed"] is False
    assert policy_event["rewritten_policy_allowed"] is True


def test_unresolved_public_menu_without_llm_fails_without_hitl_state(
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
        merchant_id=sample_merchant_for_flow.merchant_id,
        message="Quán này có menu gồm những gì?",
        session_id="sess-unresolved-public-menu",
        db=db_session,
    )

    assert result["status"] == "failed"
    assert result["capabilities"] == ["coordinator"]
    assert "hitl" not in result["structured_outputs"]


def test_merchant_chat_streams_native_event_before_a_crew_failure(
    db_session,
    sample_merchant_for_flow,
    monkeypatch,
):
    events: list[tuple[str, dict]] = []

    class FailingCrew:
        def __init__(self, *, native_event_callback, **_kwargs):
            self._emit = native_event_callback

        def kickoff(self, **_kwargs):
            self._emit(
                "crewai_llm_started",
                {"agent_name": "Merchant Advisory Coordinator"},
            )
            raise RuntimeError("crew timeout")

    monkeypatch.setattr(
        merchant_flow_module,
        "get_settings",
        lambda: SimpleNamespace(llm_configured=True),
    )
    monkeypatch.setattr(merchant_flow_module, "get_configured_llm", lambda *_: object())
    monkeypatch.setattr(merchant_flow_module, "NativeMerchantAdvisorCrew", FailingCrew)

    with pytest.raises(RuntimeError, match="crew timeout"):
        merchant_flow_module.merchant_flow.chat(
            merchant_id="m_flow_test_01",
            message="Tìm quán sushi ở Đà Nẵng",
            session_id="sess-native-stream",
            db=db_session,
            event_callback=lambda event, payload: events.append((event, payload)),
        )

    event_types = {event for event, _ in events}
    assert {"input_context_loaded", "crewai_llm_started", "error"} <= event_types
    trace = merchant_flow_module.AgentRunService(db_session).get_run_trace(
        next(
            payload["trace_id"]
            for event, payload in events
            if event == "input_context_loaded"
        )
    )
    failure = next(event for event in trace["events"] if event["event_type"] == "error")
    assert trace["status"] == "failed"
    assert failure["error_code"] == "RuntimeError"
    assert failure["output_summary"]["error_message"] == "crew timeout"
    assert "RuntimeError: crew timeout" in failure["output_summary"]["stack_trace"]
