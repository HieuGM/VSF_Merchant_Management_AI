from __future__ import annotations

import pytest
from pydantic import ValidationError

from models.merchant_execution import (
    PlannedTask,
    PlannerDelegate,
    PlannerRespond,
    parse_planner_decision,
)


def test_respond_decision_requires_nonempty_answer():
    decision = parse_planner_decision('{"mode":"respond","answer":"Xin chào."}')
    assert isinstance(decision, PlannerRespond)
    assert decision.answer == "Xin chào."


def test_delegate_accepts_one_to_four_distinct_capabilities():
    decision = parse_planner_decision(
        '{"mode":"delegate","tasks":['
        '{"capability":"owner","instruction":"Inspect owner performance"},'
        '{"capability":"policy","instruction":"Find applicable policy"}]}'
    )
    assert isinstance(decision, PlannerDelegate)
    assert [task.capability for task in decision.tasks] == ["owner", "policy"]


@pytest.mark.parametrize("raw", [
    '{"mode":"delegate","tasks":[]}',
    '{"mode":"delegate","tasks":[{"capability":"owner","instruction":"a"},{"capability":"owner","instruction":"b"}]}',
    '{"mode":"direct","tasks":[]}',
    '{"mode":"respond","answer":""}',
    '{"mode":"unknown"}',
])
def test_invalid_decision_is_rejected_once(raw):
    with pytest.raises(ValidationError):
        parse_planner_decision(raw)


def test_planned_task_forbids_extra_fields():
    with pytest.raises(ValidationError):
        PlannedTask(capability="owner", instruction="Do work", extra_field="invalid")
