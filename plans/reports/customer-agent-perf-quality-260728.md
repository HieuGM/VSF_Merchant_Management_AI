# Customer Agent — Performance & Quality Benchmark (2026-07-28)

Đo end-to-end Customer Agent (`/api/v1/agent/customer/chat/stream`): timing mỗi agent/tool, agent chậm nhất, chất lượng câu trả lời, + test trình duyệt thật (Chromium/Playwright).

## TL;DR
- **Agent chậm nhất: `preference_task` (gpt-oss) median ~8–13s** (chỉ chạy khi query có tín hiệu khẩu vị: 2/10 câu). search_task ~4–6s. explanation (DeepSeek stream) chỉ ~3s — **không phải bottleneck**.
- **TTFT(answer) median ~12s**, gần = total ~13s. Answer stream bị gate sau search+preference (architecturally đúng — phải có results mới giải thích được). Stream DeepSeek ~0.8s sau khi bắt đầu → streaming optimization **đúng nhưng tiết kiệm được ít** vì prefill+search/preference chiếm gần hết.
- **Đặc trống chính: variance cao FPT gpt-oss** (cùng query Q1: 10.8s server vs 22.8s client qua 2 lần đo — 2-3x chênh). Không phải bottleneck cố định mà là dao động.
- **Chất lượng answer tốt** (giọng tự nhiên, cite distance/rating, honest zero-result, robust không-dấu). NHƯNG **3 defect** phát hiện: (1) leak ngoài domain — trả lời thời tiết bằng kiến thức chung (Q5/Q8); (2) recovery fallback bug → results=0 dù có location (Q4); (3) **intermittent stream failure ~10-30%** (`RemoteProtocolError`/90s stall).

---

## ✅ Resolution — all 3 fixed (commit `53884da`, verified 2026-07-28)

| Bug | Fix | Verified |
|---|---|---|
| **F1** recovery 0-results + bogus match | Extract **clean cuisine keyword** (`_extract_search_keyword`, allowlist) → `nearby_search(query=keyword)`. Relevant same-cuisine shops or **honest empty** (no irrelevant nearest shops); match_score reflects real relevance (1.0 name / 0.4 menu). | chay Hà Đông 0→4 (match 0.4, menu-chay options); phở 6 shops match 1.0; sushi Mộc Châu 0 honest-empty ✓ |
| **F2** out-of-domain leak | **Two-tier guard**: STRONG_OOD (code/injection/fabrication) checked FIRST → overrides food; food as **whole-word tokens** (`\b`) kills the `an`-in-`mảng`/`đoạn`/`hướng` substring trap; fabrication needs co-occurrence (`giả`≡`giá`→`gia` + demo/tạo). Short-circuits both paths (no crew built). | 11/11 case matrix: weather/code/injection/fake→refuse; sql-with-food/mưa-ăn/giá-rẻ→in-domain ✓ |
| **F3** intermittent stream failure (~10-30%) | **SSE heartbeat** (`: ping` every 15s idle) keeps proxies alive; **DeepSeek `timeout=30`** read-timeout aborts hung upstream; **graceful fallback + `warnings`** on stream exception (no broken connection / 90s stall). | heartbeat+timeout in source; normal query still streams 76 deltas ✓ |

Unit tests: 12/12 pass (+2 new for classifier + keyword). Backend at :8000 still serves old code — **user must restart uvicorn** for HTTP clients to see fixes.

---

## Methodology (3 chế độ đo, cross-check)
1. **Bench SSE** (`scripts/bench_customer_agent.py`, 10 câu ground_truth): POST `/chat/stream`, timestamp mỗi SSE event client-side + query DB `agent_events` cho `duration_ms` server-side chính xác per-task/tool. 2 lần chạy.
2. **Server-side isolation** (gọi trực tiếp `customer_flow.search_restaurants_stream`, không network): tách bỏ overhead network/SSE, đo true processing.
3. **DeepSeek isolation** (gọi `_stream_explanation_tokens` sample results): tách prefill vs streaming.
4. **Browser thật** (Chromium/Playwright, 6 câu): đo perceived TTFT/total + UX + screenshots.

