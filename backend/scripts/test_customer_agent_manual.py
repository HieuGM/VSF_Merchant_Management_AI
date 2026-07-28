"""Manual test script for Customer Agent (test tay).

Cách chạy:
1. Start Postgres: docker compose up -d
2. Seed data: python scripts/seed_merchants.py && python scripts/seed_user_demo.py
3. Set NVIDIA NIM key (optional - nếu không có sẽ dùng fake LLM)
4. Chạy script: python scripts/test_customer_agent_manual.py
"""
from __future__ import annotations

import sys
import io
from pathlib import Path

# Fix UTF-8 encoding on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Fix SSL_CERT_FILE error on Windows (causes httpx import failure)
import os
if 'SSL_CERT_FILE' in os.environ:
    del os.environ['SSL_CERT_FILE']

# Add backend to path - works from both root and backend directory
script_path = Path(__file__).resolve()
backend_root = script_path.parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

# Check dependencies
try:
    import requests
except ImportError:
    print("[ERROR] Thiếu requests: pip install requests")
    sys.exit(1)

from core.settings import get_settings
from database.connection import SessionLocal, engine
from database.models import Merchant, UserProfile
from sqlalchemy import text


def check_db_connection() -> bool:
    """Check if Postgres is running."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("[OK] Database connected")
        return True
    except Exception as e:
        print(f"[ERROR] Database connection failed: {e}")
        print("[TIP] Hãy chạy: docker compose up -d")
        return False


def check_seed_data() -> bool:
    """Check if merchants and user_demo exist."""
    db = SessionLocal()
    try:
        merchant_count = db.query(Merchant).count()
        demo_user = db.get(UserProfile, "user_demo")

        print(f"[DATA] Merchants: {merchant_count} records")
        print(f"[DATA] Demo user: {'[OK]' if demo_user else '[MISSING]'}")

        if merchant_count == 0:
            print("[TIP] Hãy chạy: python scripts/seed_merchants.py")
        if not demo_user:
            print("[TIP] Hãy chạy: python scripts/seed_user_demo.py")

        return merchant_count > 0 and demo_user is not None
    finally:
        db.close()


def test_with_fake_llm():
    """Test CustomerFlow với fake LLM (không cần API key)."""
    print("\n" + "="*60)
    print("[TEST 1] FAKE LLM (Không cần API key)")
    print("="*60)

    from types import SimpleNamespace
    from flows.customer_flow import customer_flow
    from models.customer_tasks import MerchantCandidate, PreferenceTaskOutput, SearchTaskOutput

    # Mock crew trả về kết quả giả (explanation giờ là free-text .raw, không còn pydantic)
    class _MockCrew:
        def kickoff(self, inputs=None):
            print(f"[INPUT] {inputs}")
            return SimpleNamespace(
                raw="Kết quả giả lập",
                tasks_output=[
                    SimpleNamespace(pydantic=SearchTaskOutput(
                        candidates=[
                            MerchantCandidate(
                                merchant_id="m001",
                                name="Phở Le",
                                cuisine="Vietnamese",
                                address="123 Nguyễn Huệ, Quận 1",
                                distance_km=0.5,
                                avg_rating=4.5,
                                match_score=0.9,
                            )
                        ],
                        count=1,
                    )),
                    SimpleNamespace(pydantic=PreferenceTaskOutput(
                        suggestions=[], reasoning="không đủ tín hiệu",
                    )),
                    SimpleNamespace(raw="Tôi gợi ý Phở Le vì quán này gần vị trí của bạn (0.5km), "
                                         "phù hợp với sở thích món Việt và có đánh giá cao 4.5 sao."),
                ],
            )

    try:
        print("\n[CASE 1] Tìm phở gần đây")
        resp = customer_flow.search_restaurants(
            query="phở gần đây",
            user_id="user_demo",
            session_id="session_demo",
            crew=_MockCrew(),
        )

        print(f"[OK] Trace ID: {resp.trace_id}")
        print(f"[OK] Answer: {resp.answer}")
        print(f"[OK] Results: {len(resp.results)} quán")
        for r in resp.results:
            print(f"   - {r['name']} | {r['cuisine']} | {r['distance_km']}km | {r['avg_rating']} sao")

        return True
    except Exception as e:
        print(f"[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_with_real_llm():
    """Test CustomerFlow với real NVIDIA NIM LLM."""
    print("\n" + "="*60)
    print("[TEST 2] REAL LLM (Cần NVIDIA_NIM_API_KEY)")
    print("="*60)

    s = get_settings()
    if not s.llm_configured:
        print("[SKIP] Chưa cấu hình NVIDIA_NIM_API_KEY")
        print("[TIP] Set env var: export NVIDIA_NIM_API_KEY='your-key-here'")
        print("[TIP] Hoặc tạo file .env: NVIDIA_NIM_API_KEY=your-key-here")
        return False

    print(f"[OK] LLM configured: {s.llm_provider}")
    print(f"[OK] Model large: {s.llm_model_large}")
    print(f"[OK] Model small: {s.llm_model_small}")

    # Manager tools are now cleared in the crew definition itself (customer_coordinator
    # returns tools=[]), so no runtime patch is needed here.
    from flows.customer_flow import customer_flow

    test_cases = [
        {
            "name": "Tìm phở gần đây",
            "params": {
                "query": "Tìm quán phở gần đây cho tôi",
                "user_id": "user_demo",
                "session_id": "session_demo",
                "lat": 10.7769,
                "lng": 106.7009,
                "radius_km": 3,
            }
        },
        {
            "name": "Tìm món Nhật budget sinh viên",
            "params": {
                "query": "Tìm quán món Nhật phù hợp budget sinh viên",
                "cuisine": "Japanese",
                "budget": "cheap",
                "user_id": "user_demo",
                "session_id": "session_demo",
            }
        },
    ]

    for i, case in enumerate(test_cases, 1):
        print(f"\n[CASE {i}] {case['name']}")
        print(f"   Params: {case['params']}")

        try:
            resp = customer_flow.search_restaurants(**case["params"])

            print(f"[OK] Trace ID: {resp.trace_id}")
            print(f"[OK] Answer: {resp.answer}")
            print(f"[OK] Results: {len(resp.results)} quán")

            for r in resp.results:
                print(f"   - {r['name']}")
                print(f"     Cuisine: {r['cuisine']}")
                print(f"     Address: {r['address']}")
                if r.get('distance_km'):
                    print(f"     Distance: {r['distance_km']}km")
                if r.get('avg_rating'):
                    print(f"     Rating: {r['avg_rating']} sao")
                print(f"     Match Score: {r['match_score']}")

            if resp.preference_suggestions:
                print(f"[PREFERENCE] Suggestions: {len(resp.preference_suggestions)}")
                for sugg in resp.preference_suggestions:
                    print(f"   - {sugg}")

        except Exception as e:
            print(f"[ERROR] Test failed: {e}")
            import traceback
            traceback.print_exc()
            continue

    return True


def test_via_api():
    """Test Customer Agent qua API endpoint (nếu server đang chạy)."""
    print("\n" + "="*60)
    print("[TEST 3] API ENDPOINT")
    print("="*60)

    API_BASE = "http://localhost:8000/api/v1"

    # Check if server is running
    try:
        resp = requests.get(f"{API_BASE}/health", timeout=2)
        if resp.status_code != 200:
            print(f"[ERROR] Health check failed: {resp.status_code}")
            return False
        print("[OK] Server is running")
    except requests.exceptions.ConnectionError:
        print("[SKIP] Server not running")
        print("[TIP] Start server: uvicorn app.main:app --reload")
        return False
    except Exception as e:
        print(f"[ERROR] Health check error: {e}")
        return False

    # Test customer agent endpoint
    print("\n[API] POST /agent/customer/chat")

    payload = {
        "message": "Tìm quán phở gần đây",
        "user_id": "user_demo",
        "session_id": "session_demo",
    }

    try:
        resp = requests.post(f"{API_BASE}/agent/customer/chat", json=payload, timeout=30)

        if resp.status_code == 200:
            data = resp.json()
            print(f"[OK] Status: {resp.status_code}")
            print(f"[OK] Trace ID: {data.get('trace_id')}")
            print(f"[OK] Answer: {data.get('answer')}")
            print(f"[OK] Results: {len(data.get('results', []))} quán")
            return True
        elif resp.status_code == 501:
            print("[SKIP] Endpoint not implemented yet (stub)")
            print("[TIP] Route hiện tại trả về 'not_implemented'")
            print("[TIP] Cần implement customer_agent_routes.py trước")
            return False
        else:
            print(f"[ERROR] Request failed: {resp.status_code}")
            print(f"   Response: {resp.text}")
            return False

    except Exception as e:
        print(f"[ERROR] API test failed: {e}")
        return False


def main():
    """Run all manual tests."""
    print("\n" + "="*60)
    print("CUSTOMER AGENT MANUAL TEST")
    print("="*60)

    # Step 1: Check DB
    if not check_db_connection():
        return
    if not check_seed_data():
        print("\n[WARNING] Thiếu seed data. Hãy chạy các lệnh sau:")
        print("   docker compose up -d")
        print("   python scripts/seed_merchants.py")
        print("   python scripts/seed_user_demo.py")
        return

    # Step 2: Test with fake LLM (always works)
    test_with_fake_llm()

    # Step 3: Test with real LLM (if configured)
    s = get_settings()
    if s.llm_configured:
        test_with_real_llm()
    else:
        print("\n" + "="*60)
        print("[SKIP] TEST 2 (REAL LLM)")
        print("="*60)
        print("Không tìm thấy NVIDIA_NIM_API_KEY")
        print("[TIP] Để test với real LLM:")
        print('   export NVIDIA_NIM_API_KEY="nvapi-xxx"')
        print("   Hoặc tạo file .env với dòng: NVIDIA_NIM_API_KEY=your-key")

    # Step 4: Test via API
    test_via_api()

    print("\n" + "="*60)
    print("[DONE] ALL TESTS COMPLETED")
    print("="*60)


if __name__ == "__main__":
    main()
