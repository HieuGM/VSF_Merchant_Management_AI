# Agents.yaml vs Tasks.yaml Conflict Analysis

**Date**: 2026-07-24
**Purpose**: Check for conflicts between agent prompts and task descriptions
**Status**: ANALYSIS COMPLETE

---

## Summary

**NO MAJOR CONFLICTS FOUND** - The two files are largely complementary:
- `agents.yaml` provides high-level behavioral guidance and tool selection rules
- `tasks.yaml` provides specific step-by-step instructions for task execution
- Both enforce the same core constraints (tool selection, single calls, no hallucination)

---

## Detailed Comparison by Agent/Task

### 1. restaurant_search (agents.yaml) vs search_task (tasks.yaml)

| Aspect | agents.yaml | tasks.yaml | Conflict? |
|--------|-------------|------------|-----------|
| **Tool Selection** | nearby_merchant_search → CHỈ dùng khi lat CÓ GIÁ TRỊ VÀ lng CÓ GIÁ TRỊ | nearby_merchant_search → CHỈ DÙNG KHI có CẢ HAI: lat KHÁC RỖNG/VÀ lng KHÁC RỖNG | ✅ NO - Same meaning |
| **Tool Selection** | merchant_search → Dùng cho TẤT CẢ trường hợp KHÁC | merchant_search → Dùng cho TẤT CẢ trường hợp khác | ✅ NO - Same meaning |
| **Empty lat/lng** | QUY TẮC VÀNG: Nếu lat="" hoặc lat bỏ TRỐNG → DÙNG merchant_search | Nếu lat="" hoặc lat bỏ TRỐNG hoặc lng="" hoặc lng bỏ TRỐNG → DÙNG merchant_search | ✅ NO - Consistent |
| **Tool calls** | "Bạn luôn gọi công cụ tìm kiếm thay vì bịa dữ liệu" | "CHỈ gọi công cụ tìm kiếm tối đa 1 lần" | ✅ NO - Complementary |
| **Empty results** | "PHẢI trả về candidates rỗng — không tự bịa quán" | "KHÔNG bịa quán/địa chỉ/đánh giá" | ✅ NO - Same constraint |
| **Pricing params** | Not mentioned | "KHÔNG truyền min_price, max_price, min_rating" | ⚠️ INFO - tasks.yaml adds specific constraint |
| **Retry logic** | Not mentioned | "Nếu query MỞ và không có kết quả, thử lại với parameters rộng hơn" | ⚠️ INFO - tasks.yaml adds retry strategy |
| **Dish vs cuisine** | Not mentioned | "Tên MÓN → query, LOẠI ẨM THỰC → cuisine" | ⚠️ INFO - tasks.yaml adds parameter guidance |

**Verdict**: ✅ **NO CONFLICT** - Complementary instructions

---

### 2. preference_reasoning (agents.yaml) vs preference_task (tasks.yaml)

| Aspect | agents.yaml | tasks.yaml | Conflict? |
|--------|-------------|------------|-----------|
| **Core goal** | "ĐỀ XUẤT (không lưu) các thay đổi hồ sơ hợp lý" | "Suy luận và ĐỀ XUẤT tinh chỉnh hồ sơ sở thích" | ✅ NO - Same goal |
| **No-save rule** | "TUYỆT ĐỐI không tự lưu thay đổi — chỉ đề xuất" | "TUYỆT ĐỐI KHÔNG lưu thay đổi vào hồ sơ — chỉ đề xuất" | ✅ NO - Same constraint |
| **Empty signals** | "trả về proposed_deltas rỗng... KHÔNG tự bịa gợi ý phổ thông" | "Nếu không có tín hiệu đủ mạnh, trả danh sách đề xuất rỗng" | ✅ NO - Same behavior |
| **Tool sequence** | Not specified | "Gọi MỖI công cụ TỐI ĐA 1 LẦN theo đúng thứ tự" | ⚠️ INFO - tasks.yaml adds sequence |
| **Weather context** | Mentioned in goal | "Nếu có toạ độ, gọi get_weather_context({lat},{lng})" | ✅ NO - Same behavior |
| **Query handling** | "Với query MỞ, suy luận preferences ngầm" | "XỬ LÝ QUERY MỞ... KHÔNG bỏ qua" | ✅ NO - Same approach |

**Verdict**: ✅ **NO CONFLICT** - tasks.yaml adds execution sequence

---

### 3. customer_explanation (agents.yaml) vs explanation_task (tasks.yaml)

