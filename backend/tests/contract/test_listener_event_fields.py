"""Contract: CrewAI event models expose the fields the persisting listener reads.

The persisting listener (`agents/listeners/persisting_listener.py`) maps CrewAI event
attributes → `agent_events` columns. If a CrewAI upgrade renames a field, the listener's
`getattr(event, name, None)` silently falls back to None and events persist all-null with
no failure. This test pins the field names so such a drift fails loudly instead.
"""
from __future__ import annotations

from crewai.events.types.task_events import (
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskStartedEvent,
)
from crewai.events.types.tool_usage_events import (
    ToolUsageErrorEvent,
    ToolUsageFinishedEvent,
    ToolUsageStartedEvent,
)


def _fields(event_cls) -> set[str]:
    return set(event_cls.model_fields.keys())


def test_tool_events_expose_read_fields():
    """Tool handlers read agent_role / task_name / tool_name / tool_args directly."""
    read = {"agent_role", "task_name", "tool_name", "tool_args"}
    for event_cls in (ToolUsageStartedEvent, ToolUsageFinishedEvent, ToolUsageErrorEvent):
        missing = read - _fields(event_cls)
        assert not missing, f"{event_cls.__name__} missing {missing}"


def test_tool_finished_exposes_from_cache():
    assert "from_cache" in _fields(ToolUsageFinishedEvent)


def test_tool_error_exposes_error():
    assert "error" in _fields(ToolUsageErrorEvent)


def test_task_events_expose_direct_agent_role_and_task_name():
    """Task handlers read agent_role / task_name DIRECTLY (not via event.task.*)."""
    read = {"agent_role", "task_name"}
    for event_cls in (TaskStartedEvent, TaskCompletedEvent, TaskFailedEvent):
        missing = read - _fields(event_cls)
        assert not missing, f"{event_cls.__name__} missing {missing}"
