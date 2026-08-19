"""Unit tests for terminal specialist execution and parallel dispatch."""
from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from models.merchant_execution import PlannedTask
from services.merchant_execution_executor import (
    SpecialistResult,
    build_specialist,
    execute_parallel,
    execute_specialist,
)


class FakeGateway:
    def __init__(self, tool_calls: int = 1):
        self.completed_tool_calls = tool_calls
        self.collected_public_merchants = []
        self.tools_for = MagicMock(return_value=[])


def test_specialist_has_scoped_tools_and_cannot_delegate(monkeypatch):
    mock_prompt = MagicMock()
    mock_prompt.prompt = "Specialist goal"
    monkeypatch.setattr(
        "services.merchant_execution_executor.get_merchant_prompt",
        lambda key, label=None: mock_prompt,
    )

    gateway = FakeGateway(tool_calls=1)
    agent = build_specialist("owner", gateway=gateway, llm="openai/v-llm-v1-small")
    assert agent.allow_delegation is False
    gateway.tools_for.assert_called_once_with("owner")


def test_single_specialist_returns_self_contained_output(monkeypatch):
    mock_prompt = MagicMock()
    mock_prompt.prompt = "Specialist goal"
    monkeypatch.setattr(
        "services.merchant_execution_executor.get_merchant_prompt",
        lambda key, label=None: mock_prompt,
    )

    monkeypatch.setattr(
        "crewai.Crew.kickoff",
        lambda self: MagicMock(raw="Grounded owner answer"),
    )

    gateway = FakeGateway(tool_calls=1)
    result = execute_specialist(
        PlannedTask(capability="owner", instruction="Inspect performance"),
        gateway=gateway,
        llm="openai/v-llm-v1-small",
        trace_context={"trace_id": "a" * 32, "parent_span_id": "b" * 16},
    )

    assert result.status == "completed"
    assert result.content == "Grounded owner answer"
    assert result.capability == "owner"


def test_execute_parallel_preserves_task_order(monkeypatch):
    mock_prompt = MagicMock()
    mock_prompt.prompt = "Specialist goal"
    monkeypatch.setattr(
        "services.merchant_execution_executor.get_merchant_prompt",
        lambda key, label=None: mock_prompt,
    )

    monkeypatch.setattr(
        "crewai.Crew.kickoff",
        lambda self: MagicMock(raw="Specialist branch answer"),
    )

    tasks = [
        PlannedTask(capability="owner", instruction="Task 1"),
        PlannedTask(capability="policy", instruction="Task 2"),
    ]

    def gateway_factory():
        return FakeGateway(tool_calls=1), None

    results = execute_parallel(tasks, gateway_factory=gateway_factory, llm="openai/v-llm-v1-small")
    assert len(results) == 2
    assert results[0].capability == "owner"
    assert results[1].capability == "policy"
