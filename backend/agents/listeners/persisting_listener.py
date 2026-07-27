"""Persisting CrewAI event listener (Phase 06) — bridges the event bus to agent_events.

Subclasses CrewAI's `BaseEventListener` and subscribes to tool/task events on the global
`crewai_event_bus`. Each event is mapped to an `AgentEventRecord` (via the frozen
`build_event_record` helper — H8 contract) and persisted through `AgentRunRepository`.

The bus is a process-wide singleton, so the listener is installed ONCE. Which run an
event belongs to is tracked with a ContextVar set by the flow around `crew.kickoff`
(`run_scope`). The flow itself owns run_started / run_finished; the listener owns the
tool/task trace events emitted by CrewAI during execution.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from time import perf_counter
from typing import Any

from crewai.events import crewai_event_bus
from crewai.events.base_event_listener import BaseEventListener
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

from agents.listeners.crewai_listener import build_event_record
from repositories.agent_run_repository import AgentRunRepository

# Active (trace_id, repo, timers) for the currently-running flow. None outside a run_scope.
_active_run: ContextVar[tuple[str, AgentRunRepository, dict[tuple[str, ...], float]] | None] = ContextVar(
    "active_agent_run", default=None
)

_installed = False


@contextmanager
def run_scope(trace_id: str, repo: AgentRunRepository):
    """Bind persisted events to `trace_id` for the duration of a crew.kickoff."""
    token = _active_run.set((trace_id, repo, {}))
    try:
        yield
    finally:
        _active_run.reset(token)


def _timer_key(kind: str, agent_name: str | None, task_name: str | None,
               tool_name: str | None) -> tuple[str, ...]:
    return (kind, agent_name or "", task_name or "", tool_name or "")


def _start_timer(kind: str, *, agent_name: str | None = None,
                 task_name: str | None = None, tool_name: str | None = None) -> None:
    active = _active_run.get()
    if active is not None:
        active[2][_timer_key(kind, agent_name, task_name, tool_name)] = perf_counter()


def _finish_timer(kind: str, *, agent_name: str | None = None,
                  task_name: str | None = None, tool_name: str | None = None) -> int | None:
    active = _active_run.get()
    if active is None:
        return None
    started = active[2].pop(_timer_key(kind, agent_name, task_name, tool_name), None)
    return int((perf_counter() - started) * 1000) if started is not None else None


def _persist(event_type: str, *, agent_name=None, task_name=None, tool_name=None,
             input_payload=None, output_summary=None, duration_ms=None, status="ok", error_code=None) -> None:
    active = _active_run.get()
    if active is None:
        return  # event outside a tracked run — ignore
    trace_id, repo, _ = active
    record = build_event_record(
        trace_id=trace_id,
        event_type=event_type,
        agent_name=agent_name,
        task_name=task_name,
        tool_name=tool_name,
        input_payload=input_payload,
        output_summary=output_summary,
        duration_ms=duration_ms,
        status=status,
        error_code=error_code,
    )
    repo.add_event(record)


class PersistingListener(BaseEventListener):
    """Persists CrewAI tool/task events to agent_events for the active run."""

    def setup_listeners(self, bus) -> None:  # noqa: ANN001 - crewai bus type
        @bus.on(ToolUsageStartedEvent)
        def _on_tool_started(source: Any, event: ToolUsageStartedEvent) -> None:
            agent_name = getattr(event, "agent_role", None)
            task_name = getattr(event, "task_name", None)
            tool_name = getattr(event, "tool_name", None)
            _start_timer("tool", agent_name=agent_name, task_name=task_name, tool_name=tool_name)
            _persist(
                "tool_started",
                agent_name=agent_name, task_name=task_name, tool_name=tool_name,
                input_payload=getattr(event, "tool_args", None),
            )

        @bus.on(ToolUsageFinishedEvent)
        def _on_tool_finished(source: Any, event: ToolUsageFinishedEvent) -> None:
            agent_name = getattr(event, "agent_role", None)
            task_name = getattr(event, "task_name", None)
            tool_name = getattr(event, "tool_name", None)
            _persist(
                "tool_finished",
                agent_name=agent_name, task_name=task_name, tool_name=tool_name,
                input_payload=getattr(event, "tool_args", None),
                output_summary={"from_cache": getattr(event, "from_cache", None)},
                duration_ms=_finish_timer("tool", agent_name=agent_name, task_name=task_name, tool_name=tool_name),
            )

        @bus.on(ToolUsageErrorEvent)
        def _on_tool_error(source: Any, event: ToolUsageErrorEvent) -> None:
            agent_name = getattr(event, "agent_role", None)
            task_name = getattr(event, "task_name", None)
            tool_name = getattr(event, "tool_name", None)
            _persist(
                "tool_finished",
                agent_name=agent_name, task_name=task_name, tool_name=tool_name,
                duration_ms=_finish_timer("tool", agent_name=agent_name, task_name=task_name, tool_name=tool_name),
                status="error",
                error_code=type(getattr(event, "error", "ToolError")).__name__,
                output_summary={"error": str(getattr(event, "error", ""))},
            )

        # Task events expose `agent_role` and `task_name` DIRECTLY on the event (verified
        # against CrewAI 1.15.5 event models) — use them instead of navigating
        # event.task.agent.role / event.task.name, which are often unset (Task has no name).
        @bus.on(TaskStartedEvent)
        def _on_task_started(source: Any, event: TaskStartedEvent) -> None:
            agent_name = getattr(event, "agent_role", None)
            task_name = getattr(event, "task_name", None)
            _start_timer("task", agent_name=agent_name, task_name=task_name)
            _persist(
                "task_started",
                agent_name=agent_name, task_name=task_name,
            )

        @bus.on(TaskCompletedEvent)
        def _on_task_completed(source: Any, event: TaskCompletedEvent) -> None:
            agent_name = getattr(event, "agent_role", None)
            task_name = getattr(event, "task_name", None)
            _persist(
                "task_finished",
                agent_name=agent_name, task_name=task_name,
                duration_ms=_finish_timer("task", agent_name=agent_name, task_name=task_name),
            )

        @bus.on(TaskFailedEvent)
        def _on_task_failed(source: Any, event: TaskFailedEvent) -> None:
            agent_name = getattr(event, "agent_role", None)
            task_name = getattr(event, "task_name", None)
            _persist(
                "task_finished",
                agent_name=agent_name, task_name=task_name,
                duration_ms=_finish_timer("task", agent_name=agent_name, task_name=task_name),
                status="error",
                error_code="TaskFailed",
            )


def install_persisting_listener() -> None:
    """Install the persisting listener on the global bus exactly once (idempotent)."""
    global _installed
    if _installed:
        return
    PersistingListener()  # __init__ registers handlers on crewai_event_bus
    _installed = True
