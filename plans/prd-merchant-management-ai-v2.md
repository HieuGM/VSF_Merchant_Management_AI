# PRD — Merchant Management & AI Agent Platform (v2.0)

> Đánh giá chất lượng nhà hàng đa chiều & Trợ lý AI cho Merchant Owner và Người dùng cuối
>
> **Phiên bản:** 2.0 (thay thế `PRD_Merchant_Management_AI.docx` v1.0)
> **Loại:** Demo / Proof-of-Concept (Local Web Demo) — dự án cá nhân, phục vụ pitching
> **Ngày cập nhật:** 20/07/2026
> **Thay đổi chính so với v1.0:** bổ sung chiến lược dữ liệu dựa trên dataset thật đã crawl (`data/shopeefood_catalog.jsonl`), tái cấu trúc 13 dimensions thành 2 nhóm (scored/attribute), Trending Mining chuyển từ "mạng xã hội" sang khai thác nội bộ dataset, chốt tech stack (FastAPI + OpenAI-compatible LLM), thêm kế hoạch sinh dữ liệu synthetic (hạng mục công việc lớn nhất), thêm sprint breakdown 6 tuần.

---

## 1. Tổng quan dự án

### 1.1. Bối cảnh
Trên các nền tảng đặt đồ ăn hiện nay, đánh giá chất lượng merchant thường chỉ dựa vào một con số duy nhất (rating trung bình), khiến merchant owner khó biết chính xác mình yếu ở khâu nào (hình ảnh món, thời gian giao, đóng gói, giá...), còn người dùng cuối khó tìm quán phù hợp với sở thích và ngữ cảnh thực tế (thời tiết, ngân sách, khẩu vị).

Dự án xây dựng hệ thống Merchant Management mô hình hoá merchant thành **Merchant Profile đa chiều (multi-dimension)** có **evidence rõ ràng cho từng điểm số**, làm knowledge base cho hai AI Agent: **Merchant AI Agent** (hỗ trợ chủ quán) và **Customer AI Agent** (hỗ trợ khách tìm quán).

### 1.2. Mục tiêu dự án
1. Xây dựng **Merchant Profile Framework**: biểu diễn merchant qua nhiều dimension có evidence, thay vì một điểm số duy nhất.
2. Xây dựng **Merchant AI Agent**: chẩn đoán vấn đề, gợi ý cải thiện, so sánh đối thủ.
3. Xây dựng **Customer AI Agent**: tìm kiếm & gợi ý quán theo sở thích, ngân sách, ngữ cảnh (thời tiết, thời điểm).
4. Demo toàn bộ luồng trên web app chạy local, **mobile-first responsive**, phục vụ pitching — không yêu cầu chuẩn production.

### 1.3. Đối tượng sử dụng

| Đối tượng | Nhu cầu chính | Tương tác với | Ưu tiên |
|---|---|---|---|
| Merchant Owner | Hiểu lý do quán hoạt động kém, nhận gợi ý cải thiện, so sánh đối thủ | Merchant AI Agent | Cao |
| Customer | Tìm quán phù hợp sở thích, ngân sách, ngữ cảnh | Customer AI Agent | Cao |
| Người xem demo / nhà đầu tư | Đánh giá tính khả thi & giá trị ý tưởng | Toàn hệ thống (qua kịch bản demo) | Trung bình |

### 1.4. Ghi chú phạm vi triển khai
- Dự án cá nhân, demo trên môi trường development để pitching. Không yêu cầu HA, auto-scaling, CI/CD phức tạp.
- Ưu tiên tốc độ phát triển, chạy local.
- Không xử lý Business KPI thật (bảo mật).
- Web app local nhưng UI phải responsive, tối ưu mobile (kênh chính khi demo).

---

## 2. Business Requirements

