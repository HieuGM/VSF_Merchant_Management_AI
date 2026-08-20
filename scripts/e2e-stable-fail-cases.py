#!/usr/bin/env python
"""E2E the 5 stable-fail GT cases (TC-10/25/28/39/41) against the live /chat endpoint.

Waits for FPT latency to recover (<8s for a tiny completion) before running — the
provider has intermittent slow windows (27s+ observed 260820 ~15:00) that kill the
15s crew task timeout and false-fail everything.

Usage (from repo root, backend on :8000):
  PYTHONUTF8=1 python scripts/e2e-stable-fail-cases.py
"""
from __future__ import annotations

import io
import os
import sys
import time

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import requests

BASE = "http://localhost:8000/api/v1/agent/customer/chat"
STAMP = str(int(time.time()))

# (label, [turns...]) — the LAST turn is the one under test (replays its GT prior turn first).
CASES = [
    ("TC-41 ordinal 'Cái đầu tiên đó'",
     ["Tìm quán phở ngon ở Hà Nội", "Cái đầu tiên đó"]),
    ("TC-25 'Quán này có ổn không?'",
     ["Tìm quán cơm nhà làm ngon ở Cầu Giấy", "Quán này có ổn không?"]),
    ("TC-39 'quán này thế nào?'",
     ["Tìm quán lẩu hải sản ở Hà Đông", "Sao chỉ có đúng 1 quán vậy, quán này thế nào?"]),
    ("TC-10 'Rẻ hơn nữa được không'",
     ["Tìm quán cơm văn phòng gần Mỹ Đình dưới 40k", "Rẻ hơn nữa được không"]),
    ("TC-28 negation triple",
     ["Tìm quán ăn không cay, không phải đồ chiên, nhưng cũng đừng quá rẻ, ở Thanh Xuân"]),
]


def wait_for_fpt(max_wait_s: int = 600) -> bool:
    """Block until a tiny FPT completion answers in <8s (crew budget is 15s)."""
    from openai import OpenAI
    client = OpenAI(base_url=os.environ["FPT_BASE_URL"], api_key=os.environ["FPT_API_KEY"])
    t0 = time.time()
    while time.time() - t0 < max_wait_s:
        try:
            s = time.perf_counter()
            client.chat.completions.create(
                model="DeepSeek-V4-Flash",
                messages=[{"role": "user", "content": "ok"}], max_tokens=3, timeout=30)
            ms = (time.perf_counter() - s) * 1000
            if ms < 8000:
                print(f"[fpt-ready] {ms:.0f}ms")
                return True
            print(f"[fpt-slow ] {ms:.0f}ms — waiting...")
        except Exception as e:  # noqa: BLE001
            print(f"[fpt-err  ] {type(e).__name__} — waiting...")
        time.sleep(20)
    return False


def chat(uid: str, sid: str, msg: str, retries: int = 2) -> dict:
    for attempt in range(retries + 1):
        try:
            r = requests.post(BASE, json={"user_id": uid, "session_id": sid, "message": msg},
                              timeout=180)
            d = r.json()
            if r.status_code == 200 and (d.get("answer") or d.get("results")):
                return d
            raise RuntimeError(f"{r.status_code}: {str(d)[:100]}")
        except (RuntimeError, requests.RequestException) as e:
            if attempt == retries:
                return {"answer": f"[FAILED x{retries+1}: {e}]", "results": []}
            time.sleep(10)
    return {}


def main() -> None:
    # env from .env (probe script convention: shell sources it; fallback here reads it directly)
    if not os.environ.get("FPT_API_KEY"):
        for line in open(".env", encoding="utf-8"):
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
    if not wait_for_fpt():
        print("FPT never recovered — aborting")
        sys.exit(1)

    for label, turns in CASES:
        uid = f"e2e5_{STAMP}"
        sid = f"s5_{label.split()[0].lower().replace('-', '')}_{STAMP}"
        print(f"\n=== {label} ===")
        for i, m in enumerate(turns):
            d = chat(uid, sid, m)
            last = i == len(turns) - 1
            star = ">>" if last else "  "
            print(f"{star} [{m[:45]!r}] results={len(d.get('results') or [])}")
            if last:
                print(f"   ANS: {(d.get('answer') or '')[:300]}")
                for x in (d.get("results") or [])[:3]:
                    print(f"   - {str(x.get('name', '?'))[:60]}")


if __name__ == "__main__":
    main()
