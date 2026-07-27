# Customer Agent — State Test Report

**Date:** 2026-07-27 10:55  
**Branch:** dev-a  
**Task:** Đọc code customer agent + chạy 1 luồng hoàn chỉnh để test trạng thái hiện tại  
**Verdict:** ⛔ **FLOW BROKEN — không chạy end-to-end được** (TimeoutError)

---

## 1. Kiến trúc customer agent (đã đọc)

```
CustomerFlow.search_restaurants()                     ← backend/flows/customer_flow.py
  └─ build_customer_crew() → CustomerDiscoveryCrew    ← backend/agents/customer/customer_crew.py
       Process: hierarchical (manager = customer_coordinator)
       Agents:
         - customer_coordinator   llm_large (FPT DeepSeek-V4-Flash)  tools=[]   (manager)
         - restaurant_search      llm_nim   (NIM llama-3.1-8b)       tools=[merchant_search, nearby_merchant_search]
         - preference_reasoning   llm_fpt   (FPT DeepSeek-V4-Flash)  tools=[get_user_profile, get_session_candidates, get_weather_context, propose_profile_delta]
         - customer_explanation   llm_fpt   (FPT DeepSeek-V4-Flash)  tools=[get_merchant_profile]
       Tasks (output_pydantic): search_task → preference_task → explanation_task
       Flags: cache=True, memory=True, respect_context_window=True
  Observability: agent_runs + agent_events (PersistingListener) — mỗi run có trace_id
```

Config: `backend/agents/customer/config/{agents,tasks}.yaml`. Tool adapter: `backend/agents/tool_adapter.py` (filter output >4k chars).

---

## 2. Prerequisites (đã verify — tất cả OK)

| Item | Status |
|---|---|
| Python / CrewAI / SQLAlchemy | 3.11.15 / 1.15.5 / 2.0.51 |
| LLM vendor | FPT (DeepSeek-V4-Flash) + NVIDIA NIM (llama-3.3-70b + 3.1-8b) — **cả 2 configured** |
| Postgres | reachable |
| Seed data | 1625 merchants, 1625 profiles, `user_demo` OK |
| Tool registry | 8 tools, allow-list bind đúng cho 3 specialists |

→ Có thể chạy REAL LLM end-to-end. Script diag: `backend/scripts/check_customer_agent_state.py`.

---

## 3. Luồng test chạy (REAL LLM)

**Input:** `query="Tìm quán phở gần đây cho tôi"`, lat=10.7769, lng=106.7009 (HCM), radius=3, user=user_demo, session=session_diag_01  
**trace_id:** `trace_d01a36ed9310458f`  
**Kết quả:** ⛔ **Crew Failure** — `TimeoutError: preference_task execution timed out after 60 seconds`  
**Tổng thời gian:** 11 phút 36 giây (03:43:45 → 03:55:21) rồi fail  
**explanation_task KHÔNG chạy** → không có answer cuối cho user.

### Timeline (từ DB agent_events — 20 events)

| Thời điểm | Event | Duration | Agent | Ghi chú |
|---|---|---|---|---|
| 03:43:45 | run_started | — | customer_flow | OK |
| 03:43:49 | task_started search_task | — | — | +3.4s overhead (memory init) |
| 03:43:53 | nearby_merchant_search | 176ms | **Coordinator** | → 0 quán (HCM không có data trong 3km) |
| 03:44:00 | merchant_search | 156ms | **Coordinator** | → 10 quán (HN/ĐN/Nha Trang) — fallback OK |
| 03:44:18 | task_finished search_task | **29.8s** | — | "Maximum iterations reached" |
| 03:44:18 | task_started preference_task | — | — | |
| 03:44:36 | delegate_work_to_coworker | — | Coordinator → Preference specialist | delegate ĐÚNG |
| 03:44:38 | get_user_profile | 11ms | Preference specialist | |
| 03:44:40 | get_session_candidates | 27ms | Preference specialist | |
| 03:44:43 | get_weather_context | **3752ms** | Preference specialist | open-meteo network call |
| 03:44:52 | propose_profile_delta | 16ms | Preference specialist | → suggest add "phở" liked_cuisines conf 0.5 |
| 03:45:07 | delegate_work_to_coworker finished | **31.5s** | — | specialist round-trip OK |
| *(03:45:07 → 03:55:21 — 10 phút trống không event — manager stuck/retry)* | | | | |
| 03:55:21 | task_finished preference_task | **663s** | — | ❌ **ERR=TaskFailed** |
| 03:55:21 | error:search_restaurants | — | customer_flow | TimeoutError |

