from __future__ import annotations

from types import SimpleNamespace

import pytest

import services.crewai_local_trace as trace_module
from services.crewai_local_trace import LocalCrewAITrace
from services.merchant_trace_collector import ToolCorrelationBridge, TraceCollector


class _FakeEventBus:
    def __init__(self) -> None:
        self.actions: list[str] = []
        self.handlers: dict[object, object] = {}

    def on(self, _event_type):
        def register(handler):
            self.actions.append("on")
            self.handlers[_event_type] = handler
            return handler

        return register

    def flush(self, *, timeout: float) -> bool:
        self.actions.append(f"flush:{timeout}")
        return True

    def off(self, _event_type, _handler) -> None:
        self.actions.append("off")


def test_capture_flushes_native_events_before_unregistering_after_kickoff_error(
    monkeypatch,
):
    bus = _FakeEventBus()
    monkeypatch.setattr(trace_module, "crewai_event_bus", bus)
    crew = SimpleNamespace(agents=[], manager_agent=None)

    with pytest.raises(RuntimeError, match="kickoff timed out"):
        with LocalCrewAITrace(lambda _event, _payload: None).capture(crew):
            raise RuntimeError("kickoff timed out")

    assert "flush:2.0" in bus.actions
    assert bus.actions.index("flush:2.0") < bus.actions.index("off")


def test_agent_started_event_preserves_native_goal_and_task_prompt(monkeypatch):
    bus = _FakeEventBus()
    emitted: list[tuple[str, dict]] = []
    monkeypatch.setattr(trace_module, "crewai_event_bus", bus)
    crew = SimpleNamespace(agents=[], manager_agent=None)
    event = SimpleNamespace(
        agent=SimpleNamespace(role="Public Market Search Specialist", goal="Search public merchants."),
        task=SimpleNamespace(name="market_search"),
        task_prompt="Find sushi restaurants in Da Nang.",
    )

    with LocalCrewAITrace(lambda event_type, payload: emitted.append((event_type, payload))).capture(crew):
        handler = bus.handlers[trace_module.AgentExecutionStartedEvent]
        handler(crew, event)

    assert emitted == [
        (
            "crewai_agent_started",
            {
                "agent_name": "Public Market Search Specialist",
                "task": "market_search",
                "goal_prompt": "Search public merchants.",
                "task_prompt": "Find sushi restaurants in Da Nang.",
            },
        )
    ]


def test_optional_collector_uses_not_available_for_absent_native_prompt_data(monkeypatch):
    bus = _FakeEventBus()
    semantic_events: list[dict] = []
    monkeypatch.setattr(trace_module, "crewai_event_bus", bus)
    crew = SimpleNamespace(agents=[], manager_agent=None)
    event = SimpleNamespace(
        agent=SimpleNamespace(role="Public Market Search Specialist"),
    )

    with LocalCrewAITrace(
        lambda _event_type, _payload: None,
        collector=TraceCollector("tr-native", semantic_events.append),
    ).capture(crew):
        handler = bus.handlers[trace_module.AgentExecutionStartedEvent]
        handler(crew, event)

    assert len(semantic_events) == 1
    assert semantic_events[0]["phase"] == "agent"
    assert semantic_events[0]["debug"] == {
        "task": "not_available",
        "goal_prompt": "not_available",
        "task_prompt": "not_available",
    }


def test_optional_collector_preserves_exposed_agent_and_task_outputs(monkeypatch):
    bus = _FakeEventBus()
    semantic_events: list[dict] = []
    monkeypatch.setattr(trace_module, "crewai_event_bus", bus)
    crew = SimpleNamespace(agents=[], manager_agent=None)
    collector = TraceCollector("tr-native", semantic_events.append)

    with LocalCrewAITrace(lambda _event_type, _payload: None, collector=collector).capture(crew):
        bus.handlers[trace_module.AgentExecutionStartedEvent](
            crew,
            SimpleNamespace(agent=SimpleNamespace(role="Public Market Search Specialist")),
        )
        bus.handlers[trace_module.AgentExecutionCompletedEvent](
            crew,
            SimpleNamespace(
                agent=SimpleNamespace(role="Public Market Search Specialist"),
                output={"observed": "market data"},
            ),
        )
        bus.handlers[trace_module.TaskStartedEvent](crew, SimpleNamespace(task_name="market_search"))
        bus.handlers[trace_module.TaskCompletedEvent](
            crew,
            SimpleNamespace(task_name="market_search", result={"count": 3}),
        )

    finished = [event for event in semantic_events if event["kind"] == "finished"]
    assert finished[0]["debug"]["output"] == {"observed": "market data"}
    assert finished[1]["debug"]["output"] == {"count": 3}


def test_legacy_callback_payload_is_redacted_and_bounded(monkeypatch):
    bus = _FakeEventBus()
    emitted: list[tuple[str, dict]] = []
    monkeypatch.setattr(trace_module, "crewai_event_bus", bus)
    crew = SimpleNamespace(agents=[], manager_agent=None)
    event = SimpleNamespace(
        agent=SimpleNamespace(
            role="Public Market Search Specialist",
            goal="x" * 2_000,
        ),
        task=SimpleNamespace(name="market_search"),
        task_prompt="https://example.test/?token=supersecret",
    )

    with LocalCrewAITrace(lambda event_type, payload: emitted.append((event_type, payload))).capture(crew):
        bus.handlers[trace_module.AgentExecutionStartedEvent](crew, event)

    payload = emitted[0][1]
    assert "supersecret" not in payload["task_prompt"]
    assert "token=<redacted>" in payload["task_prompt"]
    assert len(payload["goal_prompt"]) <= 1_501


