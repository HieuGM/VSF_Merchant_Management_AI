from __future__ import annotations

from services.merchant_trace_collector import (
    COORDINATOR_INPUT_ARTIFACT_KEY,
    ToolCorrelationBridge,
    TraceCollector,
    sanitize_developer_trace,
)


def test_collector_updates_same_span_and_flushes_each_event_live():
    emitted: list[dict] = []
    collector = TraceCollector("tr-1", emitted.append)

    span_id = collector.start_span(
        phase="tool",
        actor_type="tool",
        actor_name="get_public_merchant_detail",
    )
    collector.finish_span(
        span_id,
        title="Đọc giờ mở cửa",
        summary="Mở 10:00–22:00",
        latency_ms=42,
    )

    assert [event["seq"] for event in emitted] == [1, 2]
    assert {event["span_id"] for event in emitted} == {span_id}
    assert [event["kind"] for event in emitted] == ["started", "finished"]


def test_collector_redacts_string_secrets_and_never_emits_orphan_close():
    emitted: list[dict] = []
    collector = TraceCollector("tr-1", emitted.append)

    collector.finish_span(
        "sp-missing",
        title="Không được phát",
        summary="Không được phát",
    )
    span_id = collector.start_span(
        phase="tool",
        actor_type="tool",
        actor_name="search_merchants",
        debug={
            "args": {"api_key": "x"},
            "raw": "Authorization: Bearer very-secret-token",
        },
    )

    assert len(emitted) == 1
    assert emitted[0]["span_id"] == span_id
    assert emitted[0]["debug"]["args"]["api_key"] == "<redacted>"
    assert "very-secret-token" not in emitted[0]["debug"]["raw"]


def test_collector_strictly_allowlists_preserved_coordinator_artifact():
    emitted: list[dict] = []
    collector = TraceCollector("tr-allowlist", emitted.append)

    collector.record(
        phase="coordinator",
        actor_type="coordinator",
        actor_name="coordinator",
        title="Nạp đầu vào điều phối viên",
        summary="Kiểm tra allowlist.",
        debug={
            COORDINATOR_INPUT_ARTIFACT_KEY: {
                "dynamic_context": "d" * 2_000,
                "prepared_inputs": {
                    "rewritten_query": "q",
                    "raw_tool_response": "z" * 9_000,
                },
                "coordinator_goal_prompt": "goal",
                "advisory_task_prompt": "task",
                "raw_tool_response": "z" * 9_000,
            },
            "generic_debug": "g" * 9_000,
        },
    )

    live_debug = emitted[-1]["debug"]
    artifact = live_debug[COORDINATOR_INPUT_ARTIFACT_KEY]
    assert set(artifact) == {
        "dynamic_context",
        "prepared_inputs",
        "coordinator_goal_prompt",
        "advisory_task_prompt",
    }
    assert artifact["dynamic_context"] == "d" * 2_000
    assert artifact["prepared_inputs"] == {"rewritten_query": "q"}
    assert "raw_tool_response" not in artifact
    assert len(live_debug["generic_debug"]) == 1_501
    assert live_debug["generic_debug"].endswith("…")


def test_collector_deduplicates_immediate_sdk_gateway_tool_events_but_not_repeated_calls():
    emitted: list[dict] = []
    collector = TraceCollector("tr-1", emitted.append)

    first_sdk = collector.observe_crewai_tool_started(
        "Public Market Search Specialist",
        "search_merchants",
        {"query": "bún cá"},
    )
    first_gateway = collector.observe_gateway_tool_started(
        "market_search",
        "search_merchants",
        {"query": "bún cá", "city": "hai_phong"},
    )
    collector.observe_gateway_tool_finished(
        "market_search",
        "search_merchants",
        result={"status": "ok", "count": 1},
        latency_ms=7,
    )
    collector.observe_crewai_tool_finished(
        "Public Market Search Specialist", "search_merchants", status="ok"
    )

    second_sdk = collector.observe_crewai_tool_started(
        "Public Market Search Specialist",
        "search_merchants",
        {"query": "phở"},
    )
    second_gateway = collector.observe_gateway_tool_started(
        "market_search",
        "search_merchants",
        {"query": "phở"},
    )

    assert first_sdk == first_gateway
    assert second_sdk == second_gateway
    assert second_sdk != first_sdk
    assert [event["seq"] for event in emitted] == list(range(1, len(emitted) + 1))
    assert [event["kind"] for event in emitted] == ["started", "finished", "started"]
    assert emitted[1]["debug"]["result"] == {"status": "ok", "count": 1}


def test_collector_matches_concurrent_same_tool_to_its_agent_parent_not_fifo_order():
    collector = TraceCollector("tr-1", lambda _event: None)
    market_parent = collector.observe_crewai_agent_started("Public Market Search Specialist")
    cohort_parent = collector.observe_crewai_agent_started("Public Cohort Analysis Specialist")
    market_sdk = collector.observe_crewai_tool_started(
        "Public Market Search Specialist", "search_merchants", {"query": "bún cá"}
    )
    cohort_sdk = collector.observe_crewai_tool_started(
        "Public Cohort Analysis Specialist", "search_merchants", {"query": "phở"}
    )

    cohort_gateway = collector.observe_gateway_tool_started(
        "cohort_analysis", "search_merchants", {"query": "phở"}
    )
    market_gateway = collector.observe_gateway_tool_started(
        "market_search", "search_merchants", {"query": "bún cá"}
    )

    spans = {span["span_id"]: span for span in collector.snapshot()}
    assert cohort_gateway == cohort_sdk
    assert market_gateway == market_sdk
    assert spans[cohort_sdk]["parent_span_id"] == cohort_parent
    assert spans[market_sdk]["parent_span_id"] == market_parent


