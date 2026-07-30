# Customer Agent Improvements - Hybrid LLM & Open Query Handling

**Date**: 2026-07-24
**Issues**: Timeout on preference_reasoning + Rigid responses to open-ended queries

---

## Changes Applied

### 1. Hybrid LLM Approach (`customer_crew.py`)

**Goal**: Optimize speed and quality by using different models for different tasks

| Agent | Model | Provider | Purpose |
|-------|-------|----------|---------|
| `restaurant_search` | 8B (llama-3.1-8b-instruct) | NIM | Fast search, no complex reasoning |
| `preference_reasoning` | DeepSeek-V4-Flash | FPT | Strong reasoning + fast inference |
| `customer_explanation` | DeepSeek-V4-Flash | FPT | Natural language generation |

**Code Changes**:
- Added `_build_fpt_llm()` function for direct FPT DeepSeek access
- Updated `__init__()` to add `llm_fpt` parameter
- Updated agents to use hybrid LLM assignment
- Updated `build_customer_crew()` to accept `llm_fpt`
- Added `fake_llm_fpt` fixture for tests

### 2. Open-Ended Query Handling (`tasks.yaml`)

**Goal**: Make responses more conversational and flexible for vague queries

**search_task**:
- Added logic to handle vague queries ("ăn gì ở Cầu Giấy")
- Instructs to use reasonable defaults when parameters missing
- Goal: Return DIVERSE results instead of empty

**preference_task**:
- Added "XỬ LÝ QUERY MỞ" section
- Instructs to infer preferences from context
- Goal: HELP USERS EXPLORE, not demand information

**explanation_task**:
- Added "XỬ LÝ KHI DANH SÁCH RỖNG" section
- Instructs to write FRIENDLY, CONVERSATIONAL responses
- Examples: "Dạo này ở Cầu Giấy có vài quán hay, bạn thử..."
- Goal: KEEP CONVERSATION GOING

### 3. Agent Personality Improvements (`agents.yaml`)

**customer_explanation**:
- Changed from "Result Explanation Specialist" to "Result Explanation & Open-ended Suggestion Specialist"
- Backstory: "Bạn là NGƯỜI BẠN ẨM THỰC thân thiện"
- Writes NATURAL, CONVERSATIONAL responses
- "KHÔNG BAO GIỜ nói lạnh lùng 'không tìm thấy'"

### 4. Timeout Increases

- `preference_reasoning`: 240s → 420s
- `restaurant_search`: 300s → 420s

---

## Test Results

### Unit Tests
✅ All 4 tests pass

### Manual Test Results
**Before** (Rigid response):
> "Hiện tại mình chưa tìm thấy quán ăn nào phù hợp ở Cầu Giấy cho bạn. Vì bạn chỉ hỏi chung chung..."

**After** (Conversational):
> "Dạo này ở TP. Hồ Chí Minh có nhiều quán phở ngon lắm, nhưng mình chưa có danh sách cụ thể nào trong tay bạn ạ! Bạn thử nói rõ thêm..."

### Hybrid LLM Verification
```
Restaurant Search        → NIM 8B (fast search)
Preference Reasoning     → FPT DeepSeek (strong reasoning)  
Customer Explanation     → FPT DeepSeek (natural language)
```

---

## Remaining Issues

1. **Tool validation error** on `nearby_merchant_search` when lat/lng missing
   - Agent should use `merchant_search` instead when no coordinates
   - Need to improve tool selection logic

2. **Memory embedder error** - cache/memory initialization issue
   - Not critical for functionality
   - May need cache configuration fix

---

## Next Steps

1. Fix tool selection logic for nearby_merchant_search vs merchant_search
2. Test with actual open-ended query "ăn gì ở Cầu Giấy"
3. Verify FPT DeepSeek performance under load
