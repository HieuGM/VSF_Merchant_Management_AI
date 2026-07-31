"""Deterministic capability-to-tool execution planning."""
from __future__ import annotations

import time
from typing import Any, Callable

from sqlalchemy.orm import Session

from core.cache import CachePort
from models.merchant_orchestration import (
    CitedNumber,
    Capability,
    CapabilityPlan,
    EvidenceClaim,
    ExecutionResult,
    ExecutionStep,
    MerchantExecutionContext,
)
from services.merchant_data_policy import MerchantDataPolicy
from tools.merchant.cohort_tool import (
    aggregate_public_merchant_cohort,
    compare_owner_to_public_cohort,
)
from tools.merchant.complaints_tool import get_merchant_complaints
from tools.merchant.diagnosis_tool import (
    diagnose_merchant,
    recommend_improvements,
)
from tools.merchant.metrics_tool import get_merchant_operational_metrics
from tools.merchant.image_comparison_tool import compare_merchant_images
from tools.merchant.profile_tool import get_merchant_profile_summary
from tools.merchant.reviews_tool import get_merchant_reviews
from tools.merchant.search_tool import search_merchants


EventCallback = Callable[[str, dict[str, Any]], None]


def build_execution_plan(plan: CapabilityPlan) -> list[ExecutionStep]:
    capabilities = set(plan.capabilities)
    steps: list[ExecutionStep] = []

    def add(step: ExecutionStep) -> None:
        if not any(existing.step_id == step.step_id for existing in steps):
            steps.append(step)

    if (
        Capability.RESTAURANT_SEARCH in capabilities
        or Capability.MARKET_COHORT_ANALYSIS in capabilities
        or Capability.OWNER_VS_MARKET_BENCHMARK in capabilities
        or Capability.IMAGE_COMPARISON in capabilities
    ):
        add(
            ExecutionStep(
                step_id="search",
                agent_name="market_analyst",
                tool_name="search_merchants",
            )
        )
    if (
        Capability.MARKET_COHORT_ANALYSIS in capabilities
        or Capability.OWNER_VS_MARKET_BENCHMARK in capabilities
        or Capability.IMAGE_COMPARISON in capabilities
    ):
        add(
            ExecutionStep(
                step_id="cohort",
                agent_name="market_analyst",
                tool_name="aggregate_public_merchant_cohort",
                depends_on=["search"],
            )
        )

    needs_owner_profile = bool(
        capabilities
        & {
            Capability.OWNER_PROFILE_ANALYSIS,
            Capability.OWNER_DIAGNOSIS,
            Capability.RECOMMENDATION,
        }
    )
    if needs_owner_profile:
        add(
            ExecutionStep(
                step_id="owner_profile",
                agent_name="merchant_profile_analyst",
                tool_name="get_merchant_profile_summary",
                owner_private=True,
            )
        )

    needs_diagnosis = bool(
        capabilities
        & {
            Capability.OWNER_DIAGNOSIS,
            Capability.RECOMMENDATION,
        }
    )
    needs_standard_diagnosis = needs_diagnosis and not (
        Capability.IMAGE_COMPARISON in capabilities
        and Capability.OWNER_REVIEW_ANALYSIS not in capabilities
        and Capability.RECOMMENDATION not in capabilities
    )
    needs_reviews = (
        Capability.OWNER_REVIEW_ANALYSIS in capabilities
        or needs_standard_diagnosis
    )
    if needs_reviews:
        add(
            ExecutionStep(
                step_id="owner_reviews",
                agent_name="merchant_profile_analyst",
                tool_name="get_merchant_reviews",
                owner_private=True,
            )
        )

    if Capability.OWNER_PROFILE_ANALYSIS in capabilities or needs_diagnosis:
        add(
            ExecutionStep(
                step_id="owner_metrics",
                agent_name="merchant_profile_analyst",
                tool_name="get_merchant_operational_metrics",
                owner_private=True,
            )
        )
    if (
        Capability.OWNER_REVIEW_ANALYSIS in capabilities
        or needs_standard_diagnosis
    ):
        add(
            ExecutionStep(
                step_id="owner_complaints",
                agent_name="merchant_profile_analyst",
                tool_name="get_merchant_complaints",
                owner_private=True,
            )
        )
    if needs_standard_diagnosis:
        add(
            ExecutionStep(
                step_id="diagnosis",
                agent_name="diagnosis",
                tool_name="diagnose_merchant",
                depends_on=[
                    "owner_profile",
                    "owner_reviews",
                    "owner_metrics",
                    "owner_complaints",
                ],
                owner_private=True,
            )
        )

    if Capability.OWNER_VS_MARKET_BENCHMARK in capabilities:
        add(
            ExecutionStep(
                step_id="benchmark",
                agent_name="market_analyst",
                tool_name="compare_owner_to_public_cohort",
                depends_on=["cohort"],
                owner_private=True,
            )
        )

    if Capability.IMAGE_COMPARISON in capabilities:
        add(
            ExecutionStep(
                step_id="image_comparison",
                agent_name="merchant_profile_analyst",
                tool_name="compare_merchant_images",
                depends_on=["search", "owner_profile", "benchmark"],
                owner_private=True,
            )
        )

    if Capability.RECOMMENDATION in capabilities:
        add(
            ExecutionStep(
                step_id="recommendation",
                agent_name="recommendation",
                tool_name="recommend_improvements",
                depends_on=["diagnosis"],
                owner_private=True,
            )
        )

    return steps