### 2.1. Mục tiêu kinh doanh
- Chứng minh giá trị biểu diễn merchant **multi-dimension** thay vì single score — insight rõ ràng, actionable.
- Chứng minh AI Agent **reasoning trên dữ liệu thực tế** của merchant, đưa chẩn đoán/gợi ý **có evidence**, không trả lời chung chung.
- Chứng minh **cá nhân hoá** trải nghiệm tìm kiếm dựa trên user profile & ngữ cảnh (context memory).

### 2.2. Yêu cầu nghiệp vụ chính

| Mã | Yêu cầu | Mô tả |
|---|---|---|
| BR-01 | Đánh giá merchant đa chiều | Biểu diễn merchant qua tối thiểu 8 scored dimension: Food Quality, Image Quality, Delivery Quality, Packaging, Service, Waiting Time, Menu Diversity, Price Level. |
| BR-02 | Evidence-based scoring | Mọi điểm số phải đi kèm evidence cụ thể (số review tích cực/tiêu cực, complaint, image score...) **truy vết được tới bản ghi gốc** (review id, complaint id...). Agent trả lời phải luôn trích evidence. |
| BR-03 | Chẩn đoán nguyên nhân | Merchant Owner nhận lý do cụ thể vì sao quán hoạt động kém, kèm mức độ ảnh hưởng. |
| BR-04 | Gợi ý cải thiện có ưu tiên | Gợi ý xếp hạng theo mức tác động dự kiến (estimated impact) đến doanh thu/rating. |
| BR-05 | So sánh đối thủ | So sánh với merchant tương tự (cùng khu vực/loại món) về giá, hình ảnh, đánh giá. |
| BR-06 | Tìm kiếm & gợi ý cho khách | Tìm quán theo tiêu chí tường minh (vị trí, loại món, giá, rating) và tiêu chí ngầm định qua reasoning (thời tiết, sở thích đã lưu). |
| BR-07 | Ghi nhớ hồ sơ người dùng | Lưu & tái sử dụng user profile (food preference, budget, distance, cuisine, diet, taste) xuyên suốt phiên. |

### 2.3. Tiêu chí thành công (Demo)
- Demo đủ 5 use case (UC-01 → UC-05) với dữ liệu thuyết phục.
- Mỗi câu trả lời Agent đều hiển thị evidence/nguồn dữ liệu.
- UI mượt trên trình duyệt mobile.
- Thời gian phản hồi Agent chấp nhận được cho demo trực tiếp (mục tiêu < 10s/câu, có streaming để không "đứng hình").

---

## 3. Chiến lược dữ liệu (MỚI — thay thế giả định "mock toàn bộ" của v1.0)

> Đây là hạng mục công việc lớn nhất của dự án. Demo thuyết phục hay không phụ thuộc vào chất lượng dữ liệu, không phải code.

### 3.1. Hiện trạng dữ liệu thật (`data/shopeefood_catalog.jsonl`)
- **3.277 records = 3.277 merchant riêng biệt**, mỗi merchant chỉ có **1 món đại diện** (không phải menu đầy đủ).
- 9 thành phố: TP.HCM (700), Hà Nội (700), Đà Nẵng (692), Đồng Nai (279), Cần Thơ (261), Hải Phòng (190), Khánh Hoà (154), Vũng Tàu (154), Huế (147).
- **Dùng được trực tiếp:** tên, địa chỉ, lat/lng, image_url (3.197/3.277), category/cuisine, open hours, source_url.
- **Synthetic sẵn có:** price, avg_prep_minutes (100%); taste_tags (1.237), ingredient_tags (1.127), diet_tags (151).
- **KHÔNG dùng được:** `merchant_rating`/`merchant_review_count` là giá trị rác (1000.0, 500, None cho ~50%) — phải thay thế.
- **Thiếu hoàn toàn:** reviews, complaints, delivery feedback, operational metrics, menu đầy đủ.

### 3.2. Chiến lược 2 tầng: Hero-set + Background

