# Evaluation Plan — Agent correctness & demo hardening

> Cập nhật: 2026-07-21. Maps roadmap Feature L (L-01..L-04). Nguồn: `sample-qa.md`, `demo-script.md`, design mục 5.6/11/15.
> Nguyên tắc: chấm theo **cấu trúc + evidence + guardrail**, KHÔNG so khớp chuỗi free-text.

## 0. Phân biệt benchmark và diagnostic guardrail

`backend/tests/diagnostic/test_input_routing_trace_regression.py` là regression
guardrail nhỏ, deterministic cho input routing, giới hạn công việc tool, và
contract trace live/replay. Nó dùng fixture `PreparedRequest` qua fake-analyzer
seam để test router thật, nhưng **không** gọi model/provider, không so sánh câu
trả lời tự nhiên, không tạo benchmark score, và không thay thế việc dev đọc
trace thực tế. Chạy:

```bash
conda run -n ocr python -m pytest backend/tests/diagnostic/test_input_routing_trace_regression.py -q
```

Dataset eval bên dưới là nguồn tình huống/evidence để triage và kiểm tra có
review; không được dùng một mình như thước đo chất lượng hay mục tiêu tối ưu
prompt/model.

## 1. Dataset eval (L-01)

- Cố định, versioned: `data/eval/cases.jsonl` (mỗi dòng 1 case).
- Nguồn case: `sample-qa.md` mục A–F (24 case: A×6, B×4, C×2, D×3, E×3, F×5, +1 dự phòng).
- Schema case:

```json
{
  "case_id": "A1",
  "uc": "UC-01",
  "channel": "merchant",
  "merchant_id": "233150",
  "message": "Tại sao quán tôi ít đơn?",
  "intent": "diagnosis",
  "expect": {
    "top_dimension": "waiting_time",
    "dimension_max_score": 0.2,
    "must_evidence_types": ["avg_prep_minutes"],
    "forbid_dimensions": ["packaging","delivery_quality"],
    "expect_error": null,
    "guardrails": ["no_overall_score","every_claim_has_evidence"]
  }
}
```

- Negative case (F): `expect.expect_error` = `not_found|insufficient_data|provider_error`, hoặc `guardrails:["refuse_competitor_kpi"]`.

## 2. Metrics (L-02)

| Metric | Định nghĩa | Ngưỡng pass |
|---|---|---|
| **Top-dimension accuracy** | dim yếu #1 (hoặc top-2 cho 68814) khớp `expect.top_dimension` | ≥ 0.90 |
| **Evidence resolve rate** | mọi `evidence_ref` resolve về record thật (Layer-1) | 1.00 (hard) |
| **Number fidelity** | số trích trong câu = số trong evidence record | 1.00 (hard) |
| **Forbidden-dim rate** | tỉ lệ nêu dim thuộc `forbid_dimensions` | ≤ 0.05 |
| **Guardrail pass** | no_overall_score / refuse KPI / require-confirm nhạy cảm | 1.00 (hard) |
| **Insufficient-data correctness** | negative case trả đúng error code | 1.00 (hard) |
| **Semantic grounding (Layer-2)** | claim-evidence đúng nghĩa/nhân quả (LLM judge) | ≥ 0.85 |
| **Diagnosis size** | số cause ≤ 5 | 1.00 (hard) |
| **Trace present** | có `trace_id` + agent/tool events | 1.00 (hard) |

Phụ trợ (log, không gate): latency p50/p95, token/run, tool-call count.

## 3. Chấm điểm — 2 tầng

- **Tầng tự động (deterministic):** parse structured output (Pydantic) → so `top_dimension`, resolve evidence qua evidence repository, check số, check error code, check guardrail cấu trúc (`overall_score` vắng mặt). Đây là phần gate cứng.
- **Tầng LLM-judge (semantic):** chỉ chạy trên claim đã qua tầng 1; chấm grounding + misattribution (giống Evidence Verifier Layer-2). Output pass/flag + reason.

## 4. Ground-truth per scenario (đã verify DB 2026-07-21)

| merchant | scenario | top_dimension | score | forbid (dim mạnh) |
|---|---|---|---|---|
| 233150 | slow_prep | waiting_time | 0.15 | packaging 0.91, delivery 0.70 |
| 10344 | weak_delivery | delivery_quality | 0.35 | packaging 0.96, waiting 0.75 |
| 100810 | weak_packaging | packaging | 0.30 | delivery 0.87, service 0.92 |
| 13909 | weak_food | food_quality | 0.57 | packaging 0.96, delivery 0.85 |
| 68814 | weak_service | service (top-2 với price_level) | 0.58 | delivery 0.86, packaging 0.95 |
| 2975/3752/9634 | mạnh | (none) | ≥~0.7 | → insufficient_data |

## 5. Runner (L-02/L-03)

```bash
# resettable seed
cd backend && python ../scripts/db/import_dataset.py
# chạy eval (script cần build: đọc cases.jsonl -> gọi agent API -> chấm)
python ../scripts/eval/run_eval.py --cases ../data/eval/cases.jsonl --out ../data/eval/report.json
```

Report gồm: per-case pass/fail + lý do, per-metric aggregate, latency/token, danh sách case fail để triage.

## 6. Acceptance E2E (L-04, khớp DoD design mục 18)
- [ ] 5 use-case chạy hết với fixture nhỏ (không cần full crawl).
- [ ] Mọi response có `trace_id`.
- [ ] Hard metrics = 1.00 (evidence resolve, number fidelity, guardrail, error correctness, diagnosis size, trace).
- [ ] Top-dimension accuracy ≥ 0.90; semantic grounding ≥ 0.85.
- [ ] Demo reset + rerun cho kết quả ổn định.

## 7. Regression guard (khuyến nghị)
Thêm assert scenario-invariant vào `validate_profiles.py`: đọc `SCENARIO_ASSIGN`, fail nếu `top_dimension` mỗi scenario merchant lệch bảng mục 4 (chặn `risk-log.md` R2/R3 khi rebuild). 68814 whitelist top-2.

## Unresolved
- `scripts/eval/run_eval.py` + `data/eval/cases.jsonl` chưa tạo (chờ agent API Feature G/H).
- LLM-judge dùng model nào (nên khác model sinh để giảm bias) — chưa chốt.
- Ngưỡng semantic 0.85 tạm đặt, cần calibrate sau lần chạy đầu.
