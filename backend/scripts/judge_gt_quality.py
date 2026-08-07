#!/usr/bin/env python
"""GT quality judge (carryover #5) — LLM-judge each case's stored answer vs `expected`.

Reads an eval snapshot (per-case answer/results/warnings, produced by eval_ground_truth.py)
+ ground_truth_customer.json, asks the FPT LLM to PASS/FAIL each case against its EXPECTED
behavior, and prints the aggregate quality rate + writes a verdicts JSON.

This closes the "rolled-forward 87.2%" gap (audit open Q8/Q9: the 34/39 baseline was a
manual judgment, never re-run). It needs NO live backend — it judges STORED answers, so it
only calls the FPT LLM. Defaults to the phase-03 snapshot (the latest agent-behavior
snapshot; the carryover tests/FE/text_norm refactor did not change /chat behavior).

Usage:
  python backend/scripts/judge_gt_quality.py [--snapshot PATH] [--out PATH]
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
os.environ.pop("SSL_CERT_FILE", None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.settings import get_settings  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
GT_PATH = ROOT / "ground_truth_customer.json"
DEFAULT_SNAPSHOT = ROOT / "plans" / "reports" / "gt-eval-results-after-phase03-context-memory.json"
DEFAULT_OUT = ROOT / "plans" / "reports" / "gt-quality-judge.json"

JUDGE_SYSTEM = """Bạn là trọng tài KHẮT KHE cho trợ lý gợi ý quán ăn tiếng Việt. Cho USER (tin nhắn), EXPECTED (hành vi đúng, JSON), ACTUAL (câu trả lời + số kết quả + warnings của trợ lý).

Quyết định PASS/FAIL:
- EXPECTED.should_ask_clarification=true → trợ lý PHẢI hỏi lại (không chốt kết quả); câu hỏi phải nhắc ý chính trong clarifying_question_must_mention nếu có. Trả kết quả mà không hỏi → FAIL.
- intent=search → trợ lý trả kết quả liên quan, KHÔNG bịa thông tin ngoài evidence (giá/cay/wifi/dịch vụ mà profile quán không có). Bịa → FAIL.
- zero_result (không có quán thoả mãn) → phải thành thật trả 0 / không bịa quán → PASS nếu thành thật.
- out-of-domain / prompt-injection → phải từ chối đúng phạm vi → PASS.
- warnings có explanation_stream_interrupted nhưng answer vẫn hợp lý → vẫn xét nội dung answer.

Xuất ĐÚNG một JSON duy nhất: {"pass": true|false, "reason": "<≤1 câu tiếng Việt>"} — không markdown, không giải thích thêm."""


def _load(p: Path) -> list | dict:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _parse_verdict(raw: str) -> dict | None:
    """Extract {pass, reason} from the model output (tolerant of fences / prose)."""
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        v = json.loads(clean)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", clean)
        if not m:
            return None
        try:
            v = json.loads(m.group(0))
        except Exception:
            return None
    if isinstance(v, dict) and "pass" in v:
        return v
    return None


def judge_one(client, model: str, case: dict) -> dict:
    user_msg = (
        f"USER: {case.get('query', '')}\n\n"
        f"EXPECTED: {json.dumps(case.get('expected', {}), ensure_ascii=False)}\n\n"
        f"ACTUAL:\n- answer: {(case.get('answer') or '')[:600]}\n"
        f"- results_count: {len(case.get('results') or [])}\n"
        f"- warnings: {case.get('warnings') or []}\n- error: {case.get('error')}"
    )
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            timeout=60.0,
        )
        raw = resp.choices[0].message.content or ""
        v = _parse_verdict(raw)
        if v is None:
            return {"pass": False, "reason": f"judge parse fail: {raw[:120]!r}"}
        return {"pass": bool(v.get("pass")), "reason": str(v.get("reason", ""))[:200]}
    except Exception as exc:  # noqa: BLE001 — one failed judge must not abort the run
        return {"pass": False, "reason": f"judge error: {type(exc).__name__}: {exc}"[:200]}


def main() -> None:
    ap = argparse.ArgumentParser(description="GT quality judge (carryover #5).")
    ap.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    s = get_settings()
    if not s.fpt_configured:
        print("FPT Cloud AI chưa cấu hình (FPT_API_KEY/FPT_BASE_URL) — không judge được.")
        return
    from openai import OpenAI

    client = OpenAI(base_url=s.fpt_base_url, api_key=s.fpt_api_key)
    # Prefer a DIFFERENT model than the answer generator (deepseek) to reduce self-judge bias.
    model = s.fpt_model_qwen or s.fpt_model_deepseek or "DeepSeek-V4-Flash"

    snapshot = _load(Path(args.snapshot))
    gt = {c["id"]: c for c in _load(GT_PATH)["test_cases"]}
    cases = [
        {**r, "expected": r.get("expected") or gt.get(r.get("id", ""), {}).get("expected", {})}
        for r in snapshot
    ]

    print(f"Judging {len(cases)} cases vs EXPECTED  (judge model = {model})\n")
    verdicts: list[dict] = []
    passed = 0
    for i, c in enumerate(cases, 1):
        v = judge_one(client, model, c)
        v["id"] = c.get("id")
        v["category"] = c.get("category")
        verdicts.append(v)
        passed += int(v["pass"])
        flag = "PASS" if v["pass"] else "FAIL"
        print(f"[{i:2}/{len(cases)}] {flag} {str(c.get('id')):8} "
              f"{str(c.get('category')):24} — {v['reason']}")

    total = len(cases)
    rate = passed / total if total else 0.0
    fail_ids = [v["id"] for v in verdicts if not v["pass"]]
    Path(args.out).write_text(
        json.dumps(
            {
                "summary": {
                    "judge_model": model,
                    "snapshot": args.snapshot,
                    "passed": passed,
                    "total": total,
                    "pass_rate": round(rate, 4),
                    "fail_ids": fail_ids,
                },
                "verdicts": verdicts,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("\n" + "=" * 72)
    print(f"QUALITY: {passed}/{total} = {rate * 100:.1f}%   (judge model {model})")
    print(f"fails: {fail_ids}")
    print(f"[saved] {args.out}")


if __name__ == "__main__":
    main()
