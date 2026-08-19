# Báo cáo sản phẩm Merchant Agent - Sprint 2

> Người báo cáo: Nguyễn Văn Minh


## Tổng quan

- Sprint 2 thay đổi kiến trúc agent 1 nhánh phức tạp thành 3 nhánh (phân theo mức độ phức tạp của câu hỏi). 
- Ứng dụng dịch vụ Mem0 quản lý memory của conversation. 
- Nâng cấp RAG agent (retrieve tài liệu tốt hơn).
- Monitoring: Sử dụng dịch vụ LangFuse (cloud) để tracing, quản lý SYSTEM_PROMPT cho các agent và luồng evaluation tự động.


## Usecases

| Tên | Mô tả |
|---|---|
| Phân tích reviews | Sentiment analysis, summary và phân loại issues từ reviews của người mua và tài xế.  |
| Hỗ trợ hỏi đáp tài liệu chính sách | Tìm tài liệu, chính sách áp dụng cho Merchant XanhSM, sử dụng RAG có tài liệu trích dẫn |
| Nghiên cứu thị trường cạnh tranh | Tìm merchant bán các đồ ăn tương tự, so sánh giá cả, chất lượng và các yếu tố cạnh tranh khác |
| Tìm kiếm nhà hàng | Hỗ trợ tìm kiếm nhà hàng xung quanh / theo tiêu chí của user |
| Phân tích tình trạng nhà hàng | Tổng hợp thông tin, metrics, reviews, complaints, menu/image, diagnosis/action từ các database và đưa ra khuyến nghị cho merchant |

## Nhược điểm kiến trúc Sprint 1:

1. **Thời gian phản hồi quá lâu** — latency trung bình ~1–2 phút trên 1 câu hỏi. Nguyên nhân: kiến trúc flow phụ thuộc vào planner và
các layer xử lý query intent quá phức tạp, gây nghẽn agent flow; luồng xử lý bị phức tạp hóa dù câu hỏi chỉ đơn giản.
2. **Chưa quản lý session memory và history memory phù hợp** — agentic chưa có tính cá nhân hóa tốt.
3. **Hệ thống evaluate, observation chưa monitor rõ ràng và khó quản lý, cập nhật.**
4. **Prompt cho mỗi agent chưa được quản lý tập trung** — cần service riêng quản lý prompt để phù hợp khi deploy, tránh rebuild nhiều lần khi cập nhật system prompt

## Kiến trúc mới của sprint-2

![alt text](image.png)

> **Planner agent** thực hiện semantic routing bằng khả năng suy luận của LLM. Phân loại câu hỏi của user làm 3 loại:
> 1. Câu hỏi đã đủ ngữ cảnh, có thể trả lời được luôn
> 2. Câu hỏi cần 1 agent (Task đơn lẻ)
> 3. Câu hỏi phức tạp cần nhiều agent (2-4 agents)
>
> Mỗi 1 lượt hỏi đáp đều sử dụng **Mem0** để cập nhật và truy suất memory của phiên hội thoại

Bảng ánh xạ Subagent -> list tools

| Agent  | Tools được phép sử dụng | Mô tả chức năng |
| --- | --- | --- |
| **Search Agent** | • `search_merchants`<br>• `get_public_merchant_detail` | Tìm kiếm merchant công khai theo tiêu chí và lấy thông tin chi tiết merchant |
| **Policy Agent** | • `search_policy_documents` | Tìm kiếm và truy xuất các điều khoản, quy chế, chính sách Green SM |
| **Cohort Agent** | • `search_merchants`<br>• `aggregate_public_merchant_cohort`<br>• `compare_owner_to_public_cohort`<br>• `compare_owner_to_nearby_public_merchants` | Tìm kiếm nhóm merchant, tổng hợp chỉ số cohort, so sánh và benchmark nhà hàng với nhóm đối thủ |
| **Owner Agent** | • `get_owner_profile_summary`<br>• `get_owner_operational_metrics`<br>• `get_owner_reviews`<br>• `get_owner_complaints`<br>• `get_owner_menu_and_food_images`<br>• `compare_merchant_images`<br>• `diagnose_owner_merchant`<br>• `recommend_owner_improvements` | Truy xuất toàn diện thông tin nội bộ của chủ nhà hàng (hồ sơ, chỉ số vận hành, reviews, khiếu nại, menu/ảnh) và chẩn đoán, đề xuất cải thiện |
| **Review Agent** | • `get_owner_reviews`<br>• `get_owner_complaints` | Chuyên phân tích đánh giá và khiếu nại của khách hàng / tài xế cho nhà hàng |


## **Các thay đổi so với Sprint 1**:

| Thành phần | Sprint 1 | Sprint 2 |
|---|---|---|
| Xử lý input | LLM trích suất ý chính và rewrite query | Input đưa trực tiếp vào planner agent cùng với memory từ Mem0 |
| Điều phối multi agent | Hierarchical pipeline, task được xử lý qua nhiều vòng (**latency cao**) | Planner quyết định một lần giữa trả lời trực tiếp và giao task |
| Lịch sử hội thoại | Concat 3 last turns và đưa vào context | **Mem0** cung cấp semantic memory liên quan |
| Subagent | Có thể handoff task cho agent khác và cần 1 verify agent sau mỗi lượt **(Latency cao**) | Sử dụng tool cho phép và sinh câu trả lời ngay |
| Tổng hợp response | Luôn cần thiết mỗi lượt | Chỉ cần khi có multi agent |
| Vector database | PostgreSQL lưu chunk, Chroma lưu vector | pgvector lưu cả nội dung lẫn embedding |
| Tracing | Đọc logs từ crewai | Tích hợp LangFuse cloud quản lý gọn hơn |
| Retrieval | Cosine similarity + top5| **Hybrid** (similarity + BM25) + Reciprocal Rank Fusion |

