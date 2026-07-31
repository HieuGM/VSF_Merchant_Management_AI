# Scoring Methodology — 8 Dimension

Cách chấm điểm Merchant Profile (as-built). Code gốc: `scripts/profile/dimension_scoring.py` (hàm thuần) + `scripts/profile/build_profiles.py` (ráp). Đối chiếu PRD mục 4.1. Field & pipeline xem [`data-pipeline-and-dictionary.md`](./data-pipeline-and-dictionary.md).

## Nguyên tắc chung
- Mỗi dimension là **hàm thuần** trả `(score 0–1, evidence[], basis)`. `score` luôn kèm evidence số liệu **truy vết được**.
- `clamp` mọi score về `[0, 1]`.
- **2 tầng dữ liệu:** `hero` (18) dùng reviews/complaints/delivery/vision thật+synthetic → evidence giàu; `background` (1.607) dùng rating + ops procedural → proxy.
- `overall_score = trung bình cộng 8 dimension` (không trọng số). **CHỈ dùng nội bộ** — xem Rule bên dưới.
- **Rating chuẩn hoá** (`_rating_norm`): ưu tiên ShopeeFood (0–5)/5; fallback Foody (0–10)/10; mặc định 0.7 nếu trống.
- **Complaint → dimension:** complaint đúng category mới trừ điểm dimension tương ứng (nên điểm yếu **tất định, tái lập**).

