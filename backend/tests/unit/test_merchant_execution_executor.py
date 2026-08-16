"""Unit tests for direct and parallel execution routines."""

from unittest.mock import MagicMock
from models.merchant_execution import PlannedTask
from services.merchant_execution_executor import (
    SpecialistResult,
    execute_direct,
    execute_parallel,
    merge_parallel_results,
)


class FakeGateway:
    def __init__(self):
        self.calls = []
        self.tool_calls = 0

    def tools_for(self, capability_name: str):
        return []


def test_execute_direct_returns_completed_specialist_result(monkeypatch):
    task = PlannedTask(capability="owner", instruction="Lấy tổng quan nhà hàng")
    mock_llm = MagicMock()
    mock_llm.call = MagicMock(return_value="Doanh thu ổn định 10tr/ngày")

    gateway = FakeGateway()
    monkeypatch.setattr(
        "services.merchant_execution_executor._kickoff_specialist",
        lambda *_args, **_kwargs: "Doanh thu ổn định 10tr/ngày",
    )
    monkeypatch.setattr(
        "services.merchant_execution_executor._build_specialist_agent",
        lambda *_args, **_kwargs: object(),
    )
    result = execute_direct(task, gateway=gateway, llm=mock_llm)

    assert isinstance(result, SpecialistResult)
    assert result.capability == "owner"
    assert result.status == "failed"
    assert result.error == "no_tool_evidence"


def test_execute_direct_requires_observed_tool_evidence(monkeypatch):
    task = PlannedTask(capability="owner", instruction="Lấy tổng quan nhà hàng")
    gateway = FakeGateway()
    gateway.tool_calls = 1
    monkeypatch.setattr(
        "services.merchant_execution_executor._kickoff_specialist",
        lambda *_args, **_kwargs: "Rating hiện tại là 4.6.",
    )
    monkeypatch.setattr(
        "services.merchant_execution_executor._build_specialist_agent",
        lambda *_args, **_kwargs: object(),
    )

    result = execute_direct(task, gateway=gateway, llm=MagicMock())

    assert result.status == "completed"
    assert result.tool_calls == 1


def test_execute_parallel_runs_tasks_and_preserves_order():
    tasks = [
        PlannedTask(capability="owner", instruction="Task 1 owner"),
        PlannedTask(capability="market", instruction="Task 2 market"),
    ]
    mock_llm = MagicMock()

    def gateway_factory():
        return FakeGateway(), None

    results = execute_parallel(tasks, gateway_factory=gateway_factory, llm=mock_llm)

    assert len(results) == 2
    assert results[0].capability == "owner"
    assert results[1].capability == "market"


def test_owner_complaints_input_accepts_null_string():
    from tools.merchant.gateway import OwnerComplaintsInput
    inp = OwnerComplaintsInput.model_validate({"severity": "null", "limit_samples": 3})
    assert inp.severity == "null"
    assert inp.limit_samples == 3


def test_merge_parallel_results():
    results = [
        SpecialistResult(
            capability="owner",
            instruction="Task 1",
            status="completed",
            content="Owner summary data",
            duration_ms=10.0,
        ),
        SpecialistResult(
            capability="market",
            instruction="Task 2",
            status="failed",
            content="Error",
            duration_ms=5.0,
            error="Connection timeout",
        ),
    ]
    merged = merge_parallel_results(results)
    assert "### OWNER" in merged
    assert "Owner summary data" in merged
    assert "### MARKET" in merged
    assert "Thông tin chưa khả dụng" in merged
