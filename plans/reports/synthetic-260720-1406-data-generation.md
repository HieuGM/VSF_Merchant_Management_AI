# Synthetic Data Report — Bổ sung dữ liệu thiếu

**Date:** 2026-07-20 | **Status:** HOÀN TẤT

## Phần A — Dữ liệu số (procedural, không LLM, toàn bộ 1.625 quán)
`data/synthetic/operational.jsonl` — 1 dòng/quán, sinh xác định (seed=merchant_id, tái lập):
- **operation_kpis**: avg_prep_minutes, cancel_rate, acceptance_rate, estimated_daily_orders, peak_hours (theo category)
- **delivery_stats**: avg_delivery_minutes, on_time_rate, driver_rating, packaging_ok_rate
- **customer_segments** (theo price + category + taste_tags), **price_level** (so median city+cuisine)
- Tất cả tương quan với rating THẬT (crawled). Miễn phí, tức thì.

## Phần B — Dữ liệu text (LLM, hero-set 18 quán)
- **Hero-set**: `data/synthetic/hero_set.json` — 5 đối thủ fast-food HCM (UC-03), 5 quán HCM rating trải 4.4–4.9 (UC-01/02), 8 quán phủ 9 thành phố (UC-04/05).
- **Output**: `data/synthetic/text/{merchant_id}.json` — 138 complaints + 90 delivery_feedback + 4 filled_reviews (chỉ 2 quán <8 review thật cần bù). Grounded trên menu/reviews/ops thật; complaints bám dimension yếu.

## So sánh 3 model LLM (3 quán mẫu × 3 model)
| Model | Avg latency | OK | Tuân thủ luật review-fill | Chất lượng |
|---|---|---|---|---|
| **fpt-deepseek** (DeepSeek-V4-Flash) ✅ CHỌN | **11.8s** | 3/3 | Đúng | Tốt, bám món thật |
| fpt-qwen (Qwen reasoning) | 22.8s | 3/3 | Đúng | Tốt |
| nim-qwen (Qwen 397B) | 97.5s | 3/3 | **Sai** (sinh thừa review khi đã đủ) | Tốt |

**Chọn fpt-deepseek**: nhanh nhất (batch 18 quán ~4.5 phút), tuân thủ luật, chất lượng ngang. Output so sánh lưu ở `data/synthetic/model_comparison/`.

**Fix kỹ thuật:** fpt-qwen là model reasoning, ban đầu đốt hết token vào `reasoning_content` → trả rỗng/JSON lỗi. Sửa bằng `/no_think` + tăng max_tokens=16000. nim-qwen chậm do model 397B.

## Files (scripts/synth/)
- `generate_operational.py` — Phần A (procedural)
- `select_hero_set.py` — chọn hero-set
- `llm_client.py` — client OpenAI-compatible, đọc `.env` (NIM/FPT), provider-agnostic
- `generate_text_data.py` — prompt + context builder + parse JSON
- `compare_models.py` — so sánh model
- `generate_hero_batch.py` — batch sinh cho hero-set

## Trạng thái dữ liệu tổng thể (sau crawl + synthetic)
| Dimension input | Nguồn | Coverage |
|---|---|---|
| Menu, giá, ảnh | Crawl thật | 99% (1.625) |
| Rating | Crawl thật | 99% |
| Reviews | Crawl thật + LLM bù (hero) | 40% thật + hero đủ |
| Complaints, delivery feedback, ops metrics | Synthetic | ops số: 100%; text: hero-set |

## Unresolved questions
- Có mở rộng sinh complaints/text cho nhóm background (ngoài hero-set) không? Hiện chưa cần (background chỉ phục vụ search).
- Ẩn danh tên quán khi pitch công khai? (vẫn mở từ phiên PRD)
- `.env` chứa key thật — đã gitignore, KHÔNG commit.
