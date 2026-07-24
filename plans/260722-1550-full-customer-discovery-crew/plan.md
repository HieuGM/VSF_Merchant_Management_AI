---
title: Full Customer Discovery Crew (CrewAI multi-agent)
date: 2026-07-22
branch: develop
status: complete
owner: Track A (Customer)
source_brainstorm: plans/reports/brainstorm-260722-1550-customer-crew-full-implementation.md
---

# Plan: Full Customer Discovery Crew

Wire the Customer Discovery Crew end-to-end với CrewAI thật: viết 4 tool còn thiếu, cải thiện tốt các tools đã có, build
adapter Registry→CrewAI BaseTool, dựng 4 agent + tasks, thay direct-call trong
`customer_flow.py` bằng `Crew.kickoff()`, persist `agent_runs`/`agent_events`.

## Mục tiêu
Đạt (và vượt) GATE Phase 0.5 + 1: `query → flow → CrewAI Crew → agents → tools → DB → results`,
events emit với `trace_id`, allow-list chặn tool trái phép.

## Contract nguồn (MUST comply)
- Design §5.2/§5.4/§5.5/§4 — `docs/2026-07-21-merchant-ai-agent-complete-design.md`
- Frozen seams: `tools/registry.py`, `tools/allow_list.py`, `core/settings.py` (LLM đã pluggable),
  `core/cache.py` (CachePort + TTL), `models/{agent,preference}.py`, `agents/listeners/crewai_listener.py`

## Guardrails (bất biến)
- Agents KHÔNG nhận SQLAlchemy session; tool tự mở/đóng (`SessionLocal` + `finally`).
- `propose_profile_delta` CHỈ trả proposal (`ProfileDeltaSuggestion`), KHÔNG ghi `preference_events`.
- Delegation: chỉ `customer_coordinator`, tối đa 1 hop; 3 specialist tắt.
- Allow-list (`allow_list.py`) ↔ agents.yaml ↔ `ToolSpec.allowed_agents` phải sync (contract test có sẵn).
- Weather external degrade gracefully (`weather=null`, không fail crew).
- LLM output test theo schema/structure, KHÔNG assert nội dung.
- KHÔNG kéo LangChain vào dep graph (verify `pip show crewai`).

## Phases
| # | Phase | Song song? | Status | File |
|---|---|---|---|---|
| 1 | Adapter Registry→CrewAI BaseTool (CORE) | — | ✅ | [phase-01](phase-01-tool-adapter.md) |
| 2 | Data / providers (repos + weather) | sau P1 data-indep | ✅ | [phase-02](phase-02-data-providers.md) |
| 3 | 4 customer tools + register + yaml sync | sau P2 | ✅ | [phase-03](phase-03-customer-tools.md) |
| 4 | Agents + tasks config (4 agent) | sau P3 | ✅ | [phase-04](phase-04-agents-tasks-config.md) |
| 5 | Crew assembly + LLM from settings | sau P1+P4 | ✅ | [phase-05](phase-05-crew-assembly.md) |
| 6 | Wire customer_flow → Crew.kickoff + persist runs/events | sau P5 | ✅ | [phase-06](phase-06-flow-wiring.md) |
| 7 | Tests (unit + contract + integration) | sau P6 | ✅ | [phase-07](phase-07-tests.md) |

Dependency: P1 → P2 → P3 → P4 → P5 → P6 → P7 (P2 repos + P4 yaml có thể làm xen kẽ sau P1).

## Tool inventory ĐẦY ĐỦ (§5.4 — 7 tool Customer Crew)
| Tool | Agent dùng | Trạng thái |
|---|---|---|
| `merchant_search` | restaurant_search | ✅ có - nhưng hãy cải thiện |
| `nearby_merchant_search` | restaurant_search | ✅ có - cải thiện đi |
| `get_user_profile` | coordinator, preference_reasoning | ❌ mới (P3) |
| `get_session_candidates` | coordinator, preference_reasoning | ❌ mới (P3) |
| `get_weather_context` | preference_reasoning | ❌ mới (P3) |
| `propose_profile_delta` | preference_reasoning | ❌ mới (P3) |
| `get_merchant_profile` | customer_explanation | ✅ có - cải thiện đi |
> allow_list.py ĐÃ khai đủ 7. Spec chi tiết từng tool (input/output/args_schema/behavior/errors) ở phase-03.

## Format CrewAI 1.15.5 (đã lock từ crewai-skills)
- Tool = `BaseTool` subclass: `name`/`description`/`args_schema:Type[BaseModel]`/`_run()->str`
  (**trả STRING**, lỗi→string không raise). Adapter (P01) tự bọc + json.dumps.
- Agent YAML: role/goal/backstory (folded `>`), max_iter/max_execution_time/allow_delegation.
- Task YAML: description + expected_output (string) + agent + context; structured qua `output_pydantic`.
- Crew: `@CrewBase`, `Process.hierarchical`, `manager_agent=customer_coordinator`.
- agents.yaml + tasks.yaml **viết sẵn đầy đủ nội dung** trong phase-04 (ready-to-paste).

