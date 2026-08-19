from __future__ import annotations

import httpx
import pytest

from core.errors import ProviderError, TimeoutError
from services.mem0_service import (
    Mem0Service,
    MemoryHit,
    MemoryIdentity,
    memory_identity,
)


class MockTransport(httpx.BaseTransport):
    def __init__(self, handler):
        self.handler = handler

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return self.handler(request)


def test_memory_identity_uses_owner_scoped_agent_and_session_run():
    identity = memory_identity("user-1", "merchant-9", "session-3")
    assert identity == MemoryIdentity(
        user_id="user-1",
        agent_id="merchant-advisor:merchant-9",
        run_id="session-3",
    )


def test_memory_identity_uses_merchant_in_auth_disabled_development():
    assert memory_identity(None, "merchant-9", "session-3").user_id == "merchant-9"


def test_search_sends_current_query_and_cross_session_filters_only():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        seen["method"] = request.method
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.read().decode())
        return httpx.Response(
            200,
            json={"results": [
                {"id": "internal-id", "memory": "User values fast service", "score": 0.91}
            ]},
        )

    client = httpx.Client(transport=MockTransport(handler), base_url="http://testserver")
    service = Mem0Service(client=client, api_key="test-key")
    hits = service.search("How should I improve?", MemoryIdentity("u", "merchant-advisor:m", "run"))

    assert seen["body"] == {
        "query": "How should I improve?",
        "filters": {"user_id": "u", "agent_id": "merchant-advisor:m"},
        "top_k": 5,
    }
    assert seen["headers"]["x-api-key"] == "test-key"
    assert hits == [MemoryHit(memory="User values fast service", score=0.91)]


def test_add_turn_sends_run_id_and_messages():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        seen["body"] = json.loads(request.read().decode())
        return httpx.Response(200, json={"message": "Memory added"})

    client = httpx.Client(transport=MockTransport(handler), base_url="http://testserver")
    service = Mem0Service(client=client, api_key="test-key")
    identity = MemoryIdentity("u", "merchant-advisor:m", "session-123")
    service.add_turn("User text", "Assistant text", identity)

    assert seen["body"] == {
        "messages": [
            {"role": "user", "content": "User text"},
            {"role": "assistant", "content": "Assistant text"},
        ],
        "user_id": "u",
        "agent_id": "merchant-advisor:m",
        "run_id": "session-123",
    }


def test_empty_search_result_returns_empty_list():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    client = httpx.Client(transport=MockTransport(handler), base_url="http://testserver")
    service = Mem0Service(client=client, api_key="test-key")
    hits = service.search("query", MemoryIdentity("u", "merchant-advisor:m", "run"))
    assert hits == []


def test_timeout_raises_timeout_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Timeout")

    client = httpx.Client(transport=MockTransport(handler), base_url="http://testserver")
    service = Mem0Service(client=client, api_key="test-key")
    with pytest.raises(TimeoutError):
        service.search("query", MemoryIdentity("u", "merchant-advisor:m", "run"))


def test_non_2xx_raises_provider_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    client = httpx.Client(transport=MockTransport(handler), base_url="http://testserver")
    service = Mem0Service(client=client, api_key="test-key")
    with pytest.raises(ProviderError):
        service.search("query", MemoryIdentity("u", "merchant-advisor:m", "run"))


def test_invalid_json_raises_provider_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="Not JSON")

    client = httpx.Client(transport=MockTransport(handler), base_url="http://testserver")
    service = Mem0Service(client=client, api_key="test-key")
    with pytest.raises(ProviderError):
        service.search("query", MemoryIdentity("u", "merchant-advisor:m", "run"))


def test_health_check_returns_true_when_ok():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(404)

    client = httpx.Client(transport=MockTransport(handler), base_url="http://testserver")
    service = Mem0Service(client=client, api_key="test-key")
    assert service.health() is True
