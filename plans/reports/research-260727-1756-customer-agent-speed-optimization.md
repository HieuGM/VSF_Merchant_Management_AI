# Research Report: Customer Agent Speed Optimization (no quality loss)

**Date:** 2026-07-27
**Focus:** Giảm thời gian chờ cho Customer Discovery Agent (CrewAI, hybrid LLM) mà không giảm chất lượng
**Context:** Median ~34s/query (từ baseline 90-100s), **LLM-bound 95%**. Đã làm: search+preference parallel (−18s), tool-output filtering, CrewAI `cache=True/respect_context_window`. FE đã SSE stream progress.

---

## Executive Summary

Wall-clock **~95% là LLM inference** → code-level micro-opt gần hết đòn bẩy. 3 hướng còn significant impact:

1. **Perceived latency (TTFT)** — stream answer token-by-token thay vì dump ở cuối. User bắt đầu đọc sau ~5s thay vì chờ 34s. **Đòn bẩy UX lớn nhất, total time không đổi nhưng cảm giác nhanh nhiều.**
2. **Prompt/context caching** — DeepSeek context cache **automatic** (prefix-based, hit rate ~98%, latency ms). Structured prompt = cache hit → cắt phần lớn prefill time của mỗi call.
3. **Skip + semantic cache** — skip `preference_task` cho query thuần tìm kiếm; cache kết quả tool/answer cho query lặp → cắt cả LLM call.

Speculative decoding (2-3× speedup, zero quality loss) là lever lớn nhất nhưng **cần kiểm soát inference server** (NVIDIA NIM self-host) — chỉ áp dụng nếu tự host model.

**Bottom line:** TTFT streaming + prompt-cache structuring = thay đổi nhỏ, tác động lớn, **rủi ro chất lượng gần 0**. Đó là nơi nên bắt đầu.

---

## Research Methodology

- Sources: 5 web searches (CrewAI perf, DeepSeek prompt cache, semantic cache, agent latency/streaming, inference speed)
- Date range: 2024-2026
- Codebase verified: `customer_flow.py`, `customer_agent_routes.py`, `customer_crew.py`, prior reports `agent-perf-optimization-260724`, `research-260724-agent-performance-optimization`

---

## Key Finding — "Two Clocks" Framework

