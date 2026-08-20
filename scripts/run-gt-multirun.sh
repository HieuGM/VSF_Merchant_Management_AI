#!/usr/bin/env bash
# GT-eval multirun driver — 3 eval runs x 2 judges (qwen + deepseek), then aggregate.
# Purpose: damp single-run noise (LLM answer-gen variance + judge variance) into a stable
# per-case pass-frequency band (see scripts/aggregate-multirun-judgments.py).
#
# Requires: backend on :8000 (default flags), Postgres up, FPT key in backend/.env.
# Usage:    bash scripts/run-gt-multirun.sh          (from repo root)
set -u
PY="C:/Users/Laptop/miniconda3/envs/ai_restaurant/python.exe"
export PYTHONUTF8=1
export PYTHONPATH=backend
cd "$(dirname "$0")/.." || exit 1

for r in 1 2 3; do
  echo "=== RUN $r EVAL $(date '+%H:%M:%S') ==="
  "$PY" backend/scripts/eval_ground_truth.py \
      --out "plans/reports/gt-eval-results-multirun-$r.json" \
      || echo "!! run $r eval FAILED (continuing)"

  echo "=== RUN $r JUDGE qwen $(date '+%H:%M:%S') ==="
  "$PY" backend/scripts/judge_gt_quality.py \
      --snapshot "plans/reports/gt-eval-results-multirun-$r.json" \
      --out "plans/reports/gt-quality-judge-multirun-$r-qwen.json" \
      || echo "!! run $r qwen judge FAILED"

  echo "=== RUN $r JUDGE deepseek $(date '+%H:%M:%S') ==="
  "$PY" backend/scripts/judge_gt_quality.py \
      --snapshot "plans/reports/gt-eval-results-multirun-$r.json" \
      --out "plans/reports/gt-quality-judge-multirun-$r-deepseek.json" \
      --model DeepSeek-V4-Flash \
      || echo "!! run $r deepseek judge FAILED"
done

echo "=== AGGREGATE $(date '+%H:%M:%S') ==="
"$PY" scripts/aggregate-multirun-judgments.py
echo "=== MULTIRUN DONE $(date '+%H:%M:%S') ==="
