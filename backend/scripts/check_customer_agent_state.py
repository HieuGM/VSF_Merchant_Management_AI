#!/usr/bin/env python
"""Diagnostic — báo cáo trạng thái prerequisites của Customer Agent (KHÔNG in key bí mật).

Kiểm tra: môi trường Python/CrewAI, LLM config (vendor + đã cấu hình chưa, KHÔNG in key),
kết nối Postgres, seed data (merchants / user_demo / merchant_profiles). Dùng để quyết định
có thể chạy luồng Customer Agent hoàn chỉnh hay không.

Cách chạy:
    conda run -n ai_restaurant python backend/scripts/check_customer_agent_state.py
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

# Windows: ép UTF-8 trước khi import CrewAI (log tiếng Việt/emoji không crash charmap).
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
# SSL_CERT_FILE sai đường dẫn làm httpx import fail trên vài máy Windows.
os.environ.pop("SSL_CERT_FILE", None)

# Auto-add backend/ vào sys.path để import core.settings, database.* chạy được từ bất đâu.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _section(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def check_python_env() -> None:
    _section("[1/5] PYTHON ENV")
    print(f"python : {sys.version.split()[0]} ({sys.executable})")
    try:
        import crewai

        print(f"crewai : {getattr(crewai, '__version__', '?')}")
    except Exception as exc:  # noqa: BLE001
        print(f"crewai : IMPORT FAIL -> {exc}")
    try:
        import sqlalchemy

        print(f"sqlalchemy: {sqlalchemy.__version__}")
    except Exception as exc:  # noqa: BLE001
        print(f"sqlalchemy: IMPORT FAIL -> {exc}")


def check_llm_config() -> dict:
    _section("[2/5] LLM CONFIG (không in key)")
    info: dict = {}
    try:
        from core.settings import get_settings

        s = get_settings()
        vendor = s.active_llm_vendor
        fpt_ok = bool(getattr(s, "fpt_configured", False))
        nim_ok = bool(getattr(s, "nvidia_nim_api_key", None))
        overall = bool(getattr(s, "llm_configured", False))
        info = {"vendor": vendor, "fpt": fpt_ok, "nim": nim_ok, "configured": overall}
        print(f"active_vendor : {vendor}")
        print(f"FPT (DeepSeek): {'[OK]' if fpt_ok else '[MISSING]'}")
        print(f"NVIDIA NIM    : {'[OK]' if nim_ok else '[MISSING]'}")
        print(f"llm_configured: {'[OK]' if overall else '[MISSING]'}")
        if overall:
            # In thêm model names (không nhạy cảm) để xác nhận tier đúng.
            try:
                print(f"fpt_model     : {getattr(s, 'fpt_model_deepseek', '?')}")
            except Exception:  # noqa: BLE001
                pass
            try:
                print(f"nim_model_large: {getattr(s, 'llm_model_large', '?')}")
                print(f"nim_model_small: {getattr(s, 'llm_model_small', '?')}")
            except Exception:  # noqa: BLE001
                pass
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] không load được settings -> {type(exc).__name__}: {exc}")
        import traceback

        traceback.print_exc()
    return info


def check_db() -> bool:
    _section("[3/5] POSTGRES CONNECTION")
    try:
        from database.connection import engine
        from sqlalchemy import text

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("[OK] database reachable")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] DB connection failed -> {type(exc).__name__}: {exc}")
        print("[TIP] docker compose up -d")
        return False


def check_seed_data() -> dict:
    _section("[4/5] SEED DATA")
    counts: dict = {}
    try:
        from database.connection import SessionLocal
        from database.models import Merchant, UserProfile, MerchantProfile

        db = SessionLocal()
        try:
            counts["merchants"] = db.query(Merchant).count()
            counts["merchant_profiles"] = db.query(MerchantProfile).count()
            counts["user_demo_exists"] = db.get(UserProfile, "user_demo") is not None
            for k, v in counts.items():
                print(f"{k:24}: {v}")
            if counts["merchants"] == 0:
                print("[TIP] python scripts/seed_merchants.py")
            if not counts["user_demo_exists"]:
                print("[TIP] python scripts/seed_user_demo.py")
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] không query được seed data -> {type(exc).__name__}: {exc}")
    return counts


def check_registry_tools() -> None:
    _section("[5/5] TOOL REGISTRY (allow-list bind cho crew)")
    try:
        from tools.registry import registry

        registry.auto_discover("tools.shared")
        registry.auto_discover("tools.customer")
        names = sorted(registry.names())
        print(f"registered tools ({len(names)}): {names}")
        for role in ("restaurant_search", "preference_reasoning", "customer_explanation"):
            tools = [t.spec.name for t in registry.tools_for_agent(role)]
            print(f"  {role:24}: {tools}")
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] registry -> {type(exc).__name__}: {exc}")


def main() -> None:
    print("CUSTOMER AGENT — STATE DIAGNOSTIC")
    check_python_env()
    llm = check_llm_config()
    db_ok = check_db()
    if db_ok:
        check_seed_data()
        check_registry_tools()
    _section("VERDICT")
    ready = bool(llm.get("configured")) and db_ok
    print(f"Ready chạy luồng REAL LLM: {'[YES]' if ready else '[NO]'}")
    if not llm.get("configured"):
        print("  - LLM chưa cấu hình (cần FPT_* hoặc NVIDIA_NIM_API_KEY trong .env)")
    if not db_ok:
        print("  - DB chưa kết nối được")
    print("Luôn có thể chạy FAKE LLM (mock crew) nếu DB OK.")


if __name__ == "__main__":
    main()