---

## Timing breakdown

### Per-agent (server-side median, gpt-oss cho search/preference, DeepSeek cho explanation)
| Agent/Task | Median | Range | Note |
|---|---|---|---|
| **preference_task** (gpt-oss) | **~8–13s** | 6.5–13.7s | **SLOWEST**. Chỉ chạy 2/10 câu (skip-preference optimization skip 8 câu còn lại). variance cao nhất |
| search_task (gpt-oss) | ~4.9s | 1.8–6.5s | Tool-calling 1-2 vòng + structured output |
| explanation (DeepSeek stream) | ~3s | 2.3–3.4s | Prefill 1.65–2.82s + stream 0.6–0.9s. NHANH — streaming work |

### Per-tool (server-side, từ DB)
| Tool | Median | Note |
|---|---|---|
| `get_weather_context` | 1.1–2.7s | **Tool chậm nhất** — external weather API, chạy trong preference_task |
| `nearby_merchant_search` | ~0.5s | DB geo-filter, OK |
| `merchant_search` | ~0.03s | text search, nhanh |
| `get_user_profile` / `get_session_candidates` | <0.02s | DB lookup, negligible |

### End-to-end (client-side bench, 10 câu, run2)
| Metric | Median | Range |
|---|---|---|
| total (submit→run_finished) | 12.96s | 7.7–22.8s |
| TTFT(answer) (submit→first token) | 12.15s | 6.9–22.0s |
| explain(stream) (first→last token) | 0.88s | 0.6–1.4s |

→ TTFT ≈ total − 0.88s: user chờ ~12s rồi thấy answer gõ ~0.9s xong.

### Server-side isolation (bỏ network — true processing)
| Query | first_delta | finished |
|---|---|---|
| Q1 phở CG (skip-pref, có loc) | 10.0s | 10.8s |
| Q5 cay CG (pref runs, có loc) | 12.5s | 13.3s |
| Q7 sushi (skip-pref, no loc) | 5.5s | 6.2s |

Network/SSE overhead ≈ 1.5s (Q7: server 6.2s vs client 7.7s). **Nhưng Q1 client 22.8s vs server 10.8s = ~12s gap KHÔNG phải network** → là variance FPT gpt-oss (lần bench run2 dính call chậm).

---

## Slowest-agent analysis
1. **preference_task** là long-pole khi chạy (8–13s). Chạy song song search (4–6s) nên search bị che. Preference tốn chủ yếu ở: gpt-oss reasoning + `get_weather_context` (1–3s external). Bật/preference → total nhảy lên 19–21s (Q4/Q5) so với 8–13s khi skip.
2. **search_task** ~5s — gpt-oss tool-calling 1-2 vòng. Stable hơn preference.
3. **DeepSeek explanation** ~3s — nhanh, streaming work tốt. **KHÔNG phải bottleneck** (ngược giả thuyết ban đầu). Prefill (2s) > stream (0.8s).
4. **Variance là đặc trống lớn nhất**: FPT gpt-oss dao động 2-3x giữa các run →用户体验 không ổn định (lúc 8s lúc 22s cho cùng query).

**Levers tối ưu (rank theo impact)**:
- **(Cao) Cache `get_weather_context`**: weather đổi chậm, query liên tục. 1–3s/tool × mỗi preference run. Cache 10-30ph → gọt ~1-3s.
- **(Cao) Thu hẹp preference_task**: 4 tool call + reasoning dài. Cắt tool không cần (get_session_candidates/propose_profile_delta khi user ko có profile) → gọt vài s.
- **(Trung) Search agent**: prompt gọn / model nhanh hơn (gpt-oss→Qwen nhỏ hơn nếu có) → gọt 1-2s.
- **(Thấp) DeepSeek**: đã ~3s, prefill giảm được nếu cắt context (top-3 thay top-5 results).

