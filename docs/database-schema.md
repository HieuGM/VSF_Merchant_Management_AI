# Database Schema — AI Restaurant

Schema Postgres (as-built). Định nghĩa gốc: `backend/database/models.py` (SQLAlchemy). Nạp dữ liệu: `scripts/db/import_dataset.py` (idempotent: `create_all` → `TRUNCATE ... RESTART IDENTITY CASCADE` → bulk insert). Chi tiết field nghiệp vụ + pipeline xem [`data-pipeline-and-dictionary.md`](./data-pipeline-and-dictionary.md).

## Tổng quan

- **10 bảng.** 7 bảng được import từ dataset đã chuẩn bị; 3 bảng (`user_profiles`, `chat_sessions`, `chat_messages`) là **runtime** — trống cho tới khi app dùng.
- **~208k row** sau import (dry-run thật):

| Bảng | Row | Nguồn |
|---|---|---|
| `merchants` | 1.625 | profiles.jsonl → metadata |
| `operational_metrics` | 1.625 | profiles.jsonl → operation_kpis |
| `merchant_profiles` | 1.625 | profiles.jsonl → dimensions/attributes/ratings (JSONB) |
| `reviews` | 4.391 | profiles.jsonl → reviews (thật) + synthetic_reviews |
| `delivery_feedbacks` | 90 | profiles.jsonl → delivery_feedback (18 hero × 5) |
| `menu_items` | 99.396 | crawled/*.json (menu đầy đủ) |
| `food_images` | 99.396 | crawled/*.json (1 ảnh đại diện/món) |
| `user_profiles` / `chat_sessions` / `chat_messages` | 0 | runtime (app tạo) |

> `--core-only` bỏ qua `menu_items` + `food_images` (2 bảng nặng) → chỉ 5 bảng lõi.

## Quan hệ (ER)

```
merchants (1) ─┬─< menu_items (N) ─< food_images (N)
               ├─< reviews (N)
               ├─< delivery_feedbacks (N)
               ├─< food_images (N)          [FK trực tiếp merchant_id]
               ├─1 operational_metrics       [PK = merchant_id]
               └─1 merchant_profiles         [PK = merchant_id]

user_profiles (1) ─< chat_sessions (N) ─< chat_messages (N)   [runtime, tách biệt]
```
Mọi FK con của `merchants` là `ON DELETE CASCADE`; `food_images.item_id` là `ON DELETE SET NULL`.

## Bảng import (7)

### `merchants` — PK `merchant_id` (String)
| Cột | Kiểu | Null | As-built |
|---|---|---|---|
| `merchant_id` | String | PK | ID ShopeeFood (số dạng chuỗi) |
| `name` | String | không | |
| `cuisine` | String | không | fallback `"N/A"` nếu thiếu |
| `address` `lat` `lng` | String/Float/Float | có | vị trí |
| `open_hours` | JSONB | có | `{open, close}` |
| `city` `city_slug` | String | không | slug suy từ city nếu catalog thiếu |
| `source` | String | mặc định `shopeefood` | |
| `source_url` | String | có | |
| `is_demo_target` | Integer | mặc định 0 | **1 = hero** (18 quán demo), 0 = background |
| `created_at` | TIMESTAMP | server default | |

### `operational_metrics` — PK `merchant_id`
| Cột | Kiểu | As-built |
|---|---|---|
| `avg_prep_time_min` | Float | từ `operation_kpis.avg_prep_minutes`, mặc định 12.0 |
| `peak_hours` | JSONB | mảng khung giờ |

> ⚠️ Chỉ 2 metric vào bảng riêng. Các ops khác (`cancel_rate`, `on_time_rate`, `driver_rating`, `packaging_ok_rate`…) nằm trong `merchant_profiles.dimensions_json.attributes`, KHÔNG có cột riêng.

### `merchant_profiles` — PK `merchant_id`
| Cột | Kiểu | As-built |
|---|---|---|
| `dimensions_json` | JSONB | không null. Chứa `{overall_score, tier, price_level, dimensions{8}, attributes, ratings}` — **nguồn chính cho Agent** |
| `updated_at` | TIMESTAMP | server default |

### `reviews` — PK `review_id`
`review_id` = `{mid}_rv{i}` (thật) hoặc `{mid}_srv{i}` (synthetic).
| Cột | Kiểu | Null | As-built |
|---|---|---|---|
| `merchant_id` | String FK | không | |
| `rating` | Float | có | thang 0–10 (giữ nguyên score gốc) |
| `text` | String | không | |
| `sentiment` | String | CHECK `positive/negative/neutral` | map từ score: ≥7 pos, <5 neg, else neutral |
| `source_page` | String | có | `foody` (thật) / `synthetic` (bù) |
| `total_like` | Integer | mặc định 0 | import để 0 |
| `created_at` | TIMESTAMP | không | = thời điểm import |
| `foody_restaurant_id` `author_id` `author_name` `total_comment` `total_pictures` `review_url` `comments_json` | — | có | **NULL as-built** (schema teammate dự phòng, import chưa đổ) |

### `delivery_feedbacks` — PK `feedback_id` (`{mid}_df{i}`)
| Cột | Kiểu | As-built |
|---|---|---|
| `merchant_id` | String FK | |
| `driver_id` | String | `drv_{mid}_{i}` (giả lập) |
| `rating` | Integer | CHECK 1–5; map `on_time=true→5`, `false→3` |
| `comment` | String | text phản hồi tài xế |
| `created_at` | TIMESTAMP | = thời điểm import |

### `menu_items` — PK `item_id` (`{mid}::{dish_id}`)
| Cột | Kiểu | Null | As-built |
|---|---|---|---|
| `merchant_id` | String FK | không | |
| `name` | String | không | |
| `price` | Integer | không | 0 nếu thiếu |
| `description` `category` `image_url` | String | có | category = dish_type_name |
| `diet_tags` `ingredient_tags` `taste_tags` | JSONB | có | tag mức merchant (catalog) |

### `food_images` — PK `image_id` (`img_{item_id}`)
| Cột | Kiểu | Null | As-built |
|---|---|---|---|
| `merchant_id` | String FK | không | |
| `item_id` | String FK (SET NULL) | có | |
| `url` | String | không | 1 ảnh đại diện/món |
| `dish_image_quality` | Float | có | CHECK 0–1; **NULL as-built** (vision score chưa map vào bảng này) |
| `logo_quality` `blur_score` | Float | có | CHECK 0–1; **NULL as-built** |

## Bảng runtime (3) — chưa import
`user_profiles` (user_id, liked/disliked_cuisines, spice_tolerance ∈ none/mild/medium/hot, dietary, budget_level ∈ student/standard/premium, distance_preference_km, current_lat/lng, context_memory, interaction_history) · `chat_sessions` (session_id, user_id) · `chat_messages` (message_id, session_id, sender ∈ user/agent, text). App tạo lúc chạy.

## Ghi chú (as-built vs schema)
- Schema teammate rộng hơn dữ liệu import: nhiều cột dự phòng đang **NULL** (đánh dấu ở trên). Không xoá — để tương lai đổ thêm.
- Vision image score hiện chỉ nằm trong `merchant_profiles.dimensions_json` (dimension `image_quality`), **chưa** ghi vào `food_images.dish_image_quality`.
- Ops chi tiết (delivery/packaging) tra trong `dimensions_json.attributes`, không phải bảng `operational_metrics`.
- Import idempotent: chạy lại cho cùng kết quả, không nhân đôi.
