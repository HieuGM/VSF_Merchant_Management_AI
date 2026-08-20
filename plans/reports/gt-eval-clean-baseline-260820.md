# GT-eval Clean Baseline + D4 Verdict (260820)

> Đóng task P1: harness fix + multirun judge + D4 verdict. Thay kết luận cũ "23/39 = 59% , net -2 = noise".

## 1. Harness fixes (đã commit-ready trong working tree)

| Fix | File | Trước | Sau |
|---|---|---|---|
| `--out` arg | `eval_ground_truth.py` | Mỗi run OVERWRITE `gt-eval-results.json` (baseline destroyed) | Snapshot riêng từng run; default giữ compat |
| Transient retry | `eval_ground_truth.py` | FPT timeout 1 lần = case chết | Retry 1 lần sau 5s + flag `transient_error` |
| Error-skip judge | `judge_gt_quality.py` | Case errored → judge text rỗng → auto-FAIL | `pass: null` + skipped; denominator = clean cases |
| Aggregator null-safe | `aggregate-multirun-judgments.py` | `pass=None` vỡ map | Exclude khỏi cả passes lẫn totals |
| Multirun driver | `scripts/run-gt-multirun.sh` (mới) | thủ công từng bước | 3 run × 2 judge + aggregate một lệnh |

## 2. D4 GATE: **PASS** — quyết flip flag D1 = ON

So sánh per-case `gt-eval-results.pre-d1-flagon.json` vs `gt-eval-results-d1-flagon.json`
(deterministic `pred_action`, cùng logic `compute_gt_metrics`):

- routing accuracy: baseline **0.8205** (32/39) vs flag-on **0.8205** (32/39) — parity tuyệt đối
- Tập fail GIỐNG HỆT nhau: `{TC-08, TC-11, TC-16, TC-36, TC-38, TC-45, TC-46}` — 0 fail mới
- Sentinel (TC-15/16 zero-result, TC-07/24/26/35 clarify, TC-22 toneless): tất cả UNCHANGED
- Gate `accuracy ≥ 0.82 AND no new fail AND sentinels unchanged` → **PASS**

**Khuyến nghị: flip `COORDINATOR_DESCRIPTOR_EXPANSION_ENABLED=true` ở deploy** (default code giữ
OFF theo đúng thiết kế phase-01; parity + không downside = bật được). Artifact: `gt-eval-d4-verdict.json`.

## 3. Multirun (3 run × 2 judge, qwen + deepseek) — true-quality band

Chạy sau FPT outage window (run 3 lần đầu chết 16/39 case do `Connection error` — redo sạch 0/39):

```
run1: 25/32 qwen (78.1%) · 26/32 deepseek (81.2%)   [7 errored skip]
run2: 23/31 qwen (74.2%) · 25/31 deepseek (80.6%)   [8 errored skip]
run3: 26/39 qwen (66.7%) · 30/39 deepseek (76.9%)   [0 errored]
```

**Kết luận chính:**
- **True-quality band: 24-31/39 = 62-79%** (stable-pass floor 24, +borderline ceiling 31)
- Single-run 59% cũ là **đo sai**: (a) 2 FPT-timeout đếm FAIL, (b) single judge variance
  (qwen khắc khe hơn deepseek ~4-8 điểm cố định), (c) 1 run không tách được noise
- Số trung thực để ghi docs: **stable-pass 24/39 (62%), band 62-79%** — không dùng 59% nữa

### Phân tầng per-case (quan trọng hơn con số tổng)
- **STABLE-PASS 24**: hầu hết happy-path/clarify/zero-result/OOD/tone — nền chắc
- **BORDERLINE 7**: TC-02 (bún chả Đống Đa — data-thin!), TC-06, TC-22, TC-27, TC-29, TC-34, TC-36
- **STABLE-FAIL 5** (fail thật, lặp lại xuyên run + judge):
  - **TC-41** "Cái đầu tiên đó" — anaphora không resolve được referent
  - **TC-10** "Rẻ hơn nữa được không" — refinement không giữ context giá
  - **TC-25** "Quán này có ổn không?" — explanation không cite balance khen/chê
  - **TC-28** phủ định kép (không cay + không chiên + đừng quá rẻ) — search không encode negation
  - **TC-39** "Sao chỉ 1 quán" — **bịa thêm 2 quán** (confabulation — nghiêm trọng nhất)

→ Đúng 2 cluster audit đã đoán: **anaphora/prior-context** (TC-10/25/39/41) + **confabulation** (TC-39).
Đây là mục tiêu proposal #4 (fix 2 cluster), giờ có số đo để verify.

## 4. FPT outage finding (mới)

Run-3 judge 0/23 + eval 16/39 lỗi cùng cửa sổ ~12:14-12:34 = **FPT mất kết nối hoàn toàn ~20 phút**
(không phải 401-exhaustion như memory note cũ — lỗi là `Connection error`, key hồi phục ngay sau).
Ý nghĩa: multirun PHẢI chạy ban ngày tránh giờ cao tải, hoặc thêm backoff giữa run.

## Artifacts
- `gt-eval-d4-verdict.json` — per-case diff + gate verdict
- `gt-eval-results-multirun-{1,2,3}.json` — 3 snapshot sạch
- `gt-quality-judge-multirun-{1,2,3}-{qwen,deepseek}.json` — 6 verdict sets
- `gt-multirun-aggregate.json` — phân tầng stable/borderline/fail

## Unresolved
1. Flip D1 flag: cần restart backend với env mới — làm ngay hay đợi batch deploy? (khuyến nghị: gộp)
2. 5 stable-fail fix (proposal #4) — bắt đầu sau khi user chốt
3. TC-02 borderline nhưng root cause = data-thin (không merchant bún chả Đống Đa theo geo) —
   không fix bằng code search được; cân nhắc seed thêm data hoặc chấp nhận