| Tầng | Số lượng | Dữ liệu | Phục vụ |
|---|---|---|---|
| **Hero-set** | 15–20 merchant (chọn cùng 1–2 khu vực, có nhóm 3–5 quán cùng cuisine để so sánh đối thủ) | Đầy đủ: menu mở rộng, reviews, complaints, delivery feedback, ops metrics, profile 13 dimensions | UC-01, UC-02, UC-03 (Merchant Agent) + xuất hiện trong kết quả UC-04/05 |
| **Background** | ~3.257 merchant còn lại | Catalog gốc + rating/review_count synthetic hợp lý + tags bổ sung | UC-04, UC-05 (Search & Preference Reasoning) |

### 3.3. Nguồn dữ liệu theo phương án lai (crawl + synthetic)

| Loại dữ liệu | Nguồn | Ghi chú |
|---|---|---|
| Metadata, ảnh, vị trí, catalog | **Thật (đã crawl)** | Nền tảng của toàn hệ thống |
| Reviews (hero-set) | **Crawl thử (timebox 3–4 ngày)** → thất bại thì **LLM synthetic** | Crawl từ nguồn công khai; nếu API bị chặn/thiếu dữ liệu → fallback synthetic ngay, không kéo dài |
| Menu đầy đủ (hero-set) | **LLM synthetic** dựa trên cuisine/category/price thật của quán | Cần cho Menu Diversity |
| Complaints, Delivery feedback, Operational metrics | **LLM synthetic 100%** | Dữ liệu nội bộ, không bao giờ crawl được |
| Rating/review_count (background) | **Synthetic có kiểm soát** (phân phối thực tế 3.5–4.8) | Thay giá trị rác hiện tại |
| Trending dishes | **Khai thác nội bộ dataset** (mục 3.5) | Thay "mạng xã hội" của v1.0 |
| Thời tiết | **Open-Meteo API (miễn phí, không cần key)** + nút override thủ công trong demo UI | Override đảm bảo demo chủ động kịch bản "trời mưa" |

### 3.4. Nguyên tắc sinh dữ liệu synthetic
- Sinh **có chủ đích theo kịch bản demo**: mỗi hero merchant có "câu chuyện" (VD: quán A ảnh xấu + chờ lâu, quán B giá cao hơn khu vực, quán C tốt toàn diện làm đối thủ chuẩn) để Diagnosis/Recommendation/Competitor cho kết quả rõ ràng, thuyết phục.
- Reviews synthetic phải nhất quán với taste_tags/category thật của quán, ngôn ngữ tiếng Việt tự nhiên, phân bố thời gian hợp lý.
- Mọi bản ghi synthetic có id riêng để evidence truy vết được.
- Batch generation bằng model rẻ (NIM/FPT), lưu file/DB một lần — không sinh runtime.

### 3.5. Trending Mining (thiết kế lại)
Trending dishes khai thác từ **chính dataset**: tổng hợp tần suất món + sentiment tích cực + taste_tags across merchants cùng khu vực/cuisine. Kết quả lưu thành bảng trending theo (khu vực, cuisine) làm tool cho Agent. Ưu điểm: evidence-based, không phụ thuộc mạng khi demo, tự chủ hoàn toàn. Có thể bổ sung file seed biên soạn tay nếu cần "wow" hơn.

### 3.6. Ghi chú pháp lý
Dữ liệu crawl từ nền tảng thật chỉ dùng nội bộ cho demo/pitching, không công khai, không thương mại hoá. Cân nhắc ẩn danh hoá tên quán nếu demo công khai. (Điều chỉnh so với ràng buộc 9.2 của v1.0 — chấp nhận rủi ro thấp có ghi nhận.)

---

## 4. Merchant Profile Framework

### 4.1. Cấu trúc 13 dimensions — chia 2 nhóm (điều chỉnh so với v1.0)

**Nhóm A — Scored dimensions (8): có score 0–1 + evidence, chấm điểm bằng pipeline**

