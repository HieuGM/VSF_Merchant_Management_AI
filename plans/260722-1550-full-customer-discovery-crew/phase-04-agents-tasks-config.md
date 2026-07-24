# Phase 04 — Agents + Tasks config (viết sẵn ĐẦY ĐỦ, đúng format CrewAI)

**Priority:** P1 · **Status:** ☐ · **Depends:** P03 (tool names tồn tại)

## Overview
Điền `agents/customer/config/agents.yaml` + `tasks.yaml` (đang stub rỗng). 4 agent theo §5.2/§5.5,
3 task specialist + coordinator làm manager (hierarchical). Nội dung dưới đây **ready-to-paste**,
KHÔNG để lười chỗ nào. Mỗi task có description (what/how/context/constraints/inputs) +
expected_output (format/fields) + output_pydantic + context deps.

## Format CrewAI đã verify
- `agents.yaml`: mỗi agent `role`/`goal`/`backstory` (folded `>`), optional `max_iter`,
  `max_execution_time`, `allow_delegation`, `verbose`. `{var}` interpolation single-brace.
- `tasks.yaml`: `description` + `expected_output` (LUÔN là string mô tả, KHÔNG phải tên class) +
  `agent` + `context` (deps). Structured output khai `output_pydantic` ở crew.py (P05), không ở yaml.
- Process: **hierarchical**, `manager_agent = customer_coordinator`; 3 specialist tắt delegation.
- **KHÔNG set `llm:` trong agents.yaml** — LLM gán per-agent trong crew.py (P05) vì cần api_key/base_url
  từ settings (NVIDIA NIM: coordinator+search=70b, reasoning+explanation=8b).

## Output Pydantic models (tạo ở models/ — P05 dùng làm output_pydantic)
> Thêm vào `backend/models/agent.py` (hoặc `models/customer_tasks.py`). Reuse `ProfileDeltaSuggestion` (models/preference.py).
```python
class MerchantCandidate(BaseModel):
    merchant_id: str; name: str; cuisine: str | None = None
    address: str | None = None; distance_km: float | None = None
    avg_rating: float | None = None; match_score: float = 0.0

class SearchTaskOutput(BaseModel):
    candidates: list[MerchantCandidate]
    applied_filters: dict[str, Any] = Field(default_factory=dict)
    count: int = 0

class PreferenceTaskOutput(BaseModel):
    suggestions: list[ProfileDeltaSuggestion] = Field(default_factory=list)
    weather_summary: str | None = None
    reasoning: str | None = None

class ExplanationTaskOutput(BaseModel):
    answer: str
    reasons: list[str] = Field(default_factory=list)
    referenced_signals: list[str] = Field(default_factory=list)
# Final crew output = CustomerChatResponse (đã có models/agent.py)
```

---