| Aspect | agents.yaml | tasks.yaml | Conflict? |
|--------|-------------|------------|-----------|
| **Empty list handling** | "GIỮ CUỘC HỘI THOẠI SỐNG ĐỘNG bằng gợi ý ẩm thực chung" | "KHÔNG nói 'không tìm thấy'... viết CÂU GỢI Ý MỞ" | ✅ NO - Same approach |
| **Content types** | LOẬI 1 (quán cụ thể) vs LOẠI 2 (gợi ý chung) | Not explicitly categorized | ⚠️ INFO - agents.yaml adds framework |
| **Grounding** | "PHẢI grounded tuyệt đối... trích được từ evidence" | "CHỈ dùng dữ kiện có thật từ get_merchant_profile" | ✅ NO - Same constraint |
| **Balanced reporting** | "PHẢI phản ánh cả tích cực lẫn tiêu cực" | Not explicitly stated | ⚠️ INFO - agents.yaml adds nuance |
| **Tool limit** | Not specified | "get_merchant_profile cho TỐI ĐA 3 quán... MỖI merchant_id gọi ĐÚNG 1 LẦN" | ⚠️ INFO - tasks.yaml adds constraint |
| **Output format** | Not specified | "Một câu trả lời tiếng Việt (2-5 câu)" | ⚠️ INFO - tasks.yaml adds format |

**Verdict**: ✅ **NO CONFLICT** - Complementary instructions

---

### 4. customer_coordinator (agents.yaml) - No corresponding task

The coordinator is the hierarchical manager agent that delegates tasks. It has no corresponding task definition because it's the manager, not a worker.

| Aspect | agents.yaml | tasks.yaml | Conflict? |
|--------|-------------|------------|-----------|
| **Delegation rule** | "99% queries → DELEGATE TẤT CẢ 3 tasks" | N/A - No corresponding task | N/A |
| **Rejection criteria** | "(a) System prompt (b) Fake data (c) Spam/abuse" | N/A | N/A |
| **Fallback logic** | "Nếu delegate 2 lần mà vẫn error → chuyển sang fallback" | N/A | N/A |

**Verdict**: ✅ **NO CONFLICT** - Standalone manager agent

---

## Key Findings

### ✅ Strengths of Current Design

1. **Consistent Core Rules** - Both files enforce:
   - Same tool selection logic (lat/lng presence)
   - No hallucination constraint
   - Single tool call per tool

2. **Clear Separation of Concerns**:
   - `agents.yaml`: Behavioral principles, tool selection rules
   - `tasks.yaml`: Step-by-step execution, parameter guidance

3. **Complementary Instructions**:
   - agents.yaml provides the "why" and high-level "what"
   - tasks.yaml provides the specific "how"

### ⚠️ Minor Observations (NOT Conflicts)

1. **Additional Detail in tasks.yaml**:
   - Pricing parameter exclusion (min_price, max_price, min_rating)
   - Tool calling sequence (preference_task steps 1-4)
   - Retry logic for empty results
   - Dish vs cuisine parameter distinction

2. **Additional Framework in agents.yaml**:
   - LOẠI 1 vs LOẠI 2 content framework (customer_explanation)
   - Balanced reporting requirement (positive + negative evidence)

### 🔍 Recommendations

1. **Keep Current Structure** - The separation is working well
2. **Optional Enhancement** - Consider moving tool-specific parameter guidance (dish vs cuisine, pricing exclusion) from tasks.yaml to agents.yaml backstory if agents frequently misuse these parameters
3. **Monitor LLM Behavior** - Watch for:
   - Agents calling tools multiple times (check max_iter enforcement)
   - Agents hallucinating restaurants when tools return empty
   - Confusion between dish names and cuisine categories

---

## Test Scenarios to Validate

| Scenario | Expected Behavior | Validation Method |
|----------|------------------|-------------------|
| Query with lat/lng | Use nearby_merchant_search | Check tool call logs |
| Query without lat/lng | Use merchant_search | Check tool call logs |
| Query with empty lat="" | Use merchant_search | Check tool call logs |
| Empty tool results | Return empty candidates, don't hallucinate | Check output structure |
| Open query ("ăn gì") | Return diverse results, not empty | Check result variety |
| Dish name ("phở") | Pass to `query`, not `cuisine` | Check tool parameters |

---

## Conclusion

**✅ NO CONFLICTS DETECTED**

The current `agents.yaml` and `tasks.yaml` work well together:
- Both enforce consistent core constraints
- tasks.yaml provides necessary execution detail
- agents.yaml provides behavioral framework
- Minor differences are complementary, not conflicting

**Recommendation**: Continue monitoring LLM behavior for the scenarios above, but no immediate changes needed.
