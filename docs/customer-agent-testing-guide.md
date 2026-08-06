# 🧪 Customer Agent Testing Guide

## Cách Test Tay (Manual Testing)

### Setup Nhanh (3 phút)

```bash
# 1. Start database
docker compose up -d

# 2. Seed dữ liệu mẫu
cd backend
PYTHONPATH=. alembic upgrade head
python scripts/seed_merchants.py
python scripts/seed_user_demo.py

# 3. Chạy script test (KHÔNG cần API key)
python scripts/test_customer_agent_manual.py
```

---

## 3 Cách Test

### ✅ Cách 1: Fake LLM (Nhanh nhất - Không cần API key)

```bash
python backend/scripts/test_customer_agent_manual.py
```

**Kết quả:**
- ✅ Test flow logic
- ✅ Test DB persistence (agent_runs, agent_events)
- ✅ Test tool binding (merchant_search, get_user_profile)
- ⏱️ Thời gian: ~2 giây

---

### ✅ Cách 2: Real LLM (Cần FPT Cloud AI API key)

```bash
# Set API key (FPT Cloud AI — DeepSeek/Qwen; lấy từ FPT dashboard)
export FPT_API_KEY="xxxxx"
export FPT_BASE_URL="https://...fpt.ai/..."   # xem .env.example
export FPT_MODEL_QWEN="..."
export FPT_MODEL_DEEPSEEK="..."

# Hoặc tạo file .env (đã có sẵn trên máy dev — copy từ máy cũ, xem docs/setup-guide.md §2)
# .env chứa FPT_API_KEY / FPT_BASE_URL / FPT_MODEL_QWEN / FPT_MODEL_DEEPSEEK

# Chạy test
python backend/scripts/test_customer_agent_manual.py
```

**Kết quả:**
- ✅ Real AI responses
- ✅ Test sequential specialist workflow
- ✅ Test preference reasoning + explanation
- ⏱️ Thời gian: ~10-20 giây

---

### ✅ Cách 3: API Endpoint (Full stack)

```bash
# Terminal 1: Start server
cd backend
uvicorn app.main:app --reload --port 8000

# Terminal 2: Gửi request
curl -X POST http://localhost:8000/api/v1/agent/customer/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Tìm quán phở gần đây",
    "user_id": "user_demo",
    "session_id": "session_demo"
  }'
```

**Đã implement:** `POST /api/v1/agent/customer/chat` (+ `/chat/stream` SSE) — trả `CustomerChatResponse` (trace_id, answer, results, preference_suggestions).

---

## Câu Hỏi Test Mẫu

### 🍜 Basic Search
```python
# Tìm phở gần đây
query: "phở gần đây"
user_id: "user_demo"

# Tìm món Nhật
query: "quán Japanese sushi"
cuisine: "Japanese"
```

### 💰 Budget + Location
```python
# Budget sinh viên
query: "quán rẻ phù hợp sinh viên"
budget: "cheap"

# Gần vị trí cụ thể
query: "quán ăn gần đây"
lat: 10.7769
lng: 106.7009
radius_km: 3
```

### 🌦️ Context-based
```python
# Thời tiết mưa
query: "mưa rồi, tìm quán gần đây"
lat: 10.7769  # có weather context

# Ăn chay
query: "tìm quán ăn chay"
constraints: {"dietary": ["vegetarian"]}
```

### 🎯 Preference Match
```python
# Theo sở thích (user_demo đã like Vietnamese + Japanese)
query: "gợi ý quán ăn theo sở thích"

# Multi-constraint
query: "tìm quán món Việt, gần đây, giá phải chăng"
cuisine: "Vietnamese"
budget: "standard"
radius_km: 5
```

---

## Kiểm Tra Kết Quả

### Expected Output Structure

```json
{
  "trace_id": "trace_xxx",
  "session_id": "session_demo",
  "intent": "restaurant_discovery",
  "answer": "Tôi gợi ý Phở Le vì quán này gần vị trí của bạn...",
  "results": [
    {
      "merchant_id": "m001",
      "name": "Phở Le",
      "cuisine": "Vietnamese",
      "address": "123 Nguyễn Huệ, Quận 1",
      "distance_km": 0.5,
      "avg_rating": 4.5,
      "match_score": 0.9
    }
  ],
  "preference_suggestions": [
    {
      "field": "liked_cuisines",
      "operation": "add",
      "value": "Ramen",
      "confidence": 0.8,
      "rationale": "Bạn thường tìm món Nhật"
    }
  ]
}
```

### Verify Database

```bash
# Check agent_runs
psql -U postgres -d merchant_platform -c "
SELECT trace_id, status, intent, started_at
FROM agent_runs
ORDER BY started_at DESC
LIMIT 5;
"

# Check agent_events
psql -U postgres -d merchant_platform -c "
SELECT event_type, agent_name, task_name
FROM agent_events
WHERE trace_id = 'trace_xxx'
ORDER BY timestamp;
"
```

---

## Troubleshooting

### ❌ "Database connection failed"
```bash
# Check Postgres running
docker ps | grep postgres
# Start it
docker compose up -d
```

### ❌ "Thiếu seed data"
```bash
cd backend
python scripts/seed_merchants.py
python scripts/seed_user_demo.py
```

### ❌ "FPT_API_KEY not configured" / `llm_configured:false`
```bash
# Option 1: Fake LLM (không cần key)
# Script vẫn chạy test 1 với fake LLM

# Option 2: FPT Cloud AI key — copy .env từ máy dev cũ (xem docs/setup-guide.md §2)
# Cần: FPT_API_KEY, FPT_BASE_URL, FPT_MODEL_QWEN, FPT_MODEL_DEEPSEEK
```

