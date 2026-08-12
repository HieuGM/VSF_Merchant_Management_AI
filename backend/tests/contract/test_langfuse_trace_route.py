import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database.models import ChatMessage
from routes.trace_routes import router
from services import agent_run_service

TRACE_ID = "a" * 32


def _observation(**overrides):
    values = {
        "id": "gen-1",
        "traceId": TRACE_ID,
        "parentObservationId": "root-1",
        "name": "openai.chat",
        "type": "GENERATION",
        "level": "DEFAULT",
        "startTime": "2026-08-12T08:00:00Z",
        "endTime": "2026-08-12T08:00:01Z",
        "providedModelName": "model-x",
        "usageDetails": {"input": 10, "output": 5, "total": 15},
        "costDetails": {"total": 0.01},
        "latency": 1.0,
        "timeToFirstToken": 0.2,
        "promptName": "gsm_merchant/SYNTHESIS_PROMPT",
        "promptVersion": 3,
        "input": "must not leak",
        "output": "must not leak",
        "metadata": {"must": "not leak"},
    }
    values.update(overrides)
    return values


def test_service_returns_safe_paginated_projection(monkeypatch):
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = ChatMessage(
        trace_id=TRACE_ID,
        timestamp=datetime.now(timezone.utc),
    )
    root = _observation(
        id="root-1",
        parentObservationId=None,
        name="merchant-advisor-flow",
        type="SPAN",
        usageDetails=None,
        costDetails=None,
    )
    client = MagicMock()
    client.api.observations.get_many.side_effect = [
        SimpleNamespace(data=[SimpleNamespace(model_dump=lambda **_: root)], meta=SimpleNamespace(cursor="next")),
        SimpleNamespace(data=[SimpleNamespace(model_dump=lambda **_: _observation())], meta=SimpleNamespace(cursor=None)),
    ]
    monkeypatch.setattr(agent_run_service, "get_client", lambda: client)

    payload = agent_run_service.AgentRunService(db).get_run_trace(TRACE_ID)

    assert payload["totals"]["total_tokens"] == 15
    assert payload["observations"][1]["parent_id"] == "root-1"
    serialized = json.dumps(payload)
    assert "must not leak" not in serialized
    assert client.api.observations.get_many.call_count == 2


@pytest.fixture
def route_client(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    monkeypatch.setattr("routes.trace_routes.get_db_session", lambda: None)
    return TestClient(app)


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (agent_run_service.TracePending(), 202),
        (agent_run_service.TraceNotFound(), 404),
        (agent_run_service.TraceUpstreamError(), 502),
    ],
)
def test_route_maps_trace_errors(monkeypatch, route_client, error, status):
    monkeypatch.setattr(
        "routes.trace_routes.AgentRunService.get_run_trace",
        MagicMock(side_effect=error),
    )
    response = route_client.get(f"/api/v1/agent/runs/{TRACE_ID}")
    assert response.status_code == status
    if status == 202:
        assert response.headers["Retry-After"] == "3"