### Tool-call counts (DB) — **KHÔNG có duplicate**

Mỗi tool `started=1`: nearby_merchant_search, merchant_search, delegate_work_to_coworker, get_user_profile, get_session_candidates, get_weather_context, propose_profile_delta.  
→ Constraint "mỗi tool tối đa 1 lần" được **tuân thủ**. (Log verbose CrewAI in Started/Completed interleaved — không phải gọi lại thật.)

---

## 4. Vấn đề phát hiện (xếp theo severity)

### 🔴 BLOCKER #1 — Coordinator timeout 60s quá thấp → flow fail
- **File:** `backend/agents/customer/config/agents.yaml:42` — `customer_coordinator.max_execution_time: 60`
- **Hiện tượng:** preference_task sau khi delegate xong (31s), manager (DeepSeek) aggregate/produce `PreferenceTaskOutput` (structured) bị kẹt/retry 10+ phút → TimeoutError 60s → crew fail.
- **Tác động:** flow KHÔNG trả kết quả cho user. explanation_task không chạy. Trước đó perf-report cũng có query fail (Phở 0 quán, 118.7s).
- **Fix đề xuất:** tăng `customer_coordinator.max_execution_time` lên ≥180s (hoặc bỏ để dùng default CrewAI). Phân biệt: timeout manager (aggregate) vs specialist (đã có 120s).

### 🟠 HIGH #2 — Memory feature BROKEN
- **File:** `backend/agents/customer/customer_crew.py:199` — `memory=True`
- **Hiện tượng:** mỗi task ném `Memory Query Error` + `Memory Save Error`: *"Memory requires an embedder... CHROMA_OPENAI_API_KEY not set"*. + warning `memory_save_failed empty scope stack`.
- **Tác động:** overhead mỗi task, noise log, có thể góp phần chậm. Đây là flag Phase-1 perf-opt nhưng **không hoạt động** trong env này (thiếu embedder).
- **Fix đề xuất:** hoặc set `OPENAI_API_KEY`/config embedder (FPT/NIM không có embedding endpoint compatible → cần provider riêng), hoặc **tắt `memory=False`** cho tới khi có embedder. Recommend: `memory=False` (YAGNI — discovery crew stateless, memory chưa cần).

### 🟠 HIGH #3 — Coordinator tự làm search_task (KHÔNG delegate)
- **Hiện tượng:** search_task được thực hiện trực tiếp bởi Coordinator (DeepSeek) — tự gọi nearby + merchant_search rồi "Maximum iterations reached" tự trả. `restaurant_search` specialist (NIM 8b) **KHÔNG được gọi** trong run này.
- **Tác động:** hybrid LLM design thất bại cho search: tier NIM-8b (sinh ra để nhanh) không dùng → mất lợi thế tốc độ + dùng DeepSeek đắt hơn cho task trivial.
- **Nguyên nhân khả nghi:** manager decide tự làm (hoặc do max_iter cấu hình ép final answer sớm). Cần xem lại `customer_coordinator.max_iter: 2` (agents.yaml:41) — quá thấp cho manager phải delegate.
- **Fix đề xuất:** tăng `max_iter` coordinator lên 4-5, hoặc nhấn mạnh delegation trong prompt (đã có nhưng DeepSeek vẫn tự làm). Có thể cần `allow_delegation` config + giới hạn tools manager thấy.

### 🟡 MEDIUM #4 — preference_task manager aggregate chậm (633s trống)
- **Hiện tượng:** sau delegate_work_to_coworker trả kết quả đầy đủ (specialist chạy xong 03:45:07), manager mất ~10 phút mới TaskFailed.
- **Nguyên nhân khả nghi:** DeepSeek produce structured `PreferenceTaskOutput` bị parse fail/retry loop + memory errors. Cần log chi tiết hơn (LiteLLM retry count) để confirm.
- **Fix đề xuất:** bật LiteLLM debug / giảm `preference_reasoning.max_execution_time` không giúp ( specialist OK). Vấn đề ở manager aggregate — liên quan #1.

