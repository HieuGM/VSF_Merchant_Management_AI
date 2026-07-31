# Merchant Golden Dataset

`golden_dataset.jsonl` là bộ case do merchant owner duyệt trước khi dùng để
baseline hoặc tối ưu prompt.

Mỗi dòng gồm:

- `question`: câu hỏi mới nhất;
- `history`: history cần dùng cho follow-up rewrite;
- `expected_agent`: capability nghiệp vụ mong đợi (evaluator ánh xạ sang role
  native crew như `market_search`, `cohort_analysis`, `self_analysis`);
- `expected_tools`: tool sequence mong đợi;
- `expected_content`: các nội dung tối thiểu phải xuất hiện;
- `tags`: search, compound, paraphrase, follow-up, privacy hoặc deferred image.

Ragas `ToolCallAccuracy` và `ToolCallF1` chấm tool sequence. Evaluator đồng thời
chấm role/capability F1 và content coverage, rồi giữ lại `trace_id`, token usage
và latency cho từng case. Các tên tool owner-bound của gateway được ánh xạ với
tên capability lịch sử để thay đổi policy gateway không làm sai lệch baseline.

```bash
uv run --with-requirements backend/requirements.txt \
  python3 scripts/eval/run_merchant_eval.py validate

uv run --with-requirements backend/requirements.txt \
  python3 scripts/eval/run_merchant_eval.py preview
```

`metadata.json` ghi lại review status của dataset. Runner từ chối chạy khi
`reviewed=false`; mọi thay đổi expectation phải được ghi rõ lý do và được
review lại trước khi dùng làm baseline.
