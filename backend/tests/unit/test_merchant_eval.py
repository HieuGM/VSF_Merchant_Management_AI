from __future__ import annotations

import json

import pytest

from evaluation.merchant_eval import (
    DatasetNotReviewedError,
    evaluation_exit_code,
    ensure_dataset_reviewed,
    load_cases,
    render_markdown_report,
    score_pipeline_result,
    summarize_results,
)


def _case() -> dict:
    return {
        "case_id": "compound-01",
        "merchant_id": "94",
        "history": [],
        "question": "Tìm rồi phân tích nhóm quán sushi",
        "expected_agent": [
            "restaurant_search",
            "market_cohort_analysis",
        ],
        "expected_tools": [
            "search_merchants",
            "aggregate_public_merchant_cohort",
        ],
        "expected_content": ["quán", "nhóm"],
        "tags": ["compound"],
    }


def test_load_cases_validates_required_shape_and_unique_ids(tmp_path):
    dataset = tmp_path / "golden.jsonl"
    row = _case()
    dataset.write_text(
        "\n".join([json.dumps(row), json.dumps({**row, "case_id": "compound-02"})]),
        encoding="utf-8",
    )

    cases = load_cases(dataset)

    assert [case.case_id for case in cases] == ["compound-01", "compound-02"]


def test_normal_eval_refuses_unreviewed_dataset():
    with pytest.raises(DatasetNotReviewedError, match="review"):
        ensure_dataset_reviewed({"reviewed": False})


def test_score_pipeline_result_uses_ragas_tools_and_includes_trace_tokens():
    case_path_result = {
        "capabilities": ["restaurant_search", "market_cohort_analysis"],
        "reply": "Đã tìm thấy các quán phù hợp và phân tích nhóm.",
        "trace_id": "tr-eval-01",
        "token_usage": {
            "prompt_tokens": 80,
            "completion_tokens": 20,
            "total_tokens": 100,
        },
        "duration_ms": 420,
        "trace_summary": [
            {"tool_name": "search_merchants"},
            {"tool_name": "aggregate_public_merchant_cohort"},
        ],
    }

    scored = score_pipeline_result(_case(), case_path_result)

    assert scored["scores"] == {
        "agent_f1": 1.0,
        "tool_call_accuracy": 1.0,
        "tool_call_f1": 1.0,
        "content_coverage": 1.0,
    }
    assert scored["trace_id"] == "tr-eval-01"
    assert scored["token_usage"]["total_tokens"] == 100


def test_score_pipeline_result_maps_native_roles_and_owner_bound_tool_names():
    scored = score_pipeline_result(
        _case(),
        {
            "capabilities": ["coordinator", "market_search", "cohort_analysis"],
            "reply": "Đã tìm quán và phân tích nhóm.",
            "trace_summary": [
                {
                    "event": "crewai_tool_requested",
                    "agent_name": "Merchant Advisory Coordinator",
                    "tool_name": "delegate_work_to_coworker",
                },
                {
                    "event": "tool_started",
                    "agent_name": "market_search",
                    "tool_name": "search_merchants",
                },
                {
                    "event": "tool_started",
                    "agent_name": "cohort_analysis",
                    "tool_name": "aggregate_public_merchant_cohort",
                },
            ],
        },
    )

    assert scored["actual_agent"] == ["market_search", "cohort_analysis"]
    assert scored["scores"]["agent_f1"] == 1.0
    assert scored["scores"]["tool_call_f1"] == 1.0


def test_markdown_report_exposes_per_case_trace_and_tokens():
    scored = score_pipeline_result(
        _case(),
        {
            "capabilities": ["restaurant_search", "market_cohort_analysis"],
            "reply": "Đã tìm thấy quán và phân tích nhóm.",
            "trace_id": "tr-eval-02",
            "token_usage": {
                "prompt_tokens": 8,
                "completion_tokens": 2,
                "total_tokens": 10,
            },
            "duration_ms": 42,
            "trace_summary": [
                {"tool_name": "search_merchants"},
                {"tool_name": "aggregate_public_merchant_cohort"},
            ],
        },
    )

    report = render_markdown_report([scored])

    assert "tr-eval-02" in report
    assert "10" in report
    assert "tool_call_f1" in report


def test_summary_separates_successful_and_failed_cases():
    successful = score_pipeline_result(
        _case(),
        {
            "capabilities": ["restaurant_search", "market_cohort_analysis"],
            "reply": "Đã tìm thấy quán và phân tích nhóm.",
            "trace_summary": [
                {"tool_name": "search_merchants"},
                {"tool_name": "aggregate_public_merchant_cohort"},
            ],
        },
    )
    successful["status"] = "ok"
    failed = {
        **successful,
        "case_id": "failed-01",
        "status": "error",
        "error": "database unavailable",
        "scores": {
            "agent_f1": 0.0,
            "tool_call_accuracy": 0.0,
            "tool_call_f1": 0.0,
            "content_coverage": 0.0,
        },
    }

    summary = summarize_results([successful, failed])

    assert summary["case_count"] == 2
    assert summary["successful_cases"] == 1
    assert summary["failed_cases"] == 1
    assert summary["scores"]["agent_f1"] == 1.0
    assert evaluation_exit_code([successful, failed]) == 1
    assert evaluation_exit_code([successful]) == 0


def test_markdown_report_displays_failed_case_and_error():
    scored = score_pipeline_result(_case(), {})
    scored.update(
        {
            "status": "error",
            "error": "database unavailable",
        }
    )

    report = render_markdown_report([scored])

    assert "Successful: 0" in report
    assert "Failed: 1" in report
    assert "ERROR" in report
    assert "database unavailable" in report


def test_tool_score_is_perfect_when_no_tool_is_expected_or_called():
    case = {
        **_case(),
        "expected_agent": [],
        "expected_tools": [],
        "expected_content": ["không thể"],
    }

    scored = score_pipeline_result(
        case,
        {
            "capabilities": [],
            "trace_summary": [],
            "reply": "Tôi không thể cung cấp dữ liệu riêng tư.",
        },
    )

    assert scored["scores"]["tool_call_accuracy"] == 1.0
    assert scored["scores"]["tool_call_f1"] == 1.0