| Dimension | Ý nghĩa | Nguồn tính |
|---|---|---|
| Food Quality | Chất lượng món ăn | Reviews (sentiment), độ phổ biến món |
| Image Quality | Chất lượng ảnh món (nét, sáng, trình bày) | Vision LLM trên image_url thật |
| Delivery Quality | Chất lượng giao hàng | Delivery feedback, thời gian giao |
| Packaging | Chất lượng đóng gói | Reviews/feedback liên quan đóng gói |
| Service | Thái độ phục vụ, phản hồi khiếu nại | Reviews, complaint resolution |
| Waiting Time | Thời gian chờ/chuẩn bị | avg_prep_minutes, ops metrics, reviews |
| Menu Diversity | Độ đa dạng menu | Menu mở rộng (hero-set) |
| Price Level | Mức giá so với khu vực/phân khúc | Giá catalog so với median khu vực+cuisine |

**Nhóm B — Attribute dimensions (5): dữ liệu mô tả/danh sách, KHÔNG chấm điểm**

| Dimension | Ý nghĩa | Nguồn |
|---|---|---|
| Customer Segments | Phân khúc khách chính | Suy ra từ reviews + price + category |
| Peak Time | Khung giờ cao điểm | Ops metrics synthetic |
| Competitor | Danh sách đối thủ trực tiếp | Tính từ khoảng cách lat/lng + cùng cuisine |
| Trending Dishes | Món đang thịnh hành trong khu vực | Trending mining nội bộ (mục 3.5) |
| Operation KPIs | Chỉ số vận hành (prep time, tỉ lệ huỷ...) | Synthetic, chỉ hero-set |

> Business KPI (doanh thu, lợi nhuận thật) — ngoài phạm vi (bảo mật).

**Nguyên tắc bắt buộc:** Agent trả lời phải luôn có evidence — không suy diễn thiếu số liệu. Mỗi evidence truy vết được tới bản ghi gốc.

### 4.2. Phân loại metric theo nhóm dữ liệu

| Loại | Metric | Ghi chú |
|---|---|---|
| Merchant Static | Cuisine, Location, Open hour, Price, Menu | Từ catalog thật |
| Merchant Dynamic | Review, Complaint, Driver Feedback, Promotion | Crawl (reviews hero-set) + synthetic |
| Vision | Image quality, Dish detection, Packaging, Serving size | Vision LLM, chủ yếu hero-set (kiểm soát chi phí) |
| NLP | Sentiment, Review Topic, Complaint Category, Keyword | LLM batch, offline |
| Business KPI | — | Ngoài phạm vi |

### 4.3. JSON Schema Merchant Profile (đề xuất)
```json
{
  "merchant_id": "string",
  "tier": "hero | background",
  "metadata": {
    "name": "string", "cuisine": "string", "category": "string",
    "location": { "address": "string", "lat": 0.0, "lng": 0.0, "city": "string" },
    "open_hours": { "open": "09:00", "close": "22:30" },
    "price_level": "string", "image_url": "string", "source_url": "string"
  },
  "dimensions": [
    {
      "name": "food_quality",
      "score": 0.82,
      "evidence": [
        { "type": "positive_review_count", "value": 320, "ref_ids": ["rv_001", "..."] },
        { "type": "complaint_count", "value": 28, "ref_ids": ["cp_001"] },
        { "type": "image_score", "value": 0.77, "ref_ids": ["img_001"] }
      ]
    }
  ],
  "attributes": {
    "customer_segments": ["sinh viên", "dân văn phòng"],
    "peak_time": ["11:00-13:00", "18:00-20:00"],
    "competitors": ["merchant_id_1", "merchant_id_2"],
    "trending_dishes": ["..."],
    "operation_kpis": { "avg_prep_minutes": 12, "cancel_rate": 0.04 }
  },
  "updated_at": "ISO-8601"
}
```

