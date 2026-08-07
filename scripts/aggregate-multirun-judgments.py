#!/usr/bin/env python
"""Aggregate multi-run GT eval judgments into a stable per-case pass-frequency.

Damps the two noise sources from a single run: (a) LLM answer-gen variance (3 eval runs),
(b) judge variance (qwen + deepseek). For each case: count passes across 6 verdicts
(3 runs x 2 judges). Bucket:
  - stable-pass: >=5/6  (solidly good)
  - borderline : 2-4/6  (judge/variance noise — real quality unclear)
  - stable-fail: <=1/6  (real fail)

Reads: gt-quality-judge-multirun-{1,2,3}-{qwen,deepseek}.json
Prints aggregate + per-case table; writes plans/reports/gt-multirun-aggregate.json.

Usage: python scripts/aggregate_multirun_judgments.py
"""
from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "plans" / "reports"


def _load(p: Path) -> dict | None:
    if not p.exists():
        return None
    return {v["id"]: v["pass"] for v in json.loads(p.read_text(encoding="utf-8"))["verdicts"]}


def main() -> None:
    runs = [1, 2, 3]
    judges = ["qwen", "deepseek"]
    # verdicts[run][judge] = {id: bool}
    verdicts: dict[int, dict[str, dict[str, bool]]] = {}
    for r in runs:
        verdicts[r] = {}
        for j in judges:
            v = _load(REPORTS / f"gt-quality-judge-multirun-{r}-{j}.json")
            if v is not None:
                verdicts[r][j] = v
            else:
                print(f"[warn] missing: gt-quality-judge-multirun-{r}-{j}.json")

    # Union of case ids across all available verdict sets.
    ids = sorted({i for r in verdicts.values() for j in r.values() for i in j})
    if not ids:
        print("No verdict files found. Judge the multirun snapshots first.")
        return

    # per-case pass count + total verdicts available
    rows = []
    for cid in ids:
        passes = 0
        total = 0
        per = []
        for r in runs:
            for j in judges:
                v = verdicts.get(r, {}).get(j)
                if v is not None and cid in v:
                    total += 1
                    if v[cid]:
                        passes += 1
                    per.append(f"{r}{j[0]}={'P' if v[cid] else 'F'}")
        rows.append((cid, passes, total, per))

    # buckets
    stable_pass = [c for c, p, t, _ in rows if t and p / t >= 5 / 6]
    borderline = [c for c, p, t, _ in rows if t and 2 / 6 <= p / t <= 4 / 6]
    stable_fail = [c for c, p, t, _ in rows if t and p / t <= 1 / 6]

    # per-run aggregate rates
    print("=" * 72)
    print("PER-RUN RATES (pass/total judged)")
    for r in runs:
        for j in judges:
            v = verdicts.get(r, {}).get(j)
            if v:
                ids_r = sorted(v)
                # exclude TC-41 if it errored that run (no real answer) — detect via snapshot error
                snap = REPORTS / f"gt-eval-results-multirun-{r}.json"
                errored = set()
                if snap.exists():
                    for x in json.loads(snap.read_text(encoding="utf-8")):
                        if x.get("error"):
                            errored.add(x["id"])
                judged = [i for i in ids_r if i not in errored]
                passed = sum(1 for i in judged if v[i])
                print(f"  run{r} {j:9}: {passed}/{len(judged)} = {passed/len(judged)*100:.1f}%"
                      f"{'  (TC-41 errored, excluded)' if errored else ''}")

    print()
    print("PER-CASE PASS-FREQUENCY (over 6 verdicts: 3 runs x 2 judges)")
    print(f"{'ID':7} {'pass/tot':9} {'rate':6} verdicts(runN+judge-initial)")
    for cid, p, t, per in sorted(rows, key=lambda x: (x[1] / x[2] if x[2] else 0, x[0])):
        rate = p / t if t else 0
        bucket = "PASS" if rate >= 5 / 6 else ("FAIL" if rate <= 1 / 6 else "~~~~")
        print(f"{cid:7} {p}/{t:<7} {rate*100:5.0f}% {bucket}  {' '.join(per)}")

    print()
    print("=" * 72)
    print(f"STABLE-PASS (>=5/6): {len(stable_pass)}  {stable_pass}")
    print(f"BORDERLINE  (2-4/6): {len(borderline)}   {borderline}")
    print(f"STABLE-FAIL (<=1/6): {len(stable_fail)}  {stable_fail}")
    n = len(ids)
    # Conservative true-quality estimate: stable_pass + half of borderline (midpoint)
    est_lo = len(stable_pass)
    est_hi = len(stable_pass) + len(borderline)
    print()
    print(f"True-quality band: {est_lo}-{est_hi}/{n} = {est_lo/n*100:.0f}-{est_hi/n*100:.0f}%")
    print(f"  (stable-pass floor .. + all borderline ceiling)")

    out = REPORTS / "gt-multirun-aggregate.json"
    out.write_text(json.dumps({
        "stable_pass": stable_pass,
        "borderline": borderline,
        "stable_fail": stable_fail,
        "per_case": [{"id": c, "passes": p, "total": t, "verdicts": per} for c, p, t, per in rows],
        "band": {"lo": est_lo, "hi": est_hi, "n": n},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[saved] {out}")


if __name__ == "__main__":
    main()
