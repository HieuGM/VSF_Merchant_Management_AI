from __future__ import annotations

from unittest.mock import MagicMock
import pytest
from pydantic import ValidationError

from agents.merchant.planner import plan_request
from models.merchant_execution import PlannerDelegate, PlannerRespond
from services.mem0_service import MemoryHit


def test_plan_request_delegates_to_specialists(monkeypatch):
    mock_prompt = MagicMock()
    mock_prompt.compile.return_value = "compiled planner prompt"

    monkeypatch.setattr(
        "agents.merchant.planner.get_merchant_prompt",
        lambda key, label=None: mock_prompt,
    )

    mock_llm = MagicMock()
    mock_llm.model = "v-llm-v1-small"
    mock_llm.call.return_value = (
        '{"mode":"delegate","tasks":[{"capability":"owner","instruction":"Check metrics"}]}'
    )

    decision = plan_request(
        query="How can I improve?",
        memories=[MemoryHit("User prioritizes service", 0.9)],
        owner_context={"merchant_id": "m1", "city": "Hanoi"},
        llm=mock_llm,
    )

    assert isinstance(decision, PlannerDelegate)
    assert decision.tasks[0].capability == "owner"
    mock_llm.call.assert_called_once_with("compiled planner prompt")
    mock_prompt.compile.assert_called_once_with(
        query="How can I improve?",
        memory_context='["User prioritizes service"]',
        owner_context='{"city": "Hanoi", "merchant_id": "m1"}',
    )


def test_plan_request_direct_respond(monkeypatch):
    mock_prompt = MagicMock()
    mock_prompt.compile.return_value = "compiled prompt"

    monkeypatch.setattr(
        "agents.merchant.planner.get_merchant_prompt",
        lambda key, label=None: mock_prompt,
    )

    mock_llm = MagicMock()
    mock_llm.call.return_value = '{"mode":"respond","answer":"Chào bạn!"}'

    decision = plan_request(
        query="Chào",
        memories=[],
        owner_context={"merchant_id": "m1"},
        llm=mock_llm,
    )

    assert isinstance(decision, PlannerRespond)
    assert decision.answer == "Chào bạn!"
    mock_llm.call.assert_called_once()


def test_plan_request_invalid_output_raises_validation_error_without_retry(monkeypatch):
    mock_prompt = MagicMock()
    mock_prompt.compile.return_value = "compiled prompt"

    monkeypatch.setattr(
        "agents.merchant.planner.get_merchant_prompt",
        lambda key, label=None: mock_prompt,
    )

    mock_llm = MagicMock()
    mock_llm.call.return_value = '{"mode":"invalid"}'

    with pytest.raises(ValidationError):
        plan_request(
            query="test",
            memories=[],
            owner_context={},
            llm=mock_llm,
        )

    # Asserts exactly one call was made without retry loop
    mock_llm.call.assert_called_once()
