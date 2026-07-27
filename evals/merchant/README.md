# Merchant Golden Dataset

`golden_dataset.jsonl` là bộ case do merchant owner duyệt trước khi dùng để
baseline hoặc tối ưu prompt.

Mỗi dòng gồm:

- `question`: câu hỏi mới nhất;
- `history`: history cần dùng cho follow-up rewrite;
- `expected_agent`: capability plan mong đợi;
- `expected_tools`: tool sequence mong đợi;
- `expected_content`: các nội dung tối thiểu phải xuất hiện;
- `tags`: search, compound, paraphrase, follow-up, privacy hoặc deferred image.

Ragas `ToolCallAccuracy` và `ToolCallF1` chấm tool sequence. Evaluator đồng thời
chấm capability F1 và content coverage, rồi giữ lại `trace_id`, token usage và
latency cho từng case.

```bash
uv run --with-requirements backend/requirements.txt \
  python3 scripts/eval/run_merchant_eval.py validate

uv run --with-requirements backend/requirements.txt \
  python3 scripts/eval/run_merchant_eval.py preview
```

`metadata.json` cố ý đặt `reviewed=false`. Không đổi cờ này và không chạy
baseline/tuning cho tới khi merchant owner xác nhận nội dung dataset.