## `agents/customer/config/agents.yaml` (ĐẦY ĐỦ)
```yaml
customer_coordinator:
  role: >
    Điều phối viên Khám phá Ẩm thực (Customer Discovery Coordinator)
  goal: >
    Hiểu đúng ý định của người dùng từ câu hỏi "{query}", nạp bối cảnh (hồ sơ sở thích,
    ứng viên trong phiên) và điều phối đúng chuyên gia (tìm quán / suy luận sở thích /
    giải thích) để trả về gợi ý quán ăn phù hợp, mạch lạc, có căn cứ.
  backstory: >
    Bạn là điều phối viên kỳ cựu của một nền tảng ẩm thực Việt Nam, 10 năm kinh nghiệm
    hiểu nhu cầu thực khách. Bạn giỏi tách bạch việc: khi nào cần tìm quán mới, khi nào
    chỉ tinh chỉnh danh sách đã có, khi nào cần giải thích. Bạn giao việc gọn cho đúng
    chuyên gia và tổng hợp kết quả, không tự làm thay phần chuyên môn của họ.
  allow_delegation: true
  max_iter: 8
  max_execution_time: 90
  verbose: true

restaurant_search:
  role: >
    Chuyên gia Tìm kiếm Nhà hàng (Restaurant Search Specialist)
  goal: >
    Chuyển ràng buộc đã chuẩn hoá (cuisine, ngân sách, vị trí, bán kính) thành lời gọi
    công cụ tìm kiếm và trả về danh sách quán ứng viên xếp hạng theo mức phù hợp và khoảng cách.
  backstory: >
    Bạn thuộc lòng dữ liệu 1.600+ quán ăn ở TP.HCM. Bạn luôn gọi công cụ tìm kiếm thay vì
    bịa dữ liệu, biết chọn merchant_search khi có bộ lọc tổng quát và nearby_merchant_search
    khi ưu tiên khoảng cách. Bạn không suy diễn thông tin không có trong kết quả công cụ.
  allow_delegation: false
  max_iter: 6
  max_execution_time: 60

preference_reasoning:
  role: >
    Chuyên gia Suy luận Sở thích & Bối cảnh (Preference & Context Reasoning Specialist)
  goal: >
    Kết hợp sở thích đã xác nhận, ràng buộc trong phiên và bối cảnh thời tiết/vị trí để
    ĐỀ XUẤT (không lưu) các thay đổi hồ sơ hợp lý, kèm lý do rõ ràng cho từng đề xuất.
  backstory: >
    Bạn là chuyên gia phân tích hành vi ẩm thực. Bạn kết hợp tín hiệu tường minh (người dùng
    nói) với tín hiệu ngầm (thời tiết mưa, vị trí, ngân sách sinh viên) để đề xuất tinh chỉnh
    sở thích. Bạn TUYỆT ĐỐI không tự lưu thay đổi — chỉ đề xuất; việc xác nhận thuộc về người dùng.
  allow_delegation: false
  max_iter: 6
  max_execution_time: 60

customer_explanation:
  role: >
    Chuyên gia Giải thích Kết quả (Result Explanation Specialist)
  goal: >
    Giải thích ngắn gọn, thuyết phục vì sao các quán được gợi ý khớp với nhu cầu, dựa trên
    tín hiệu hồ sơ nhìn thấy được và dữ liệu quán (hồ sơ 8 chiều).
  backstory: >
    Bạn là người kể chuyện ẩm thực, biến số liệu khô khan thành lời giải thích dễ hiểu.
    Bạn chỉ dùng dữ kiện có thật từ công cụ get_merchant_profile và tín hiệu hồ sơ; không
    thổi phồng, không bịa điểm mạnh mà dữ liệu không hỗ trợ.
  allow_delegation: false
  max_iter: 5
  max_execution_time: 45
```

---

## `agents/customer/config/tasks.yaml` (ĐẦY ĐỦ)
```yaml
search_task:
  description: >
    Tìm các quán ăn phù hợp với yêu cầu: "{query}".
    Ràng buộc đã biết — cuisine: {cuisine}, thành phố: {city}, ngân sách: {budget},
    vị trí: (lat={lat}, lng={lng}), bán kính tối đa: {radius_km} km.

    Cách làm:
    1. Chuẩn hoá ràng buộc thành tham số tìm kiếm.
    2. Nếu người dùng ưu tiên "gần đây" hoặc có toạ độ + bán kính → dùng nearby_merchant_search;
       ngược lại dùng merchant_search với các bộ lọc phù hợp.
    3. Trả tối đa 10 quán, ưu tiên match_score cao rồi tới khoảng cách gần.

    Ràng buộc: CHỈ dùng dữ liệu trả về từ công cụ, KHÔNG bịa quán/địa chỉ/đánh giá.
    Nếu không có kết quả, trả danh sách rỗng và nêu rõ.
  expected_output: >
    Danh sách quán ứng viên (tối đa 10). Mỗi quán gồm: merchant_id, name, cuisine, address,
    distance_km (nếu có toạ độ), avg_rating, match_score. Kèm applied_filters (các bộ lọc đã
    dùng) và count (số quán). Không thêm quán ngoài kết quả công cụ.
  agent: restaurant_search

preference_task:
  description: >
    Suy luận và ĐỀ XUẤT tinh chỉnh hồ sơ sở thích cho người dùng {user_id} (phiên {session_id}),
    dựa trên yêu cầu "{query}".

    Cách làm:
    1. Gọi get_user_profile để đọc sở thích đã xác nhận.
    2. Gọi get_session_candidates để biết ứng viên đã có trong phiên (nếu có).
    3. Nếu có toạ độ, gọi get_weather_context({lat},{lng}) lấy thời tiết; trời mưa → cân nhắc
       ưu tiên quán gần / giao tận nơi.
    4. Gọi propose_profile_delta với constraints rút ra từ hội thoại + weather để sinh đề xuất.

    Ràng buộc: TUYỆT ĐỐI KHÔNG lưu thay đổi vào hồ sơ — chỉ đề xuất (candidate). Mỗi đề xuất
    phải kèm lý do (rationale). Nếu không có tín hiệu đủ mạnh, trả danh sách đề xuất rỗng.
  expected_output: >
    Danh sách đề xuất thay đổi hồ sơ (có thể rỗng). Mỗi đề xuất: field, operation (add/remove/set),
    value, confidence (0-1), rationale (lý do bằng tiếng Việt). Kèm weather_summary (tóm tắt thời
    tiết nếu có) và reasoning (giải thích tổng thể). KHÔNG chứa dấu hiệu đã ghi vào DB.
  agent: preference_reasoning
  context:
    - search_task

explanation_task:
  description: >
    Giải thích vì sao các quán trong danh sách ứng viên khớp với nhu cầu "{query}" của người dùng.

    Cách làm:
    1. Với vài quán tiêu biểu ở đầu danh sách, gọi get_merchant_profile(merchant_id) để lấy
       hồ sơ 8 chiều (chất lượng món, phục vụ, hình ảnh...).
    2. Đối chiếu điểm mạnh của quán với tín hiệu sở thích (cuisine thích, ngân sách, khoảng cách)
       và các đề xuất từ bước suy luận sở thích.
    3. Viết câu trả lời thân thiện, ngắn gọn cho người dùng.

    Ràng buộc: CHỈ dùng dữ kiện có thật từ get_merchant_profile và hồ sơ; không thổi phồng.
    Nêu tối đa 3 lý do/quán.
  expected_output: >
    Một câu trả lời tiếng Việt (2-5 câu) giải thích lựa chọn, kèm: reasons (danh sách lý do ngắn
    gọn, mỗi lý do gắn với dữ kiện quán hoặc tín hiệu hồ sơ) và referenced_signals (các tín hiệu
    hồ sơ/chiều dữ liệu đã tham chiếu). Không bịa điểm mạnh không có trong dữ liệu.
  agent: customer_explanation
  context:
    - search_task
    - preference_task
```