def _cohort_claims(cohort: dict[str, Any], step_id: str) -> list[EvidenceClaim]:
    claims: list[EvidenceClaim] = []
    dimensions = cohort.get("aggregates", {}).get("dimensions", {})
    for dimension, stats in dimensions.items():
        mean = stats.get("mean")
        ref = f"aggregate:{step_id}:dimensions.{dimension}.mean"
        if mean is None or ref not in cohort.get("evidence_refs", []):
            continue
        claims.append(
            EvidenceClaim(
                claim=f"Điểm trung bình {dimension} của cohort là {mean}.",
                dimension=dimension,
                evidence_refs=[ref],
                numbers=[
                    CitedNumber(value=float(mean), evidence_ref=ref, field=dimension)
                ],
            )
        )
    return claims


def _benchmark_claims(
    benchmark: dict[str, Any],
) -> list[EvidenceClaim]:
    claims: list[EvidenceClaim] = []
    for dimension, comparison in benchmark.get("dimensions", {}).items():
        owner_ref = comparison.get("owner_evidence_ref")
        cohort_ref = comparison.get("cohort_evidence_ref")
        if not owner_ref or not cohort_ref:
            continue
        owner_value = float(comparison["owner_value"])
        cohort_mean = float(comparison["cohort_mean"])
        claims.append(
            EvidenceClaim(
                claim=(
                    f"{dimension} của owner là {owner_value}, "
                    f"cohort trung bình là {cohort_mean}."
                ),
                dimension=dimension,
                evidence_refs=[owner_ref, cohort_ref],
                numbers=[
                    CitedNumber(
                        value=owner_value,
                        evidence_ref=owner_ref,
                        field=dimension,
                    ),
                    CitedNumber(
                        value=cohort_mean,
                        evidence_ref=cohort_ref,
                        field=dimension,
                    ),
                ],
            )
        )
    return claims


def _diagnosis_claims(diagnosis: dict[str, Any]) -> list[EvidenceClaim]:
    claims: list[EvidenceClaim] = []
    for cause in diagnosis.get("causes", []):
        refs = [str(ref) for ref in cause.get("evidence_refs", []) if ref]
        if not refs:
            continue
        claims.append(
            EvidenceClaim(
                claim=str(cause.get("issue") or cause.get("dimension")),
                dimension=cause.get("dimension"),
                evidence_refs=refs,
            )
        )
    return claims


