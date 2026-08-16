"""Unit tests for ExecutionPlan validation contracts."""

import pytest
from pydantic import ValidationError
from models.merchant_execution import ExecutionPlan, PlannedTask


def test_valid_direct_plan():
    plan = ExecutionPlan(
        mode="direct",
        tasks=[PlannedTask(capability="owner", instruction="Lấy thông tin nhà hàng")],
        response_type="fact",
    )
    assert plan.mode == "direct"
    assert len(plan.tasks) == 1
    assert plan.response_type == "fact"


def test_valid_parallel_plan():
    plan = ExecutionPlan(
        mode="parallel",
        tasks=[
            PlannedTask(capability="owner", instruction="Lấy thông tin của tôi"),
            PlannedTask(capability="market", instruction="Tìm đối thủ trong khu vực"),
        ],
        response_type="summary",
    )
    assert plan.mode == "parallel"
    assert len(plan.tasks) == 2
    assert plan.response_type == "summary"


def test_valid_hierarchical_plan():
    plan = ExecutionPlan(
        mode="hierarchical",
        tasks=[
            PlannedTask(capability="owner", instruction="Phân tích doanh thu"),
            PlannedTask(capability="cohort", instruction="So sánh nhóm tương đồng"),
            PlannedTask(capability="policy", instruction="Kiểm tra quy định khuyến mãi"),
        ],
        response_type="analysis",
    )
    assert plan.mode == "hierarchical"
    assert len(plan.tasks) == 3
    assert plan.response_type == "analysis"


def test_direct_plan_rejects_multiple_tasks():
    with pytest.raises(ValidationError, match="direct mode requires exactly 1 task"):
        ExecutionPlan(
            mode="direct",
            tasks=[
                PlannedTask(capability="owner", instruction="Task 1"),
                PlannedTask(capability="market", instruction="Task 2"),
            ],
            response_type="fact",
        )


def test_parallel_plan_rejects_single_task():
    with pytest.raises(ValidationError, match="parallel mode requires 2–4 tasks|parallel mode requires 2-4 tasks"):
        ExecutionPlan(
            mode="parallel",
            tasks=[PlannedTask(capability="owner", instruction="Task 1")],
            response_type="summary",
        )


def test_parallel_plan_rejects_duplicate_capabilities():
    with pytest.raises(ValidationError, match="parallel mode tasks must have distinct capabilities"):
        ExecutionPlan(
            mode="parallel",
            tasks=[
                PlannedTask(capability="owner", instruction="Task 1"),
                PlannedTask(capability="owner", instruction="Task 2"),
            ],
            response_type="summary",
        )


def test_fact_response_type_only_allowed_for_direct():
    with pytest.raises(ValidationError, match="response_type 'fact' is only allowed with direct mode"):
        ExecutionPlan(
            mode="parallel",
            tasks=[
                PlannedTask(capability="owner", instruction="Task 1"),
                PlannedTask(capability="market", instruction="Task 2"),
            ],
            response_type="fact",
        )


def test_analysis_response_type_not_allowed_for_parallel():
    with pytest.raises(ValidationError, match="response_type 'analysis' is not allowed with parallel mode"):
        ExecutionPlan(
            mode="parallel",
            tasks=[
                PlannedTask(capability="owner", instruction="Task 1"),
                PlannedTask(capability="market", instruction="Task 2"),
            ],
            response_type="analysis",
        )


def test_execution_plan_forbids_extra_fields():
    with pytest.raises(ValidationError):
        ExecutionPlan.model_validate({
            "mode": "direct",
            "tasks": [{"capability": "owner", "instruction": "Task 1"}],
            "response_type": "fact",
            "unknown_field": "invalid",
        })
