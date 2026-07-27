#!/usr/bin/env python
"""Quality eval — chạy nhiều query (ground_truth subset) với prompt mới, detect hallucination.

Mỗi case: chạy CustomerFlow.search_restaurants, in count + answer snippet + flag hallucination
(name=="string" hoặc expect_empty mà count>0). Dùng để đo chất lượng sau khi rewrite prompt.

Cách chạy:
    conda run -n ai_restaurant python backend/scripts/test_customer_quality.py
"""
from __future__ import annotations

import io
import os
import sys
import time
import traceback
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
os.environ.pop("SSL_CERT_FILE", None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# (label, query, lat, lng, radius, expect_empty, session_tag)
CASES = [
    ("TC-15 zero-result (sushi Mộc Châu)",
     "Tìm quán sushi Nhật Bản chính gốc ở Mộc Châu", None, None, None, True, "q15"),
    ("TC-01 happy (cơm Cầu Giấy <50k >4sao)",
     "Tìm quán cơm gần Cầu Giấy, giá dưới 50k, rating trên 4 sao", None, None, None, False, "q01"),
    ("TC-14 constraint (rating==5.0 tuyệt đối)",
     "Chỉ lấy quán đúng 5.0 sao, không lấy quán nào dưới 5.0", None, None, None, True, "q14"),
    ("TC-23 noisy (Tây Hồ 100k, code-switch)",
     "yo tìm giúp mình cái spot ăn uống nào chill chill ở khu Tây Hồ á, budget tầm 100k thôi nha",
     None, None, None, False, "q23"),
    ("TC-03 missing-slot (ăn ngon, ko location)",
     "Tìm chỗ ăn ngon", None, None, None, None, "q03"),
    ("TONE bâng quơ (chán, ko biết ăn gì, ko location)",
     "hôm nay chán quá, tớ chưa biết ăn gì luôn", None, None, None, None, "qtone"),
]


def _has_string_marker(results: list[dict]) -> bool:
    """True nếu có candidate có name/id chứa 'string' (placeholder hallucination)."""
    for r in results:
        for k in ("name", "merchant_id", "cuisine", "address"):
            v = str(r.get(k) or "").lower()
            if v == "string" or "string" in v:
                return True
    return False


def main() -> None:
    from flows.customer_flow import customer_flow

    print("=" * 78)
    print("CUSTOMER AGENT — QUALITY EVAL (prompt mới, anti-hallucination)")
    print("=" * 78)
    summary = []
    for label, query, lat, lng, radius, expect_empty, tag in CASES:
        session_id = f"qual_{tag}"
        print(f"\n--- {label} ---")
        print(f"query: {query}")
        t0 = time.time()
        try:
            kwargs = dict(query=query, user_id="user_demo", session_id=session_id)
            if lat is not None:
                kwargs["lat"] = lat
            if lng is not None:
                kwargs["lng"] = lng
            if radius is not None:
                kwargs["radius_km"] = radius
            resp = customer_flow.search_restaurants(**kwargs)
            dt = time.time() - t0
            count = len(resp.results)
            string_flag = _has_string_marker(resp.results)
            ans = (resp.answer or "").replace("\n", " ")[:240]
            sugg = len(resp.preference_suggestions or [])

            # Hallucination heuristic
            hallu = ""
            if string_flag:
                hallu = " ⚠️NAME='string'"
            if expect_empty is True and count > 0:
                hallu += " ⚠️EXPECTED-EMPTY-BUT-GOT-RESULTS(bịa?)"
            if expect_empty is False and count == 0:
                hallu += " ⚠️EXPECTED-RESULTS-BUT-EMPTY"

            print(f"  → {dt:.1f}s | trace={resp.trace_id} | results={count} | pref_sugg={sugg}{hallu}")
            print(f"  answer: {ans}")
            if count:
                sample = resp.results[0]
                print(f"  top: {sample.get('name')} | {sample.get('cuisine')} | "
                      f"rating={sample.get('avg_rating')} | match={sample.get('match_score')}")
            summary.append((tag, count, string_flag, expect_empty, hallu or "ok"))
        except Exception as exc:  # noqa: BLE001
            dt = time.time() - t0
            print(f"  ✗ ERROR after {dt:.1f}s: {type(exc).__name__}: {exc}")
            traceback.print_exc()
            summary.append((tag, -1, False, expect_empty, f"ERROR:{type(exc).__name__}"))

    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    for tag, count, string_flag, expect_empty, status in summary:
        print(f"  {tag}: count={count} string={string_flag} expect_empty={expect_empty} → {status}")


if __name__ == "__main__":
    main()
