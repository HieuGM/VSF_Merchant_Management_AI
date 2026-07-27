from __future__ import annotations

import json
from typing import Any

from models.merchant_orchestration import (
    Capability,
    MerchantExecutionContext,
)
from services.merchant_query_planner import rewrite_then_plan


CONTEXT = MerchantExecutionContext(
    trace_id="tr-planner-test",
    session_id="sess-planner-test",
    owner_merchant_id="94",
)


class FakeLLM:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[list[dict[str, Any]]] = []

    def call(self, messages: list[dict[str, Any]]) -> str:
        self.calls.append(messages)
        return self.responses.pop(0)


class UsageAwareFakeLLM(FakeLLM):
    def __init__(self, responses: list[str]) -> None:
        super().__init__(responses)
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def call(self, messages: list[dict[str, Any]]) -> str:
        self.prompt_tokens += 10
        self.completion_tokens += 5
        return super().call(messages)

    def get_token_usage_summary(self):
        return type(
            "Usage",
            (),
            {
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "total_tokens": self.prompt_tokens + self.completion_tokens,
            },
        )()


def test_compound_query_returns_multiple_capabilities_without_llm():
    result = rewrite_then_plan(
        "Tìm quán sushi ở Đà Nẵng rồi phân tích nhóm đó và so sánh với quán tôi",
        history=[],
        context=CONTEXT,
        llm_factory=lambda _tier: None,
    )

    assert result.rewritten_query.startswith("Tìm quán sushi")
    assert result.plan.capabilities == [
        Capability.RESTAURANT_SEARCH,
        Capability.MARKET_COHORT_ANALYSIS,
        Capability.OWNER_VS_MARKET_BENCHMARK,
    ]
    assert result.plan.filters.city == "Đà Nẵng"
    assert result.plan.filters.cuisine == "sushi"


def test_follow_up_is_rewritten_before_capability_planning():
    llm = FakeLLM(
        [
            json.dumps(
                {
                    "capabilities": [
                        "market_cohort_analysis",
                        "owner_vs_market_benchmark",
                    ],
                    "filters": {"city": "Đà Nẵng", "cuisine": "sushi"},
                    "requested_dimensions": [],
                },
                ensure_ascii=False,
            ),
        ]
    )

    result = rewrite_then_plan(
        "Còn nhóm đó thì sao?",
        history=[
            {"sender": "user", "text": "Tìm quán sushi ở Đà Nẵng"},
            {"sender": "agent", "text": "Đây là danh sách phù hợp."},
        ],
        context=CONTEXT,
        llm_factory=lambda _tier: llm,
    )

    assert result.rewritten_query.startswith("Tìm quán sushi ở Đà Nẵng")
    planner_user_message = llm.calls[0][-1]["content"]
    assert result.rewritten_query in planner_user_message
    assert "Còn nhóm đó thì sao?" in planner_user_message
    assert result.plan.capabilities == [
        Capability.RESTAURANT_SEARCH,
        Capability.MARKET_COHORT_ANALYSIS,
        Capability.OWNER_VS_MARKET_BENCHMARK,
    ]


def test_invalid_planner_json_retries_once_then_uses_fallback():
    llm = FakeLLM(
        [
            "not-json",
            '{"unsupported": true}',
        ]
    )

    result = rewrite_then_plan(
        "Tìm đối thủ gần quán tôi và so sánh",
        history=[],
        context=CONTEXT,
        llm_factory=lambda _tier: llm,
    )

    assert len(llm.calls) == 2
    assert result.used_fallback is True
    assert Capability.RESTAURANT_SEARCH in result.plan.capabilities
    assert Capability.MARKET_COHORT_ANALYSIS in result.plan.capabilities
    assert Capability.OWNER_VS_MARKET_BENCHMARK in result.plan.capabilities


def test_simple_greeting_uses_no_data_capabilities_without_llm():
    result = rewrite_then_plan(
        "Xin chào em",
        history=[],
        context=CONTEXT,
        llm_factory=lambda _tier: None,
    )

    assert result.plan.capabilities == [Capability.GENERAL_CHAT]


def test_diagnosis_and_recommendation_include_owner_profile_dependency():
    result = rewrite_then_plan(
        "Phân tích quán tôi, giải thích điểm yếu và gợi ý cải thiện",
        history=[],
        context=CONTEXT,
        llm_factory=lambda _tier: None,
    )

    assert result.plan.capabilities == [
        Capability.OWNER_PROFILE_ANALYSIS,
        Capability.OWNER_DIAGNOSIS,
        Capability.RECOMMENDATION,
    ]


def test_planner_reports_rewrite_and_planning_token_usage():
    llm = UsageAwareFakeLLM(
        [
            json.dumps(
                {
                    "capabilities": ["restaurant_search"],
                    "filters": {"city": "Đà Nẵng", "cuisine": "sushi"},
                    "requested_dimensions": [],
                }
            ),
        ]
    )

    result = rewrite_then_plan(
        "Tìm sushi ở Đà Nẵng",
        history=[],
        context=CONTEXT,
        llm_factory=lambda _tier: llm,
    )

    assert result.token_usage.model_dump() == {
        "total_tokens": 15,
        "prompt_tokens": 10,
        "completion_tokens": 5,
    }


