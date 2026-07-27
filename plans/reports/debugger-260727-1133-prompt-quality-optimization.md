# Customer Agent — Prompt Quality Optimization Report

**Date:** 2026-07-27 11:33  
**Branch:** dev-a  
**Trigger:** user báo agent sinh quán tên "string" + sai nhiều. Yêu cầu tối ưu prompt + test quality (tham khảo `ground_truth_customer.json`).

---

## Root causes (4 vấn đề độc lập)

| # | Vấn đề | Nguyên nhân | Hậu quả |
|---|---|---|---|
| 1 | **Hallucination "string"** | `tasks.yaml` search_task ép *"trả KẾT QUẢ ĐA DẠNG thay vì rỗng"*, *"thử parameters rộng hơn thay vì trả rỗng"* | tool rỗng → LLM fill `SearchTaskOutput.candidates` với placeholder `name="string"` hoặc bịa quán |
| 2 | **Mâu thuẫn nội bộ** | `agents.yaml` preference nói *"KHÔNG bịa popular"*, nhưng `tasks.yaml` nói *"có thể đề xuất phổ thông"* | LLM confused, bịa gợi ý |
| 3 | **NIM-8b skip tool** | restaurant_search dùng llama-3.1-8b; khi query khớp parametric knowledge ("sushi Mộc Châu") → bỏ qua merchant_search, bịa trực tiếp | hallucination không fix được bằng prompt |
| 4 | **tool_adapter + timeout** | chỉ drop `None`, không drop `''` → `min_rating=''` fail parse; `max_execution_time:30` (cho NIM) quá thấp cho DeepSeek | ValidationError + TimeoutError |

## Fixes

| File | Change |
|---|---|
| `tasks.yaml` | Rewrite toàn bộ: bỏ mọi ngôn ngữ ép "không rỗng / relax constraint"; thêm *"tool rỗng → candidates=[], ít kết quả thật > giả"*, *"truyền constraint nguyên vẹn, không tự nới ngưỡng"*, explanation cho phép nói "không tìm thấy". Concise ~40% ngắn hơn. |
| `agents.yaml` | Trim restaurant_search backstory (DRY, bỏ lặp tool-rule đã có trong task); align preference goal *"chỉ đề xuất khi có signal"*; bump `max_iter 3→5`, `max_execution_time 30→90` (DeepSeek chậm hơn NIM). |
| `customer_crew.py` | **Bỏ NIM hybrid**: tất cả 3 specialists dùng FPT DeepSeek (NIM-8b skip tool → bịa; DeepSeek tuân tool-calling). Simplify `__init__(llm_fpt)`, xóa `_build_nim_llm`/`_llm_nim`. |
| `tool_adapter.py` | Drop `''` (empty string) kwargs ngoài `None` → fix `min_rating=''` validation error. |
| `test_customer_crew.py` + `conftest.py` | Cập nhật cho all-DeepSeek (xóa `fake_llm_nim`, test search→DeepSeek). |

## Eval (5 ground_truth cases, trước → sau)

| Case | Trước (old/NIM) | Sau (new/DeepSeek) |
|---|---|---|
| **TC-15** sushi Mộc Châu (zero-result) | ❌ bịa "2 quán sushi Mộc Châu", "Sushi Restaurant" 4.5★ | ✅ count=0, honest empty, ko bịa |
| **TC-14** rating==5.0 tuyệt đối | — | ✅ giữ constraint, 10 quán **rating 5.0 thật** (DB có — giả định empty của GT sai) |
| **TC-23** Tây Hồ 100k (noisy/code-switch) | ❌ ValidationError (stuck) | ✅ count=7 ("Bami Sot" 4.9★) |
| **TC-03** "ăn ngon" (missing-slot) | ❌ bịa "Quán Ăn Ngon/Phở 24/Sushi Zen" SG | ✅ count=0, hỏi lại khu vực |
| **TC-01** cơm Cầu Giấy <50k >4sao | — | ⚠️ count=0 (data issue, xem dưới) |

**Bug "string": FIXED hoàn toàn** (string=False trên mọi case). **Hallucination: FIXED** (q15/q03 chuyển từ bịa → honest empty).

## Còn lại (KHÔNG phải prompt/agent — data/search limitation)

**TC-01 count=0**: agent extract đúng location "Cầu Giấy" nhưng `merchant_search(city="Cầu Giấy")` trả 0 vì DB lưu `city="Hà Nội"` (district vs city granularity). Test trực tiếp tool:
- `city="Cầu Giấy"` → 0 | `city="Hà Nội"` → 5 | `city=""` → 5

Agent xử lý **đúng** (honest empty, ko bịa). Fix ở search-service: district→city mapping, hoặc fuzzy city match, hoặc search thêm field `address`. Ngoài scope prompt.

## Tests
- Full backend suite: **68/68 pass** (sau mọi thay đổi).
- YAML structure validated (agents: 3 specialists đủ keys; tasks: agent+context đúng).

## Files changed (chưa commit)
- `backend/agents/customer/config/agents.yaml` (prompt + timeout)
- `backend/agents/customer/config/tasks.yaml` (rewrite anti-hallucination)
- `backend/agents/customer/customer_crew.py` (all-DeepSeek)
- `backend/agents/tool_adapter.py` (drop empty-string)
- `backend/tests/unit/test_customer_crew.py` + `conftest.py` (all-DeepSeek)
- `backend/scripts/test_customer_quality.py` (mới — eval script)

## Unresolved
- Q1: TC-01 district-vs-city — có muốn fix search-service (district→city / fuzzy) không?
- Q2: DeepSeek over-call tools (2-3× thay vì 1) — không sai kết quả nhưng chậm (q23 108s). Có muốn thêm code-guard cap tool calls/agent không?
- Q3: missing-slot clarification (TC-03/04/16/26) hiện explanation agent tự hỏi — đủ dùng, nhưng ko có coordinator gate chính thức. Có muốn thêm relevance/clarification layer không?
- Q4: Commit đợt này?
