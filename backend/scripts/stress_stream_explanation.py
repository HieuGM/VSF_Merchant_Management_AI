"""Stress-test _stream_explanation_tokens directly — isolates the FPT DeepSeek stream
path from the ~10s search/preference overhead.

Calls the function N times with fixed messages and reports the success vs failure
(exception) rate + timing. The retry + non-streaming fallback should recover the
~10-30% of FPT stream drops, so the post-fix failure rate is ~0 (pre-fix, every drop
raised and lost the answer).

Usage (env ai_restaurant):
  PYTHONUTF8=1 PYTHONPATH=backend python backend/scripts/stress_stream_explanation.py
"""
from __future__ import annotations

import io
import sys
import time

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from flows.customer_flow import _stream_explanation_tokens

# Minimal grounded messages — exercises the real FPT streaming endpoint (DeepSeek-V4-Flash).
MESSAGES = [
    {"role": "system", "content": "Bạn là trợ lý gợi ý quán ăn thân thiện. Trả lời ngắn 2-3 câu."},
    {"role": "user", "content": "Gợi ý mình món phở nóng ngon cho buổi trưa ở Cầu Giấy."},
]

N = 25


def main() -> None:
    print("=" * 70)
    print(f"STRESS _stream_explanation_tokens x{N} (isolated FPT DeepSeek stream)")
    print("=" * 70)
    ok = fail = 0
    times: list[float] = []
    errors: dict[str, int] = {}
    samples: list[str] = []
    for i in range(1, N + 1):
        t0 = time.perf_counter()
        try:
            text = "".join(_stream_explanation_tokens(MESSAGES))
            dt = time.perf_counter() - t0
            times.append(dt)
            if text.strip():
                ok += 1
                tag = "ok"
                if len(samples) < 3:
                    samples.append(text[:90])
            else:
                fail += 1
                tag = "EMPTY"
        except Exception as exc:  # noqa: BLE001 - record the failure type
            dt = time.perf_counter() - t0
            times.append(dt)
            fail += 1
            key = type(exc).__name__
            errors[key] = errors.get(key, 0) + 1
            tag = f"RAISE:{key}"
        print(f"  [{i:2d}/{N}] {dt:5.2f}s  {tag}")

    print("\n" + "=" * 70)
    print(f"SUCCESS: {ok}/{N}    FAIL: {fail}/{N}")
    if errors:
        print(f"failure types: {errors}")
    if times:
        times.sort()
        med = times[len(times) // 2]
        print(f"timing: min={times[0]:.2f}s  median={med:.2f}s  max={times[-1]:.2f}s")
    if samples:
        print("\nsample answers:")
        for s in samples:
            print(f"  - {s}")
    print("\nVerdict: FAIL ~0 => retry + non-stream fallback recovers FPT stream drops.")


if __name__ == "__main__":
    main()
