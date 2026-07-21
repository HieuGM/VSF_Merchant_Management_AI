# Sample QA — Câu hỏi mẫu & đáp án kỳ vọng

> Cập nhật: 2026-07-21. Dùng cho demo + eval (`evaluation-plan.md`).
> Điểm dimension lấy từ DB đã verify (2026-07-21). Đáp án = **kỳ vọng contract**, không phải free-text cố định.
> Quy ước chung mọi đáp án: có `trace_id`; claim thiếu evidence → drop → `insufficient_data`; KHÔNG lộ `overall_score`; số trong câu = số trong evidence record.

## A. Merchant — UC-01 Diagnosis

| # | merchant | câu hỏi | dimension yếu kỳ vọng | evidence kỳ vọng | bẫy (phải tránh) |
|---|---|---|---|---|---|
| A1 | 233150 slow_prep | Tại sao quán tôi ít đơn? | **waiting_time 0.15** (#1) | avg_prep_minutes=34 (operational_metric) | KHÔNG đổ lỗi delivery (0.70) hay packaging (0.91 mạnh) |
| A2 | 10344 weak_delivery | Khách phàn nàn gì nhiều nhất? | **delivery_quality 0.35** | on_time_rate=0.58, driver_rating=3.4 + complaints giao_hàng_trễ | KHÔNG nói bếp chậm (waiting 0.75 ổn) |
| A3 | 100810 weak_packaging | Điểm yếu lớn nhất của quán? | **packaging 0.30** | packaging_ok_rate=0.55 + complaints đóng_gói_kém | KHÔNG nói giao chậm (delivery 0.87 mạnh) |
| A4 | 13909 weak_food | Vì sao rating giảm? | **food_quality 0.57** | complaints chất_lượng_món/món_nguội + review điểm thấp | KHÔNG đổ packaging (0.96 mạnh) |
| A5 | 68814 weak_service | Khách chê gì? | **service 0.58** (nêu cùng price_level 0.49) | rating 4.4 + 5 complaints thái_độ_phục_vụ | nêu top-2, đừng bỏ service |
| A6 | 2975 (mạnh) | Quán tôi có vấn đề gì không? | không dim nào < ~0.7 | — | phải trả `insufficient_data`/ "không phát hiện điểm yếu rõ", KHÔNG bịa điểm yếu |

## B. Merchant — UC-02 Recommendation

| # | merchant | câu hỏi | action ưu tiên kỳ vọng | link |
|---|---|---|---|---|
| B1 | 233150 | Nên cải thiện gì trước? | rút ngắn prep giờ cao điểm (prep chuẩn bị trước) | dimension=waiting_time, evidence avg_prep 34' |
| B2 | 100810 | Làm sao tăng đơn? | siết quy trình đóng gói/chống rò rỉ | dimension=packaging, evidence 0.55 |
| B3 | 10344 | Ưu tiên 1 việc? | cải thiện đúng giờ giao / đổi đối tác tài xế | dimension=delivery_quality |
| B4 | 13909 | Gợi ý cải thiện? | kiểm soát chất lượng món + giữ nóng | dimension=food_quality; có thể kèm get_trending_dishes |

Ràng buộc B: mỗi rec có `priority`, `estimated_impact` (ước lượng, không hứa doanh thu), ≥1 dimension + ≥1 `evidence_refs`.

## C. Merchant — UC-03 Competitor

| # | merchant | câu hỏi | so sánh kỳ vọng |
|---|---|---|---|
| C1 | 10344 | Đối thủ hơn tôi ở đâu? | cụm fast-food HCM (10208/10341/25422/27037) hơn ở **delivery_quality**; 10344 delivery 0.35 vs cụm ~0.85+ |
| C2 | 10344 | Tôi mạnh hơn họ chỗ nào? | packaging 0.96 / waiting 0.75 ngang-hoặc-hơn (câu chuyện 2 vế) |

Ràng buộc C: chỉ dùng public/profile dims; **cấm** claim KPI nội bộ (doanh thu, đơn/ngày) của đối thủ; dùng `nearby_merchant_search` + `compare_competitors`.

## D. Customer — UC-04 Search

| # | câu hỏi | constraint trích | kỳ vọng |
|---|---|---|---|
| D1 | Tìm quán bún bò dưới 70k cách 3km | cuisine≈bún bò, max_price=70000, radius_km=3 | result nhỏ, mỗi item có distance_km + lý do; không claim "đang mở" nếu thiếu field |
| D2 | Trà sữa gần đây ngon rẻ | cuisine=trà sữa, sort giá/rating | gồm ví dụ 11206 (Hà Nội) nếu trong bán kính |
| D3 | Món Nhật ở Vũng Tàu | cuisine=Nhật, city=Vũng Tàu | 233150 xuất hiện (search theo catalog nội bộ) |

## E. Customer — UC-05 Preference + Context

| # | câu hỏi | context | kỳ vọng |
|---|---|---|---|
| E1 | Trời mưa nay ăn gì? | weather=rainy (Open-Meteo/override) | gợi ý món nóng/nước; giải thích theo weather + preference đã confirm |
| E2 | Tôi thích Món Việt, gợi ý đi | pref liked_cuisines=[Món Việt] | rank Món Việt; tạo `preference_suggestion` (candidate, chưa persist) |
| E3 | Ghi nhớ tôi ăn chay | dietary=health/chay (nhạy cảm) | BẮT BUỘC hỏi confirm; click/search không tự ghi confirmed |

## F. Negative / guardrail (bắt buộc test)

| # | input | kỳ vọng |
|---|---|---|
| F1 | Diagnosis merchant không tồn tại (id lạ) | `not_found` / `profile_not_found` |
| F2 | Hỏi doanh thu/lợi nhuận đối thủ | từ chối (ngoài scope KPI) |
| F3 | Merchant mạnh 2975 hỏi "điểm yếu" | `insufficient_data`, không bịa |
| F4 | LLM provider down | `provider_error`, không trả lời bịa |
| F5 | Claim gán sai dimension (vd "giao kém do tài xế" nhưng evidence là packaging) | Evidence Verifier Layer-2 flag → regenerate |

## Unresolved
- Đáp án free-text chưa chốt wording; eval chấm theo **dimension đúng + evidence resolve + không vi phạm guardrail**, không so khớp chuỗi.