---

## 5. Use Cases

Hai nhóm AI Agent, dùng chung Merchant Profile Framework làm nguồn tri thức.

### 4.1 Merchant AI Agent (Actor: Merchant Owner — chỉ hero-set)

**UC-01: Merchant Diagnosis — "Tại sao quán ít đơn?"**
- Trigger: hỏi trực tiếp hoặc mở mục "Chẩn đoán quán" trên dashboard.
- Điều kiện: Merchant Profile đã tính (hero-set).
- Luồng: Agent truy vấn profile → xếp hạng dimension score thấp/evidence tiêu cực nổi bật → tổng hợp Top nguyên nhân theo mức ảnh hưởng → hiển thị kèm evidence trích dẫn.
- Output: Top ≤ 5 nguyên nhân + evidence từng nguyên nhân.
- Rules: mỗi lý do bắt buộc có evidence; tối đa 5 nguyên nhân.

**UC-02: Merchant Recommendation — Gợi ý cải thiện & tăng doanh thu**
- Trigger: yêu cầu gợi ý, hoặc sau khi xem Diagnosis.
- Luồng: phân tích dimension yếu, đối chiếu pattern cải thiện (image score thấp → chụp lại ảnh) → tra bảng Trending nội bộ theo cuisine/khu vực → tổng hợp khuyến nghị + **estimated impact** (sửa lỗi "compact rate" của v1.0) → hiển thị kèm evidence + mức ưu tiên.
- Output: danh sách khuyến nghị xếp theo ưu tiên/tác động ước tính.
- Rules: khuyến nghị gắn với ≥ 1 dimension/evidence; trending chỉ từ dữ liệu nội bộ dataset.

**UC-03: Competitor Analysis — So sánh đối thủ**
- Điều kiện: hero-set có nhóm 3–5 quán cùng khu vực/cuisine (đảm bảo khi chọn hero-set, mục 3.2).
- Luồng: xác định competitors từ attribute → so sánh dimension công khai (ảnh, giá, đánh giá) → bảng so sánh + điểm mạnh/yếu tương đối.
- Rules: chỉ so sánh thông tin công khai, không dùng Business KPI đối thủ.

### 4.2 Customer AI Agent (Actor: Customer — toàn bộ 3.277 merchant)

**UC-04: Restaurant Search — tìm theo tiêu chí tường minh**
- Luồng: Agent trích tiêu chí từ câu chat (vị trí, loại món, giá, rating) → tool search truy vấn merchant DB → trả danh sách xếp theo liên quan (tên, rating, giá, khoảng cách).

**UC-05: Preference Reasoning — gợi ý theo sở thích & ngữ cảnh**
- Điều kiện: User Profile khởi tạo/cập nhật qua hội thoại trước (context memory).
- Luồng: đọc User Profile (preference, budget, distance, cuisine, diet, taste) → lấy ngữ cảnh (thời tiết Open-Meteo/override, thời điểm) → kết hợp lọc & xếp hạng trên Merchant Profile → trả kết quả + giải thích cá nhân hoá ("phù hợp vì không cay, giá sinh viên, gần bạn").
- Rules: User Profile cập nhật dần qua hội thoại, tái sử dụng; thiếu ngữ cảnh (không lấy được thời tiết) vẫn phải trả kết quả từ tiêu chí còn lại.

---

## 6. Phân loại câu hỏi cho AI & Yêu cầu xử lý

