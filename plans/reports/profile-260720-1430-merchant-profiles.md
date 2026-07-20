# Merchant Profile Build Report

**Date:** 2026-07-20 | **Status:** HOÀN TẤT — validated PASS

## Deliverable
`data/profiles/{merchant_id}.json` — **1.625 Merchant Profile hợp nhất, tự chứa đủ**. Agent/UI đọc thẳng, không cần lục file rời. Cấu trúc đầy đủ tại `docs/data-dictionary.md`.

## Nội dung mỗi profile
metadata · tier (hero/background) · overall_score · **8 dimensions** (score 0-1 + evidence + basis) · **5 attributes** (segments, peak_time, competitors, trending, ops/delivery) · ratings · menu (trimmed) · reviews (thật + synthetic) · complaints + delivery_feedback (hero) · data_sources.

## Validation (PASS)
| Kiểm tra | Kết quả |
|---|---|
| Tổng profiles | 1.625 (18 hero, 1.607 background) |
| Vision image score (hero) | 18/18 |
| Lỗi chặn (missing/range/evidence) | 0 |
| Competitor tham chiếu hỏng | 0 |
| Trending rỗng | 0 |
| Thiếu tọa độ | 0 |
| Empty menu | 9 (quán đã đóng) |

Dimension basis: food_quality 654 hero/reviews + 971 rating proxy; image_quality 18 vision + 1607 heuristic; 6 dimension còn lại 100% từ ops/menu/rating.

## Thành phần đã build (scripts/profile/)
- `trending_and_competitors.py` — trending theo cụm (194) + competitors geo≤8km cùng cuisine (1.528 quán có đối thủ)
- `dimension_scoring.py` — hàm thuần tính 8 dimension + evidence
- `vision_image_score.py` — Vision LLM (nim-qwen, model duy nhất hỗ trợ ảnh; deepseek 500) chấm 18 hero, điểm 0.62–0.95
- `build_profiles.py` — hợp nhất mọi nguồn → profiles
- `validate_profiles.py` — kiểm tra kỹ

## Vision note
Chỉ nim-qwen (Qwen 397B) nhận ảnh; fpt-deepseek trả 500. Vision ~90s/quán, 3 ảnh phổ biến nhất/quán, 1 call. Điểm phân hóa tốt: chuỗi ảnh studio 0.85-0.95, quán nhỏ 0.62-0.76.

## Git
- Ignored (lớn/tái tạo): `data/profiles/` (33M), `data/crawled/` (523M).
- Tracked (nhỏ, tốn LLM để tạo lại): `data/synthetic/`, `data/profile_cache/`.
- Rebuild profiles: `python scripts/profile/build_profiles.py` (cần crawled+synthetic local).

## Unresolved
- Ẩn danh tên quán khi pitch? (chưa quyết)
- Trending cụm "Món Việt" hơi nhiễu trà sữa (do merchant tag cuisine rộng) — chấp nhận cho demo, tinh chỉnh sau nếu cần.
- Mở rộng complaints/text cho background? Hiện chưa cần.
