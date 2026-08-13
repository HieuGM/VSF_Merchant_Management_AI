#!/usr/bin/env bash
# Integration tests (non-destructive — skips the global purge_now(1) test to protect
# the dev DB's ~3200 eval rows). Portable: conda activate ai_restaurant.
cd "$(dirname "$0")"
# shellcheck disable=SC1091
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate ai_restaurant
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
PYTHONPATH=backend python -m pytest backend/tests/integration/test_customer_memory_wireup.py \
  -k "not test_purge_deletes_stale_rows" -q -p no:warnings 2>&1 | tail -25