| Level | Kiểu câu hỏi / Ví dụ | Yêu cầu xử lý | Use case |
|---|---|---|---|
| 1. Retrieval | "Quán cơm gần đây giá dưới 50k" | Tool search theo vị trí/tiêu chí | UC-04 |
| 2. Aggregation | Lọc theo đánh giá; tự sinh tiêu chí từ user profile | Context memory → spec tiêu chí; tool search + aggregate | UC-04, UC-05 |
| 3. Analysis | "Khách thích/ghét gì ở quán tôi?" | Tool lấy review liên quan; Agent sentiment/topic analysis | UC-05, UC-01 |
| 4. Recommendation | "Gợi ý cách tăng doanh thu" | Tổng hợp phân tích chất lượng/review/order → Top gợi ý + impact | UC-02 |
| 5. Strategic Comparison | "Quán nào tương tự đang làm tốt hơn tôi?" | So sánh thông tin công khai thị trường | UC-03 |

---

## 7. Technical Requirements

### 7.1. Nguyên tắc thiết kế
- Đơn giản, chạy local, hạn chế dependency ngoài.
- Tách rõ: **Data & Knowledge Layer** (offline pipeline) và **Agent Layer** (runtime).
- Mọi câu trả lời Agent truy vết được evidence gốc (traceable).
- Mobile-first responsive; desktop chỉ cần hiển thị tốt.
- **LLM provider-agnostic**: mọi lời gọi LLM qua chuẩn OpenAI-compatible API (đổi provider = đổi `base_url` + `model` trong config).

### 7.2. Kiến trúc tổng thể (5 lớp, dữ liệu chảy một chiều)
1. **Data Layer**: catalog thật (jsonl) + dữ liệu crawl/synthetic (reviews, complaints, feedback, menu, ops metrics) → SQLite.
2. **Processing Layer (offline, chạy 1 lần)**: Vision + NLP batch → score & evidence từng dimension.
3. **Knowledge Layer (Merchant Profile Store)**: profile chuẩn hoá (dimension/score/evidence + attributes) — source of truth cho Agent.
4. **Agent Layer**: Merchant Agent & Customer Agent — LLM function-calling truy vấn Knowledge Layer qua tools.
5. **Presentation Layer**: web responsive — Merchant Dashboard + Customer Chat/Search UI.

### 7.3. Tech Stack (đã chốt)

| Thành phần | Lựa chọn | Lý do |
|---|---|---|
| Frontend | React (Vite) + TailwindCSS, mobile-first | Phát triển nhanh, dễ responsive |
| Backend/API | **Python FastAPI** | Crawl, data pipeline, synthetic generation, agent — một ngôn ngữ |
| Lưu trữ | **SQLite** (+ file JSON cho profile nếu tiện) | Đủ cho local demo, query được cho search |
| LLM Agent runtime | **OpenAI API** (function calling ổn định nhất trong các key sẵn có) | UC-01→05 reasoning + tool use, có streaming |
| LLM batch (offline) | **NVIDIA NIM / FPT Cloud** (model rẻ, OpenAI-compatible) | Sinh synthetic data, sentiment, scoring hàng loạt |
| Vision | Model vision qua OpenAI/NIM (ảnh hero-set trước, background nếu còn budget) | Image Quality score có evidence |
| Thời tiết | Open-Meteo (free, không cần key) + override UI | Ổn định khi demo |
| Triển khai | Local (localhost) | Đúng phạm vi demo |

### 7.4. API (mức cao)

| Endpoint | Mục đích | Dùng bởi |
|---|---|---|
| `GET /merchants/:id/profile` | Merchant Profile đầy đủ (dimensions + evidence + attributes) | Dashboard, Merchant Agent |
| `GET /merchants/search` | Tìm merchant theo tiêu chí có cấu trúc (tool nội bộ của agent, expose để debug) | Customer Agent |
| `POST /agent/merchant/diagnosis` | UC-01 | Merchant Dashboard |
| `POST /agent/merchant/recommendation` | UC-02 | Merchant Dashboard |
| `POST /agent/merchant/competitor-analysis` | UC-03 | Merchant Dashboard |
| `POST /agent/customer/chat` | UC-04 + UC-05 (một endpoint chat hợp nhất, agent tự định tuyến level câu hỏi) | Customer App |
| `GET/PUT /users/:id/profile` | Đọc/cập nhật User Profile | Customer App |
| `GET /evidence/:type/:id` | Truy vết bản ghi gốc của evidence (review/complaint/feedback) | UI "Vì sao?" expandable |