---

## Implementation steps
1. Paste 2 file YAML trên; rà `{var}` khớp inputs crew.kickoff (P05/P06): query, cuisine, city,
   budget, lat, lng, radius_km, user_id, session_id.
2. Tạo output Pydantic models (models/).
3. Verify YAML load: `python -c "import yaml,pathlib; [yaml.safe_load(open(p)) for p in [...]]"`.
4. `allowed_tools` không còn cần trong agents.yaml (tool gắn ở crew.py qua adapter theo allow_list.py) —
   NHƯNG contract test hiện có kiểm `allowed_tools` yaml ↔ allow_list. → GIỮ block `allowed_tools`
   trong agents.yaml khớp allow_list.py (đừng xoá) để test pass; hoặc cập nhật contract test.
   (Quyết định: GIỮ `allowed_tools` cho mỗi agent = đúng allow_list.py.)

## Todo
- [ ] agents.yaml: 4 agent đầy đủ role/goal/backstory + max_iter/timeout/delegation + allowed_tools
- [ ] tasks.yaml: 3 task đầy đủ description + expected_output + agent + context
- [ ] output Pydantic models (MerchantCandidate, SearchTaskOutput, PreferenceTaskOutput, ExplanationTaskOutput)
- [ ] YAML valid; `{var}` khớp inputs; allowed_tools ↔ allow_list.py sync (contract test pass)
- [ ] delegation chỉ coordinator

## Success criteria
- YAML load không lỗi; contract test yaml↔allow-list pass.
- Chỉ coordinator có allow_delegation: true.
- Task có context deps đúng (preference & explanation phụ thuộc search).

## Risks
- Interpolation thiếu biến → literal `{var}` lọt vào prompt. Đảm bảo P06 truyền đủ inputs
  (dùng default rỗng cho biến optional: cuisine/city/budget/radius_km khi None → truyền "" ).
- Hierarchical + `agent:` trong task: CrewAI cho phép gán agent hint; nếu xung đột manager,
  verify qua `crewai-skills:ask-docs`. Fallback: bỏ `agent:` để manager tự phân (kém xác định hơn).

## Next
→ Phase 05: crew.py đọc yaml, gắn tool (adapter), output_pydantic, hierarchical manager=coordinator.