### 🔵 INFO #5 — nearby search HCM = 0 (data distribution, không phải bug)
- 1625 merchants seed đa số ở **Hà Nội / Đà Nẵng / Nha Trang / Vũng Tàu**. user_demo `current_lat=10.7769` (HCM) → không có quán trong 3km → nearby trả 0.
- **Tốt:** coordinator fallback `merchant_search(query="phở")` đúng theo instruction → trả 10 quán. Đây là behavior mong muốn.
- **Đề xuất (data):** thêm seed data HCM nếu muốn test geo-flow thực tế, hoặc đổi lat/lng test sang HN (21.0285, 105.8542).

### 🟢 WIN — Observability pipeline HOẠT ĐỘNG
- 20 events persisted đúng: run_started/finished, task_started/finished (kèm duration_ms), tool_started/finished (kèm duration_ms), error event. PersistingListener + AgentRunRepository OK.
- Inspect script: `backend/scripts/inspect_customer_run.py`.

### ⚪ LOW #6 — WinError 10054 trace batch
- `"Error initializing trace batch: [WinError 10054]"` ở startup (CrewAI/LiteLLM telemetry). Noise only, không ảnh hưởng logic.

---

## 5. Trạng thái từng thành phần

| Thành phần | Trạng thái |
|---|---|
| DB connection + seed data | ✅ OK |
| LLM config (FPT + NIM) | ✅ OK |
| Tool registry + allow-list | ✅ OK |
| Tool execution (merchant_search, nearby, get_*, propose_delta) | ✅ OK (nhanh, đúng schema) |
| Observability (agent_runs + agent_events) | ✅ OK |
| search_task | ⚠️ Hoàn thành nhưng **coordinator tự làm**, specialist NIM không dùng |
| preference_task (specialist) | ✅ Delegate đúng, 4 tools đúng, output đúng |
| preference_task (manager aggregate) | ❌ **Timeout/fail** |
| explanation_task | ❌ **Không chạy** (flow fail trước) |
| `memory=True` | ❌ **Broken** (no embedder) |
| End-to-end response (answer + results) | ❌ **Không có** (flow fail) |

---

## 6. Fix ưu tiên (đề xuất, chưa implement)

1. **[BLOCKER]** `customer_coordinator.max_execution_time: 60 → 180` (agents.yaml:42) + `max_iter: 2 → 4` (agents.yaml:41).
2. **[HIGH]** `memory=True → False` (customer_crew.py:199) tới khi có embedder.
3. **[HIGH]** Điều chỉnh coordinator prompt/config để **bắt buộc delegate** search_task cho restaurant_search specialist (dùng NIM 8b như thiết kế hybrid).
4. **[VERIFY]** Sau fix, chạy lại flow + verify explanation_task chạy + answer trả về. Test cả lat/lng HN để có nearby results.

---

## 7. Unresolved questions

- Q1: Có nên fix ngay các vấn đề #1–#3 (config-only, low risk) và chạy lại luồng để confirm end-to-end pass không? Hay chỉ cần báo cáo trạng thái?
- Q2: `memory=True` có chủ đích không (dự định config embedder sau), hay vô tình bật trong Phase-1 perf-opt?
- Q3: Coordinator tự làm search_task — có phải do `max_iter: 2` ép "Maximum iterations reached" sớm, hay manager chủ động chọn tự làm? Cần log LLM decision để confirm.
- Q4: Seed data HCM thiếu — có cần thêm để test geo-flow thực tế, hay chấp nhận fallback merchant_search?

---

## Files tham chiếu
- `backend/agents/customer/customer_crew.py` (crew assembly, memory=True:199, manager:195)
- `backend/agents/customer/config/agents.yaml` (coordinator max_execution_time:42, max_iter:41)
- `backend/flows/customer_flow.py` (entry point)
- `backend/agents/tool_adapter.py` (output filtering)
- `backend/scripts/check_customer_agent_state.py` (diag, mới tạo)
- `backend/scripts/inspect_customer_run.py` (DB inspect, mới tạo)
- Log chạy: background task `bwol1bob6.output`