> Thay đổi so với v1.0: gộp `POST /agent/customer/search` + `/recommend` thành một endpoint chat (UC-04/05 đều vào từ ô chat, agent tự phân loại level); thêm `/merchants/search` và `/evidence` phục vụ traceability.

### 7.5. Frontend / UI
- Mobile-first: layout, typography, tap target tối ưu điện thoại trước.
- Breakpoints tối thiểu mobile + desktop.
- **Merchant Dashboard**: dimension cards (score + evidence), tab/section cho Diagnosis / Recommendation / Competitor.
- **Customer App**: chat/search + kết quả dạng card (tên, rating, giá, khoảng cách, lý do gợi ý).
- Mọi kết quả Agent có phần "Vì sao gợi ý này / Evidence" mở rộng được, link tới bản ghi gốc.
- Streaming response cho chat (tránh cảm giác treo khi demo).

---

## 8. Non-Functional Requirements

| Hạng mục | Yêu cầu |
|---|---|
| Hiệu năng | Phản hồi agent < 10s có streaming; không yêu cầu chịu tải đồng thời. |
| Bảo mật | Không dữ liệu nhạy cảm/Business KPI thật; API key trong `.env`, không commit. |
| Mở rộng | Không bắt buộc; tách lớp rõ để dễ mở rộng sau. |
| Khả dụng | Mobile mượt, trực quan, demo được trong thời gian ngắn. |
| Tin cậy dữ liệu | Hero-set nhất quán nội bộ (reviews khớp tags/câu chuyện quán); background đủ phong phú cho search 9 thành phố. |
| Triển khai | Chạy hoàn toàn local; chỉ phụ thuộc ngoài: LLM API + Open-Meteo (có override offline). |
| Chi phí LLM | Batch offline dùng model rẻ + cache kết quả; vision giới hạn hero-set trước; theo dõi usage. |

---

## 9. Ngoài phạm vi (Out of Scope)
- Business KPI thật (doanh thu, lợi nhuận nội bộ).
- Hạ tầng production: CI/CD, auto-scaling, multi-region, monitoring sâu.
- Thanh toán, đặt đơn thật, tích hợp tài xế realtime.
- Authentication chuẩn production (dùng mock login/user id).
- Đa ngôn ngữ (chỉ tiếng Việt), đa khu vực ngoài 9 thành phố có sẵn.
- Crawl quy mô lớn/định kỳ — chỉ crawl bổ sung một lần cho hero-set (timeboxed).

## 10. Giả định & Ràng buộc

**Giả định**
- Catalog thật đã có; reviews hero-set crawl được HOẶC synthetic thay thế (đã có fallback, không chặn tiến độ).
- Có API key OpenAI / NVIDIA NIM / FPT Cloud dùng suốt quá trình phát triển & demo.
- Người xem demo dùng trình duyệt (mobile/desktop) kết nối server local.

**Ràng buộc**
- Thời gian: **6 tuần**, solo (sprint breakdown mục 12). *(v1.0 tham chiếu `Sprint_Tracking_6_Tuan.xlsx` — file không tồn tại trong repo; thay bằng mục 12.)*
- Không có QA/DevOps riêng; tự kiểm thử mức đủ demo.
- Dữ liệu crawl chỉ dùng nội bộ demo (mục 3.6).

---

## 11. Kịch bản Demo & Nghiệm thu

