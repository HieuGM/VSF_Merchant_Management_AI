import pytest
import json
from flows.merchant_flow import merchant_flow

def test_chat_stream_error_reporting_on_exception(monkeypatch):
    # Monkeypatch chat to raise a simulated error
    def mock_chat_failure(*args, **kwargs):
        raise RuntimeError("Simulated 400 Bad Request error for testing")

    monkeypatch.setattr(merchant_flow, "chat", mock_chat_failure)

    gen = merchant_flow.chat_stream(
        merchant_id="94",
        message="hello",
        session_id="sess_test_err"
    )

    events = list(gen)
    assert len(events) >= 2

    # Check for agent_error event
    has_agent_error = any("event: agent_error" in e for e in events)
    has_failed_finish = any("FAILED" in e for e in events)

    assert has_agent_error, "agent_error SSE event should be emitted on error"
    assert has_failed_finish, "execution_finish with status FAILED should be emitted on error"
    assert all("Simulated 400 Bad Request error" not in event for event in events)
    assert any("RuntimeError" in event for event in events)
