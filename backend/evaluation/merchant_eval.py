"""Ragas-backed evaluation contracts and report rendering for merchant chat."""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any

from pydantic import BaseModel, Field, field_validator


# Golden cases describe business capabilities, while the native crew reports
# role names.  Keep this migration map here (not in prompts) so evaluation
# remains stable across an implementation rename.
_AGENT_ALIASES: dict[str, str] = {
    "restaurant_search": "market_search",
    "market_cohort_analysis": "cohort_analysis",
    "owner_profile_analysis": "self_analysis",
    "owner_review_analysis": "self_analysis",
    "owner_diagnosis": "self_analysis",
    "recommendation": "self_analysis",
    "owner_vs_market_benchmark": "cohort_analysis",
    "image_comparison": "self_analysis",
}

_TOOL_ALIASES: dict[str, str] = {
    "get_merchant_profile_summary": "get_owner_profile_summary",
    "get_merchant_operational_metrics": "get_owner_operational_metrics",
    "get_merchant_reviews": "get_owner_reviews",
    "get_merchant_complaints": "get_owner_complaints",
    "get_menu_and_food_images": "get_owner_menu_and_food_images",
    "diagnose_merchant": "diagnose_owner_merchant",
    "recommend_improvements": "recommend_owner_improvements",
}


def _canonical(values: list[str], aliases: dict[str, str]) -> list[str]:
    return list(dict.fromkeys(aliases.get(value, value) for value in values))


class DatasetNotReviewedError(RuntimeError):
    """Raised when a golden dataset is used before owner review."""


