"""Contract tests for Observability Trace Inspection Routes (Task 4).

Ensures:
- `GET /api/v1/agent/runs/{trace_id}` returns 404 for non-existent trace.
- `GET /api/v1/agent/runs/{trace_id}` returns complete trace details with events list.
- Service layer correctly records agent runs and tool execution events.
"""
from __future__ import annotations

import pytest
from datetime import datetime
from database.models import AgentRun, AgentEvent, ChatMessage, ChatSession
from services.agent_run_service import AgentRunService
from core.dependencies import get_db_session
from app.main import app


@pytest.fixture
def real_client(client, db_session):
    """Override get_db_session with real DB session for trace route contract tests."""
    app.dependency_overrides[get_db_session] = lambda: db_session
    yield client
    app.dependency_overrides.clear()


def test_get_trace_not_found(real_client):
    resp = real_client.get("/api/v1/agent/runs/non-existent-trace-id")
    assert resp.status_code == 404


def test_get_trace_success(real_client, db_session):
    db_session.add(
        ChatSession(
            session_id="sess_123",
            context_snapshot_json={"merchant_id": "94", "current_intent": "search"},
        )
    )
    # Seed agent_run first
    run = AgentRun(
        trace_id="tr-test-obs-001",
        session_id="sess_123",
        user_id="user_456",
        crew_name="merchant_advisor_crew",
        intent="diagnose_merchant",
        status="completed",
        started_at=datetime.utcnow(),
        finished_at=datetime.utcnow(),
    )
    db_session.add(run)
    db_session.flush()

    event1 = AgentEvent(
        event_id="evt-001",
        trace_id="tr-test-obs-001",
        event_type="crewai_tool_requested",
        agent_name="diagnosis_specialist",
        task_name="diagnose_merchant_task",
        tool_name="diagnose_merchant",
        input_hash="hash_abc123",
        output_summary_json={"args": {"query": "tôm", "city": "da_nang"}},
        duration_ms=120,
        status="ok",
        created_at=datetime.utcnow(),
    )
    db_session.add(event1)
    db_session.add_all(
        [
            ChatMessage(
                message_id="msg-trace-user",
                session_id="sess_123",
                sender="user",
                text="Tìm quán tôm ở Đà Nẵng",
                trace_id="tr-test-obs-001",
            ),
            ChatMessage(
                message_id="msg-trace-agent",
                session_id="sess_123",
                sender="agent",
                text="Đây là kết quả tìm kiếm.",
                trace_id="tr-test-obs-001",
            ),
        ]
    )
    db_session.flush()

    resp = real_client.get("/api/v1/agent/runs/tr-test-obs-001")
    assert resp.status_code == 200

    data = resp.json()
    assert data["trace_id"] == "tr-test-obs-001"
    assert data["crew_name"] == "merchant_advisor_crew"
    assert data["intent"] == "diagnose_merchant"
    assert data["status"] == "completed"
    assert "events" in data
    assert len(data["events"]) == 1

    evt = data["events"][0]
    assert evt["event_id"] == "evt-001"
    assert evt["tool_name"] == "diagnose_merchant"
    assert evt["duration_ms"] == 120
    assert evt["status"] == "ok"
    assert evt["output_summary"]["args"]["city"] == "da_nang"
    assert data["session_state"]["merchant_id"] == "94"
    assert data["summary"]["event_count"] == 1
    assert data["llm_usage"]["total_tokens"] == 0
    assert data["chat"]["user_query"] == "Tìm quán tôm ở Đà Nẵng"
    assert data["chat"]["final_answer"] == "Đây là kết quả tìm kiếm."


def test_agent_run_service_record_run_and_events(db_session):
    svc = AgentRunService(db_session)

    run = svc.start_run(
        trace_id="tr-service-002",
        crew_name="merchant_advisor_crew",
        session_id="sess_789",
        intent="recommend_improvements",
    )
    assert run.trace_id == "tr-service-002"
    assert run.status == "running"

    evt = svc.record_event(
        trace_id="tr-service-002",
        event_type="tool_call",
        agent_name="recommendation_specialist",
        tool_name="recommend_improvements",
        duration_ms=85,
        status="ok",
    )
    assert evt.event_id is not None
    assert evt.trace_id == "tr-service-002"

    completed_run = svc.finish_run(trace_id="tr-service-002", status="completed")
    assert completed_run.status == "completed"
    assert completed_run.finished_at is not None


def test_agent_run_service_persists_semantic_span(db_session):
    svc = AgentRunService(db_session)
    svc.start_run(trace_id="tr-semantic-003", crew_name="merchant_advisor_crew")

    svc.record_event(
        trace_id="tr-semantic-003",
        event_type="trace_span",
        output_summary_json={
            "title": "Gọi tool: search_policy_documents",
            "summary": "Đang truy xuất chính sách.",
            "status": "running",
        },
        status="running",
        seq=1,
        span_id="sp-policy-tool",
        phase="tool",
        kind="started",
        actor_type="tool",
        actor_name="search_policy_documents",
        metrics_json={},
        debug_payload_json={"args": {"query": "phí nền tảng"}},
    )

    event = svc.get_run_trace("tr-semantic-003")["events"][0]
    assert event["event_type"] == "trace_span"
    assert event["seq"] == 1
    assert event["span_id"] == "sp-policy-tool"
    assert event["display"]["status"] == "running"
    assert event["debug"]["args"]["query"] == "phí nền tảng"
