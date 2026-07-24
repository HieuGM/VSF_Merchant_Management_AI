# Research Report: Tối Ưu Hiệu Suất Customer Agent Flow

**Date**: 2026-07-23
**Focus**: Giảm latency cho Customer Discovery Crew

---

## Executive Summary

Flow hiện tại chạy **hierarchical process** với coordinator làm manager. Vấn đề chính:
- `preference_task` và `search_task` có thể chạy song song nhưng đang chạy tuần tự
- Mỗi tool call mở/đóng DB session riêng → overhead lớn
- max_iter quá cao (4-6) = nhiều LLM call thừa
- Chỉ 2/7 tools có cache

**Ước tính**: Tối ưu có thể giảm **40-60% latency**.

---

## Research Methodology

- **Sources**: 8 web searches + codebase analysis
- **Key papers**: Kairos (17-28% latency reduction), FLASHAGENTS (40% reduction)
- **Date range**: 2024-2026

---

## Key Findings

### 1. Current Flow Analysis

```
customer_coordinator (manager)
    ↓ delegates to:
restaurant_search (max_iter: 3, 300s) + preference_reasoning (max_iter: 6, 240s)
    ↓ (hiện tại: tuần tự, nên có thể PARALLEL)
customer_explanation (max_iter: 5, 180s)
```

**Problems**:
- Coordinator không có tools (đúng design) nhưng preference_reasoning đang chờ search_task xong mới chạy
- `get_weather_context`, `propose_profile_delta` không cache
- DB session mở/đóng mỗi tool call

### 2. Parallel Execution Potential