class MerchantEvalCase(BaseModel):
    case_id: str
    merchant_id: str
    history: list[dict[str, str]] = Field(default_factory=list)
    question: str
    expected_agent: list[str]
    expected_tools: list[str]
    expected_content: list[str]
    tags: list[str] = Field(default_factory=list)

    @field_validator("expected_agent", "expected_tools", "expected_content")
    @classmethod
    def no_duplicate_expectations(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("expectations must not contain duplicates")
        return value


def load_cases(path: str | Path) -> list[MerchantEvalCase]:
    dataset_path = Path(path)
    cases: list[MerchantEvalCase] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(
        dataset_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not raw_line.strip():
            continue
        try:
            case = MerchantEvalCase.model_validate_json(raw_line)
        except Exception as error:
            raise ValueError(
                f"Invalid dataset row {line_number}: {error}"
            ) from error
        if case.case_id in seen:
            raise ValueError(f"Duplicate case_id: {case.case_id}")
        seen.add(case.case_id)
        cases.append(case)
    if not cases:
        raise ValueError("Evaluation dataset is empty")
    return cases


def load_metadata(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Dataset metadata must be a JSON object")
    return value


def ensure_dataset_reviewed(metadata: dict[str, Any]) -> None:
    if metadata.get("reviewed") is not True:
        raise DatasetNotReviewedError(
            "Golden dataset is awaiting merchant-owner review. "
            "Use the preview command; do not tune or run baseline evaluation yet."
        )


def _set_f1(expected: list[str], actual: list[str]) -> float:
    expected_set = set(expected)
    actual_set = set(actual)
    if not expected_set and not actual_set:
        return 1.0
    if not expected_set or not actual_set:
        return 0.0
    true_positive = len(expected_set & actual_set)
    precision = true_positive / len(actual_set)
    recall = true_positive / len(expected_set)
    if precision + recall == 0:
        return 0.0
    return round(2 * precision * recall / (precision + recall), 4)


def _ragas_tool_scores(
    expected_tools: list[str],
    actual_tools: list[str],
) -> tuple[float, float]:
    if not expected_tools and not actual_tools:
        return 1.0, 1.0
    # Lazy import keeps dataset validation/preview lightweight while the normal
    # evaluation path still uses Ragas' official agent tool-call metrics.
    from ragas.messages import AIMessage, ToolCall
    from ragas.metrics.collections import ToolCallAccuracy, ToolCallF1

    actual_calls = [ToolCall(name=name, args={}) for name in actual_tools]
    reference_calls = [ToolCall(name=name, args={}) for name in expected_tools]
    messages = [AIMessage(content="", tool_calls=actual_calls)]
    accuracy = ToolCallAccuracy(strict_order=True).score(
        user_input=messages,
        reference_tool_calls=reference_calls,
    )
    f1 = ToolCallF1().score(
        user_input=messages,
        reference_tool_calls=reference_calls,
    )
    return round(float(accuracy.value), 4), round(float(f1.value), 4)


def score_pipeline_result(
    case_data: MerchantEvalCase | dict[str, Any],
    pipeline_result: dict[str, Any],
) -> dict[str, Any]:
    case = (
        case_data
        if isinstance(case_data, MerchantEvalCase)
        else MerchantEvalCase.model_validate(case_data)
    )
    traced_agents = [
        str(step["agent_name"])
        for step in pipeline_result.get("trace_summary", [])
        if step.get("event") == "tool_started" and step.get("agent_name")
    ]
    raw_agents = traced_agents or [
        str(value) for value in pipeline_result.get("capabilities", [])
    ]
    actual_agents = _canonical(raw_agents, _AGENT_ALIASES)
    gateway_tools = [
        str(step["tool_name"])
        for step in pipeline_result.get("trace_summary", [])
        if step.get("event") == "tool_started" and step.get("tool_name")
    ]
    raw_tools = gateway_tools or [
        str(step["tool_name"])
        for step in pipeline_result.get("trace_summary", [])
        if step.get("tool_name")
    ]
    actual_tools = _canonical(raw_tools, _TOOL_ALIASES)
    expected_agents = _canonical(case.expected_agent, _AGENT_ALIASES)
    expected_tools = _canonical(case.expected_tools, _TOOL_ALIASES)
    reply = str(pipeline_result.get("reply", ""))
    lowered_reply = reply.casefold()
    matched_content = [
        item for item in case.expected_content if item.casefold() in lowered_reply
    ]
    content_coverage = (
        len(matched_content) / len(case.expected_content)
        if case.expected_content
        else 1.0
    )
    tool_accuracy, tool_f1 = _ragas_tool_scores(
        expected_tools,
        actual_tools,
    )
    return {
        "case_id": case.case_id,
        "question": case.question,
        "expected_agent": expected_agents,
        "actual_agent": actual_agents,
        "expected_tools": expected_tools,
        "actual_tools": actual_tools,
        "expected_content": case.expected_content,
        "matched_content": matched_content,
        "scores": {
            "agent_f1": _set_f1(expected_agents, actual_agents),
            "tool_call_accuracy": tool_accuracy,
            "tool_call_f1": tool_f1,
            "content_coverage": round(content_coverage, 4),
        },
        "trace_id": pipeline_result.get("trace_id"),
        "token_usage": pipeline_result.get(
            "token_usage",
            {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        ),
        "duration_ms": pipeline_result.get("duration_ms"),
        "reply": reply,
        "tags": case.tags,
    }


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [row for row in results if row.get("status", "ok") == "ok"]
    metric_names = (
        "agent_f1",
        "tool_call_accuracy",
        "tool_call_f1",
        "content_coverage",
    )
    scores = {
        name: (
            round(mean(row["scores"][name] for row in successful), 4)
            if successful
            else 0.0
        )
        for name in metric_names
    }
    token_total = sum(
        int(row.get("token_usage", {}).get("total_tokens", 0))
        for row in results
    )
    return {
        "case_count": len(results),
        "successful_cases": len(successful),
        "failed_cases": len(results) - len(successful),
        "scores": scores,
        "total_tokens": token_total,
        "average_tokens": round(token_total / len(results), 2) if results else 0,
        "average_duration_ms": round(
            mean(float(row.get("duration_ms") or 0) for row in results),
            2,
        )
        if results
        else 0,
    }


def evaluation_exit_code(results: list[dict[str, Any]]) -> int:
    """Return a failing process status when any case could not be evaluated."""
    return 1 if any(row.get("status", "ok") != "ok" for row in results) else 0


def render_markdown_report(results: list[dict[str, Any]]) -> str:
    summary = summarize_results(results)
    lines = [
        "# Merchant Agent Evaluation",
        "",
        f"- Cases: {summary['case_count']}",
        f"- Successful: {summary['successful_cases']}",
        f"- Failed: {summary['failed_cases']}",
        f"- Total tokens: {summary['total_tokens']}",
        f"- Average tokens/case: {summary['average_tokens']}",
        f"- Average latency: {summary['average_duration_ms']} ms",
        "",
        "## Aggregate scores",
        "",
        "| Metric | Score |",
        "|---|---:|",
    ]
    lines.extend(
        f"| {name} | {value:.4f} |"
        for name, value in summary["scores"].items()
    )
    lines.extend(
        [
            "",
            "## Per-case traces",
            "",
            "| Case | Status | Trace | Agents F1 | Tool accuracy | Tool F1 | Content | Tokens | Latency | Error |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in results:
        scores = row["scores"]
        tokens = row.get("token_usage", {}).get("total_tokens", 0)
        status = str(row.get("status", "ok")).upper()
        error = str(row.get("error", "")).replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {row['case_id']} | {status} | {row.get('trace_id') or '-'} | "
            f"{scores['agent_f1']:.4f} | {scores['tool_call_accuracy']:.4f} | "
            f"{scores['tool_call_f1']:.4f} | {scores['content_coverage']:.4f} | "
            f"{tokens} | {row.get('duration_ms') or 0} ms | {error or '-'} |"
        )
    return "\n".join(lines) + "\n"