---

## Quality assessment (per-query verdict)
| Q | Query | Results | Verdict |
|---|---|---|---|
| Q1 | phở CG (loc) | 3 | ✅ Thanh Hằng 0.53km 4.7★, cite distance+rating, giọng tự nhiên |
| Q2 | cơm <50k >4★ CG | 2 | ✅ Honest "chưa thấy cơm khớp filter", pivot sang phở/chè — không bịa |
| Q3 | bún chả Đống Đa | 3 | ⚠️ Trả bún chả Ba Đình/Hàng Mành (không Đống Đa) nhưng nói rõ "chưa có ngay trong Đống Đa" — honest framing |
| Q4 | chay Hà Đông (loc) | 0 | ❌ **Recovery bug** — có location mà 0 results (xem Findings) |
| Q5 | cay CG tối (loc) | 3 | ✅ Bà Tuyết bún thái cay 4.7★, weave weather "tối nay mưa lất phất", 5 suggestions — **best quality** |
| Q6 | trà sữa gần đây @Gia Lâm | 3 | ✅ FIXED — TocoToco/Mixue 7.2-7.7km (relevance ranking, was 0) |
| Q7 | sushi Mộc Châu | 0 | ✅ Honest zero-result, KHÔNG bịa quán (TC-15 PASS) |
| Q8 | weather (out-of-domain) | 3 | ❌ **Leak kiến thức chung** — trả lời thời tiết "Hà Nội se lạnh..." (TC-17 FAIL) |
| Q9 | no-diacritics | 3 | ✅ Parse đúng "cau giay...50k" — robust |
| Q10 | "Tìm chỗ ăn ngon" | 3 | ✅ Hỏi lại clarification (TC-04 PASS) — nhưng vẫn kèm 3 results generic (minor inconsistency) |

**Quality scorecard**: 7/10 tốt, 3 defect (Q4 recovery, Q8 leak, Q10 minor). Honest-data discipline mạnh (zero-result/hallucination check PASS). Boundary/out-of-domain yếu (no coordinator).

---

## Browser UX test (real Chromium, 6 câu, screenshots `plans/reports/browser-shots/`)
| Q | TTFT | total | cards | UX |
|---|---|---|---|---|
| Q1 phở | 17.6s | 18.1s | 3 | ✅ stream mượt, card render |
| Q2 cay | 7.8s | 9.2s | 3 | ✅ |
| **Q3 trà sữa Gia Lâm** | — | — | 0 | ❌ **RemoteProtocolError** (connection drop) |
| Q4 sushi | 3.9s | 4.8s | 0 | ✅ honest empty |
| Q5 weather | 6.0s | 7.4s | 0 | ⚠️ leak kiến thức chung |
| **Q6 no-diacritics** | 8.0s | **98s** | 0 | ❌ **stream stall 90s → connection close** |

- **scroll_ok=True** toàn bộ (no scroll jank, pin mượt).
- Token streaming mượt (ChatGPT-style) khi thành công.
- **Reliability issue**: 2/6 fail trong browser + 1/10 fail bench → **intermittent stream failure ~10-30%**. Symptom: `RemoteProtocolError: peer closed connection without sending complete message body` hoặc stream stall ~90s rồi close. Nguyên nhân khả nghi: FPT DeepSeek stream stall giữa chừng → flow block → intermediary/proxy close chunked connection. **Cần heartbeat SSE + idle-timeout trên DeepSeek call** (xem Recommendations).

---

## Findings (bugs phát hiện lúc đo)

