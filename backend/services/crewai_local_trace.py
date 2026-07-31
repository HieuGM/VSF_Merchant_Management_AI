"""Local, structured observability for native CrewAI execution.

This observes CrewAI's event bus without enabling CrewAI Plus tracing.  It
contains no model prompts or raw LLM responses; gateway events remain the
authoritative trace for tool arguments and tool outputs.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from threading import Lock
from typing import Any

from crewai.events import (
    AgentExecutionCompletedEvent,
    AgentExecutionErrorEvent,
    AgentExecutionStartedEvent,
    CrewKickoffCompletedEvent,
    CrewKickoffFailedEvent,
    CrewKickoffStartedEvent,
    LLMCallCompletedEvent,
    LLMCallFailedEvent,
    LLMCallStartedEvent,
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskStartedEvent,
    ToolUsageErrorEvent,
    ToolUsageFinishedEvent,
    ToolUsageStartedEvent,
    crewai_event_bus,
)
from services.merchant_trace_collector import (
    ToolCorrelationBridge,
    TraceCollector,
    sanitize_developer_trace,
)


TraceEmit = Callable[[str, dict[str, Any]], None]


class LocalCrewAITrace:
    """Temporarily bridge one Crew's SDK events to the application trace."""

    def __init__(
        self,
        emit: TraceEmit,
        *,
        collector: TraceCollector | None = None,
        tool_correlation_bridge: ToolCorrelationBridge | None = None,
    ) -> None:
        self._emit_callback = emit
        self._collector = collector
        self._tool_correlation_bridge = tool_correlation_bridge
        self._terminal_sdk_correlations: set[str] = set()
        self._llm_started: dict[str, float] = {}
        self._lock = Lock()

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        """Keep the legacy callback shape, but never leak unbounded raw data."""
        self._emit_callback(event_type, sanitize_developer_trace(payload))

    @staticmethod
    def _observable_output(event: Any) -> Any:
        """Use only output fields actually exposed by a native event."""
        for attribute in ("output", "task_output", "result"):
            value = getattr(event, attribute, None)
            if value not in (None, ""):
                return value
        return "not_available"

    @staticmethod
    def _tool_correlation_id(event: Any, *, finished: bool = False) -> str | None:
        attributes = (
            ("started_event_id", "tool_call_id", "tool_usage_id", "call_id", "event_id", "id")
            if finished
            else ("tool_call_id", "tool_usage_id", "call_id", "event_id", "id")
        )
        for attribute in attributes:
            value = getattr(event, attribute, None)
            if value not in (None, ""):
                return str(value)
        return None

    def _record_sdk_only_once(
        self,
        *,
        agent_name: str | None,
        tool_name: str,
        args: Any,
        correlation_id: str | None,
        reason: str,
    ) -> None:
        if not self._collector or not correlation_id or correlation_id in self._terminal_sdk_correlations:
            return
        self._terminal_sdk_correlations.add(correlation_id)
        self._collector.record_sdk_only_tool(
            agent_name,
            tool_name,
            args,
            correlation_id=correlation_id,
            reason=reason,
        )

    @contextmanager
    def capture(self, crew: Any) -> Iterator[None]:
        roles = {
            agent.role
            for agent in [*crew.agents, crew.manager_agent]
            if agent is not None
        }
        agent_ids = {
            str(agent.id)
            for agent in [*crew.agents, crew.manager_agent]
            if agent is not None
        }

        def belongs_to_crew(source: Any, event: Any) -> bool:
            if source is crew or getattr(event, "crew", None) is crew:
                return True
            agent = getattr(event, "agent", None)
            if agent is not None and str(getattr(agent, "id", "")) in agent_ids:
                return True
            return (
                str(getattr(event, "agent_id", "")) in agent_ids
                or getattr(event, "agent_role", None) in roles
            )

        def on_crew_started(source: Any, event: CrewKickoffStartedEvent) -> None:
            if belongs_to_crew(source, event):
                self._emit("crewai_crew_started", {"agent_name": "coordinator"})
                if self._collector:
                    self._collector.observe_crewai_crew_started()

        def on_crew_completed(source: Any, event: CrewKickoffCompletedEvent) -> None:
            if belongs_to_crew(source, event):
                self._emit(
                    "crewai_crew_finished",
                    {
                        "agent_name": "coordinator",
                        "status": "ok",
                        "token_usage": {"total_tokens": event.total_tokens},
                    },
                )
                if self._collector:
                    self._collector.observe_crewai_crew_finished(
                        token_usage={"total_tokens": event.total_tokens}
                    )

        def on_crew_failed(source: Any, event: CrewKickoffFailedEvent) -> None:
            if belongs_to_crew(source, event):
                self._emit(
                    "error",
                    {
                        "agent_name": "coordinator",
                        "task": "crewai_kickoff",
                        "status": "error",
                        "error_code": str(event.error)[:180],
                    },
                )
                if self._collector:
                    self._collector.observe_crewai_crew_failed(event.error)

        def on_agent_started(source: Any, event: AgentExecutionStartedEvent) -> None:
            if belongs_to_crew(source, event):
                task = getattr(event, "task", None)
                self._emit(
                    "crewai_agent_started",
                    {
                        "agent_name": event.agent.role,
                        "task": getattr(task, "name", None),
                        "goal_prompt": getattr(event.agent, "goal", None),
                        "task_prompt": getattr(event, "task_prompt", None),
                    },
                )
                if self._collector:
                    self._collector.observe_crewai_agent_started(
                        event.agent.role,
                        task=getattr(task, "name", None) or "not_available",
                        goal_prompt=getattr(event.agent, "goal", None) or "not_available",
                        task_prompt=getattr(event, "task_prompt", None) or "not_available",
                    )

        def on_agent_completed(source: Any, event: AgentExecutionCompletedEvent) -> None:
            if belongs_to_crew(source, event):
                self._emit(
                    "crewai_agent_finished",
                    {"agent_name": event.agent.role, "status": "ok"},
                )
                if self._collector:
                    self._collector.observe_crewai_agent_finished(
                        event.agent.role,
                        output=self._observable_output(event),
                    )

        def on_agent_error(source: Any, event: AgentExecutionErrorEvent) -> None:
            if belongs_to_crew(source, event):
                self._emit(
                    "error",
                    {
                        "agent_name": event.agent.role,
                        "task": "crewai_agent_execution",
                        "status": "error",
                        "error_code": str(event.error)[:180],
                    },
                )
                if self._collector:
                    self._collector.observe_crewai_agent_failed(event.agent.role, event.error)

        def on_task_started(source: Any, event: TaskStartedEvent) -> None:
            if belongs_to_crew(source, event):
                self._emit(
                    "crewai_task_started",
                    {"task": getattr(event, "task_name", None) or "advisory_task"},
                )
                if self._collector:
                    self._collector.observe_crewai_task_started(
                        getattr(event, "task_name", None) or "not_available"
                    )

        def on_task_completed(source: Any, event: TaskCompletedEvent) -> None:
            if belongs_to_crew(source, event):
                self._emit(
                    "crewai_task_finished",
                    {"task": getattr(event, "task_name", None) or "advisory_task", "status": "ok"},
                )
                if self._collector:
                    self._collector.observe_crewai_task_finished(
                        getattr(event, "task_name", None) or "not_available",
                        output=self._observable_output(event),
                    )

        def on_task_failed(source: Any, event: TaskFailedEvent) -> None:
            if belongs_to_crew(source, event):
                self._emit(
                    "error",
                    {
                        "task": getattr(event, "task_name", None) or "advisory_task",
                        "status": "error",
                        "error_code": str(event.error)[:180],
                    },
                )
                if self._collector:
                    self._collector.observe_crewai_task_failed(
                        getattr(event, "task_name", None) or "not_available", event.error
                    )

        def on_llm_started(source: Any, event: LLMCallStartedEvent) -> None:
            if belongs_to_crew(source, event):
                with self._lock:
                    self._llm_started[event.call_id] = time.perf_counter()
                self._emit(
                    "crewai_llm_started",
                    {
                        "agent_name": getattr(event, "agent_role", None),
                        "model": event.model,
                        "call_id": event.call_id,
                    },
                )
                if self._collector:
                    self._collector.observe_crewai_llm_started(
                        event.call_id,
                        getattr(event, "agent_role", None),
                        getattr(event, "model", None),
                    )

        def on_llm_completed(source: Any, event: LLMCallCompletedEvent) -> None:
            if belongs_to_crew(source, event):
                with self._lock:
                    started = self._llm_started.pop(event.call_id, None)
                self._emit(
                    "crewai_llm_finished",
                    {
                        "agent_name": getattr(event, "agent_role", None),
                        "model": event.model,
                        "call_id": event.call_id,
                        "duration_ms": (
                            round((time.perf_counter() - started) * 1000, 3)
                            if started is not None
                            else None
                        ),
                        "token_usage": event.usage,
                        "finish_reason": event.finish_reason,
                    },
                )
                if self._collector:
                    self._collector.observe_crewai_llm_finished(
                        event.call_id,
                        duration_ms=(
                            round((time.perf_counter() - started) * 1000, 3)
                            if started is not None
                            else None
                        ),
                        token_usage=getattr(event, "usage", None),
                        finish_reason=getattr(event, "finish_reason", None) or "not_available",
                    )

        def on_llm_failed(source: Any, event: LLMCallFailedEvent) -> None:
            if belongs_to_crew(source, event):
                self._emit(
                    "error",
                    {
                        "agent_name": getattr(event, "agent_role", None),
                        "task": "crewai_llm_call",
                        "status": "error",
                        "error_code": str(event.error)[:180],
                    },
                )
                if self._collector:
                    self._collector.observe_crewai_llm_failed(
                        getattr(event, "call_id", ""), event.error
                    )

        def on_tool_started(source: Any, event: ToolUsageStartedEvent) -> None:
            if belongs_to_crew(source, event):
                correlation_id = self._tool_correlation_id(event)
                args = getattr(event, "tool_args", "not_available")
                resolution = None
                if self._tool_correlation_bridge and correlation_id:
                    resolution = self._tool_correlation_bridge.observe_sdk_event(
                        getattr(event, "agent_role", None),
                        event.tool_name,
                        args,
                        correlation_id,
                        is_start=True,
                    )
                self._emit(
                    "crewai_tool_requested",
                    {
                        "agent_name": event.agent_role,
                        "tool_name": event.tool_name,
                        "args": event.tool_args,
                    },
                )
                if self._collector:
                    if resolution and resolution.state == "gateway":
                        self._collector.observe_sdk_gateway_link(
                            resolution.span_id,
                            correlation_id=correlation_id,
                            agent_name=getattr(event, "agent_role", None),
                        )
                    elif resolution and resolution.state == "sdk_only" and correlation_id:
                        self._record_sdk_only_once(
                            agent_name=getattr(event, "agent_role", None),
                            tool_name=event.tool_name,
                            args=args,
                            correlation_id=correlation_id,
                            reason="no_exact_gateway_match",
                        )
                    else:
                        self._collector.observe_crewai_tool_started(
                            getattr(event, "agent_role", None),
                            event.tool_name,
                            args,
                            correlation_id=correlation_id,
                        )
                        if resolution and resolution.state == "ambiguous":
                            for unlinked_id in resolution.ambiguous_ids:
                                self._collector.observe_crewai_tool_unlinked(
                                    unlinked_id,
                                    reason="ambiguous_same_agent_tool_arguments",
                                )

        def on_tool_finished(source: Any, event: ToolUsageFinishedEvent) -> None:
            if belongs_to_crew(source, event):
                correlation_id = self._tool_correlation_id(event, finished=True)
                args = getattr(event, "tool_args", "not_available")
                resolution = (
                    self._tool_correlation_bridge.observe_sdk_event(
                        getattr(event, "agent_role", None),
                        event.tool_name,
                        args,
                        correlation_id,
                        is_start=False,
                    )
                    if self._tool_correlation_bridge
                    else None
                )
                self._emit(
                    "crewai_tool_finished",
                    {
                        "agent_name": event.agent_role,
                        "tool_name": event.tool_name,
                        "status": "cache_hit" if event.from_cache else "ok",
                        "correlation_id": correlation_id,
                    },
                )
                if self._collector:
                    if resolution and resolution.state == "gateway":
                        self._collector.observe_sdk_gateway_link(
                            resolution.span_id,
                            correlation_id=correlation_id,
                            agent_name=getattr(event, "agent_role", None),
                        )
                    elif resolution and resolution.state == "sdk_only" and correlation_id:
                        self._record_sdk_only_once(
                            agent_name=getattr(event, "agent_role", None),
                            tool_name=event.tool_name,
                            args=args,
                            correlation_id=correlation_id,
                            reason="sdk_finished_without_exact_gateway_match",
                        )
                    else:
                        self._collector.observe_crewai_tool_finished(
                            getattr(event, "agent_role", None),
                            event.tool_name,
                            status="cache_hit" if event.from_cache else "ok",
                            correlation_id=correlation_id,
                            sdk_only=bool(resolution and resolution.state == "pending"),
                        )
                if self._tool_correlation_bridge:
                    self._tool_correlation_bridge.discard(correlation_id)

        def on_tool_error(source: Any, event: ToolUsageErrorEvent) -> None:
            if belongs_to_crew(source, event):
                correlation_id = self._tool_correlation_id(event, finished=True)
                args = getattr(event, "tool_args", "not_available")
                resolution = (
                    self._tool_correlation_bridge.observe_sdk_event(
                        getattr(event, "agent_role", None),
                        event.tool_name,
                        args,
                        correlation_id,
                        is_start=False,
                    )
                    if self._tool_correlation_bridge
                    else None
                )
                self._emit(
                    "error",
                    {
                        "agent_name": event.agent_role,
                        "tool_name": event.tool_name,
                        "status": "error",
                        "error_code": str(event.error)[:180],
                    },
                )
                if self._collector:
                    if resolution and resolution.state == "gateway":
                        self._collector.observe_sdk_gateway_link(
                            resolution.span_id,
                            correlation_id=correlation_id,
                            agent_name=getattr(event, "agent_role", None),
                        )
                    elif resolution and resolution.state == "sdk_only" and correlation_id:
                        self._record_sdk_only_once(
                            agent_name=getattr(event, "agent_role", None),
                            tool_name=event.tool_name,
                            args=args,
                            correlation_id=correlation_id,
                            reason="sdk_error_without_exact_gateway_match",
                        )
                    else:
                        self._collector.observe_crewai_tool_failed(
                            getattr(event, "agent_role", None),
                            event.tool_name,
                            event.error,
                            correlation_id=correlation_id,
                            sdk_only=bool(resolution and resolution.state == "pending"),
                        )
                if self._tool_correlation_bridge:
                    self._tool_correlation_bridge.discard(correlation_id)

        handlers = [
            (CrewKickoffStartedEvent, on_crew_started),
            (CrewKickoffCompletedEvent, on_crew_completed),
            (CrewKickoffFailedEvent, on_crew_failed),
            (AgentExecutionStartedEvent, on_agent_started),
            (AgentExecutionCompletedEvent, on_agent_completed),
            (AgentExecutionErrorEvent, on_agent_error),
            (TaskStartedEvent, on_task_started),
            (TaskCompletedEvent, on_task_completed),
            (TaskFailedEvent, on_task_failed),
            (LLMCallStartedEvent, on_llm_started),
            (LLMCallCompletedEvent, on_llm_completed),
            (LLMCallFailedEvent, on_llm_failed),
            (ToolUsageStartedEvent, on_tool_started),
            (ToolUsageFinishedEvent, on_tool_finished),
            (ToolUsageErrorEvent, on_tool_error),
        ]
        for event_type, handler in handlers:
            crewai_event_bus.on(event_type)(handler)
        try:
            yield
        finally:
            # Kickoff failures can still have queued LLM/task/error events.
            # Flush before unregistering so the failure trace is durable.
            crewai_event_bus.flush(timeout=2.0)
            if self._tool_correlation_bridge:
                self._tool_correlation_bridge.drain_pending()
            if self._collector:
                self._collector.finalize_unlinked_sdk_tools(
                    reason="native_capture_completed_without_gateway_link"
                )
            for event_type, handler in handlers:
                crewai_event_bus.off(event_type, handler)