Nghiên cứu 2025-2026 ([Kunal Ganglani](https://www.kunalganglani.com/blog/ai-agent-latency-optimization-budget), [Latitude.so](https://latitude.so/blog/real-time-llms-optimizing-latency-streaming)) nhấn mạnh **2 đồng hồ quyết định UX**:

| Clock | Định nghĩa | Ảnh hưởng |
|---|---|---|
| **TTFT** (Time To First Token) | Giây từ submit đến ký tự đầu tiên user thấy | **First impression** — quyết định "cảm giác nhanh" |
| **Total turn time** | Tổng thời gian xử lý xong | Throughput/complete |

**Hệ quả:** Giảm TTFT = cải thiện cảm giác tốc độ nhiều hơn giảm tổng thời gian. App hiện tại TTFT ≈ total time (answer chỉ xuất hiện cuối) → đây là gap lớn nhất.

**Codebase confirm:** `customer_agent_routes.py:84` — `answer_delta` emit **toàn bộ answer 1 lần** sau `crew.kickoff()` trả về. Progress events (`tool_started/finished`) có stream, nhưng **answer text thì block đến cuối**.

---

## Prioritized Recommendations (mapped to codebase)

### 🥇 Tier 1 — Perceived latency + cache (impact cao, risk thấp)

#### 1. Stream answer token-by-token (giảm TTFT cảm nhận)
**Vấn đề:** `worker()` đợi `search_restaurants` trả về full `CustomerChatResponse`, rồi mới `events.put(answer_delta)`. User chờ đủ ~34s.

**Fix:** CrewAI 1.15+ hỗ trợ streaming token qua `crew.kickoff(stream=True)` (trả generator `CrewOutput` chunks) hoặc listener `on_llm_new_token`. Stream token của **explanation agent** ra SSE ngay khi generate.

```python
# customer_agent_routes.py worker()
# Thay: response = ...; events.put(answer_delta full)
# Bằng: kickoff với stream, forward token chunks qua events.put(answer_delta, {answer: chunk})
for chunk in crew.kickoff(inputs=inputs, stream=True):  # stream này là usage_events/token
    ...  # emit token
```

Lưu ý CrewAI `stream=True` hiện trả **usage events**, không thẳng token text — cần verify API 1.15.5 exact behavior, hoặc dùng LLM-level streaming (`llm.stream`) cho explanation task rồi组装 answer. **Risk:** medium (phải giữ structured output cho results/suggestions; chỉ stream phần answer text). **Quality:** unchanged (cùng model, cùng prompt). **Perceived:** ~34s chờ → ~4-6s đến chữ đầu.

#### 2. Prompt/context cache structuring (DeepSeek automatic)
**Tìm được:** DeepSeek **Context Caching on Disk** — **enabled by default, no code change** ([docs](https://api-docs.deepseek.com/guides/kv_cache/)). Cache prefix-based (system prompt + fixed prefix), hit rate **~98%** report, **90% cheaper + ms latency** cho cached prefix. Skip prefill (= phần lớn time của long prompt).

**Codebase áp dụng:** Đảm bảo **agent backstory/system prompt là STATIC PREFIX** + đặt TRƯỚC dynamic content (query, results). Nếu FPT Cloud endpoint DeepSeek-compatible → cache tự động. Nếu không → bật tương đương.
- Kiểm tra `agents.yaml` backstories: phần cố định (role, rules, output format) lên đầu; `{query}`, `{candidates}` xuống cuối.
- Tránh build prompt mà mỗi request shuffle format → cache miss.
- **Verify:** log `usage` (`prompt_cache_hit_tokens`) từ API response để đo cache hit thực tế.

**Risk:** none. **Quality:** unchanged. **Latency:** cắt prefill time của prefix lặp (system prompt dài).

### 🥈 Tier 2 — Skip + parallel (cắt cả LLM call)

#### 3. Skip preference_task cho query thuần tìm kiếm
`preference_task` = bottleneck (per memory `customer-agent-perf.md`). Nhiều query chỉ cần search+explain ("phở gần tôi", "quán Nhật Cầu Giấy") → không cần suy luận khẩu vị.

**Fix:** Conditional routing — classify intent nhanh (rule-based hoặc cheap LLM) trước crew. Nếu pure-discovery → skip preference, search→explain trực tiếp. Chỉ chạy preference khi query có tín hiệu khẩu vị ("thích cay", "ăn chay", "cho người lớn tuổi").
- CrewAI sequential không native skip → dùng **2 crew variants** (3-task vs 2-task) hoặc pre-route ở `customer_flow.py` dựa trên query heuristic.
- **Risk:** low nếu heuristic chính (keyword/dietary detection). **Quality:** preserved cho query thuần; full path cho query phức tạp. **Latency:** −1 LLM call (~10-15s) cho majority queries.

#### 4. Confirm async_execution thật sự parallel
Đã claim search+preference parallel (−18s). **Verify** `async_execution=True` trên task + `Process.sequential` đúng chạy concurrent (CrewAI 1.15 `async_execution` flag trên Task). Đo: 2 task phải overlap timeline, không nối đuôi. Nếu chưa overlap → fix để save thêm.

#### 5. Semantic cache (tool + answer)
Repeat/similar query ("phở gần tôi" hỏi lại) → return cached, skip crew.

**Tool-layer cache (DRY, safe):** cache `merchant_search`/`nearby_merchant_search` theo (query, cuisine, lat/lng rounded, radius). Deterministic data → cache vô hạn hoặc TTL dài. [GPTCache](https://github.com/zilliztech/gptcache) hoặc Redis vector cho semantic; **in-memory dict cho exact-match** đủ cho MVP.

**Answer cache (optional):** semantic match query → reuse answer. 30-70% cost/latency cut ([Spheron](https://www.spheron.network/blog/semantic-cache-llm-inference-gpu-cloud/), [Redis blog](https://redis.io/blog/10-techniques-for-semantic-cache-optimization/)). Risk: staleness (merchant đổi) → TTL ngắn + scope theo location.

CrewAI `cache=True` đã bật nhưng **chỉ cache tool result cùng args** — semantic cache mở rộng ra "gần giống".

### 🥉 Tier 3 — Token reduction (speeds inference trực tiếp)

#### 6. Cắt candidate count + compress output
Ít token input → fast prefill + decode. `search` fetch `limit*2`, `nearby_search` fetch `limit=2000` (toàn catalog) rồi filter. Truyền top-N (10-12) vào preference/explain thay vì 20+.
- Đã filter essential fields (Phase 2). Thêm: cap `top_menu_items` per merchant (3→2), drop null fields, compact address.
- **Risk:** low nếu giữ đủ signal rank. **Quality:** preserved (agent chỉ cần top để chọn).

#### 7. Trim agent backstories
System prompt = mỗi request, ảnh hưởng prefill time. Backstory dài → chậm. Cắt backstory `agents.yaml` về essential (role + rules + format). **Bonus:** prefix ngắn + cố định = cache hit tốt hơn (xem #2).

### 🏆 Tier 4 — Inference server (lever lớn nhất, cần control infra)

#### 8. Speculative decoding (2-3× speedup, ZERO quality loss)
Draft model nhỏ predict token → target model verify. [BentoML](https://www.bentoml.com/blog/3x-faster-llm-inference-with-speculative-decoding): **2-3× faster, no quality tradeoff**. vLLM: 1.4-1.6×. [NVIDIA intro](https://developer.nvidia.com/blog/an-introduction-to-speculative-decoding-for-reducing-latency-in-ai-inference/).
- **Chỉ khả thi nếu self-host** (NVIDIA NIM / vLLM). Nếu dùng FPT Cloud API → phụ thuộc vendor có bật spec decoding không.
- **Risk:** infra change. **Quality:** mathematically lossless (reject sampling). **Latency:** −33-60%.

#### 9. Faster model cho bottleneck
`preference_task` dùng `gpt-oss-20b`. Test model nhanh hơn (DeepSeek-V4-Flash đã dùng cho explain — thử cho cả preference) xem quality giữ否. Quick A/B.

#### 10. KV cache warmup / connection keep-alive
Request đầu = cold start (model load, connection). Keep worker warm (uvicorn `--workers`, health-check ping định kỳ). HTTP keep-alive đến LLM endpoint.

---

## Comparative Analysis

| Tech | Impact (latency) | Effort | Quality risk | Áp dụng codebase này? |
|---|---|---|---|---|
| **Answer streaming (TTFT)** | 🟢🟢🟢 perceived | Medium | None | ✅ #1 priority |
| **Prompt cache structuring** | 🟢🟢 (prefix) | Low | None | ✅ free if DeepSeek-comp |
| **Skip preference_task** | 🟢🟢🟢 (−1 call) | Medium | Low (heuristic) | ✅ majority queries |
| **Async verify** | 🟢🟢 | Low | None | ✅ confirm current |
| **Tool/semantic cache** | 🟢🟢 (repeat) | Medium | Low (TTL) | ✅ |
| **Token reduction** | 🟢 | Low | Low | ✅ incremental |
| **Trim backstories** | 🟢 + cache hit | Low | None | ✅ |
| **Speculative decoding** | 🟢🟢🟢 | High (infra) | **None (lossless)** | ⚠️ cần self-host |
| **Faster model** | 🟢🟢 | Low (A/B) | Medium | ⚠️ test |

---

## Implementation Roadmap (phased)

**Phase A — Quick wins (1-2 ngày, risk thấp):**
1. Trim `agents.yaml` backstories (static prefix first) → prompt cache hit + ít token
2. Verify `async_execution` thật sự parallel (đo timeline)
3. Tool-layer exact cache cho `merchant_search`/`nearby`
4. Cap candidates truyền cho preference/explain

**Phase B — Perceived latency (2-4 ngày):**
5. Stream answer token (CrewAI stream / LLM-level stream cho explain task) → TTFT ~5s
6. Conditional skip preference_task (intent heuristic)

**Phase C — Semantic + measure (3-5 ngày):**
7. Semantic cache (GPTCache/Redis) cho answer
8. Logging: TTFT, per-task time, prompt_cache_hit_tokens, cache hit rate

**Phase D — Infra (optional, nếu self-host):**
9. Speculative decoding trên NIM/vLLM
10. Model swap A/B cho preference_task

---

## Codebase-specific Notes

- `customer_crew.py` hybrid LLM (gpt-oss-20b search/preference, DeepSeek-V4-Flash explain) — tier routing đã đúng.
- `tool_adapter.py` đã filter essential fields (Phase 2) — extend với cap count.
- `persisting_listener` + `streaming_listener` đã có event bus → dễ thêm token-stream event.
- SSE contract FE: `answer_delta` hiện replace (full answer). Nếu stream incremental → **FE hook phải accumulate** (`text: prev + chunk`) thay vì replace. **Breaking contract change** — cập nhật `use-customer-chat.ts` + FE message render.
- `nearby_search` fetch `limit=2000` (whole catalog) rồi Haversine filter trong Python — với catalog ~1681 OK, nhưng nếu grow → cân nhăng PostGIS (`<->` operator + GiST index) cho geo filter ở SQL (O(log n) vs O(n) Python loop).

---

## Common Pitfalls

- **Streaming incremental ≠ replace:** nếu stream token, FE phải accumulate; quên = mỗi chunk ghi đè → chỉ thấy token cuối. Test kỹ.
- **Cache staleness:** merchant data đổi (giờ, rating) → cache trả stale. Scope cache theo location + TTL ngắn (5-15min) cho answer; tool cache TTL dài (merchant data ít đổi).
- **Over-compression:** cắt quá → agent hallucinate/generic. Giữ min signal (name, rating, price, distance).
- **Skip heuristic sai:** skip preference khi query thật sự cần → answer kém cá nhân hóa. Conservative: chỉ skip khi HIGH confidence pure-discovery.
- **Measure before optimize:** thêm timing logging (TTFT, per-task, cache hit) TRƯỚC khi optimize, để biết lever nào thật sự tác động. Premature opt = waste.

---

## Resources & References

### Latency / Streaming / TTFT
- [AI Agent Latency Budgets: 6-Tier Framework (2026)](https://www.kunalganglani.com/blog/ai-agent-latency-optimization-budget) — TTFT vs total turn
- [Real-Time LLMs: Optimizing Latency in Streaming (Latitude.so)](https://latitude.so/blog/real-time-llms-optimizing-latency-streaming)
- [Latency Optimization in LLM Streaming (Latitude.so)](https://latitude.so/blog/latency-optimization-in-llm-streaming-key-techniques)

### Prompt / Context Caching
- [DeepSeek Context Caching (official)](https://api-docs.deepseek.com/guides/kv_cache/) — automatic, default on
- [Prompt Caching Infrastructure Guide 2025 (Introl)](https://introl.com/blog/prompt-caching-infrastructure-llm-cost-latency-reduction-guide-2025)
- [DeepSeek V4 Context Caching (Wavespeed)](https://wavespeed.ai/blog/posts/blog-deepseek-v4-context-caching/)

### Semantic Caching
- [Semantic Caching for LLM: GPTCache, Redis (Spheron)](https://www.spheron.network/blog/semantic-cache-llm-inference-gpu-cloud/)
- [GPTCache (GitHub/zilliztech)](https://github.com/zilliztech/gptcache)
- [10 Techniques for Semantic Cache Optimization (Redis)](https://redis.io/blog/10-techniques-for-semantic-cache-optimization/)
- [GPT Semantic Cache paper (arXiv)](https://arxiv.org/html/2411.05276v2)

### Inference Speed (lossless)
- [3× Faster LLM Inference with Speculative Decoding (BentoML)](https://www.bentoml.com/blog/3x-faster-llm-inference-with-speculative-decoding)
- [Intro to Speculative Decoding (NVIDIA)](https://developer.nvidia.com/blog/an-introduction-to-speculative-decoding-for-reducing-latency-in-ai-inference/)
- [LLM Inference Acceleration Guide](https://inferenceengineering.tech/llm-inference-acceleration/)

### CrewAI-specific
- [CrewAI Performance Tuning (Wednesday)](https://www.wednesday.is/writing-articles/crewai-performance-tuning-optimizing-multi-agent-systems)
- [Async Execution in Hierarchical CrewAI](https://community.crewai.com/t/async-execution-slowing-down-hierarchical-crewai-setup/6136)
- [Speed Up CrewAI Execution (community)](https://community.crewai.com/t/speed-up-the-execution/296)

---

## Unresolved Questions

1. **FPT Cloud có phải DeepSeek-compatible API không?** Nếu có → prompt cache automatic (verify `prompt_cache_hit_tokens` trong usage). Nếu là NIM/proxy riêng → cần bật cache thủ công hoặc spec decoding.
2. **CrewAI 1.15.5 `stream=True` trả token text hay chỉ usage events?** Cần test local trước khi commit FE contract change (incremental answer_delta). Có thể phải stream ở LLM-level cho explain task.
3. **Self-host hay vendor API?** Quyết định speculative decoding khả thi không (lever 2-3× lớn nhất nhưng cần control inference server).
4. **Query distribution thực tế** — bao nhiêu % là pure-discovery (skip-able) vs taste-based (cần preference)? Cần log intent để size skip optimization.
5. **Catalog có grow quá ~2000 không?** Quyết định có cần PostGIS geo filter (SQL) thay Python Haversine loop không.

---

## TL;DR Action List

1. **Stream answer (TTFT)** — perceived 34s→5s, risk chất lượng 0 *(biggest UX win)*
2. **Structure prompts cho cache hit** — trim backstory, static prefix first *(free if DeepSeek-comp)*
3. **Skip preference_task** cho pure-discovery *(−1 LLM call, ~10-15s)*
4. **Tool + semantic cache** cho repeat query *(−toàn crew)*
5. **Cap candidates + compress** *(faster inference)*
6. **Measure first** — add TTFT/per-task/cache-hit logging trước khi optimize tiếp
7. *(optional)* **Speculative decoding** nếu self-host *(2-3×, lossless)*

**Report generated:** 2026-07-27 | **Sources:** 5 web searches + codebase audit | **Confidence:** High
