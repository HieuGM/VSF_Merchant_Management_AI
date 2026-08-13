#!/usr/bin/env bash
# =============================================================================
# Đóng gói project để chuyển sang máy KHÔNG có git.
# Loại thư mục nặng/regenerable (node_modules, venv, cache, .git).
# GIỮ: source + .env + data/ + environment.yml (đủ để setup.sh chạy).
#
# Chạy từ repo root:  bash scripts/pack-for-transfer.sh
# Kết quả: <parent>/AI_Restaurant-transfer.tar.gz  (copy qua USB / OneDrive / Drive)
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."          # repo root
REPO_NAME="$(basename "$(pwd)")"  # AI_Restaurant
cd ..

OUT="${REPO_NAME}-transfer.tar.gz"
echo "Packing ./${REPO_NAME} → ${OUT}  (loại node_modules, venv, cache, .git; giữ .env + data)"

tar --exclude="${REPO_NAME}/.git" \
    --exclude=node_modules \
    --exclude=.venv \
    --exclude=__pycache__ \
    --exclude='*.pyc' \
    --exclude=.pytest_cache \
    --exclude=dist \
    --exclude=.playwright-mcp \
    --exclude=.DS_Store \
    -czf "$OUT" "$REPO_NAME"

echo ""
echo "✓ Xong: $(pwd)/${OUT}"
echo "  Size: $(du -h "$OUT" | cut -f1)"
echo ""
echo "Trên máy công ty: giải nén rồi chạy 'bash scripts/setup.sh'."
echo "  tar -xzf ${OUT}   →  cd ${REPO_NAME}   →  bash scripts/setup.sh"
