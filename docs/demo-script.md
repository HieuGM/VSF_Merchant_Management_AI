# Demo Script — Merchant AI Agent

> Cập nhật: 2026-07-21. Kèm: `sample-qa.md`, `evaluation-plan.md`.
> Mục tiêu: chạy trọn 5 use-case (UC-01..05) trên hero-set 18 merchant với fixture nhỏ.
> Nguồn contract: `2026-07-21-merchant-ai-agent-complete-design.md` (mục 3, 11).

## 0. Readiness (2026-07-21)

| Lớp | Trạng thái | Ghi chú |
|---|---|---|
| Data + `profiles.jsonl` + DB import | ✅ Sẵn | 1625 merchant, 18 hero, 5 scenario |
| Merchant search (UC-04) | ⏳ Pending | cần service C-04 + route 11.2 |
| Customer/Merchant chat agent | ⏳ Pending | Feature G/H chưa start |

Demo hiện chạy được: inspect profile qua DB/API tĩnh + kiểm điểm 8 dimension. Phần agent chat là **target flow** (script dưới mô tả kịch bản đích để review contract & chuẩn bị eval).

## 1. Hero-set & vai trò demo

### Cụm đối thủ fast-food HCM (UC-03)
| id | tên | rating | scenario |
|---|---|---|---|
| 10208 | Burger King - Phạm Ngũ Lão | 4.7 | — (mạnh) |
| 10341 | Popeyes - Cộng Hòa | 4.7 | — |
| **10344** | Popeyes - Tùng Thiện Vương | 4.7 | **weak_delivery** |
| 25422 | McDonald's - Satra Phạm Hùng | 4.8 | — |
| 27037 | Lotteria - Mỹ Khánh 4 | 4.8 | — |

### Cụm chẩn đoán HCM Món Việt (UC-01/02)
| id | tên | rating | scenario | điểm yếu nhất (verify) |
|---|---|---|---|---|
| **68814** | Dì Bảy - Bún Mắm | 4.4 | **weak_service** | service 0.58 (price_level 0.49*) |
| **100810** | 3 Râu - Gà Rán/Pizza | 4.6 | **weak_packaging** | packaging 0.30 |
| 2975 | Boom - Cà Phê & Trà Sữa | 4.9 | — | (mạnh toàn diện) |
| 3752 | Bánh Mì Chim Chạy | 4.9 | — | (mạnh) |
| 9634 | Xôi Bình Tiên | 4.9 | — | (mạnh) |

\* 68814: price_level 0.49 < service 0.58 — chấp nhận (giá 51k vs peer median 38k = 1.34×). Diagnosis nêu top-2 → service vẫn lọt. Xem `risk-log.md` R1.

### Cụm đa dạng thành phố (UC-04/05, Customer search)
101948 Đà Nẵng · 104480 Đồng Nai · 11206 Hà Nội · 126520 Cần Thơ · 131531 Khánh Hoà · **13909 Hải Phòng (weak_food, food 0.57)** · 15625 Huế · **233150 Vũng Tàu (slow_prep, waiting 0.15)**.

## 2. Setup trước demo

```bash
# 1) DB + Redis up (docker), .env có POSTGRES_*/DB_*, LLM key
# 2) Re-import dataset (idempotent, TRUNCATE + insert)
cd backend && PYTHONIOENCODING=utf-8 python ../scripts/db/import_dataset.py
# 3) Verify 5 scenario giữ đúng điểm yếu nhất
python ../scripts/profile/validate_profiles.py
# 4) Health
curl localhost:8000/health   # {status, database, redis, llm_configured}
```

## 3. Kịch bản chạy (5 màn)

### Màn 1 — UC-01 Diagnosis (merchant 233150, slow_prep)
- Vai: chủ Sushi Lounge Vũng Tàu hỏi *"Tại sao quán tôi ít đơn?"*
- Gọi: `POST /api/v1/agent/merchant/chat` `{merchant_id:"233150", message:..., intent:"diagnosis"}`
- Kỳ vọng: nguyên nhân #1 = **waiting_time (0.15)** kèm `evidence_refs` (avg_prep 34'), ≤5 cause, không bịa. `overall_score` KHÔNG xuất hiện.
- Điểm nhấn: waiting_time thấp rõ trong khi packaging/delivery cao → câu chuyện 2 vế.

### Màn 2 — UC-02 Recommendation (merchant 100810, weak_packaging)
- *"Tôi nên cải thiện điều gì trước?"* `intent:"recommendation"`
- Kỳ vọng: action ưu tiên cao gắn **packaging (0.30)** + `evidence_refs` (packaging_ok_rate 0.55), estimated_impact là ước lượng. Mỗi rec link ≥1 dimension + ≥1 evidence.

### Màn 3 — UC-03 Competitor (merchant 10344, weak_delivery)
- *"Đối thủ gần đây làm tốt hơn tôi ở điểm nào?"* `intent:"competitor_analysis", competitor_radius_km:8`
- Kỳ vọng: so với cụm fast-food HCM (10208/10341/25422/27037), 10344 yếu **delivery_quality (0.35)**; KHÔNG claim KPI nội bộ đối thủ; chỉ public/profile dims.

### Màn 4 — UC-04 Customer Search
- Vai khách: *"Tìm quán bún bò dưới 70 nghìn, cách đây 3 km."*
- `POST /api/v1/agent/customer/chat` + `location{lat,lng}`
- Kỳ vọng: result nhỏ có `distance_km` + lý do; không claim "đang mở" nếu nguồn thiếu field.

### Màn 5 — UC-05 Preference + Context
- *"Trời mưa thì hôm nay tôi nên ăn gì?"* `weather_override` hoặc Open-Meteo.
- Kỳ vọng: đọc preference đã confirm + weather; rank + giải thích theo tín hiệu hiển thị; `preference_suggestions` chỉ là candidate (chưa persist).

## 4. Điểm phải soi khi review (mọi màn)
- Mỗi response có `trace_id` (+ header `X-Request-ID`).
- Claim không có evidence → bị drop; hết claim → `insufficient_data` (không bịa).
- `overall_score` bị strip khỏi mọi surface (chỉ per-dimension + evidence).
- Trace inspect: `GET /api/v1/agent/runs/{trace_id}` (agent/task/tool events, duration).

## 5. Reset demo
Chạy lại mục 2 bước 2 (import TRUNCATE + insert) → seed sạch, lặp lại được (roadmap L-03).

## Unresolved
- UC-04/05 cần route search + customer crew (pending) để chạy live; hiện chỉ chạy được inspect tĩnh.