## 🔒 Rule cứng: `overall_score` KHÔNG bao giờ hiển thị ra ngoài
**NON-NEGOTIABLE.** `overall_score` chỉ là chỉ số **nội bộ** (sort/filter/QA). TUYỆT ĐỐI không surface cho merchant/customer qua UI hoặc Agent output.
- **Lý do:** bình quân 8 dimension → 1 điểm yếu mạnh bị pha loãng (VD 233150 waiting=0.15 nhưng overall=0.66 vẫn "khá"). Một con số duy nhất mâu thuẫn triết lý PRD (BR-01: multi-dimension thay vì single score) và che mất điểm cần chẩn đoán.
- **Thay bằng:** luôn trả **per-dimension score + evidence**. Diagnosis xếp hạng dimension thấp nhất; Competitor so từng dimension công khai.
- **Enforce ở đâu:** API response (`/merchants/:id/profile`) và Agent prompt phải loại `overall_score` khỏi payload gửi ra; giữ lại chỉ ở tầng nội bộ. Ghi lại rule này trong API Contract (doc #7).

## Công thức 8 dimension

### 1. food_quality
- Có reviews: `0.55·rating_norm + 0.30·sentiment + 0.15·popularity`; sentiment = pos/(pos+neg) (pos: score≥7, neg: 0<score<5).
- Không reviews (background): `0.85·rating_norm + 0.15·popularity`.
- popularity = trung bình like của top-5 món / 500 (clamp).
- Trừ: `− 0.03 × (complaint chất_lượng_món + món_nguội)`.
- Evidence: rating, positive/negative_review_count, top_dish_avg_likes, food_complaint_count.

### 2. image_quality
- Hero (có vision): `clamp(vision_score)`. Evidence: vision_score, vision_notes.
- Background (heuristic): `0.45·ratio_photo + 0.45·ratio_hd + (0.1 nếu is_quality_merchant)`. ratio_photo = món có ảnh/tổng; ratio_hd = món có ảnh ≥750px/tổng.
- Evidence: dishes_with_photo, dishes_with_hd_photo, is_quality_merchant.

### 3. delivery_quality
- `0.5·on_time_rate + 0.3·(driver_rating/5) + 0.2·(1 − clamp(avg_delivery_minutes/60)) − 0.03·complaint_giao_hàng_trễ`.
- Mặc định khi thiếu ops: on_time 0.85, driver 4.3, 30 phút.
- Evidence: on_time_rate, avg_delivery_minutes, driver_rating, late_complaint_count.

### 4. packaging
- `packaging_ok_rate − 0.05·complaint_đóng_gói_kém`. Mặc định ok_rate 0.88.
- Evidence: packaging_ok_rate, packaging_complaint_count.

### 5. service
- `rating_norm − 0.06·complaint_thái_độ_phục_vụ`.
- Evidence: rating, service_complaint_count.

### 6. waiting_time
- `1 − (avg_prep_minutes − 5)/40`. (5 phút≈1.0, 45 phút≈0.0). Mặc định prep 15.
- Evidence: `avg_prep_minutes` only. Khiếu nại giao trễ thuộc `delivery_quality`.

### 7. menu_diversity
- `0.6·clamp(dish_count/80) + 0.4·clamp(dish_type_count/8)`.
- Evidence: dish_count, dish_type_count.

### 8. price_competitiveness  *(PRD 4.1: giá vs phân khúc/khu vực)*
- **KHÔNG phải "giá tuyệt đối cao = xấu".** Điểm = độ cạnh tranh giá so với **peer cùng cuisine**.
- `ratio = price / peer_median` (median giá cùng cuisine; cuisine <5 quán → fallback median toàn cục).
- `over = max(0, ratio − 1)`; `score = clamp(1 − over·1.5)`. Giá ngang/rẻ hơn peers → 1.0; chỉ ĐẮT hơn peers mới giảm.
- Evidence: price, peer_median_price, price_ratio_vs_peers, price_level_label.

## Bảng tóm tắt trọng số

| Dimension | Tín hiệu chính | Complaint trừ điểm |
|---|---|---|
| food_quality | rating 0.55 · sentiment 0.30 · popularity 0.15 | chất_lượng_món, món_nguội (−0.03) |
| image_quality | vision (hero) / photo coverage (bg) | — |
| delivery_quality | on_time 0.5 · driver 0.3 · time 0.2 | giao_hàng_trễ (−0.03) |
| packaging | packaging_ok_rate | đóng_gói_kém (−0.05) |
| service | rating_norm | thái_độ_phục_vụ (−0.06) |
| waiting_time | avg_prep_minutes | — |
| menu_diversity | dish_count 0.6 · dish_type 0.4 | — |
| price_competitiveness | ratio vs peer_median cùng cuisine | — (giá_cao phản ánh gián tiếp qua ratio) |

## Kịch bản quán yếu có chủ đích
5 hero được gán 1 điểm yếu tất định (config `scripts/synth/scenarios.py`, nguồn gán `SCENARIO_ASSIGN`): `weak_delivery` (10344), `weak_service` (68814), `weak_packaging` (100810), `weak_food` (13909), `slow_prep` (233150). Hai cơ chế: (a) *ops-driven* ép số vận hành xấu (delivery/packaging/prep); (b) *rating-anchored* qua complaints tập trung + review điểm thấp. Chi tiết: [`data-pipeline-and-dictionary.md`](./data-pipeline-and-dictionary.md) (mục "Kịch bản quán yếu có chủ đích").

## Decision log
| Ngày | Quyết định | Trạng thái | Tác động |
|---|---|---|---|
| 2026-07-21 | **`overall_score` chỉ nội bộ**, không surface ra UI/Agent | ✅ chốt (rule cứng ở trên) | Enforce ở API #7 + Agent prompt |
| 2026-07-23 | **Bỏ penalty `giao_hàng_trễ` khỏi `waiting_time`** (waiting = prep thuần); vẫn giữ ở `delivery_quality` | ✅ đã migrate | Evidence waiting-time chỉ còn thời gian chuẩn bị; complaint giao trễ không còn bị gán cho bếp |

**Lý do (b):** `giao_hàng_trễ` = khiếu nại *đơn tới trễ*, thuộc về giao hàng → chỉ trừ `delivery_quality`. Trừ thêm `waiting_time` (tốc độ bếp) là quy kết sai nguồn, tạo điểm yếu phụ giả, làm nhiễu chẩn đoán demo (mỗi hero nên lộ đúng 1 điểm yếu).

## Kiểm chứng distribution & 5 hero (2026-07-21)
Chạy `data/profiles.jsonl` (n=1.625). Distribution có spread hợp lý (image_quality/packaging cụm cao ~0.93 do heuristic; price_level median 1.0 sau fix peer-median). **5 hero lộ đúng điểm yếu:** 10344/100810/13909/233150 có target là dimension **thấp nhất**; 68814 target `service`=0.58 xếp thứ 2 (dưới `price_level`=0.49 — đắt thật 34% so peer cùng cuisine, đã chấp nhận). Cả 2 đều là điểm yếu thật → Diagnosis surface đủ.

## Giới hạn đã biết
- Trọng số cố định (heuristic), chưa calibrate với ground-truth thật.
- Background thiếu review (971 quán = 0) → food_quality chạy rating proxy, ít tín hiệu.
- overall_score bình quân đều 8 dimension — 1 điểm yếu mạnh bị pha loãng; dùng dimension lẻ (không phải overall) để chẩn đoán.
