#!/usr/bin/env bash
# =============================================================================
# VSF Merchant Management AI — fast setup on a fresh machine.
# Run from repo root:  bash scripts/setup.sh
#
# Prereqs (install first): Docker, Miniconda, Node.js 20+, Git.
# Manual copy BEFORE running (gitignored): .env, data/profiles.jsonl,
#   data/merchants_unique.jsonl  — see docs/setup-guide.md.
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."          # repo root
REPO="$(pwd)"

# --- activate conda ---
if ! command -v conda >/dev/null 2>&1; then
  echo "❌ conda not on PATH. Open Anaconda Prompt / run 'conda init' first."; exit 1
fi
source "$(conda info --base)/etc/profile.d/conda.sh"

echo "=== [1/6] Python env: ai_restaurant (from environment.yml) ==="
conda env create -f environment.yml -y 2>/dev/null || conda env update -f environment.yml -y
conda activate ai_restaurant
python --version

echo "=== [2/6] Postgres (docker compose) ==="
docker compose up -d
echo "waiting for postgres..."
for i in $(seq 1 30); do
  docker exec gsm_merchant_postgres pg_isready -U postgres >/dev/null 2>&1 && break
  sleep 1
done
docker exec gsm_merchant_postgres pg_isready -U postgres

echo "=== [3/6] DB migrate (alembic upgrade head) ==="
cd backend && PYTHONPATH=. alembic upgrade head && cd "$REPO"

echo "=== [4/6] Import dataset (needs data/profiles.jsonl + .env) ==="
test -f data/profiles.jsonl       || { echo "❌ missing data/profiles.jsonl (copy from old machine)"; exit 1; }
test -f data/merchants_unique.jsonl || { echo "❌ missing data/merchants_unique.jsonl (copy from old machine)"; exit 1; }
test -f .env                       || { echo "❌ missing .env (copy from old machine, has LLM keys)"; exit 1; }
PYTHONUTF8=1 PYTHONPATH=backend python scripts/db/import_dataset.py

echo "=== [5/6] Frontend deps (npm install) ==="
cd frontend && npm install && cd "$REPO"

echo ""
echo "=== [6/6] ✅ Setup done. Start servers: ==="
echo "  backend :  conda activate ai_restaurant"
echo "             cd backend && PYTHONUTF8=1 PYTHONPATH=. python -m uvicorn app.main:app --port 8000"
echo "  frontend:  cd frontend && npm run dev     → http://localhost:5173"
echo "  health   :  curl localhost:8000/health"
