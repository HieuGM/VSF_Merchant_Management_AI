import pytest
import json
from fastapi.testclient import TestClient
from app.main import app
from flows.merchant_flow import merchant_flow

client = TestClient(app)


@pytest.mark.llm_required
def test_merchant_chat_stream_endpoint():
    payload = {
        "merchant_id": "94",
        "message": "Xin chào, hãy so sánh quán của tôi với đối thủ",
        "session_id": "test_sess_stream_001",
        "competitor_radius_km": 5.0,
    }
    response = client.post("/api/v1/agent/merchant/chat/stream", json=payload)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    content = response.text
    assert "event: agent_start" in content or "event: token_chunk" in content


def test_chat_stream_executes_chat_once_and_finishes_with_plan_trace_tokens(
    monkeypatch,
):
    calls = {"count": 0}

    def fake_chat(*args, event_callback=None, **kwargs):
        calls["count"] += 1
        assert event_callback is not None
        event_callback(
            "plan",
            {
                "rewritten_query": "Tìm và phân tích nhóm sushi tại Đà Nẵng",
                "capabilities": [
                    "restaurant_search",
                    "market_cohort_analysis",
                ],
            },
        )
        event_callback(
            "tool_call",
            {"tool_name": "search_merchants", "step_id": "search"},
        )
        return {
            "trace_id": "tr-stream-plan",
            "reply": "Đã phân tích nhóm sushi.",
            "capabilities": [
                "restaurant_search",
                "market_cohort_analysis",
            ],
            "rewritten_query": "Tìm và phân tích nhóm sushi tại Đà Nẵng",
            "token_usage": {
                "total_tokens": 120,
                "prompt_tokens": 90,
                "completion_tokens": 30,
            },
            "duration_ms": 456,
            "merchants": [],
        }

    monkeypatch.setattr(merchant_flow, "chat", fake_chat)

    raw_events = list(
        merchant_flow.chat_stream(
            merchant_id="94",
            message="Tìm sushi rồi phân tích nhóm đó",
            session_id="sess-stream-plan",
        )
    )

    assert calls["count"] == 1
    assert sum("event: plan" in item for item in raw_events) == 1
    finish_line = next(
        item for item in raw_events if "event: execution_finish" in item
    )
    payload = json.loads(
        next(
            line.removeprefix("data: ")
            for line in finish_line.splitlines()
            if line.startswith("data: ")
        )
    )
    assert payload["trace_id"] == "tr-stream-plan"
    assert payload["capabilities"] == [
        "restaurant_search",
        "market_cohort_analysis",
    ]
    assert payload["token_usage"]["total_tokens"] == 120
    assert payload["duration_ms"] == 456