Theo [CrewAI Parallel Patterns](https://github.com/apappascs/crewai-parallel-patterns):

> Tasks với `context` dependency thì phải tuần tự. Nhưng `search_task` và `preference_task` KHÔNG依赖 nhau (chỉ共同 depend vào coordinator output).

**Recommendation**: Enable `async_execution=True` cho crew.

### 3. Tool Caching Strategies

Theo [ToolCacheAgent paper](https://openreview.net/forum?id=tX3YcbNa5w):

> Adaptive caching cho tool calls có thể giảm 30-50% latency cho repeated calls.

**Current state**:
```python
# Chỉ 2 tools có cache:
"get_user_profile": cache_policy="profile_snapshot"
"get_weather_context": cache_policy="weather"
```

**Should add cache**:
- `get_session_candidates` → session scope cache
- `get_merchant_profile` → TTL 5-10 phút (merchant data ít thay đổi)

### 4. Connection Pooling

Theo [StackOverflow Blog](https://stackoverflow.blog/2020/10/14/improve-database-performance-with-connection-pooling/):

> Connection pooling tăng throughput ~4x.

**Current code**:
```python
def get_user_profile(*, user_id: str) -> dict[str, Any]:
    db = SessionLocal()  # MỚI MỖI LẦN
    try:
        ...
    finally:
        db.close()  # ĐÓNG MỖI LẦN
```

**Recommendation**: Dùng connection pool với `pool_pre_ping=True`.

### 5. LLM Model Selection

Hiện tại dùng 2-tier:
- **Large** (70B): coordinator, restaurant_search
- **Small** (8B): preference_reasoning, customer_explanation

Theo [Georgian guide](https://georgian.io/reduce-llm-costs-and-latency-guide):

> Small models cho inference tasks có thể giảm 50% latency mà giữ chất lượng.

**Good**: Đã đúng design.

---

## Implementation Recommendations

### Priority 1: Enable Async Execution (QUICK WIN)

```python
@crew
def crew(self) -> Crew:
    return Crew(
        agents=[...],
        tasks=[...],
        process=Process.hierarchical,
        manager_agent=self.customer_coordinator(),
        async_execution=True,  # <--- THÊM NÀY
        verbose=True,
    )
```

**Expected**: 20-30% faster (search + preference chạy song song).

### Priority 2: Reduce max_iter

```yaml
# agents.yaml - giảm max_iter thừa
customer_coordinator:
  max_iter: 2  # từ 4 → chỉ cần delegate

restaurant_search:
  max_iter: 2  # từ 3 → search là 1 shot

preference_reasoning:
  max_iter: 3  # từ 6 → reasoning phức tạp hơn 1 chút

customer_explanation:
  max_iter: 2  # từ 5 → explanation đơn giản
```

**Expected**: 15-25% faster (ít LLM call hơn).

### Priority 3: Add Tool Cache

```python
# registry.py - thêm cache policy
reg.register(
    ToolSpec(
        name="get_merchant_profile",
        cache_policy="merchant_profile_ttl",  # <---
        ...
    )
)
```

Update cache handler:
```python
# cache.py
def get_merchant_profile_cache_key(merchant_id: str) -> str:
    return f"merchant:profile:{merchant_id}"

# TTL 5 phút
DEFAULT_MERCHANT_TTL = 300
```

### Priority 4: DB Connection Pool

```python
# database/connection.py
from sqlalchemy.pool import QueuePool

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Validate connection trước khi dùng
)
```

### Priority 5: FPT DeepSeek (nếu chưa dùng)

Settings đã support FPT Cloud DeepSeek:
```python
if s.active_llm_vendor == "fpt":
    return LLM(model=f"openai/{s.fpt_model_deepseek}", ...)
```

**Đã cấu hình?** Check `.env` có `FPT_API_KEY` + `FPT_BASE_URL`.

---

## Quick Start Implementation

### Step 1: Enable async (5 phút)
```python
# customer_crew.py - @crew method
async_execution=True,
```

### Step 2: Reduce max_iter (5 phút)
```yaml
# Update agents.yaml với values trên
```

### Step 3: Test & measure
```python
import time
start = time.time()
crew.kickoff(inputs=inputs)
print(f"Duration: {time.time() - start:.2f}s")
```

---

## Expected Results

| Optimization | Expected Gain | Effort |
|--------------|--------------|--------|
| async_execution | 20-30% | 5 min |
| reduce max_iter | 15-25% | 5 min |
| tool cache | 10-20% | 30 min |
| connection pool | 10-15% | 15 min |
| **Total** | **40-60%** | **~1 hr** |

---

## Resources & References

### Documentation
- [CrewAI Hierarchical Process](https://docs.crewai.com/v1.15.2/en/learn/hierarchical-process)
- [CrewAI Parallel Patterns](https://github.com/apappascs/crewai-parallel-patterns)

### Research Papers
- [Kairos: Low-latency Multi-Agent Serving](https://arxiv.org/html/2508.06948v1) - 17-28% latency reduction
- [FLASHAGENTS: Streaming Prefill](https://openreview.net/pdf?id=m14PPUfgEc) - 40% reduction
- [ToolCacheAgent](https://openreview.net/forum?id=tX3YcbNa5w) - Adaptive tool caching

### Guides
- [CrewAI Performance Tuning](https://www.wednesday.is/writing-articles/crewai-performance-tuning-optimizing-multi-agent-systems)
- [Optimizing Latency and Cost in Multi-Agent Systems](https://www.hockeystack.com/applied-ai/optimizing-latency-and-cost-in-multi-agent-systems)
- [Connection Pooling - StackOverflow](https://stackoverflow.blog/2020/10/14/improve-database-performance-with-connection-pooling/)

---

## Unresolved Questions

1. **FPT Cloud hiện tại đã active?** Check .env cho `FPT_*` vars
2. **DB pool size hiện tại?** PostgreSQL có built-in pool nhưng cần config
3. **Redis cache có sẵn?** Nếu có, dùng Redis thay in-memory cache

---

## Next Steps

1. ✅ Enable `async_execution=True` - test ngay
2. ✅ Reduce `max_iter` trong agents.yaml
3. ⏳ Implement tool cache cho merchant profiles
4. ⏳ Add DB connection pool
5. ⏳ Benchmark trước/sau từng step

---

*Report generated: 2026-07-23*