![changes](changes.png)

## Semantic memory với Mem0

Mem0 cung cấp lớp memory riêng cho từng principal và merchant advisor:

```python
user_id  = application principal
agent_id = merchant_id
run_id   = chat session ID
```

![alt text](image-1.png)
> Giao diện quản lý memory (Mem0) - Self hosted

Mỗi request chỉ gửi query hiện tại tới semantic search. Mem0 trả về tối đa
**3-5 memories** liên quan để planner sử dụng, thay vì đưa toàn bộ chat log vào
prompt. Search dùng `user_id` và `agent_id` để truy xuất kiến thức xuyên
session; `run_id` được giữ cho thao tác ghi memory của từng lượt hội thoại.

Lưu trữ chung với merchant data (Postgresql + pgvector)

## Planner và specialist runtime

Planner có hai kiểu quyết định:

- `respond`: context hiện có đã đủ để trả lời ngay;
- `delegate`: giao từ 1 đến 4 task độc lập cho các subagent `owner`,
  `market`, `policy`, `review` và `cohort`.

Mỗi specialist nhận một instruction cụ thể, có danh sách tools có thể gọi được định nghĩa rõ ràng. Specialist không gọi agent khác,
không mở rộng scope và không tạo thêm vòng lặp.

Runtime có ba đường thực thi rõ ràng:

1. Planner trả lời trực tiếp, không gọi specialist.
2. Một specialist thực thi task và output của specialist trở thành response
   cuối.
3. Hai đến bốn specialist chạy song song; synthesis sử dụng các kết quả đó để
   tạo một response thống nhất mà không gọi tool.

> Cấu trúc này loại bỏ NLU + rewrite layer, hierarchical
delegation loop, evidence-verifier handoff và synthesis không cần thiết. => **Tối ưu latency gấp 10 lần**

## Policy Knowledge Database

Sử dụng dữ liệu craw từ web với miền xanhsm.com

- Điều khoản sử dụng và quy định chung Green SM;
- Quy chế sử dụng sản phẩm Green SM Food;
- Điều khoản miễn trừ trách nhiệm;
- Quy trình giải quyết tranh chấp và khiếu nại;
- Chính sách bảo vệ dữ liệu cá nhân;
- Điều khoản chung của hợp đồng dịch vụ;
- Bộ quy tắc ứng xử dành cho thương nhân nhà hàng;
- Giới thiệu chương trình Green SM Merchant;
- Hướng dẫn và hỗ trợ đối tác nhà hàng.

### Xử lý và chunking tài liệu

Structured-based chunking theo heading 1, 2 từ định dạng Markdown.

- Chunk size: 1.024 token;
- Overlap: 64 token;

> => **174 chunks**

**Metadata**:
- Title
- URL
- Section path
- Section title
- Section level
- Chunk index
- Token count
- Content hash
- Chunk ID

### Embedding và vector index

Policy chunks sử dụng model embedding `BAAI/bge-small-en-v1.5` chạy local phù hợp với lượng tài liệu nhỏ, thời gian truy vấn nhanh. **Số chiều:** 384


## Hybrid retrieval với BM25, pgvector và RRF

Policy search kết hợp hai tín hiệu độc lập:
![hf](hybridflow.png)

1. **BM25 lexical retrieval** lấy tối đa 20 chunks phù hợp theo từ khóa và
   thuật ngữ chính sách.
2. **Dense vector retrieval** lấy tối đa 20 chunks gần nhất theo cosine
   similarity trên pgvector.
3. **Reciprocal Rank Fusion** hợp nhất hai ranking mà không phụ thuộc trực
   tiếp vào thang điểm riêng của BM25 hoặc vector search.
4. Hệ thống chọn 5 evidence chunks có thứ hạng tốt nhất và hydrate nội dung
   đầy đủ từ PostgreSQL.

BM25 xử lý tốt tên chương trình, thuật ngữ, mức phí và cụm từ chính xác. Dense
retrieval xử lý tốt câu hỏi diễn đạt khác với văn bản chính sách. RRF cân bằng
hai loại bằng chứng để agent nhận được context vừa đúng nghĩa vừa đúng thuật
ngữ.

## Langfuse prompts và evaluation-ready tracing

### Observations with langfuse:
![tracing view](trace.png)


### Prompt Management:
![prompt](prompt.png)

### Automation evaluation
![eval](evaluate.png)

## Công việc Sprint 3:

- Hoàn thiện kiểm tra đánh giá Latency, Token usage sau khi tối ưu pipeline
- LLM-as-a-Judge: Sử dụng LLM đánh giá chất lượng câu trả lời
- Hoàn thiện báo cáo chi tiết