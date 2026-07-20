# Data Dictionary — AI Restaurant

Tài liệu mô tả toàn bộ dữ liệu đã chuẩn bị. **Đọc file này thay vì lục thư mục `data/`.**

## Nguồn sự thật (source of truth) cho Agent/UI
➡️ **`data/profiles/{merchant_id}.json`** — Merchant Profile hợp nhất, mỗi quán 1 file, TỰ CHỨA ĐỦ. Agent chỉ cần đọc file này.

## Sơ đồ thư mục `data/`
```
data/
├── shopeefood_catalog.jsonl        # [SOURCE, tracked] 3.277 record gốc crawl (raw)
├── merchants_unique.jsonl          # [gitignored] 1.681 quán unique sau dedupe (1.625 có id số)
├── crawled/{id}.json               # [gitignored, 523MB] dữ liệu crawl thô: menu+rating+reviews
├── synthetic/
│   ├── operational.jsonl           # ops metrics + delivery stats + segments (procedural, 1.625)
│   ├── hero_set.json               # 18 hero merchant + lý do chọn
│   ├── text/{id}.json              # complaints + delivery_feedback + filled_reviews (LLM, 18 hero)
│   └── model_comparison/           # output so sánh 3 model LLM (tham khảo)
├── profile_cache/
│   ├── trending_by_cluster.json    # trending dishes theo "city||cuisine"
│   ├── competitors_by_merchant.json# đối thủ gần nhất theo merchant
│   └── vision/{id}.json            # image score Vision LLM (18 hero)
└── profiles/{id}.json              # ⭐ MERCHANT PROFILE HỢP NHẤT (1.625) — đọc cái này
    └── _validation_report.json     # báo cáo kiểm tra
```

## Cấu trúc `data/profiles/{merchant_id}.json`
| Trường | Ý nghĩa |
|---|---|
| `merchant_id` | ID ShopeeFood (số) |
| `tier` | `hero` (18, dữ liệu sâu) hoặc `background` (1.607, nhẹ) |
| `overall_score` | Trung bình 8 dimension (0–1) |
| `metadata` | name, cuisine, category, location{address,lat,lng,city}, open_hours, image_url, source_url, phones, taste_tags, diet_tags |
| `price_level` | nhãn: rẻ / trung bình / cao cấp |
| `dimensions` | 8 scored dimension, mỗi cái: `{score 0-1, evidence[], basis}` |
| `attributes` | customer_segments, peak_time, competitors[], trending_dishes[], operation_kpis, delivery_stats |
| `ratings` | shopeefood_avg (0-5), shopeefood_total_review, foody_rating (0-10), foody_review_count |
| `menu` | list món: name, type, price, discount_price, total_like, has_photo (ảnh đầy đủ ở `crawled/`) |
| `reviews` | review THẬT (Foody): text + score/10 |
| `synthetic_reviews` | review bù LLM (chỉ hero thiếu <8 review) |
| `complaints` | khiếu nại synthetic (hero): category, text, severity, date |
| `delivery_feedback` | phản hồi tài xế synthetic (hero) |
| `data_sources` | ghi rõ nguồn từng nhóm dữ liệu (thật/synthetic/vision/heuristic) |

## 8 Scored Dimensions (score 0–1 + evidence)
| Dimension | Cách tính | Evidence chính |
|---|---|---|
| food_quality | rating + sentiment review + độ phổ biến món − complaint | positive/negative_review_count, top_dish_avg_likes |
| image_quality | Vision LLM (hero) HOẶC heuristic phủ ảnh HD | vision_score / dishes_with_hd_photo |
| delivery_quality | on_time_rate + driver_rating + thời gian giao − complaint trễ | on_time_rate, avg_delivery_minutes |
| packaging | packaging_ok_rate − complaint đóng gói | packaging_ok_rate, packaging_complaint_count |
| service | rating − complaint thái độ | service_complaint_count |
| waiting_time | thời gian chuẩn bị (thấp→cao điểm) − complaint trễ | avg_prep_minutes |
| menu_diversity | số món + số nhóm món | dish_count, dish_type_count |
| price_level | giá so median (city+cuisine); score = độ phù hợp túi tiền | price_ratio, price_level_label |

**Nguyên tắc:** mọi score đi kèm evidence số liệu truy vết được. Hero dùng dữ liệu thật+synthetic; background dùng rating + ops procedural.

## 5 Attributes (mô tả, không chấm điểm)
customer_segments · peak_time · competitors (id+name+dist_km, cùng cuisine ≤8km) · trending_dishes (theo cụm city+cuisine) · operation_kpis + delivery_stats.

## Pipeline tái tạo (thứ tự chạy)
```
scripts/crawl/dedupe_catalog.py          # -> merchants_unique.jsonl
scripts/crawl/crawl_merchants.py         # -> crawled/  (Playwright + Foody)
scripts/synth/generate_operational.py    # -> synthetic/operational.jsonl
scripts/synth/select_hero_set.py         # -> synthetic/hero_set.json
scripts/synth/generate_hero_batch.py     # -> synthetic/text/  (cần .env LLM)
scripts/profile/trending_and_competitors.py  # -> profile_cache/{trending,competitors}
scripts/profile/vision_image_score.py    # -> profile_cache/vision/  (cần NIM vision)
scripts/profile/build_profiles.py        # -> profiles/  ⭐
scripts/profile/validate_profiles.py     # kiểm tra
```

## Ghi chú
- Rating cũ trong catalog (`merchant_rating`) là RÁC (đã bỏ) — dùng `ratings.shopeefood_avg` thật.
- `shopeefood_total_review` chặn ở 1000 ("999+") — số chính xác thấp dùng `foody_review_count`.
- 9 quán menu rỗng = đã đóng/gỡ khỏi ShopeeFood (rating=0).
- Reviews thật chỉ ~40% quán (Foody thưa) — background thiếu review dùng rating proxy cho food_quality.

## Unresolved
- Ẩn danh tên quán khi pitch công khai? (chưa quyết)
- Có mở rộng complaints/text cho background không? (hiện chưa cần)