def test_standalone_query_is_not_rewritten_or_expanded_by_llm():
    llm = FakeLLM(
        [
            json.dumps(
                {
                    "capabilities": ["restaurant_search"],
                    "filters": {"city": "Đà Nẵng", "cuisine": "sushi"},
                    "requested_dimensions": [],
                }
            )
        ]
    )

    result = rewrite_then_plan(
        "Tìm sushi ở Đà Nẵng",
        history=[],
        context=CONTEXT,
        llm_factory=lambda _tier: llm,
    )

    assert result.rewritten_query == "Tìm sushi ở Đà Nẵng"
    assert len(llm.calls) == 1


def test_fallback_handles_exploration_questions_and_search_filters():
    result = rewrite_then_plan(
        "Tôi muốn khám phá nhà hàng món Việt ở Hà Nội có rating từ 4.5 trở lên.",
        history=[],
        context=CONTEXT,
        llm_factory=lambda _tier: None,
    )

    assert result.plan.capabilities == [Capability.RESTAURANT_SEARCH]
    assert result.plan.filters.city == "Hà Nội"
    assert result.plan.filters.cuisine == "món việt"
    assert result.plan.filters.min_rating == 4.5


def test_fallback_uses_history_for_reference_resolution_without_llm():
    result = rewrite_then_plan(
        "Còn so với quán tôi thì sao?",
        history=[
            {"sender": "user", "text": "Tìm quán bún bò ở Huế giá dưới 70k"},
            {"sender": "assistant", "text": "Đây là danh sách phù hợp."},
        ],
        context=CONTEXT,
        llm_factory=lambda _tier: None,
    )

    assert "Tìm quán bún bò" in result.rewritten_query
    assert result.plan.capabilities == [
        Capability.RESTAURANT_SEARCH,
        Capability.MARKET_COHORT_ANALYSIS,
        Capability.OWNER_VS_MARKET_BENCHMARK,
    ]


def test_deterministic_filters_override_llm_translation_drift():
    llm = FakeLLM(
        [
            json.dumps(
                {
                    "capabilities": ["restaurant_search"],
                    "filters": {
                        "city": "Da Nang",
                        "cuisine": "vegetarian",
                    },
                    "requested_dimensions": [],
                }
            )
        ]
    )

    result = rewrite_then_plan(
        "Tìm quán chay ở Đà Nẵng.",
        history=[],
        context=CONTEXT,
        llm_factory=lambda _tier: llm,
    )

    assert result.plan.filters.city == "Đà Nẵng"
    assert result.plan.filters.cuisine == "chay"


def test_recommendation_implies_diagnosis_and_review_is_preserved():
    result = rewrite_then_plan(
        "Dựa trên review khách hàng, tôi nên sửa điều gì trước?",
        history=[],
        context=CONTEXT,
        llm_factory=lambda _tier: None,
    )

    assert result.plan.capabilities == [
        Capability.OWNER_PROFILE_ANALYSIS,
        Capability.OWNER_REVIEW_ANALYSIS,
        Capability.OWNER_DIAGNOSIS,
        Capability.RECOMMENDATION,
    ]


def test_public_cohort_review_request_does_not_open_owner_private_reviews():
    result = rewrite_then_plan(
        "Tìm quán chay rồi tổng hợp rating và review của nhóm đó.",
        history=[],
        context=CONTEXT,
        llm_factory=lambda _tier: None,
    )

    assert result.plan.capabilities == [
        Capability.RESTAURANT_SEARCH,
        Capability.MARKET_COHORT_ANALYSIS,
    ]


def test_search_accepts_optional_determiner_without_broad_find_keyword():
    result = rewrite_then_plan(
        "Tìm các quán sushi ở Đà Nẵng.",
        history=[],
        context=CONTEXT,
        llm_factory=lambda _tier: None,
    )

    assert result.plan.capabilities == [Capability.RESTAURANT_SEARCH]


def test_public_dimension_benchmark_does_not_fetch_separate_owner_profile():
    result = rewrite_then_plan(
        "Đối chiếu image quality, menu và giá của quán tôi với thị trường.",
        history=[],
        context=CONTEXT,
        llm_factory=lambda _tier: None,
    )

    assert result.plan.capabilities == [
        Capability.RESTAURANT_SEARCH,
        Capability.MARKET_COHORT_ANALYSIS,
        Capability.OWNER_VS_MARKET_BENCHMARK,
    ]


def test_owner_complaint_grouping_does_not_trigger_market_cohort():
    result = rewrite_then_plan(
        "Tổng hợp review và khiếu nại của quán tôi, nhóm theo chủ đề.",
        history=[],
        context=CONTEXT,
        llm_factory=lambda _tier: None,
    )

    assert result.plan.capabilities == [Capability.OWNER_REVIEW_ANALYSIS]
