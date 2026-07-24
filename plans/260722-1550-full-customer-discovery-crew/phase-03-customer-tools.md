# Phase 03 — Customer Crew tool catalog (ĐẦY ĐỦ 7 tool)

**Priority:** P0 · **Status:** ☐ · **Depends:** P02 (data/providers)

## Overview
Toàn bộ tool mà Customer Crew cần để chạy đủ chức năng UC-04/UC-05 (design §5.4). 7 tool:
2 đã có (search), 1 shared read-only (đã có fixture), 4 viết mới. Phase này định nghĩa
**spec đầy đủ từng tool** (input/output/args_schema/behavior/errors) để adapter (P01) bọc
thành CrewAI BaseTool. Mọi tool: plain function nhận kwargs, tự mở/đóng `SessionLocal`,
`register(reg)` với `allowed_agents=agents_allowed_for(name)`.

## Bảng tổng quan 7 tool (§5.4)
| # | Tool | Dùng bởi agent(s) | Trạng thái | File |
|---|---|---|---|---|
| 1 | `merchant_search` | restaurant_search | ✅ có | tools/customer/merchant_tools.py |
| 2 | `nearby_merchant_search` | restaurant_search | ✅ có | tools/customer/merchant_tools.py |
| 3 | `get_user_profile` | customer_coordinator, preference_reasoning | ❌ mới | tools/customer/customer_context_tools.py |
| 4 | `get_session_candidates` | customer_coordinator, preference_reasoning | ❌ mới | tools/customer/customer_context_tools.py |
| 5 | `get_weather_context` | preference_reasoning | ❌ mới | tools/customer/weather_tools.py |
| 6 | `propose_profile_delta` | preference_reasoning | ❌ mới | tools/customer/customer_context_tools.py |
| 7 | `get_merchant_profile` | customer_explanation | ✅ có (shared fixture) | tools/shared/shared_readonly_tools.py |

> `allow_list.py` ĐÃ khai báo đủ 7 (không sửa). Registry tự cross-check `allowed_agents` khi register.

---

## Spec chi tiết từng tool

### 1. `merchant_search` ✅ (giữ nguyên, chỉ rà lại)
- **Input:** query, cuisine, city, min_price, max_price, min_rating, lat, lng, radius_km, limit(=20)
- **Output dict:** `{merchants: [{merchant_id,name,cuisine,address,city,lat,lng,distance_km,avg_rating,match_score}], total, filters_applied}`
- **Behavior:** service ranking (§11.2). cache_policy=`none`. Không side-effect.
- **Rà:** đảm bảo `to_dict()` không lộ field nội bộ; giữ nguyên.

### 2. `nearby_merchant_search` ✅ (giữ nguyên)
- **Input:** lat(req), lng(req), radius_km(=5.0), cuisine, limit(=20)
- **Output:** `{merchants:[...], total, search_center:{lat,lng}, radius_km}`
- **Behavior:** Haversine (`haversine()` PL/pgSQL hoặc service). cache_policy=`none`.

### 3. `get_user_profile` ❌ mới
- **Mục đích:** đọc hồ sơ sở thích đã xác nhận của user (§6.5).
- **args_schema `GetUserProfileArgs`:** `user_id: str = Field(..., description="ID người dùng")`
- **Output dict** (= `UserProfilePublic.model_dump()`):
  `{user_id, liked_cuisines[], disliked_cuisines[], spice_tolerance, dietary[], budget_level, distance_preference_km, current_lat, current_lng, context_memory{}, updated_at}`