### 11.1. Kịch bản demo
1. Mở Merchant Dashboard quán hero → xem profile dimension scores + evidence.
2. Chạy Diagnosis → Top nguyên nhân ít đơn + evidence.
3. Chạy Recommendation → gợi ý cải thiện, tham chiếu trending dishes khu vực.
4. Chạy Competitor Analysis → so sánh với 2–3 đối thủ cùng khu vực/cuisine.
5. Sang Customer App → Restaurant Search theo tiêu chí (vị trí, món, giá, rating) trên toàn bộ 3.277 quán.
6. Preference Reasoning → hỏi gợi ý chung, hệ thống dùng User Profile + thời tiết (demo nút override "trời mưa") + thời điểm → gợi ý kèm giải thích.

### 11.2. Definition of Done
- 5 use case chạy end-to-end, không lỗi chặn luồng demo.
- Mọi câu trả lời Agent hiển thị evidence link tới dữ liệu profile, mở rộng xem được bản ghi gốc.
- UI tốt trên mobile (test ≥ 1 thiết bị/kích thước mô phỏng).
- ≥ 15 hero merchant (có nhóm cùng cuisine/khu vực cho UC-03) + ≥ 2 user profile mẫu khác biệt rõ (VD: sinh viên tiết kiệm không ăn cay vs dân văn phòng thích healthy).
- Search hoạt động trên toàn bộ dataset 9 thành phố.

---

## 12. Sprint breakdown 6 tuần (thay file xlsx bị thiếu)

| Tuần | Mục tiêu chính | Deliverable |
|---|---|---|
| 1 | Data foundation: schema SQLite, import catalog, làm sạch (rating rác), chọn hero-set; thử crawl reviews (timebox hết tuần 1) | DB + hero-set list + kết luận crawl |
| 2 | Sinh synthetic data: menu mở rộng, reviews (nếu crawl fail), complaints, delivery feedback, ops metrics theo "câu chuyện" từng hero | Bộ dữ liệu hero-set hoàn chỉnh |
| 3 | Processing pipeline: NLP batch (sentiment/topic), Vision batch (image score), tính 8 scored dimensions + 5 attributes + trending mining → Merchant Profile Store | Profile đầy đủ cho hero-set + background |
| 4 | Agent Layer: FastAPI + tools + Merchant Agent (UC-01/02/03) với evidence | API demo được qua REST |
| 5 | Customer Agent (UC-04/05): chat, user profile memory, weather context; Frontend khung + Merchant Dashboard | UC end-to-end qua UI cơ bản |
| 6 | Frontend hoàn thiện mobile-first, Customer App UI, evidence expandable, polish + chuẩn bị kịch bản pitch, buffer sửa lỗi | Demo hoàn chỉnh theo mục 11 |

**Rủi ro chính & giảm thiểu**
- Crawl reviews thất bại → fallback synthetic (đã thiết kế, không chặn).
- Chi phí/latency LLM → batch offline model rẻ, cache, streaming runtime.
- 13 dimensions quá tải → nhóm B là attribute (không pipeline chấm điểm); nếu trễ tiến độ, giảm chất lượng nhóm B trước, không bỏ nhóm A.
- Solo 6 tuần → tuần 6 là buffer; UI ưu tiên mobile, desktop chỉ cần "không vỡ".

## 13. Phụ lục

**Luồng dữ liệu tổng quan:**
Catalog thật + Crawl/Synthetic (Reviews, Menu, Complaint, Delivery Feedback, Ops Metrics) → Processing (Vision + NLP batch, offline) → Merchant Profile Store (8 scored dimensions + 5 attributes, evidence traceable) → Merchant AI Agent (Diagnosis, Recommendation, Competitor) & Customer AI Agent (Search, Preference Reasoning) → Web UI (Dashboard + Chat).

**Tham chiếu:**
- `plans/PRD_Merchant_Management_AI.docx` — PRD v1.0 gốc (giữ làm tham chiếu lịch sử).
- `data/shopeefood_catalog.jsonl` — dataset catalog thật (3.277 merchants, 9 thành phố).
- Tài liệu Knowledge-Agent gốc (Merchant Profile Framework, phân loại câu hỏi AI) — nguồn ý tưởng.