def _image_claims(comparison: dict[str, Any]) -> list[EvidenceClaim]:
    owner_value = comparison.get("owner_summary", {}).get("quality_mean")
    cohort_value = comparison.get("public_cohort_summary", {}).get("quality_mean")
    if owner_value is None or cohort_value is None:
        return []
    owner_ref = "aggregate:image_comparison:owner_summary.quality_mean"
    cohort_ref = (
        "aggregate:image_comparison:public_cohort_summary.quality_mean"
    )
    return [
        EvidenceClaim(
            claim=(
                f"Chất lượng hình ảnh trung bình của quán là {owner_value}, "
                f"nhóm công khai là {cohort_value}."
            ),
            dimension="image_quality",
            evidence_refs=[owner_ref, cohort_ref],
            numbers=[
                CitedNumber(
                    value=float(owner_value),
                    evidence_ref=owner_ref,
                    field="owner_image_quality",
                ),
                CitedNumber(
                    value=float(cohort_value),
                    evidence_ref=cohort_ref,
                    field="public_cohort_image_quality",
                ),
            ],
        )
    ]


def _tool_result_summary(
    step: ExecutionStep,
    result: dict[str, Any],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "tool_name": step.tool_name,
        "status": result.get("status", "ok"),
    }
    if step.step_id == "search":
        payload["result"] = {
            "count": result.get("count", 0),
            "merchants": result.get("merchants", []),
        }
        payload["merchants"] = result.get("merchants", [])
    elif step.step_id == "cohort":
        payload["result"] = {
            "cohort_count": result.get("cohort_count", 0),
            "aggregates": result.get("aggregates", {}),
        }
    elif step.step_id == "benchmark":
        payload["result"] = {
            "cohort_count": result.get("cohort_count", 0),
            "dimensions": result.get("dimensions", {}),
        }
    elif step.step_id == "image_comparison":
        payload["result"] = {
            "status": result.get("status"),
            "owner_summary": result.get("owner_summary", {}),
            "public_cohort_summary": result.get("public_cohort_summary", {}),
            "gaps": result.get("gaps", {}),
            "owner_samples": result.get("owner_samples", []),
            "public_samples": result.get("public_samples", []),
        }
    else:
        payload["result"] = result
    return payload