def test_collector_refuses_ambiguous_same_agent_same_tool_merge_without_correlation_id():
    collector = TraceCollector("tr-1", lambda _event: None)
    collector.observe_crewai_agent_started("Public Market Search Specialist")
    first_sdk = collector.observe_crewai_tool_started(
        "Public Market Search Specialist", "search_merchants", {"query": "a"}
    )
    second_sdk = collector.observe_crewai_tool_started(
        "Public Market Search Specialist", "search_merchants", {"query": "b"}
    )

    gateway_span = collector.observe_gateway_tool_started(
        "market_search", "search_merchants", {"query": "b"}
    )

    assert gateway_span not in {first_sdk, second_sdk}


def test_developer_trace_sanitizer_redacts_query_tokens_and_bounds_payloads():
    payload = sanitize_developer_trace(
        {
            "prompt": "https://example.test/search?token=supersecret&query=bun-ca",
            "nested": {
                "token": "also-secret",
                "x-api-key": "hyphen-secret",
                "access-token": "another-hyphen-secret",
            },
            "large": "x" * 2_000,
        }
    )

    assert "supersecret" not in payload["prompt"]
    assert "token=<redacted>" in payload["prompt"]
    assert payload["nested"]["token"] == "<redacted>"
    assert payload["nested"]["x-api-key"] == "<redacted>"
    assert payload["nested"]["access-token"] == "<redacted>"
    assert len(payload["large"]) <= 1_501


def test_bridge_correlates_repeated_same_agent_tool_calls_out_of_order_without_orphans():
    collector = TraceCollector("tr-1", lambda _event: None)
    bridge = ToolCorrelationBridge()
    collector.observe_crewai_agent_started("Public Market Search Specialist")
    first_args = {"query": "bún cá"}
    second_args = {"query": "phở"}

    assert bridge.observe_sdk_event(
        "Public Market Search Specialist",
        "search_merchants",
        first_args,
        "sdk-1",
        is_start=True,
    ).state == "pending"
    first_span = collector.observe_crewai_tool_started(
        "Public Market Search Specialist",
        "search_merchants",
        first_args,
        correlation_id="sdk-1",
    )
    assert bridge.observe_sdk_event(
        "Public Market Search Specialist",
        "search_merchants",
        second_args,
        "sdk-2",
        is_start=True,
    ).state == "pending"
    second_span = collector.observe_crewai_tool_started(
        "Public Market Search Specialist",
        "search_merchants",
        second_args,
        correlation_id="sdk-2",
    )

    second_invocation = bridge.begin_gateway_call("market_search", "search_merchants", second_args)
    second_id = second_invocation.correlation_id
    second_gateway = collector.observe_gateway_tool_started(
        "market_search", "search_merchants", second_args, correlation_id=second_id
    )
    bridge.register_gateway_span(second_invocation, second_gateway)
    collector.observe_gateway_tool_finished(
        "market_search",
        "search_merchants",
        result={"status": "ok"},
        latency_ms=1,
        span_id=second_gateway,
    )
    collector.observe_crewai_tool_finished(
        "Public Market Search Specialist", "search_merchants", correlation_id="sdk-2"
    )

    first_invocation = bridge.begin_gateway_call("market_search", "search_merchants", first_args)
    first_id = first_invocation.correlation_id
    first_gateway = collector.observe_gateway_tool_started(
        "market_search", "search_merchants", first_args, correlation_id=first_id
    )
    bridge.register_gateway_span(first_invocation, first_gateway)
    collector.observe_gateway_tool_finished(
        "market_search",
        "search_merchants",
        result={"status": "ok"},
        latency_ms=1,
        span_id=first_gateway,
    )
    collector.observe_crewai_tool_finished(
        "Public Market Search Specialist", "search_merchants", correlation_id="sdk-1"
    )

    tool_spans = [span for span in collector.snapshot() if span["phase"] == "tool"]
    assert second_id == "sdk-2"
    assert first_id == "sdk-1"
    assert second_gateway == second_span
    assert first_gateway == first_span
    assert len(tool_spans) == 2
    assert all(span["display"]["status"] == "ok" for span in tool_spans)


def test_bridge_links_sdk_events_arriving_after_gateway_completed_without_duplicate_span():
    collector = TraceCollector("tr-1", lambda _event: None)
    bridge = ToolCorrelationBridge()
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

    finished_first = bridge.observe_sdk_event(
        "Public Market Search Specialist",
        "search_merchants",
        args,
        "sdk-late",
        is_start=False,
    )
    collector.observe_sdk_gateway_link(
        finished_first.span_id,
        correlation_id="sdk-late",
        agent_name="Public Market Search Specialist",
    )
    started_late = bridge.observe_sdk_event(
        "Public Market Search Specialist",
        "search_merchants",
        args,
        "sdk-late",
        is_start=True,
    )
    collector.observe_sdk_gateway_link(
        started_late.span_id,
        correlation_id="sdk-late",
        agent_name="Public Market Search Specialist",
    )

    tool_spans = [span for span in collector.snapshot() if span["phase"] == "tool"]
    assert finished_first.state == started_late.state == "gateway"
    assert tool_spans == [collector.snapshot()[0]]
    assert tool_spans[0]["span_id"] == gateway_span
    assert tool_spans[0]["display"]["status"] == "ok"
    assert tool_spans[0]["debug"]["link_status"] == "gateway_authoritative"
