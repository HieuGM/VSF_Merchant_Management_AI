from __future__ import annotations

from models.merchant_orchestration import (
    Capability,
    CapabilityPlan,
    MerchantExecutionContext,
    SearchFilters,
)
from services.merchant_plan_executor import build_execution_plan, execute_plan


def test_compound_plan_searches_once_and_reuses_candidates():
    plan = CapabilityPlan(
        capabilities=[
            Capability.RESTAURANT_SEARCH,
            Capability.MARKET_COHORT_ANALYSIS,
            Capability.OWNER_VS_MARKET_BENCHMARK,
        ],
        filters=SearchFilters(city="Đà Nẵng", cuisine="sushi"),
    )

    steps = build_execution_plan(plan)

    assert [step.tool_name for step in steps].count("search_merchants") == 1
    by_name = {step.step_id: step for step in steps}
    assert by_name["cohort"].depends_on == ["search"]
    assert by_name["benchmark"].depends_on == ["cohort"]
    assert [step.agent_name for step in steps] == [
        "market_analyst",
        "market_analyst",
        "market_analyst",
    ]


def test_owner_diagnosis_and_recommendation_reuse_owner_dependencies():
    plan = CapabilityPlan(
        capabilities=[
            Capability.OWNER_DIAGNOSIS,
            Capability.RECOMMENDATION,
        ]
    )

    steps = build_execution_plan(plan)
    tool_names = [step.tool_name for step in steps]

    assert tool_names.count("get_merchant_profile_summary") == 1
    assert tool_names.count("get_merchant_reviews") == 1
    assert tool_names[-2:] == ["diagnose_merchant", "recommend_improvements"]


def test_owner_profile_analysis_includes_quality_and_private_operations():
    steps = build_execution_plan(
        CapabilityPlan(capabilities=[Capability.OWNER_PROFILE_ANALYSIS])
    )

    assert [step.tool_name for step in steps] == [
        "get_merchant_profile_summary",
        "get_merchant_operational_metrics",
    ]


def test_owner_review_analysis_includes_reviews_and_private_complaints():
    steps = build_execution_plan(
        CapabilityPlan(capabilities=[Capability.OWNER_REVIEW_ANALYSIS])
    )

    assert [step.tool_name for step in steps] == [
        "get_merchant_reviews",
        "get_merchant_complaints",
    ]


def test_image_comparison_runs_after_public_benchmark_and_owner_profile():
    steps = build_execution_plan(
        CapabilityPlan(
            capabilities=[
                Capability.IMAGE_COMPARISON,
                Capability.OWNER_DIAGNOSIS,
            ]
        )
    )
    tool_names = [step.tool_name for step in steps]
    by_name = {step.step_id: step for step in steps}

    assert tool_names[-1] == "compare_merchant_images"
    assert by_name["image_comparison"].depends_on == [
        "search",
        "owner_profile",
        "benchmark",
    ]
    assert "get_merchant_operational_metrics" in tool_names
    assert by_name["image_comparison"].owner_private is True


def test_image_only_diagnosis_uses_image_tool_without_private_review_pipeline():
    steps = build_execution_plan(
        CapabilityPlan(
            capabilities=[
                Capability.OWNER_DIAGNOSIS,
                Capability.IMAGE_COMPARISON,
            ]
        )
    )

    assert [step.tool_name for step in steps] == [
        "search_merchants",
        "aggregate_public_merchant_cohort",
        "get_merchant_profile_summary",
        "get_merchant_operational_metrics",
        "compare_owner_to_public_cohort",
        "compare_merchant_images",
    ]


def test_execute_compound_plan_reuses_public_search_and_emits_trace(db_session):
    from database.models import Merchant
    from relational_test_fixtures import seed_relational_profile

    owner_id = "m_executor_owner"
    db_session.add(
        Merchant(
            merchant_id=owner_id,
            name="Owner Executor",
            cuisine="Cuisine Executor Unique",
            category="Quán ăn",
            city="Hà Nội",
            city_slug="ha_noi",
            lat=21.028,
            lng=105.854,
            is_active=True,
        )
    )
    seed_relational_profile(
        db_session,
        owner_id,
        scores={"food_quality": 0.6, "image_quality": 0.7},
    )
    for index, score in enumerate((0.8, 0.9), start=1):
        merchant_id = f"m_executor_comp_{index}"
        db_session.add(
            Merchant(
                merchant_id=merchant_id,
                name=f"Competitor Executor {index}",
                cuisine="Cuisine Executor Unique",
                category="Quán ăn",
                city="Hà Nội",
                city_slug="ha_noi",
                lat=21.029 + index / 1000,
                lng=105.855,
                is_active=True,
            )
        )
        seed_relational_profile(
            db_session,
            merchant_id,
            scores={"food_quality": score, "waiting_time": 0.1},
        )
    db_session.commit()
    plan = CapabilityPlan(
        capabilities=[
            Capability.RESTAURANT_SEARCH,
            Capability.MARKET_COHORT_ANALYSIS,
            Capability.OWNER_VS_MARKET_BENCHMARK,
        ],
        filters=SearchFilters(
            city="Hà Nội",
            cuisine="Cuisine Executor Unique",
        ),
    )
    context = MerchantExecutionContext(
        trace_id="tr-executor",
        session_id="sess-executor",
        owner_merchant_id=owner_id,
    )
    events: list[tuple[str, dict]] = []

    result = execute_plan(
        plan,
        context=context,
        db=db_session,
        event_callback=lambda event, payload: events.append((event, payload)),
    )

    assert result.outputs["cohort"]["cohort_count"] == 2
    assert result.outputs["benchmark"]["dimensions"]["food_quality"]["delta"] < 0
    assert owner_id not in {
        merchant["merchant_id"] for merchant in result.merchants
    }
    assert [event for event, _ in events].count("tool_call") == 3
    assert [event for event, _ in events].count("tool_result") == 3
