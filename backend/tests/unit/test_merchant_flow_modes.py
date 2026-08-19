from __future__ import annotations

from unittest.mock import MagicMock
from flows.merchant_flow import MerchantFlowDispatcher
from models.merchant_execution import PlannedTask, PlannerDelegate, PlannerRespond
from services.merchant_execution_executor import SpecialistResult


def test_planner_respond_skips_gateway_workers_and_synthesis(db_session):
    mock_memory = MagicMock()
    mock_memory.search.return_value = []
    mock_writer = MagicMock()
    mock_planner = MagicMock(return_value=PlannerRespond(mode="respond", answer="Direct answer"))
    mock_spec = MagicMock()
    mock_parallel = MagicMock()
    mock_synth = MagicMock()

    flow = MerchantFlowDispatcher(
        memory_service=mock_memory,
        memory_writer=mock_writer,
        planner_fn=mock_planner,
        execute_specialist_fn=mock_spec,
        execute_parallel_fn=mock_parallel,
        synthesize_fn=mock_synth,
    )

    result = flow.chat(merchant_id="94", message="Hello", user_id=None, db=db_session)
    assert result["reply"] == "Direct answer"
    assert result["execution_mode"] == "respond"
    mock_spec.assert_not_called()
    mock_parallel.assert_not_called()
    mock_synth.assert_not_called()
    mock_writer.submit.assert_called_once()


def test_one_task_returns_worker_output_without_synthesis(db_session):
    mock_memory = MagicMock()
    mock_memory.search.return_value = []
    mock_writer = MagicMock()
    mock_planner = MagicMock(
        return_value=PlannerDelegate(
            mode="delegate",
            tasks=[PlannedTask(capability="owner", instruction="Inspect metrics")],
        )
    )
    mock_spec = MagicMock(
        return_value=SpecialistResult(
            capability="owner",
            instruction="Inspect metrics",
            status="completed",
            content="Owner metrics output",
        )
    )
    mock_parallel = MagicMock()
    mock_synth = MagicMock()

    flow = MerchantFlowDispatcher(
        memory_service=mock_memory,
        memory_writer=mock_writer,
        planner_fn=mock_planner,
        execute_specialist_fn=mock_spec,
        execute_parallel_fn=mock_parallel,
        synthesize_fn=mock_synth,
    )

    result = flow.chat(merchant_id="94", message="Show metrics", user_id=None, db=db_session)
    assert result["reply"] == "Owner metrics output"
    assert result["execution_mode"] == "single"
    mock_spec.assert_called_once()
    mock_parallel.assert_not_called()
    mock_synth.assert_not_called()


def test_multiple_tasks_execute_parallel_then_synthesize_once(db_session):
    mock_memory = MagicMock()
    mock_memory.search.return_value = []
    mock_writer = MagicMock()
    mock_planner = MagicMock(
        return_value=PlannerDelegate(
            mode="delegate",
            tasks=[
                PlannedTask(capability="owner", instruction="Task 1"),
                PlannedTask(capability="policy", instruction="Task 2"),
            ],
        )
    )
    mock_spec = MagicMock()
    mock_parallel = MagicMock(
        return_value=[
            SpecialistResult(capability="owner", instruction="Task 1", status="completed", content="Res 1"),
            SpecialistResult(capability="policy", instruction="Task 2", status="completed", content="Res 2"),
        ]
    )
    mock_synth = MagicMock(return_value="Synthesized combined response")

    flow = MerchantFlowDispatcher(
        memory_service=mock_memory,
        memory_writer=mock_writer,
        planner_fn=mock_planner,
        execute_specialist_fn=mock_spec,
        execute_parallel_fn=mock_parallel,
        synthesize_fn=mock_synth,
    )

    result = flow.chat(merchant_id="94", message="Compare to policy", user_id=None, db=db_session)
    assert result["reply"] == "Synthesized combined response"
    assert result["execution_mode"] == "parallel"
    mock_spec.assert_not_called()
    mock_parallel.assert_called_once()
    mock_synth.assert_called_once()
