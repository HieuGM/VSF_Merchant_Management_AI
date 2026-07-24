"""Chạy Customer Discovery Crew trực tiếp trong terminal — xem giao diện verbose kiểu CrewAI.

Khác với server HTTP (nuốt console output), script này gọi thẳng crew.kickoff nên bạn thấy
đầy đủ các khung box: manager delegate, agent suy nghĩ, tool chạy + kết quả, task finished.

Cách chạy (Git Bash):
    cd backend
    source activate ai_restaurant
    PYTHONPATH=. python scripts/run_customer_chat.py "Tìm quán ăn Nhật gần đây"

Tuỳ chọn:
    --lat 10.7769 --lng 106.7009   # thêm toạ độ để bật geo + weather reasoning
    --user user_demo --session session_demo

Yêu cầu: Postgres đang chạy (docker compose up -d) + seed data + LLM key trong .env.
Script tự ép UTF-8 nên KHÔNG cần set PYTHONUTF8 thủ công.
"""
from __future__ import annotations

import argparse
import io
import os
import sys
import time
from pathlib import Path

# --- Bắt buộc trên Windows: ép stdout/stderr UTF-8 TRƯỚC khi import CrewAI, nếu không
#     log verbose tiếng Việt + emoji sẽ làm crash crew (charmap/UnicodeEncodeError). ---
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
# SSL_CERT_FILE sai đường dẫn làm httpx import fail trên vài máy Windows.
os.environ.pop("SSL_CERT_FILE", None)

# Cho phép chạy từ cả thư mục gốc lẫn backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    parser = argparse.ArgumentParser(description="Chạy Customer Discovery Crew (verbose UI).")
    parser.add_argument("query", help="Câu hỏi/tìm kiếm, vd: 'Tìm quán phở gần đây'")
    parser.add_argument("--lat", type=float, default=None, help="Vĩ độ (bật geo + weather)")
    parser.add_argument("--lng", type=float, default=None, help="Kinh độ")
    parser.add_argument("--radius", type=float, default=None, help="Bán kính km")
    parser.add_argument("--user", default="user_demo", help="user_id (mặc định user_demo)")
    parser.add_argument("--session", default="session_demo", help="session_id")
    args = parser.parse_args()

    from flows.customer_flow import customer_flow

    print("=" * 70)
    print(f"QUERY: {args.query}")
    print("=" * 70)

    t0 = time.time()
    resp = customer_flow.search_restaurants(
        query=args.query,
        lat=args.lat,
        lng=args.lng,
        radius_km=args.radius,
        user_id=args.user,
        session_id=args.session,
    )
    dt = time.time() - t0

    print("\n" + "=" * 70)
    print(f"[DONE] {dt:.1f}s | trace_id={resp.trace_id} | {len(resp.results)} quán")
    print("=" * 70)
    print(f"ANSWER:\n{resp.answer}\n")
    for r in resp.results:
        print(f"  - {r.get('name')} | {r.get('cuisine')} | rating={r.get('avg_rating')}")
    if resp.preference_suggestions:
        print(f"\nĐỀ XUẤT SỞ THÍCH: {len(resp.preference_suggestions)}")


if __name__ == "__main__":
    main()
