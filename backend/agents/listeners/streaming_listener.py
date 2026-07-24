"""Streaming CrewAI event listener — forwards live progress to an SSE sink.

Complements the PersistingListener (which writes agent_events to the DB): this listener
pushes lightweight progress dicts (task/tool started/finished) to a per-request sink so the
`/chat/stream` endpoint can emit them as Server-Sent Events. This turns a 20-55s blank wait
into a live "đang tìm quán → đang phân tích → đang giải thích" experience (design §11.4
STREAM_EVENT_TYPES).

The sink is a ContextVar-bound callable set by `stream_scope(...)` in the same thread that
runs `crew.kickoff`; CrewAI fires bus callbacks synchronously in that thread, so the sink is
visible without cross-thread propagation. Outside a stream_scope the listener is a no-op, so
the non-streaming route and unit tests are unaffected.
"""
from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from crewai.events import crewai_event_bus
from crewai.events.base_event_listener import BaseEventListener
from crewai.events.types.task_events import TaskCompletedEvent, TaskStartedEvent
from crewai.events.types.tool_usage_events import (
    ToolUsageFinishedEvent,
    ToolUsageStartedEvent,
)

# Per-request SSE sink (a callable taking a progress dict). None outside a stream_scope.
_sink: ContextVar[Callable[[dict[str, Any]], None] | None] = ContextVar(
    "customer_stream_sink", default=None
)

_installed = False


@contextmanager
def stream_scope(emit: Callable[[dict[str, Any]], None]):
    """Bind progress events to `emit` for the duration of a streamed crew.kickoff."""
    token = _sink.set(emit)
    try:
        yield
    finally:
        _sink.reset(token)


def _emit(event: str, **data: Any) -> None:
    sink = _sink.get()
    if sink is None:
        return  # not streaming — no-op
    sink({"event": event, "data": {k: v for k, v in data.items() if v is not None}})


class StreamingListener(BaseEventListener):
    """Forwards CrewAI task/tool events to the active SSE sink (progress only)."""

    def setup_listeners(self, bus) -> None:  # noqa: ANN001 - crewai bus type
        @bus.on(TaskStartedEvent)
        def _task_started(source: Any, event: TaskStartedEvent) -> None:
            _emit("task_started", agent=getattr(event, "agent_role", None),
                  task=getattr(event, "task_name", None))

        @bus.on(TaskCompletedEvent)
        def _task_completed(source: Any, event: TaskCompletedEvent) -> None:
            _emit("task_finished", agent=getattr(event, "agent_role", None),
                  task=getattr(event, "task_name", None))

        @bus.on(ToolUsageStartedEvent)
        def _tool_started(source: Any, event: ToolUsageStartedEvent) -> None:
            _emit("tool_started", tool=getattr(event, "tool_name", None),
                  agent=getattr(event, "agent_role", None))

        @bus.on(ToolUsageFinishedEvent)
        def _tool_finished(source: Any, event: ToolUsageFinishedEvent) -> None:
            _emit("tool_finished", tool=getattr(event, "tool_name", None),
                  agent=getattr(event, "agent_role", None))


def install_streaming_listener() -> None:
    """Install the streaming listener on the global bus exactly once (idempotent)."""
    global _installed
    if _installed:
        return
    StreamingListener()  # __init__ registers handlers on crewai_event_bus
    _installed = True
