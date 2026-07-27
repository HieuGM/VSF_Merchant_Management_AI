# Customer Agent — Sequential Refactor Result

**Date:** 2026-07-27 11:12  
**Branch:** dev-a  
**Plan:** `.claude-glm/plans/imperative-stargazing-sonnet.md` (approved)  
**Verdict:** ✅ **SUCCESS** — flow chạy end-to-end, latency −93%, quality giữ/tốt hơn

---

## Đã làm (refactor hierarchical → sequential)

| File | Change |
|---|---|
| `backend/agents/customer/customer_crew.py` | `Process.sequential`, bỏ `manager_agent` + `@agent customer_coordinator`, `memory=False`, simplify LLM builders (`__init__(llm_nim, llm_fpt)`, xóa `_build_llm`/`_llm_large`/`_llm_small`), update docstrings. 217→148 dòng. |
| `backend/agents/customer/config/agents.yaml` | Xóa block `customer_coordinator` (44 dòng). |
| `backend/tools/allow_list.py` | Xóa entry `customer_coordinator` (lockstep với yaml). |
| `backend/tests/unit/test_customer_crew.py` | Rewrite 3 tests cho sequential, đổi `test_coordinator_allows_delegation` → `test_specialists_do_not_delegate`. |
| `backend/tests/conftest.py` | Xóa fixtures `fake_llm_large` + `fake_llm_small` (không dùng). |
| `backend/scripts/` | Xóa 6 scripts obsolete (check_coordinator, verify_hierarchical_×2, verify_task_agent_assignment, test_delegation_debug, test_coordinator_tools). Update `test_phase1_simple.py` (memory=True→False). |
| KHÔNG đổi | `customer_flow.py`, routes, listeners, models, frontend (transparent — `CustomerChatResponse` shape process-agnostic). |

## Verification

### 1. Tests — **68 passed** (full backend suite, exit 0)
- `test_customer_crew.py` 4/4, `test_allow_list_sync.py` 1/1, `test_customer_flow_crew.py` 2/2, + 61 others.
- Chỉ deprecation warnings (CrewAI `function_calling_llm`), không phải errors.

### 2. Real LLM e2e — **45.7s, success**
- Query `"Tìm quán phở gần đây"`, lat/lng **Hà Nội** (21.0285, 105.8542), radius 5, session `session_seq_01`.
- trace `trace_7f7962148142421a`, `status=ok`, answer đầy đủ friendly Vietnamese.
- **Không TimeoutError, không Memory Error.**

### 3. DB inspect (18 events) — task breakdown

| Task | Duration | Agent | Tools |
|---|---|---|---|
| search_task | **5.5s** | Restaurant Search Specialist (NIM 8b) ✅ | nearby_merchant_search ×1 (140ms) |
| preference_task | 29.7s | Preference Specialist (DeepSeek) | get_user_profile, get_session_candidates, get_weather_context (HN mưa 30.4°C), propose_profile_delta — mỗi cái ×1 |
| explanation_task | 9.8s | Explanation Specialist (DeepSeek) | không tool (search trả burger≠phở → dùng gợi ý chung Loại 2) |
| **total** | **45.7s** | | |

Tool calls: mỗi tool đúng 1 lần (constraint tuân thủ). Không còn `delegate_work_to_coworker`.

## Quality assessment — **không giảm, tốt hơn**

- Search giờ chạy đúng **NIM-8b specialist** (hybrid LLM hoạt động đúng thiết kế) thay vì manager DeepSeek tự làm.
- Answer honest: flag mismatch (search trả burger, user cần phở; profile HCM vs query HN) → graceful fallback gợi ý Phở Thìn/Lý Quốc Sư + hỏi thêm info. Đúng prompt design (Loại 1 grounded / Loại 2 free).
- Weather context dùng được (HN mưa → gợi ý món nóng/giao gần).
- `reasons` + `referenced_signals` đầy đủ, không bịa.

## Trước vs Sau

| | Trước (hierarchical) | Sau (sequential) |
|---|---|---|
| End-to-end | ❌ crash | ✅ ok |
| Latency | 11m36s (fail) | **45.7s** |
| Manager hop/task | có (DeepSeek) | bỏ |
| Memory errors | mỗi task | không |
| Hybrid LLM search | thất bại (manager tự làm) | hoạt động (NIM 8b) |

## Risk đã xác nhận
- NIM-8b chọn tool đúng (nearby khi có lat/lng HN) — risk "chọn tool sai" không xảy ra.
- Edge case non-food: chưa test riêng, nhưng explanation agent handle empty/mismatch gracefully (đã thấy với search trả sai món).

## Docs impact: **none required**
- Master design doc (`2026-07-21-merchant-ai-agent-complete-design.md:1354`): *"hierarchical or sequential"* — permissive, OK.
- `customer-agent-testing-guide.md`: không mention process type. (Lưu ý pre-existing inaccuracy: guide nói route là "stub 501" nhưng thực tế đã implemented — không liên quan refactor.)
- Không có `docs/system-architecture.md` / `codebase-summary.md`.

## Unresolved
- Q1: Search HN radius 5 trả "burger" thay "phở" → data distribution (DB HN ít phở trong radius). Có thể test thêm query khác hoặc mở radius để verify search trả đúng phở.
- Q2: `test_phase1_performance.py` dùng mock data stale (field `rating`/`price_range`/`query_understanding` không có trong schema thực) — pre-existing, không do refactor. Có thể cleanup sau.
- Q3: Commit refactor? (user quyết định)