## Quyết định đã chốt
1. Full Customer Crew ngay (không slice tối thiểu).
2. Weather = **Open-Meteo** (free, no key) + cache CachePort (`TTL_WEATHER=600`, `CacheKeys.weather`).
3. **LLM = NVIDIA NIM, per-agent 2 tier** (qua litellm provider `nvidia_nim/`):
   | Agent | Model | Tier |
   |---|---|---|
   | customer_coordinator (manager) | `meta/llama-3.3-70b-instruct` | large |
   | restaurant_search | `meta/llama-3.3-70b-instruct` | large |
   | preference_reasoning | `meta/llama-3.1-8b-instruct` | small |
   | customer_explanation | `meta/llama-3.1-8b-instruct` | small |
   - Model string CrewAI/litellm: `nvidia_nim/meta/llama-3.3-70b-instruct`.
   - API key: **`NVIDIA_NIM_API_KEY` trong `.env`** (litellm tự đọc; settings cũng đọc để pass tường minh).
   - Base URL mặc định `https://integrate.api.nvidia.com/v1` (override qua `LLM_BASE_URL` nếu self-host NIM).
   - Test dùng fake/monkeypatch LLM (không gọi NIM).

## Unresolved / cần làm kèm
- Seed `user_demo` + 1 `chat_session` fixture (Phase 0.5 deliverable #2 chưa làm) → để test `get_user_profile`/`get_session_candidates`. Đưa vào P2.
- Geocode: DEFER — chỉ làm nếu weather cần city→lat/lng (Open-Meteo nhận lat/lng trực tiếp, thường không cần).
- Ownership overlap: `agents/listeners/*` + agent_run persistence vốn là Dev B territory. Owner gộp Track A nên tự làm; flag để Phase 3 reconcile nếu tách lại 2 dev.

## Implementation Log

### Phase 1–7 complete — 2026-07-23
Full Customer Discovery Crew wired end-to-end với CrewAI 1.15.5 thật. Toàn bộ Phase 1→7 xong.
- **P1 Adapter:** `agents/tool_adapter.py` — Registry→CrewAI `BaseTool` (json.dumps output, error→string never raise, args_schema từ ToolSpec/input_schema). Điểm coupling CrewAI DUY NHẤT.
- **P2 Data/providers:** repos `agent_run`/`session`/`user_profile`; `providers/weather/open_meteo_provider.py` (Open-Meteo free, CachePort TTL=600); `services/{merchant_search,preference}`; seed `scripts/seed_user_demo.py` + `seed_merchants.py`.
- **P3 Tools:** 4 tool mới `get_user_profile`/`get_session_candidates`/`get_weather_context`/`propose_profile_delta` + cải thiện `merchant_search`/`nearby_merchant_search`/`get_merchant_profile`. YAML↔allow-list sync.
- **P4 Agents/tasks:** `agents/customer/config/{agents,tasks}.yaml` — 4 agent (coordinator manager + 3 specialist), per-agent LLM tier NVIDIA NIM.
- **P5 Crew:** `agents/customer/customer_crew.py` — `Process.hierarchical`, manager=coordinator, LLM from settings.
- **P6 Flow wiring:** `flows/customer_flow.py` dùng `crew.kickoff`; `agents/listeners/persisting_listener.py` persist `agent_runs`+`agent_events` (trace_id, REQUIRED_EMIT_FIELDS).
- **P7 Tests:** **53 passed / 0 failed / 0 skipped** (conda env `ai_restaurant`, Postgres up). Full 11-item matrix phủ: adapter wrap, allow-list, weather cache hit/miss+offline, propose_delta no-persist, get_user_profile, yaml↔allow-list sync, event emit, crew fake-LLM, per-agent tier, flow persist run+events, no-DB-session, no-LangChain.
- **Bug fix session:** 4 test "fail" ban đầu = Postgres chưa khởi động (connection refused) — không phải lỗi code. Sau khi start container `gsm_merchant_postgres`, all green. Skips 7→0 (integration tests chạy được).
- **⚠️ Chưa commit:** toàn bộ P1–7 còn untracked/modified trên `develop`.

### Code review + fixes — 2026-07-23
Report: `plans/reports/code-reviewer-260723-0923-customer-crew-review.md`. Verdict: ship-able, 0 critical/security, 7 guardrails test-enforced, SQLi fix confirmed. Fixed:
- **[Med] Listener task-event field mapping (silent-null risk):** task handlers dùng nested `event.task.agent.role`/`event.task.name` (thường None — Task không có `.name`). Verified qua introspect CrewAI 1.15.5 event models → đổi sang field TRỰC TIẾP `event.agent_role`/`event.task_name`. Thêm contract test `tests/contract/test_listener_event_fields.py` pin tên field (fail loudly nếu CrewAI upgrade đổi tên). Tool handlers đã đúng sẵn.
- **[Med] `finish_run` datetime tz mismatch:** `datetime.utcnow()` (naive) → `datetime.now(timezone.utc)` (tz-aware, khớp parsed timestamps).
- **[Med] `get_weather_context` `cached` hardcoded False:** peek cache trước khi fetch (share cache instance với provider) → phản ánh cache-hit thật.
- **Tests:** 53 → **57 passed / 0 failed / 0 skipped**.
- **Còn treo (chưa fix, YAGNI/cần runtime):** (a) manager_agent + tools — vài bản CrewAI drop tool của manager; cần verify lúc kickoff thật với NIM key. (b) Event persist fire-and-forget (bus nuốt lỗi) → mất event khi DB lỗi tạm thời — chấp nhận theo design. (c) Low findings (import register thừa, `db.merge` vs insert, per-event SessionLocal, NIM routing dùng chung `llm_provider`) — cosmetic, defer.

### Runtime validation (real NVIDIA NIM LLM) — 2026-07-23
Chạy `scripts/test_customer_agent_manual.py` với NIM key thật (`.env`). Kiểm chứng luồng hoàn chỉnh, quan sát qua `agent_runs`/`agent_events`.
- **✅ Plumbing xác nhận hoạt động end-to-end:** `run_started → task_started → coordinator delegate_work_to_coworker → restaurant_search gọi merchant_search/nearby_merchant_search → task_finished`. Persisting listener ghi event với `agent_name`+`task_name` ĐẦY ĐỦ (xác nhận fix listener chạy đúng runtime, không null). trace_id nhất quán toàn chuỗi. Error handling graceful (crew timeout → run status=error, error_code=TimeoutError, không crash process).
- **🔧 Fix #2 (manager tools) — làm thật trong crew:** `customer_coordinator()` giờ trả `tools=[]` (CrewAI hierarchical từ chối manager có tool). Bỏ monkeypatch tạm trong manual script. Xác nhận: manager tools rỗng + delegate=True, 3 specialist giữ đúng allow-list tool. 57 test vẫn xanh.
- **⚠️ Vấn đề runtime THẬT — crew timeout do agent loop:** cả manager (delegate 3×) lẫn restaurant_search (gọi merchant_search/nearby 5× mỗi cái, xen kẽ) LẶP do LLM 70b thiếu quyết đoán → chạm `max_execution_time` → 2 case real-LLM đều `TimeoutError`, CHƯA sinh được answer thành công. Plumbing đúng nhưng agent không hội tụ.
- **🔧 Convergence tuning:** coordinator max_iter 8→4 (exec 90→120s); restaurant_search max_iter 6→3 (exec 60→90s); `search_task` thêm ràng buộc "CHỌN ĐÚNG 1 công cụ, gọi ĐÚNG 1 LẦN, KHÔNG lặp/xen kẽ, có kết quả thì DỪNG". Đang re-validate 1 case live.
- **Còn treo:** prompt/agent tuning cho hội tụ là việc lặp (cần thêm data runtime); nếu vẫn timeout sau tuning → cân nhắc tăng thêm exec-time hoặc đơn giản hoá crew 3-task.

### Data fix — get_merchant_profile wired to DB — 2026-07-23
Điều tra data merchant_profile theo yêu cầu user. Kết luận + fix:
- **Làm rõ:** customer search KHÔNG dùng `dimensions_json`. Rating/giá/cuisine/geo đều là CỘT thật (`reviews.rating` indexed, `menu_items.price`, `merchants.*`). `dimensions_json` chỉ là hồ sơ 8 chiều nested cho Merchant Advisor (đọc-nguyên-khối). JSONB vẫn index được (GIN). Schema hiện tại đúng hướng hybrid.
- **🔧 Bug 1 FIXED — get_merchant_profile đọc DB thật:** trước đây tool đọc fixture 1-merchant (68814) → explanation NotFoundError với mọi quán thật. Wire sang DB: thêm `repositories/merchant_profile_repository.py` (đọc `merchant_profiles`, ưu tiên `profile_json`, fallback `dimensions_json`); tool `shared_readonly_tools` giờ DB-first + fixture-fallback graceful (offline/dev vẫn chạy), tự quản SessionLocal (guardrail). Verified: merchant "94" (KHÔNG có trong fixture) trả full 8-dim từ DB, strip overall_score. 1625 profile giờ reachable.
- **Tests:** thêm `tests/integration/test_merchant_profile_db.py` (3 test: read DB thật, trending shape, unknown→NotFound); sửa 2 unit test content-exact → structural. **60 passed / 0 failed / 0 skipped.**
- **Còn treo (Bug 2, chưa fix theo ý user):** data nằm `dimensions_json` thay vì `profile_json` (contract §6.4) — reconcile sau, thuộc Dev B. Promote dimension-fields thành cột: KHÔNG làm (UC-04 chưa cần lọc theo chiều).

### ✅ Luồng hoàn chỉnh CHẠY THÀNH CÔNG (real NIM) — 2026-07-23
Sau convergence tuning + tăng budget: 1 case live `ok=true, n_results=4, answer≈1180 ký tự, ~418s`. Chứng minh end-to-end hoạt động với LLM thật; blocker trước đó chỉ là NIM 70b latency (55–170s/inference). Khuyến nghị production: cân nhắc model nhanh hơn hoặc NIM self-host cho độ trễ thấp.

## Cook
`/cook plans/260722-1550-full-customer-discovery-crew/plan.md`
