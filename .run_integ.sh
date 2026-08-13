#!/usr/bin/env bash
# Integration tests (non-destructive — skips the global purge_now(1) test to protect
# the dev DB's ~3200 eval rows). conda env python direct.
PY="/c/Users/Laptop/miniconda3/envs/ai_restaurant/python.exe"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
cd "$(dirname "$0")"
PYTHONPATH=backend "$PY" -m pytest backend/tests/integration/test_customer_memory_wireup.py \
  -k "not test_purge_deletes_stale_rows" -q -p no:warnings 2>&1 | tail -25
