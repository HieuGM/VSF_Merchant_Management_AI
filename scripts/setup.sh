#!/usr/bin/env bash
# =============================================================================
# VSF Merchant Management AI — one-command setup on a fresh machine.
# Run from repo root:  bash scripts/setup.sh
#
# Prereqs (install first): Docker Desktop, Miniconda, Node.js 20+, Git.
# Manual copy BEFORE running (the ONLY file not in git):  .env
#
# DB strategy:
#   - If merchant_platform_full.dump is present (committed to git) → restore the
#     FULL database (schema + 1625 merchants + chat/user_profiles/memory state).
#   - Otherwise → alembic creates schema + dataset import (merchants only, no
#     chat state). Used when no dump is available or a clean DB is wanted.
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."          # repo root
REPO="$(pwd)"

# --- activate conda (portable: resolves miniconda path via conda info --base) ---
if ! command -v conda >/dev/null 2>&1; then
  echo "❌ conda not on PATH. Open Anaconda Prompt / run 'conda init bash' first."; exit 1
fi
# shellcheck disable=SC1091
source "$(conda info --base)/etc/profile.d/conda.sh"

# Run an alembic upgrade inside backend/ without changing the script's CWD.
run_alembic_upgrade() { ( cd backend && PYTHONPATH=. alembic upgrade head ); }

echo "=== [1/6] Python env: ai_restaurant (from environment.yml) ==="
conda env create -f environment.yml -y 2>/dev/null || conda env update -f environment.yml -y
conda activate ai_restaurant
python --version

echo "=== [2/6] Postgres 18 (docker compose up -d) ==="
docker compose up -d
echo "waiting for postgres..."
for _ in $(seq 1 30); do
  docker exec gsm_merchant_postgres pg_isready -U postgres >/dev/null 2>&1 && break
  sleep 1
done
docker exec gsm_merchant_postgres pg_isready -U postgres

echo "=== [3/6] .env check (ONLY manual file — has FPT keys + DB creds) ==="
test -f .env || { echo "❌ missing .env — copy it from the old machine (gitignored, not in git)."; exit 1; }

if [ -f merchant_platform_full.dump ]; then
  echo "=== [4/6] Restore FULL DB from merchant_platform_full.dump ==="
  echo "  (schema + 1625 merchants + user_profiles + chat_sessions/messages + memory)"
  # --clean --if-exists: drop & recreate in correct FK order (safe on fresh or reused DB).
  # --no-owner: avoid cross-machine role mismatch. pg_restore exits 1 on benign warnings,
  # so we don't let set -e abort here — we verify row counts below instead.
  docker exec -i gsm_merchant_postgres pg_restore \
    -U postgres -d merchant_platform --clean --if-exists --no-owner \
    < merchant_platform_full.dump || echo "  (pg_restore reported non-zero — verifying below)"
  # Catch up schema if dump predates current migrations (no-op when already at head).
  run_alembic_upgrade
  m=$(docker exec gsm_merchant_postgres psql -U postgres -d merchant_platform -t -A -c "SELECT count(*) FROM merchants;")
  m=$(echo "$m" | tr -d '[:space:]')
  echo "  merchants in DB: $m"
  [ "${m:-0}" -gt 0 ] || { echo "❌ restore failed (0 merchants) — check dump/pg_restore output above."; exit 1; }
  echo "✓ DB restored with runtime state"
else
  echo "=== [4/6] No dump → fresh schema (alembic) + dataset import (merchants only) ==="
  run_alembic_upgrade
  test -f data/profiles.jsonl       || { echo "❌ missing data/profiles.jsonl"; exit 1; }
  test -f data/merchants_unique.jsonl || { echo "❌ missing data/merchants_unique.jsonl"; exit 1; }
  PYTHONUTF8=1 PYTHONPATH=backend python scripts/db/import_dataset.py
  echo "⚠ no merchant_platform_full.dump → DB has merchants but NO chat/user_profiles state."
fi

echo "=== [5/6] Frontend deps (npm install) ==="
cd frontend && npm install && cd "$REPO"

echo ""
echo "=== [6/6] ✅ Setup done. Start servers: ==="
echo "  backend :  conda activate ai_restaurant && bash .start_backend.sh"
echo "             (equiv: cd backend && PYTHONUTF8=1 PYTHONPATH=. python -m uvicorn app.main:app --port 8000)"
echo "  frontend:  cd frontend && npm run dev     → http://localhost:5173"
echo "  health   :  curl localhost:8000/health"
echo "  tests    :  bash .run_all.sh              # unit + integration"