def execute_plan(
    plan: CapabilityPlan,
    context: MerchantExecutionContext,
    db: Session,
    cache: CachePort | None = None,
    event_callback: EventCallback | None = None,
) -> ExecutionResult:
    emit = event_callback or (lambda _event, _payload: None)
    policy = MerchantDataPolicy(context.owner_merchant_id)
    outputs: dict[str, dict[str, Any]] = {}
    aggregate_snapshots: dict[str, dict[str, Any]] = {}
    merchants: list[dict[str, Any]] = []
    claims: list[EvidenceClaim] = []
    trace_steps: list[dict[str, Any]] = []

    for step in build_execution_plan(plan):
        tool_args: dict[str, Any] = {}
        if step.step_id == "search":
            tool_args = plan.filters.model_dump(exclude_none=True)
            use_owner_location = bool(
                tool_args.pop("use_owner_location", False)
            )
            if use_owner_location:
                tool_args["anchor_merchant_id"] = context.owner_merchant_id
                tool_args.setdefault("radius_km", 5.0)
                tool_args.setdefault("sort_by", "distance")
        emit(
            "agent_start",
            {
                "agent_name": step.agent_name,
                "task": step.step_id,
                "step_id": step.step_id,
            },
        )
        if step.owner_private:
            policy.assert_owner_target(context.owner_merchant_id)
            emit(
                "policy_decision",
                {
                    "step_id": step.step_id,
                    "decision": "owner_private_allowed",
                    "owner_merchant_id": context.owner_merchant_id,
                },
            )
        elif step.step_id in {"search", "cohort"}:
            emit(
                "policy_decision",
                {
                    "step_id": step.step_id,
                    "decision": "competitor_public_only",
                },
            )

        emit(
            "tool_call",
            {
                "tool_name": step.tool_name,
                "step_id": step.step_id,
                "agent_name": step.agent_name,
                "depends_on": step.depends_on,
                "args": tool_args,
                "token_usage": None,
            },
        )
        started = time.perf_counter()

        if step.step_id == "search":
            try:
                result = search_merchants(
                    db=db,
                    cache=cache,
                    cache_event_callback=lambda payload: emit(
                        "cache",
                        {
                            **payload,
                            "step_id": step.step_id,
                            "agent_name": step.agent_name,
                            "token_usage": None,
                        },
                    ),
                    **tool_args,
                )
            except Exception as error:
                duration_ms = round(
                    (time.perf_counter() - started) * 1000,
                    3,
                )
                error_payload = {
                    "tool_name": step.tool_name,
                    "step_id": step.step_id,
                    "agent_name": step.agent_name,
                    "status": "error",
                    "error_code": type(error).__name__,
                    "error": str(error),
                    "duration_ms": duration_ms,
                    "token_usage": None,
                }
                emit("tool_result", error_payload)
                emit(
                    "agent_finish",
                    {
                        **error_payload,
                        "task": step.step_id,
                    },
                )
                raise
            if (
                Capability.MARKET_COHORT_ANALYSIS in plan.capabilities
                or Capability.OWNER_VS_MARKET_BENCHMARK in plan.capabilities
            ):
                result = {
                    **result,
                    "merchants": [
                        item
                        for item in result.get("merchants", [])
                        if str(item.get("merchant_id"))
                        != context.owner_merchant_id
                    ],
                }
                result["count"] = len(result["merchants"])
            merchants = result.get("merchants", [])
        elif step.step_id == "cohort":
            result = aggregate_public_merchant_cohort(
                [str(item["merchant_id"]) for item in merchants],
                step_id=step.step_id,
                db=db,
            )
            aggregate_snapshots[step.step_id] = result
            claims.extend(_cohort_claims(result, step.step_id))
        elif step.step_id == "owner_profile":
            result = get_merchant_profile_summary(
                context.owner_merchant_id,
                db=db,
            )
        elif step.step_id == "owner_reviews":
            result = get_merchant_reviews(context.owner_merchant_id, db=db)
        elif step.step_id == "owner_metrics":
            result = get_merchant_operational_metrics(
                context.owner_merchant_id,
                db=db,
            )
        elif step.step_id == "owner_complaints":
            result = get_merchant_complaints(
                context.owner_merchant_id,
                db=db,
            )
        elif step.step_id == "diagnosis":
            result = diagnose_merchant(context.owner_merchant_id, db=db)
            claims.extend(_diagnosis_claims(result))
        elif step.step_id == "benchmark":
            result = compare_owner_to_public_cohort(
                context.owner_merchant_id,
                outputs["cohort"],
                db=db,
            )
            claims.extend(_benchmark_claims(result))
        elif step.step_id == "image_comparison":
            result = compare_merchant_images(
                context.owner_merchant_id,
                [str(item["merchant_id"]) for item in merchants],
                db=db,
            )
            aggregate_snapshots[step.step_id] = result
            claims.extend(_image_claims(result))
        elif step.step_id == "recommendation":
            result = recommend_improvements(context.owner_merchant_id, db=db)
        else:
            result = {"status": "unsupported", "step_id": step.step_id}

        duration_ms = round((time.perf_counter() - started) * 1000)
        outputs[step.step_id] = result
        trace_steps.append(
            {
                "step_id": step.step_id,
                "agent_name": step.agent_name,
                "tool_name": step.tool_name,
                "duration_ms": duration_ms,
                "status": result.get("status", "ok"),
            }
        )
        emit(
            "tool_result",
            {
                **_tool_result_summary(step, result),
                "duration_ms": duration_ms,
                "token_usage": None,
            },
        )
        emit(
            "agent_finish",
            {
                "agent_name": step.agent_name,
                "task": step.step_id,
                "step_id": step.step_id,
                "status": result.get("status", "ok"),
                "duration_ms": duration_ms,
                "token_usage": None,
            },
        )

    return ExecutionResult(
        outputs=outputs,
        merchants=merchants,
        claims=claims,
        aggregate_snapshots=aggregate_snapshots,
        trace_steps=trace_steps,
    )
