#!/usr/bin/env python3
"""Validate, preview, or run the merchant-owner golden evaluation dataset."""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from database.connection import SessionLocal  # noqa: E402
from evaluation.merchant_eval import (  # noqa: E402
    DatasetNotReviewedError,
    evaluation_exit_code,
    ensure_dataset_reviewed,
    load_cases,
    load_metadata,
    render_markdown_report,
    score_pipeline_result,
    summarize_results,
)
from flows.merchant_flow import merchant_flow  # noqa: E402
from services.chat_session_service import ChatSessionService  # noqa: E402


DEFAULT_DATASET = REPO_ROOT / "evals/merchant/golden_dataset.jsonl"
DEFAULT_METADATA = REPO_ROOT / "evals/merchant/metadata.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "evals/merchant/results"


def _load(args: argparse.Namespace):
    cases = load_cases(args.dataset)
    metadata = load_metadata(args.metadata)
    return cases, metadata


def validate_command(args: argparse.Namespace) -> int:
    cases, metadata = _load(args)
    tags = Counter(tag for case in cases for tag in case.tags)
    print(f"Dataset: {args.dataset}")
    print(f"Cases: {len(cases)}")
    print(f"Reviewed: {metadata.get('reviewed', False)}")
    print("Tags: " + ", ".join(f"{key}={value}" for key, value in sorted(tags.items())))
    return 0


def preview_command(args: argparse.Namespace) -> int:
    cases, metadata = _load(args)
    print(
        f"Golden dataset preview — {len(cases)} cases — "
        f"reviewed={metadata.get('reviewed', False)}"
    )
    for index, case in enumerate(cases, start=1):
        print(f"\n[{index:02d}] {case.case_id} ({', '.join(case.tags)})")
        if case.history:
            print(f"history: {json.dumps(case.history, ensure_ascii=False)}")
        print(f"question: {case.question}")
        print(f"expected_agent: {', '.join(case.expected_agent) or '(none)'}")
        print(f"expected_tools: {', '.join(case.expected_tools) or '(none)'}")
        print(f"expected_content: {', '.join(case.expected_content)}")
    return 0


def _execute_case(case) -> dict[str, Any]:
    session_id = f"eval_{case.case_id}_{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    try:
        session_service = ChatSessionService(db)
        session_service.get_or_create_session(
            session_id=session_id,
            context_snapshot={"merchant_id": case.merchant_id, "eval": True},
        )
        for message in case.history:
            sender = message.get("sender", "user")
            session_service.append_message(
                session_id=session_id,
                sender="agent" if sender in {"assistant", "agent"} else "user",
                text=message["text"],
            )
        return merchant_flow.chat(
            merchant_id=case.merchant_id,
            message=case.question,
            session_id=session_id,
            user_id="merchant-eval",
            db=db,
        )
    finally:
        db.close()


def run_command(args: argparse.Namespace) -> int:
    cases, metadata = _load(args)
    try:
        ensure_dataset_reviewed(metadata)
    except DatasetNotReviewedError as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 2

    if args.case_id:
        requested = set(args.case_id)
        cases = [case for case in cases if case.case_id in requested]
        missing = requested - {case.case_id for case in cases}
        if missing:
            print(f"Unknown case IDs: {', '.join(sorted(missing))}", file=sys.stderr)
            return 2
    if args.limit:
        cases = cases[: args.limit]

    results: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        try:
            pipeline_result = _execute_case(case)
            scored = score_pipeline_result(case, pipeline_result)
            scored["status"] = "ok"
        except Exception as error:
            scored = score_pipeline_result(
                case,
                {
                    "capabilities": [],
                    "reply": "",
                    "trace_summary": [],
                    "token_usage": {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                    },
                },
            )
            scored["status"] = "error"
            scored["error"] = str(error)
        results.append(scored)
        scores = scored["scores"]
        print(
            f"[{index:02d}/{len(cases):02d}] {case.case_id} "
            f"status={scored['status']} "
            f"trace={scored.get('trace_id') or '-'} "
            f"agent={scores['agent_f1']:.2f} "
            f"tools={scores['tool_call_f1']:.2f} "
            f"content={scores['content_coverage']:.2f} "
            f"tokens={scored['token_usage'].get('total_tokens', 0)} "
            f"latency={scored.get('duration_ms') or 0}ms"
        )
        if scored["status"] == "error":
            print(f"  error={scored['error']}", file=sys.stderr)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"merchant_eval_{timestamp}.json"
    markdown_path = output_dir / f"merchant_eval_{timestamp}.md"
    payload = {
        "generated_at": timestamp,
        "dataset": str(args.dataset),
        "metadata": metadata,
        "summary": summarize_results(results),
        "results": results,
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown_report(results), encoding="utf-8")
    print("\nSummary")
    for metric, value in payload["summary"]["scores"].items():
        print(f"  {metric}: {value:.4f}")
    print(f"  successful_cases: {payload['summary']['successful_cases']}")
    print(f"  failed_cases: {payload['summary']['failed_cases']}")
    print(f"  total_tokens: {payload['summary']['total_tokens']}")
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")
    return evaluation_exit_code(results)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    subparsers.add_parser("preview")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--case-id", action="append")
    run_parser.add_argument("--limit", type=int)
    run_parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "validate":
        return validate_command(args)
    if args.command == "preview":
        return preview_command(args)
    return run_command(args)


if __name__ == "__main__":
    raise SystemExit(main())
