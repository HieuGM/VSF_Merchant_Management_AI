#!/usr/bin/env bash
# Start the customer backend (memory-system code) on :8000.
# Portable: activates conda env `ai_restaurant` (no hardcoded miniconda path),
# so it works on any machine after `bash scripts/setup.sh`.
# PYTHONUTF8 avoids the CrewAI Windows cp1252 crash (memory: crewai-windows-utf8-crash).
cd "$(dirname "$0")"
# shellcheck disable=SC1091
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate ai_restaurant
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8 PYTHONPATH=backend
exec python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
