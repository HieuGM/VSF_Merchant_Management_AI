from flows.merchant_flow import MerchantFlowDispatcher
from models.merchant_orchestration import TokenUsage


def test_final_answer_selects_heading_and_preserves_existing_markdown():
    search_answer = MerchantFlowDispatcher._format_native_answer(
        "Tìm thấy 2 quán phù hợp.",
        [{"event": "tool_finished", "tool_name": "search_merchants"}],
    )
    answer = "## Kết quả tìm kiếm\nTìm thấy 2 quán phù hợp."
    diagnosis_answer = MerchantFlowDispatcher._format_native_answer(
        "Dữ liệu cho thấy chất lượng món và trải nghiệm khách chưa ổn định.",
        [
            {"event": "tool_finished", "tool_name": "get_owner_reviews"},
            {"event": "tool_finished", "tool_name": "diagnose_owner_merchant"},
        ],
    )

    assert search_answer.startswith("## Kết quả tìm kiếm")
    assert "Tìm thấy 2 quán phù hợp." in search_answer
    assert MerchantFlowDispatcher._format_native_answer(answer, []) == answer
    assert diagnosis_answer.startswith("## Điểm yếu và nguyên nhân")


def test_final_answer_restores_public_search_members_without_duplicate_section():
    cohort_answer = MerchantFlowDispatcher._format_native_answer(
        "## Phân tích nhóm quán\n\nRating trung bình là 4.4.",
        [
            {"event": "tool_finished", "tool_name": "search_merchants"},
            {
                "event": "tool_finished",
                "tool_name": "aggregate_public_merchant_cohort",
            },
        ],
        public_search_members=[
            {"name": "Quán A", "ratings": {"shopeefood": {"rating": 4.5}}},
            {"name": "Quán B"},
        ],
    )
    empty_search_answer = MerchantFlowDispatcher._format_native_answer(
        "### Kết quả tìm kiếm\nDữ liệu không đủ.",
        [
            {"event": "tool_finished", "tool_name": "search_merchants"},
            {
                "event": "tool_finished",
                "tool_name": "aggregate_public_merchant_cohort",
            },
        ],
        public_search_members=[{"name": "Quán A"}],
    )

    assert cohort_answer.startswith("## Kết quả tìm kiếm")
    assert "Quán A — 4.5 sao" in cohort_answer
    assert "Quán B" in cohort_answer
    assert "## Phân tích nhóm quán" in cohort_answer
    assert empty_search_answer.count("Kết quả tìm kiếm") == 1
    assert "Quán A" in empty_search_answer
    assert "Phân tích nhóm quán" in empty_search_answer


def test_native_token_usage_prefers_semantic_llm_spans_over_crew_total():
    usage = MerchantFlowDispatcher._native_trace_token_usage(
        [
            {
                "event": "trace_span",
                "kind": "finished",
                "display": {"title": "LLM response"},
                "metrics": {
                    "token_usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 2,
                        "total_tokens": 12,
                    }
                },
            },
            {
                "event": "trace_span",
                "kind": "finished",
                "display": {"title": "LLM response"},
                "metrics": {
                    "token_usage": {
                        "prompt_tokens": 20,
                        "completion_tokens": 3,
                        "total_tokens": 23,
                    }
                },
            },
            {
                "event": "trace_span",
                "kind": "finished",
                "display": {"title": "Điều phối tác vụ"},
                "metrics": {"token_usage": {"total_tokens": 999}},
            },
            {"event": "crewai_llm_finished", "token_usage": "<redacted>"},
        ]
    )

    assert usage.model_dump() == {
        "prompt_tokens": 30,
        "completion_tokens": 5,
        "total_tokens": 35,
    }


def test_native_response_summary_counts_sdk_only_and_gateway_tools_once():
    class SessionService:
        def append_message(self, **_kwargs):
            return None

    class RunService:
        def finish_run(self, **_kwargs):
            return None

    trace = [
        {
            "event": "crewai_tool_finished",
            "tool_name": "search_merchants",
            "correlation_id": "pair-1",
        },
        {
            "event": "tool_finished",
            "tool_name": "search_merchants",
            "correlation_id": "pair-1",
        },
        {
            "event": "tool_finished",
            "tool_name": "legacy_compatible_tool",
            "correlation_id": "gateway-only",
        },
        {"event": "crewai_llm_finished"},
    ]

    MerchantFlowDispatcher._finish_native_response(
        session_svc=SessionService(),
        run_svc=RunService(),
        trace_id="tr-tool-count",
        session_id="sess-tool-count",
        merchant_id="94",
        query="Tìm quán sushi",
        reply="Kết quả",
        status="completed",
        capabilities=["coordinator"],
        trace_summary=trace,
        started_clock=0.0,
        structured_outputs={},
        token_usage=TokenUsage(),
    )

    assert trace[-1]["tool_count"] == 2


def test_native_response_summary_counts_sdk_only_tool_completion():
    class SessionService:
        def append_message(self, **_kwargs):
            return None

    class RunService:
        def finish_run(self, **_kwargs):
            return None

    trace = [
        {
            "event": "crewai_tool_finished",
            "tool_name": "search_merchants",
            "correlation_id": "sdk-only",
        }
    ]

    MerchantFlowDispatcher._finish_native_response(
        session_svc=SessionService(),
        run_svc=RunService(),
        trace_id="tr-sdk-only-tool-count",
        session_id="sess-sdk-only-tool-count",
        merchant_id="94",
        query="Tìm quán sushi",
        reply="Kết quả",
        status="completed",
        capabilities=["coordinator"],
        trace_summary=trace,
        started_clock=0.0,
        structured_outputs={},
        token_usage=TokenUsage(),
    )

    assert trace[-1]["tool_count"] == 1


def test_native_response_summary_counts_same_name_independent_correlations():
    trace = [
        {
            "event": "tool_finished",
            "tool_name": "search_merchants",
            "correlation_id": "gateway-1",
        },
        {
            "event": "tool_finished",
            "tool_name": "search_merchants",
            "correlation_id": "gateway-2",
        },
        {
            "event": "crewai_tool_finished",
            "tool_name": "search_merchants",
            "correlation_id": "sdk-only",
        },
    ]

    assert MerchantFlowDispatcher._trace_tool_count(trace) == 3