- **Behavior:** `user_profile_repository.get_by_id(user_id)` → map `UserProfilePublic`.
  cache_policy=`profile_snapshot` (key `CacheKeys.profile_snapshot(user_id)`, TTL 15').
- **Errors:** không thấy → `NotFoundError(f"Không tìm thấy hồ sơ user '{user_id}'")`.
- **Side-effect:** không.

### 4. `get_session_candidates` ❌ mới
- **Mục đích:** đọc danh sách quán ứng viên đã tạo trong session hiện tại (để refine, tránh search lại).
- **args_schema `GetSessionCandidatesArgs`:** `session_id: str = Field(..., description="ID phiên chat")`
- **Output dict:** `{session_id, candidates: [{merchant_id, name, cuisine, ...}], total}`
- **Behavior:** `session_repository.get_candidates(session_id)` đọc từ
  `chat_sessions.context_snapshot_json` (hot copy trong Redis qua CachePort key
  `CacheKeys.session_candidates`, TTL 5'). Session rỗng/không có → `{candidates: [], total: 0}` (KHÔNG raise).
- **Side-effect:** không.

### 5. `get_weather_context` ❌ mới
- **Mục đích:** lấy thời tiết hiện tại tại vị trí user để reasoning (mưa → ưu tiên giao tận nơi/quán gần).
- **args_schema `GetWeatherArgs`:** `lat: float = Field(..., description="Vĩ độ")`, `lng: float = Field(..., description="Kinh độ")`
- **Output dict:** `{weather: {temperature_c, precipitation_mm, condition, is_rain} | null, source:"open-meteo", cached: bool}`
- **Behavior:** `open_meteo_provider.get_current(lat,lng)` + cache (`CacheKeys.weather`, TTL 10').
  cache_policy=`weather`.
- **Errors/degrade:** timeout/HTTP lỗi → `{weather: null, ...}` (KHÔNG raise, không fail crew).
- **Side-effect:** không (chỉ đọc + cache).

### 6. `propose_profile_delta` ❌ mới
- **Mục đích:** ĐỀ XUẤT thay đổi hồ sơ (candidate delta) dựa trên tín hiệu; **KHÔNG persist** (§7.1).
  Persist là việc của route `/preferences` (§11.6), không phải tool.
- **args_schema `ProposeDeltaArgs`:**
  `user_id: str`, `session_id: str | None = None`,
  `constraints: dict = Field(default_factory=dict, description="Ràng buộc rút từ hội thoại, vd {'cuisine':'chay','budget':'student'}")`,
  `weather: dict | None = Field(None, description="Kết quả get_weather_context")`
- **Output dict:** `{suggestions: [ProfileDeltaSuggestion{delta_id, field, operation, value, confidence, rationale}], count}`
- **Behavior:** `preference_service.propose_deltas(...)` — rule-based (KISS), vd:
  trời mưa → suggest `distance_preference_km` giảm / ưu tiên gần; constraints có "sinh viên" → `budget_level=student`;
  cuisine lặp lại nhiều → thêm vào `liked_cuisines`. Mỗi suggestion có `rationale` (giải thích vì sao).
- **[GUARDRAIL] KHÔNG ghi `preference_events` / `user_profiles`.** has_side_effect=`False`.

### 7. `get_merchant_profile` ✅ (shared, giữ nguyên)
- **Input:** `merchant_id: str`
- **Output:** hồ sơ 8 chiều public (đã strip `overall_score`, §6.4). Phase 0: fixture-backed.
- **Dùng bởi:** customer_explanation (giải thích kết quả tham chiếu dimensions/attributes).

---

## Related files
- CREATE: `backend/tools/customer/customer_context_tools.py` (tool 3,4,6 + args_schema + register)
- CREATE: `backend/tools/customer/weather_tools.py` (tool 5 + args_schema + register)
- (args_schema Pydantic đặt CẠNH tool trong cùng file — adapter đọc `spec.args_schema` nếu khai,
  không thì tự sinh từ input_schema. Khuyến nghị KHAI args_schema tường minh cho 4 tool mới để
  LLM có field description tốt.)
- NO EDIT allow_list.py / registry.py.

## Reference skeleton (1 tool, đúng pattern merchant_tools.py + args_schema)
```python
# tools/customer/customer_context_tools.py
from pydantic import BaseModel, Field
from database.connection import SessionLocal
from repositories.user_profile_repository import UserProfileRepository
from tools.allow_list import agents_allowed_for
from tools.registry import ToolRegistry, ToolSpec

class GetUserProfileArgs(BaseModel):
    user_id: str = Field(..., description="ID người dùng cần lấy hồ sơ sở thích")

def get_user_profile(*, user_id: str) -> dict:
    db = SessionLocal()
    try:
        return UserProfileRepository(db).get_public(user_id).model_dump()
    finally:
        db.close()

def register(reg: ToolRegistry) -> None:
    reg.register(ToolSpec(
        name="get_user_profile",
        description="Lấy hồ sơ sở thích đã xác nhận của người dùng (cuisine thích/ghét, mức chi, khẩu vị, ăn kiêng, vị trí).",
        input_schema={"user_id": "str (required)"},
        output_schema={"user_id":"str","liked_cuisines":"list","budget_level":"str","...":"..."},
        allowed_agents=agents_allowed_for("get_user_profile"),
        cache_policy="profile_snapshot", source_kind="real",
        args_schema=GetUserProfileArgs,   # nếu đã thêm field này vào ToolSpec (P01)
    ), get_user_profile)
    # ... get_session_candidates, propose_profile_delta tương tự
```

## Todo
- [ ] customer_context_tools.py: get_user_profile, get_session_candidates, propose_profile_delta (+3 args_schema + register)
- [ ] weather_tools.py: get_weather_context (+args_schema + register)
- [ ] (nếu chọn args_schema tường minh) thêm `args_schema: type[BaseModel] | None = None` vào ToolSpec
- [ ] auto_discover("tools.customer") load đủ 6 tool, allow-list cross-check pass
- [ ] get_weather_context trả weather:null khi provider None
- [ ] propose_profile_delta KHÔNG ghi DB

## Success criteria
- `registry.names()` chứa đủ 6 customer tool + 2 shared sau auto_discover (shared + customer).
- Mỗi tool có `args_schema` hợp lệ → adapter bọc ra BaseTool có field description.
- `get_user_profile(user_id="user_demo")` trả profile; unknown → NotFoundError.
- `propose_profile_delta(...)` → `preference_events` count KHÔNG đổi.
- `get_weather_context` offline → `{weather: null}`.

## Risks
- Sai `allowed_agents` → registry raise. Luôn `agents_allowed_for(name)`.
- Output không JSON-serializable → adapter json.dumps fail. Luôn dict thuần / `.model_dump()`.

## Next
→ Phase 04: agents.yaml/tasks.yaml dùng đúng 7 tool-name này.