### ❌ "Endpoint trả lỗi"
Route `/api/v1/agent/customer/chat` đã implement (`backend/routes/customer_agent_routes.py`).
Nếu lỗi, kiểm tra server chạy (`uvicorn app.main:app --reload --port 8000`) và DB đã seed.
Test trực tiếp qua flow:
```bash
python -c "
from flows.customer_flow import customer_flow
resp = customer_flow.search_restaurants(query='phở', user_id='user_demo')
print(resp.answer)
"
```

---

## Ground-Truth Eval Harness

GT-driven regression for the customer agent (39 cases, `ground_truth_customer.json`):

```bash
cd backend
PYTHONUTF8=1 PYTHONPATH=. python scripts/eval_ground_truth.py
```

- **Harness:** `backend/scripts/eval_ground_truth.py`. **Cases:** `ground_truth_customer.json` (at repo root).
- Per-run unique session/user ids (no cross-run `chat_messages`/`user_profile` leak); coords derived from prior+test turns (multiturn proof).
- Current baseline: **39/39 PARITY** (87.2% quality rolled forward). See `plans/reports/tester-260805-*-gt-eval.md` (phase-1/2/3 snapshots) + `plans/reports/eval-260731-*.md` (prior rounds).
- 12 coordinator-only TCs are skipped (declined coordinator — see `plans/reports/eval-260731-final-6-round-arc.md`).

---

## Unified Preference/Memory — Test Matrix (plan A, phases 1–4)

| Path | How to verify | Expected |
|---|---|---|
| **PATCH profile** (explicit edit) | `curl -X PATCH :8000/api/v1/users/u1/profile -d '{"liked_cuisines":["Vietnamese"]}'` (dev env only) | 200 `UserProfilePublic`, row updated, `preference_events(source="user_edit")` row |
| **GET profile** | `curl :8000/api/v1/users/u1/profile` | 200 with taste fields + `context_memory.notes`, or 404 |
| **Confirm-delta** | chat suggestion → `POST .../deltas/{id}/confirm` | profile mutated via `apply_delta`; idempotent on re-confirm |
| **IDOR guard** | same PATCH with `APP_ENV=prod` | **403** + warning log |
| **Ranking** | profile with disliked cuisine → search | disliked merchant dropped/penalized; `ranking_enabled=False` → baseline |
| **context_memory** | send "tôi dị ứng đậu phộng" → `get_user_profile` | note persisted (PII-redacted), FIFO cap 8, deduped; DB fail → swallowed (F3) |
| **FE round-trip** | Preference Center toggle → reload / 2nd tab | persists cross-device; clear-browser → prefs survive (backend); offline → cache fallback |

Cross-layer tests: `backend/tests/unit/test_profile_ranking.py`, `backend/tests/unit/test_context_memory_service.py`, `backend/tests/integration/test_customer_memory_wireup.py`. FE build: `cd frontend && npm run build` (0 errors, oxlint pass).

---

## Test Checklist

- [ ] Database connected (`docker compose up -d`)
- [ ] Migrations applied (`alembic upgrade head`)
- [ ] Merchants seeded (`seed_merchants.py`)
- [ ] User demo seeded (`seed_user_demo.py`)
- [ ] Fake LLM test passes
- [ ] Real LLM test passes (FPT key set)
- [ ] API endpoint returns 200
- [ ] GT eval harness green (`scripts/eval_ground_truth.py`)
- [ ] Unified-memory round-trip (PATCH → GET → ranking → context_memory)

---

## Test Scenarios Document

### UC-04: Restaurant Discovery
**Input:** "Tìm quán phở gần đây"
**Expected:**
- `restaurant_search` agent gọi `nearby_merchant_search`
- Trả về danh sách quán Vietnamese cuisine
- Sắp xếp theo distance_km và match_score

### UC-05: Preference-based Recommendation
**Input:** "Gợi ý quán theo sở thích"
**Expected:**
- `preference_reasoning` agent gọi `get_user_profile`
- Đọc `liked_cuisines: ["Vietnamese", "Japanese"]`
- `propose_profile_delta` đề xuất (không lưu)
- `explanation` agent giải thích lý do chọn quán

### Multi-agent Workflow
**Input:** "Tìm quán món Nhật, budget sinh viên, gần đây"
**Expected:**
- `restaurant_search` → merchant_search với filters
- `preference_reasoning` → propose budget constraint, dùng kết quả search làm context
- `customer_explanation` → tổng hợp search + preference context

---

## Advanced Testing

### Test Error Handling
```python
# Unknown user
customer_flow.search_restaurants(query="x", user_id="unknown_user")
# Expected: NotFoundError or graceful degradation

# Invalid coordinates
customer_flow.search_restaurants(query="x", lat=-999, lng=-999)
# Expected: No results or error in search_task

# Empty database
# Delete all merchants then test
# Expected: Empty results list
```

### Performance Test
```python
import time

start = time.time()
resp = customer_flow.search_restaurants(query="phở", user_id="user_demo")
elapsed = time.time() - start

print(f"Response time: {elapsed:.2f}s")
# Expected: < 30s with real LLM, < 1s with fake LLM
```

---

## Next Steps

1. ✅ Test fake LLM (validate logic)
2. ✅ Test real LLM (validate AI quality)
3. ⚠️ Implement API route
4. ⚠️ Add API tests
5. ⚠️ Add frontend integration test
