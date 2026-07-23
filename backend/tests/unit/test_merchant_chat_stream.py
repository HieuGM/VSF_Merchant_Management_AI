import pytest
from fastapi.testclient import TestClient
from app.main import app

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
