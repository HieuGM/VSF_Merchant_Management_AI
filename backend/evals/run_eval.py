"""Co-located Evaluation Runner inside backend/evals/merchant/.

Runs:
- Tier 1: Planner Evaluation (plan_request mode & capability dispatch)
- Tier 2: End-to-End Chat Flow Evaluation (merchant_flow.chat latency & answer quality)

Usage:
    cd backend && ./.venv/bin/python evals/merchant/run_eval.py [--cases evals/merchant/cases.json] [--label candidate|production] [--tier 1|2]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Disable telemetry and suppress unverified HTTPS warnings ────────────────
os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"
os.environ["CREWAI_TRACING_ENABLED"] = "false"
os.environ["OTEL_EXPORTER_OTLP_TRACES_TIMEOUT"] = "1"
os.environ["OTEL_EXPORTER_OTLP_TIMEOUT"] = "1"

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── Path bootstrap: must happen before any backend imports ──────────────────
EVAL_DIR = Path(__file__).resolve().parent
BACKEND_DIR = Path(__file__).resolve().parents[1]  # .../backend
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(dotenv_path=BACKEND_DIR.parent / ".env")
load_dotenv(dotenv_path=BACKEND_DIR / ".env")
# ────────────────────────────────────────────────────────────────────────────

from crewai import LLM
from app.main import initialize_langfuse
from agents.merchant.planner import plan_request
from flows.merchant_flow import merchant_flow
from models.merchant_execution import PlannerRespond, PlannerDelegate
from core.settings import get_settings

DEFAULT_CASES_FILE = EVAL_DIR / "cases.json"
REPORT_FILE = EVAL_DIR / "report.json"

def get_configured_llm(tier: str = "large") -> LLM | None:
    settings = get_settings()
    if not settings.llm_api_key:
        return None
    model = settings.llm_model_small if tier == "small" else settings.llm_model_large
    if not model:
        return None
    options: dict[str, Any] = {
        "model": model,
        "api_key": settings.llm_api_key,
        "temperature": 0,
        "timeout": 300,
    }
    if settings.llm_base_url:
        options.update(base_url=settings.llm_base_url, provider="openai")
    elif settings.llm_provider != "openai":
        options["provider"] = settings.llm_provider
    try:
        return LLM(**options)
    except Exception as error:
        return None

def load_cases(cases_path: Path | None = None) -> list[dict[str, Any]]:
    path = cases_path or DEFAULT_CASES_FILE
    if not path.exists():
        raise FileNotFoundError(f"Cases file {path} not found")
    return json.loads(path.read_text(encoding="utf-8"))


from services.mem0_service import Mem0Service, memory_identity

def run_tier1_planner(cases: list[dict[str, Any]], llm: Any, label: str | None = None) -> list[dict[str, Any]]:
    """Tier 1: Evaluate planner agent + Mem0 memory routing precision."""
    print(f"\n--- Running Tier 1: Planner Evaluation with Mem0 (label={label or 'production'}) ---")
    results = []
    passed = 0
    direct_passed = 0
    direct_total = 0
    single_passed = 0
    single_total = 0
    multi_passed = 0
    multi_total = 0

    mem0_service = Mem0Service()

    for c in cases:
        start = time.perf_counter()
        query = c["query"]
        expected_outcome = c.get("expected_outcome", "delegate")
        expected_delegations = c.get("expected_delegations", [])
        expected_mode = "respond" if expected_outcome in ("reject", "respond") or not expected_delegations else "delegate"

        is_direct = (expected_mode == "respond")
        is_single = (expected_mode == "delegate" and len(expected_delegations) == 1)
        is_multi = (expected_mode == "delegate" and len(expected_delegations) > 1)

        if is_direct:
            direct_total += 1
        elif is_single:
            single_total += 1
        elif is_multi:
            multi_total += 1

        # 1. Retrieve memories from Mem0
        identity = memory_identity(user_id="eval_user", merchant_id="94", session_id="eval_sess")
        try:
            memories = mem0_service.search(query, identity)
        except Exception:
            memories = []

        # 2. Execute planner
        owner_context = {
            "merchant_id": "94",
            "name": "Cơm Tấm Sài Gòn 94",
            "city": "ho_chi_minh",
            "cuisine": "Cơm Tấm, Món Việt",
        }
        try:
            plan = plan_request(
                query=query,
                memories=memories,
                owner_context=owner_context,
                llm=llm,
                label=label,
            )
            actual_mode = plan.mode
            actual_caps = [t.capability for t in plan.tasks] if isinstance(plan, PlannerDelegate) else []
            error_msg = None
        except Exception as exc:
            actual_mode = "error"
            actual_caps = []
            error_msg = str(exc)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        # 3. Match evaluation
        mode_matched = (actual_mode == expected_mode)
        caps_matched = True
        if expected_mode == "delegate":
            if len(expected_delegations) == 1:
                caps_matched = (
                    actual_caps == expected_delegations
                    or any(cap in actual_caps for cap in expected_delegations)
                )
            else:
                caps_matched = set(expected_delegations).issubset(set(actual_caps)) or set(actual_caps) == set(expected_delegations)

        matched = mode_matched and caps_matched

        if matched:
            passed += 1
            if is_direct:
                direct_passed += 1
            elif is_single:
                single_passed += 1
            elif is_multi:
                multi_passed += 1
            print(f"  ✅ [{c['case_id']}] PASS ({duration_ms}ms) | mode={actual_mode} caps={actual_caps}")
        else:
            print(f"  ❌ [{c['case_id']}] FAIL ({duration_ms}ms) | exp_mode={expected_mode} got={actual_mode} | exp_caps={expected_delegations} got={actual_caps} err={error_msg}")

        results.append({
            "case_id": c["case_id"],
            "query": query,
            "expected_mode": expected_mode,
            "actual_mode": actual_mode,
            "expected_delegations": expected_delegations,
            "actual_capabilities": actual_caps,
            "matched": matched,
            "duration_ms": duration_ms,
            "error": error_msg,
            "ground_truth": c.get("ground_truth_answer", ""),
        })

    print(f"\n==================== Tier 1 Evaluation Summary ====================")
    if direct_total:
        print(f"  - Direct Answer (Respond):  {direct_passed}/{direct_total} ({round(direct_passed/direct_total*100, 1)}%)")
    if single_total:
        print(f"  - Single Agent Routing:     {single_passed}/{single_total} ({round(single_passed/single_total*100, 1)}%)")
    if multi_total:
        print(f"  - Multi Agent Routing:      {multi_passed}/{multi_total} ({round(multi_passed/multi_total*100, 1)}%)")
    overall_acc = round(passed / len(cases) * 100, 2) if cases else 0.0
    print(f"  -----------------------------------------------------------------")
    print(f"  - TOTAL OVERALL ACCURACY:   {passed}/{len(cases)} ({overall_acc}%)\n")
    return results


def run_tier2_flow(cases: list[dict[str, Any]], label: str | None = None) -> list[dict[str, Any]]:
    """Tier 2: End-to-end flow evaluation (latency, grounding, reply)."""
    print(f"\n--- Running Tier 2: End-to-End Flow Evaluation (label={label or 'production'}) ---")
    results = []
    passed = 0

    for c in cases:
        start = time.perf_counter()
        query = c["query"]
        expected_answer = c.get("ground_truth_answer", "")

        try:
            res = merchant_flow.chat(
                merchant_id="94",
                message=query,
                label=label,
            )
            reply = res.get("reply", "")
            status = res.get("status", "failed")
            trace_id = res.get("trace_id")
            error_msg = res.get("error")
        except Exception as exc:
            reply = ""
            status = "failed"
            trace_id = None
            error_msg = str(exc)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        success = (status == "completed" and bool(reply.strip()))

        if success:
            passed += 1
            print(f"  ✅ [{c['case_id']}] OK ({duration_ms}ms) | trace={trace_id} | preview={reply[:60]}...")
        else:
            print(f"  ❌ [{c['case_id']}] FAILED ({duration_ms}ms) | status={status} | err={error_msg}")

        results.append({
            "case_id": c["case_id"],
            "query": query,
            "status": status,
            "reply": reply,
            "trace_id": trace_id,
            "duration_ms": duration_ms,
            "expected_answer": expected_answer,
            "error": error_msg,
        })

    rate = round(passed / len(cases) * 100, 2) if cases else 0.0
    print(f"\nTier 2 Summary: {passed}/{len(cases)} succeeded ({rate}%)")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Merchant Agent Evaluation Runner")
    parser.add_argument("--cases", type=str, default=None, help="Path to cases JSON file")
    parser.add_argument("--label", type=str, default=None, help="Langfuse prompt label (candidate, production, etc.)")
    parser.add_argument("--tier", type=int, choices=[1, 2], default=None, help="Run specific tier (1 or 2). Default: both.")
    args = parser.parse_args()

    try:
        initialize_langfuse()
    except Exception as e:
        print(f"Warning: could not initialize langfuse: {e}")

    cases_file = Path(args.cases) if args.cases else DEFAULT_CASES_FILE
    cases = load_cases(cases_file)
    label = args.label

    run_t1 = args.tier in (None, 1)
    run_t2 = args.tier in (None, 2)

    tier1_results: list[dict[str, Any]] = []
    tier2_results: list[dict[str, Any]] = []

    if run_t1:
        try:
            llm = get_configured_llm("small")
        except Exception as e:
            print(f"Warning: could not initialize small LLM: {e}")
            llm = None
        tier1_results = run_tier1_planner(cases, llm=llm, label=label)

    if run_t2:
        tier2_results = run_tier2_flow(cases, label=label)

    report = {
        "summary": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cases_file": str(cases_file),
            "label": label or "default",
            "tier1_total": len(tier1_results),
            "tier1_passed": sum(1 for r in tier1_results if r.get("matched")),
            "tier2_total": len(tier2_results),
            "tier2_success": sum(1 for r in tier2_results if r.get("status") == "completed"),
        },
        "tier1_results": tier1_results,
        "tier2_results": tier2_results,
    }

    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport saved to: {REPORT_FILE.relative_to(BACKEND_DIR)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