def test_late_sdk_tool_events_merge_into_completed_gateway_span(monkeypatch):
    bus = _FakeEventBus()
    semantic_events: list[dict] = []
    monkeypatch.setattr(trace_module, "crewai_event_bus", bus)
    crew = SimpleNamespace(agents=[], manager_agent=None)
    bridge = ToolCorrelationBridge()
    collector = TraceCollector("tr-native", semantic_events.append)
    args = {"query": "bún cá"}
    invocation = bridge.begin_gateway_call("market_search", "search_merchants", args)
    gateway_span = collector.observe_gateway_tool_started(
        "market_search", "search_merchants", args, correlation_id=invocation.correlation_id
    )
    bridge.register_gateway_span(invocation, gateway_span)
    collector.observe_gateway_tool_finished(
        "market_search",
        "search_merchants",
        result={"status": "ok"},
        latency_ms=1,
        span_id=gateway_span,
    )

    with LocalCrewAITrace(
        lambda _event_type, _payload: None,
        collector=collector,
        tool_correlation_bridge=bridge,
    ).capture(crew):
        bus.handlers[trace_module.ToolUsageFinishedEvent](
            crew,
            SimpleNamespace(
                agent_role="Public Market Search Specialist",
                tool_name="search_merchants",
                tool_args=args,
                started_event_id="sdk-late",
                from_cache=False,
            ),
        )
        bus.handlers[trace_module.ToolUsageStartedEvent](
            crew,
            SimpleNamespace(
                agent_role="Public Market Search Specialist",
                tool_name="search_merchants",
                tool_args=args,
                event_id="sdk-late",
            ),
        )

    tool_spans = [span for span in collector.snapshot() if span["phase"] == "tool"]
    assert len(tool_spans) == 1
    assert tool_spans[0]["span_id"] == gateway_span
    assert tool_spans[0]["display"]["status"] == "ok"


def test_unmatched_sdk_tool_start_is_terminal_sdk_only_when_capture_ends(monkeypatch):
    bus = _FakeEventBus()
    semantic_events: list[dict] = []
    monkeypatch.setattr(trace_module, "crewai_event_bus", bus)
    crew = SimpleNamespace(agents=[], manager_agent=None)
    collector = TraceCollector("tr-native", semantic_events.append)

    with LocalCrewAITrace(
        lambda _event_type, _payload: None,
        collector=collector,
        tool_correlation_bridge=ToolCorrelationBridge(),
    ).capture(crew):
        bus.handlers[trace_module.ToolUsageStartedEvent](
            crew,
            SimpleNamespace(
                agent_role="Public Market Search Specialist",
                tool_name="search_merchants",
                tool_args={"query": "bún cá"},
                event_id="sdk-unmatched",
            ),
        )

    tool_span = next(span for span in collector.snapshot() if span["phase"] == "tool")
    assert tool_span["display"]["status"] == "sdk_only"
    assert tool_span["debug"]["link_status"] == "sdk_only"


def test_unmatched_sdk_completion_and_error_are_explicit_sdk_only(monkeypatch):
    bus = _FakeEventBus()
    monkeypatch.setattr(trace_module, "crewai_event_bus", bus)
    crew = SimpleNamespace(agents=[], manager_agent=None)
    collector = TraceCollector("tr-native", lambda _event: None)

    with LocalCrewAITrace(
        lambda _event_type, _payload: None,
        collector=collector,
        tool_correlation_bridge=ToolCorrelationBridge(),
    ).capture(crew):
        bus.handlers[trace_module.ToolUsageStartedEvent](
            crew,
            SimpleNamespace(
                agent_role="Public Market Search Specialist",
                tool_name="search_merchants",
                tool_args={"query": "không khớp"},
                event_id="sdk-finished",
            ),
        )
        bus.handlers[trace_module.ToolUsageFinishedEvent](
            crew,
            SimpleNamespace(
                agent_role="Public Market Search Specialist",
                tool_name="search_merchants",
                tool_args={"query": "không khớp"},
                started_event_id="sdk-finished",
                from_cache=False,
            ),
        )
        bus.handlers[trace_module.ToolUsageStartedEvent](
            crew,
            SimpleNamespace(
                agent_role="Public Market Search Specialist",
                tool_name="get_public_merchant_detail",
                tool_args={"merchant_id": "m-1"},
                event_id="sdk-error",
            ),
        )
        bus.handlers[trace_module.ToolUsageErrorEvent](
            crew,
            SimpleNamespace(
                agent_role="Public Market Search Specialist",
                tool_name="get_public_merchant_detail",
                tool_args={"merchant_id": "m-1"},
                started_event_id="sdk-error",
                error=ValueError("database unavailable"),
            ),
        )

    tool_spans = [span for span in collector.snapshot() if span["phase"] == "tool"]
    assert len(tool_spans) == 2
    assert all(span["display"]["status"] == "sdk_only" for span in tool_spans)
    assert all(span["debug"]["link_status"] == "sdk_only" for span in tool_spans)
    assert {span["debug"]["sdk_outcome"] for span in tool_spans} == {"finished", "error"}
