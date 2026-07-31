#!/usr/bin/env python3
"""Interactive Multi-Turn CLI Tool for Testing Spec-Compliant Merchant Advisor Agent (Design §11.5).

Usage:
    /home/minhnv/miniconda3/envs/ocr/bin/python scripts/merchant_advisor_cli.py
"""
from __future__ import annotations

import argparse
import logging
import sys
import os
import uuid
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parents[1] / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from dotenv import find_dotenv, load_dotenv
load_dotenv(find_dotenv(usecwd=True), override=False)

from database.connection import SessionLocal
from core.logging import configure_logging, get_logger
from services.merchant_profile_service import MerchantProfileService
from services.agent_run_service import AgentRunService
from services.chat_session_service import ChatSessionService
from flows.merchant_flow import merchant_flow

trace_logger = get_logger("merchant.trace")


def print_banner():
    print("\n" + "=" * 65)
    print("   MERCHANT ADVISOR AGENTIC CHATBOT — MULTI-TURN TESTING CLI   ")
    print("=" * 65)


def menu(session_id: str):
    print(f"\n[CHỌN CHỨC NĂNG TEST] (Session ID: '{session_id}'):")
    print("  1. Trò chuyện Trực tiếp với Advisor Agent (Multi-Turn Chat)")
    print("  2. Xem Lịch sử Phiên Đối thoại (Chat Session History)")
    print("  3. Xem Hồ sơ 8 Chiều của Merchant (Security C2 Check)")
    print("  4. Kiểm tra Chi tiết Tracing Log theo trace_id")
    print("  q. Thoát CLI")
    print("-" * 65)


def handle_chat(
    merchant_id: str,
    session_id: str,
    *,
    trace_full: bool = False,
):
    db = SessionLocal()
    try:
        query = input(f"\n💬 Enter your prompt for Merchant '{merchant_id}': ").strip()
        if not query:
            return

        print("\n⏳ Native CrewAI Agent đang suy luận và phân tích...")

        res = merchant_flow.chat(
            merchant_id=merchant_id,
            message=query,
            session_id=session_id,
            db=db
        )

        print(f"\n🤖 ADVISOR AGENT REPLY (Trace ID: {res['trace_id']}):")
        print(f"{res['reply']}")

        if "token_usage" in res:
            tokens = res["token_usage"]
            print(f"\n📊 Token Usage: {tokens.get('total_tokens', 0)} total ({tokens.get('prompt_tokens', 0)} prompt, {tokens.get('completion_tokens', 0)} completion)")
    except Exception as e:
        print(f"\n❌ Lỗi: {e}")
    finally:
        db.close()


def handle_view_history(session_id: str):
    db = SessionLocal()
    try:
        session_svc = ChatSessionService(db)
        history = session_svc.get_recent_history(session_id=session_id, limit=20)
        print(f"\n📜 LỊCH SỬ PHIÊN ĐỐI THOẠI ({session_id}):")
        if not history:
            print("   (Phiên hội thoại chưa có tin nhắn nào)")
        else:
            for msg in history:
                icon = "👤" if msg["sender"] == "user" else "🤖"
                print(f"   {icon} [{msg['sender'].upper()}] ({msg['timestamp']}): {msg['text']}")
    except Exception as e:
        print(f"\n❌ Lỗi: {e}")
    finally:
        db.close()


def handle_view_profile(merchant_id: str):
    db = SessionLocal()
    try:
        svc = MerchantProfileService(db)
        profile = svc.get_profile_view(merchant_id)
        print(f"\n✅ HỒ SƠ 8 CHIỀU MERCHANT '{merchant_id}':")
        print(f"   Tier: {profile.get('tier', 'standard')}")
        print("   Dimensions (Overall Score stripped per C2):")
        for dim, details in profile.get("dimensions", {}).items():
            if isinstance(details, dict):
                score = details.get("score", "N/A")
                basis = details.get("basis", "")
                refs = details.get("evidence_refs", [])
                print(f"     - {dim:18s}: {score}/10 | {basis} | Refs: {refs}")
    except Exception as e:
        print(f"\n❌ Lỗi: {e}")
    finally:
        db.close()


def handle_view_trace():
    trace_id = input("\n🔎 Nhập trace_id cần kiểm tra: ").strip()
    if not trace_id:
        return

    db = SessionLocal()
    try:
        svc = AgentRunService(db)
        trace_data = svc.get_run_trace(trace_id)
        print(f"\n✅ TRACE LOG DETAILS ({trace_id}):")
        print(f"   Crew       : {trace_data['crew_name']}")
        print(f"   Intent     : {trace_data['intent']}")
        print(f"   Status     : {trace_data['status']}")
        print(f"   Started At : {trace_data['started_at']}")
        print(f"   Finished At: {trace_data['finished_at']}")
        print(f"   Events Count: {len(trace_data['events'])}")

        for i, evt in enumerate(trace_data["events"], 1):
            print(f"     [{i}] Type: {evt['event_type']} | Agent: {evt['agent_name']} | Status: {evt['status']} | Duration: {evt['duration_ms']}ms")
    except Exception as e:
        print(f"\n❌ Lỗi: {e}")
    finally:
        db.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Interactive Merchant Advisor debugging CLI.",
    )
    parser.add_argument(
        "--trace-full",
        action="store_true",
        help="Log complete sanitized event payloads instead of compact traces.",
    )
    return parser.parse_args()


def main():
    args = _parse_args()
    configure_logging(logging.INFO)
    print_banner()
    default_merchant = "94"
    session_id = f"sess_{uuid.uuid4().hex[:8]}"

    print(f"💡 Ví dụ Merchant ID trong DB: '94', '585', '791', '1060'")
    merchant_id = input(f"Nhập Merchant ID để test [Mặc định '{default_merchant}']: ").strip() or default_merchant

    while True:
        menu(session_id)
        choice = input(f"Lựa chọn của bạn (Merchant: '{merchant_id}'): ").strip().lower()

        if choice == "1":
            handle_chat(
                merchant_id,
                session_id,
                trace_full=args.trace_full,
            )
        elif choice == "2":
            handle_view_history(session_id)
        elif choice == "3":
            handle_view_profile(merchant_id)
        elif choice == "4":
            handle_view_trace()
        elif choice == "q":
            print("\n👋 Đã thoát Merchant Advisor Testing CLI. Cảm ơn bạn!\n")
            break
        else:
            print("⚠️ Lựa chọn không hợp lệ, vui lòng thử lại.")


if __name__ == "__main__":
    main()
