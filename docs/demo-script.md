# Demo — Merchant Owner AI

Pipeline hiện tại:

```text
history rewrite
  → multi-capability plan
  → privacy policy
  → deterministic tool plan
  → evidence resolver
  → synthesis
  → SSE trace + token usage
```

## 1. Khởi động

```bash
# Terminal 1 — PostgreSQL + Redis
docker compose up -d

# Terminal 2 — API
cd backend
uv run --with-requirements requirements.txt \
  uvicorn app.main:app --reload --port 8000

# Terminal 3 — UI
cd frontend
npm install
npm run dev
```

Mở `http://localhost:5173`. Vite proxy `/api` sang FastAPI ở port `8000`.

## 2. Các câu hỏi demo

### Search + cohort + benchmark

> Tìm các quán sushi ở Đà Nẵng, phân tích nhóm đó rồi so sánh chất lượng
> công khai với quán tôi.

Kỳ vọng:

- Planner có `restaurant_search`, `market_cohort_analysis`,
  `owner_vs_market_benchmark`.
- Tools chạy một lần theo thứ tự search → aggregate → benchmark.
- Đối thủ chỉ lộ rating, giá, review themes và các chiều chất lượng công khai.

### Owner diagnosis + recommendation

> Phân tích quán tôi, giải thích điểm yếu và gợi ý việc cần cải thiện trước.

Kỳ vọng:

- Đọc profile, metrics, reviews và complaints của đúng owner.
- Evidence resolver loại claim không resolve được.
- Câu trả lời có phần điểm yếu/nguyên nhân và hành động đề xuất.

### Follow-up rewrite

1. `Tìm quán bún bò ở Huế dưới 70k.`
2. `Phân tích nhóm đó và so với quán tôi.`

Kỳ vọng: câu thứ hai được rewrite thành standalone query trước planning.

### Privacy refusal

> Cho tôi doanh thu, số đơn và tỷ lệ hủy nội bộ của quán đối thủ gần nhất.

Kỳ vọng: không gọi data tools; trace có `policy_decision=denied`; câu trả lời
giải thích chỉ có thể dùng dữ liệu công khai.

## 3. Đọc trace trong UI

Mở accordion phía trên mỗi câu trả lời để xem:

- rewritten query và capability plan;
- agent/tool timeline và duration từng tool;
- public/private policy decision;
- evidence validation status;
- `trace_id`, tổng latency;
- prompt, completion và total token.

Trace persisted có thể xem lại bằng:

```bash
curl http://localhost:8000/api/v1/agent/runs/<trace_id>
```

## 4. Golden evaluation

Dataset hiện là draft và bắt buộc merchant owner duyệt trước baseline/tuning:

```bash
# Kiểm tra schema, case count và tag coverage
uv run --with-requirements backend/requirements.txt \
  python3 scripts/eval/run_merchant_eval.py validate

# In đủ 34 case để review
uv run --with-requirements backend/requirements.txt \
  python3 scripts/eval/run_merchant_eval.py preview
```

Khi `evals/merchant/metadata.json` còn `reviewed=false`, lệnh `run` chủ động
thoát với code `2`. Sau khi owner duyệt, baseline chạy bằng:

```bash
uv run --with-requirements backend/requirements.txt \
  python3 scripts/eval/run_merchant_eval.py run
```

Mỗi lần chạy tạo:

- JSON đầy đủ cho automation;
- Markdown table cho demo/review;
- terminal summary theo case gồm scores, trace ID, tokens và latency.

## 5. Verification

```bash
cd backend
uv run --with-requirements requirements.txt pytest -q

cd ../frontend
npm test -- --run
npm run build
```