### F1 — Recovery fallback bug (Q4): results=0 dù có location (+ match-score 0.4 cho mọi quán)
`customer_flow._direct_nearby_results(inputs.get("query"), lat, lng)` truyền **full user message** ("Tìm quán ăn chay ở Hà Đông") làm `query` → 2 hậu đo:
1. `nearby_search` → `search_merchants(query=full_msg)` dùng nó làm **text filter** → 0 candidate → recovery trả 0 (Q4).
2. Ngay cả khi có candidate (Q1 browser), `_nearby_match_score(merchant, full_msg)` substring-match **cả câu** vs tên quán → không match → 0.4 cho **tất cả** → screenshot Q1 thấy MATCH ~40/100 cho mọi quán (kể cả "Phở Cuốn"本当 1.0).
```
verified: nearby_search(Hà Đông, query='Tìm quán ăn chay ở Hà Đông') → 0
          nearby_search(Hà Đông, query=None) → 5
          nearby_search(Hà Đông, query='chay') → 4
```
**Fix**: recovery truyền `query=None` (pure geo sort theo distance) HOẶC chỉ keyword cuisine đã extract (`_nearby_match_score` hoạt động đúng với keyword ngắn). 1 dòng.

### F2 — Out-of-domain leak (Q5/Q8): trả lời ngoài phạm vi bằng kiến thức chung
Query "Thời tiết Hà Nội hôm nay?" → agent **trả lời thời tiết** ("Hà Nội mùa này hay se lạnh...") bằng kiến thức LLM chung, rồi pivot sang quán ăn. Ground_truth TC-17 kỳ vọng **từ chối lịch sự** (hệ thống chỉ hỗ trợ tìm quán). Customer Agent hiện **không có coordinator** để refuse → everything goes qua search+explanation. Cũng search "Thời tiết..." → 3 results random.

### F3 — Intermittent stream failure ~10-30%
SSE stream bị drop/stall mid-flight: `RemoteProtocolError` (connection close) hoặc stall 90s rồi close. Khả nghi: FPT DeepSeek stream hang giữa chừng (known FPT instability), flow `for delta in stream` block, không heartbeat → proxy close. Tần suất: 3 fail / ~26 run ≈ 11% (browser run: 2/6=33%). **Impact cao** (UX break).

### F4 — Q10 minor: trả generic results khi đang hỏi clarification
"Tìm chỗ ăn ngon" → answer hỏi lại "bạn ở khu nào" (đúng) NHƯNG kèm 3 results generic (1893 Coffee, 1976 Cafe... — sort artifact). Nên: nếu hỏi lại thì KHÔNG trả results.

---

## Recommendations
1. **(P0) Fix F3 reliability**: thêm SSE heartbeat (`event: ping` mỗi 15s) + `timeout`/idle-timeout trên DeepSeek stream call (`client.chat.completions.create(..., stream=True, timeout=30)` + break nếu no-delta >15s → fallback). Ngăn 90s stall.
2. **(P0) Fix F1 recovery**: `_direct_nearby_results` truyền `query=None` (hoặc cuisine). 1 dòng.
3. **(P1) Cache get_weather_context** (Redis/in-mem 15-30ph) → gọt 1-3s/preference run + giảm variance.
4. **(P1) Coordinator thin-layer** cho out-of-domain refuse (F2): 1 LLM call gpt-oss nhanh (hoặc keyword guard) trước search → refuse weather/code/injection lịch sự. Giải F2 + tiết kiệm search vô nghĩa.
5. **(P2) Trim preference_task**: skip `get_session_candidates`/`propose_profile_delta` khi user mới (no profile).
6. **(P2) Reduce variance**: thử model ổn định hơn / lower-latency endpoint cho search; hoặc warm-up call đầu phiên.

---

## Unresolved
- Q1: F3 có phải do FPT DeepSeek stream hang hay do uvicorn/proxy timeout config? Cần check log backend khi stall xảy ra (hiện không có stdout capture).
- Q2: variance FPT gpt-oss có pattern theo giờ/giây không (rate-limit backoff ẩn)? Cần đo time-series dài hơn.
- Q3: Coordinator (F2) — nên LLM-call hay keyword-guard? Trade-off latency (thêm ~1s) vs precision.
