# Path A Phase 2+3 Verdict — Search-log analysis + FPT embedding probe (260820)

> Đóng phase-02 (D2) + phase-03 (D3) của plan `260811-1431-hybrid-search-yagni-coordinator-expansion`.
> Câu hỏi cần trả lời: **có nên xây vector leg không?** Trả lời bằng data, không cảm tính.

## D3 — FPT embedding probe: ✅ AUTHORIZED, 2 model dùng được

Probe script gốc sai model ids (candidate list đoán `bge-m3`, `text-embedding-3-*` → 404 hết).
`models.list()` cho key hiện tại lộ **thật**:

| Model | dim | Latency batch-8 | Ghi chú |
|---|---|---|---|
| `Vietnamese_Embedding` | 1024 | ~11s | Chậm kinh khủng; phân biệt match/non-match TỐT (0.49 vs 0.43) |
| `multilingual-e5-large` | 1024 | ~0.25s (không prefix) / ~11s (2 call có prefix) | Nhanh; score nén 0.80-0.87, KHÔNG phân biệt được match vs non-match |

Sanity-check cặp query~passage (`bún chả` ~ `Bún Chả Đường Láng` vs `Phở Thìn`):
- `Vietnamese_Embedding`: match 0.49 / non-match 0.43 → margin +0.07 (dùng được, cần threshold calibrate).
- `multilingual-e5-large`: 0.859 / 0.847 (đã thử đủ prefix `query:`/`passage:` đúng spec e5) → margin +0.01, **không phân biệt nổi** — loại.

Kèm theo: `bge-reranker-v2-m3` cũng có sẵn trên endpoint (option rerank tương lai, chưa cần).

## D2 — Search-log analysis (412 rows, 2026-08-11 → 08-20): KHÔNG có recall gap thật

Phân loại 108 zero-result rows (22 distinct calls) — 3 vòng verify, mỗi vòng chặt hơn:

| Vòng | recall-gap | data-thin | Ghi chú |
|---|---|---|---|
| 1. Substring thô | 14 | 4 | Match "Hanoi" không khớp "ha noi" (fold giữ khoảng trắng) |
| 2. Production semantics (city OR address, phrase) | 4 | 14 | Loại false-gap do city |
| 3. Reproduce trên repo + service THẬT | **0** | 18 | 4 gap còn lại đều trả kết quả khi gọi lại |

**Root cause 4 "gap" vòng-2**: tái hiện được — gọi service với profile eval-case-3.2
(allergen seafood + note "an chay truong") → `chay` constraint hard-filter-zero mọi query
thường (`cay`: 5→0, `trưa`: 5→0, `sang trọng`: 2→0, `lẩu`: 5→1). Đó là **L1 safety filter
hoạt động ĐÚNG thiết kế**, không phải miss của keyword leg. Log thời điểm 08-13 10:28-10:45
trùng khớp cửa sổ chạy memory-eval live E2E.

Phân bố cuối: **noise 83 rows (test queries) · data-thin 20 · constraint-filtered (by-design) 5 · recall-gap 0**.

Zero-result thật = **data-thin** (không có merchant thỏa): `sushi Mộc Châu`, `chay Cầu Giấy`,
`com văn phòng Mỹ Đình ≤40k`, `lẩu hải sản Hà Đông r5km`, `đồ ăn 200 calo`, `pho thin Hanoi`
(fold "ha noi" ≠ query "hanoi" — note nhỏ bên dưới), `korean Gia Lâm`, `đồ thuần Việt Gia Lâm`.

### Đáng chú ý ngoài recall
1. **Folding "hanoi" vs "ha noi"**: user gõ `city="Hanoi"` (không khoảng trắng) sẽ miss
   toàn bộ `Hà Nội` (fold → `ha noi`). Production hợp nhất qua `_norm_text` cả 2 phía nên
   chỉ lỗi khi user gõ tên city không dấu + không khoảng trắng → coordinator LLM đang truyền
   `city="Hanoi"` thô. Fix rẻ: normalize khoảng trắng khi fold city ở coordinator/tool args.
2. **Timeout 15s của search_task** (thấy trong lỗi run eval): FPT chậm lúc cao tải →
   5-7 case/run eval bị `execution timed out after 15 seconds`. Đây là infra, không phải recall.

## VERDICT: ĐÓNG vector leg ( Path A hoàn tất, không mở P2.5)

Lý do dựa trên data (đúng tinh thần YAGNI của plan gốc):
1. **0 recall-gap thật trong 412 calls / 1+ tuần** — catalog-keyword leg không bỏ sót merchant
   nào tìm được. Chân ác (TC-02 'bún chả Đống Đa') là **data-thin theo geo+city**, vector
   không cứu được merchant không tồn tại.
2. Model embedding VN duy nhất phân biệt được (`Vietnamese_Embedding`) có latency **~11s/batch**
   — thêm vào search path là giết UX (hiện tổng median ~15s đã căng).
3. `multilingual-e5-large` nhanh nhưng score match≈non-match (margin 0.01) — không dùng làm
   recall leg được.

Điều kiện tái mở (ghi lại cho tương lai): catalog merchant tăng >5k, hoặc có data
zero-result thật với merchant-match xác nhận (probe như vòng-2 của analysis này), hoặc FPT
ra embedding model VN nhanh hơn.

## Artifacts
- `plans/reports/search-log-analysis-260820.json` — full classification 22 calls
- Probe outputs: trong session log (models.list + 2 model sanity)

## Unresolved
1. `city` normalization ("Hanoi"→"ha noi") — fix 30 phút ở tool-arg sanitize, có nên gộp
   vào batch sau không? (đề xuất: có, độc lập với vector verdict)
2. Timeout 15s search_task: tăng lên 25-30s khi FPT chậm? (đề xuất: retry một lần đã có ở
   harness; server-side giữ nguyên — tăng timeout làm tăng p95)
