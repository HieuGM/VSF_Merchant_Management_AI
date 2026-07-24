# Phase 02 — Data layer + providers (repos + weather + seed)

**Priority:** P0 · **Status:** ☐ · **Depends:** none (song song P01)

## Overview
Dựng lớp dữ liệu cho 4 tool mới: user_profile repo, session candidates, preference-delta
logic (no persist), weather provider (Open-Meteo + cache). + seed `user_demo`.

## Key insights
- Bảng đã có: `user_profiles`, `chat_sessions` (`context_snapshot_json`, `last_trace_id`),
  `chat_messages` (`structured_payload_json`), `preference_events`. Models Pydantic sẵn:
  `UserProfilePublic`, `ProfileDeltaSuggestion`, `PreferenceEvent` (`models/preference.py`).
- Cache: `core/cache.py` có `CacheKeys.weather(lat,lng)`, `TTL_WEATHER=600`,
  `CacheKeys.session_candidates(session_id, constraint_hash)`, `TTL_CANDIDATES=300`.
  Lấy adapter qua `core.dependencies.get_cache()`.
- `providers/weather/` đã có package rỗng — điền vào đây.
- Pattern repo: xem `repositories/merchant_repository.py`. Repo nhận `Session`, KHÔNG mở session.
  Tool là lớp mở/đóng `SessionLocal` (Phase 03).
- Open-Meteo: `https://api.open-meteo.com/v1/forecast?latitude=..&longitude=..&current=temperature_2m,precipitation,weather_code` — free, no key.

## Requirements
1. `user_profile_repository.py`: `get_by_id(user_id) -> UserProfile | None` → map sang `UserProfilePublic`.
2. `session_repository.py`: `get_candidates(session_id) -> list[dict]` — đọc candidates từ
   `chat_sessions.context_snapshot_json` (hoặc last `chat_messages.structured_payload_json`). Nếu
   session không có → `[]`.
3. `preference_delta` logic (service-level, no DB write): hàm thuần nhận (explicit constraints,
   weather, profile) → trả `list[ProfileDeltaSuggestion]`. KHÔNG ghi `preference_events`.
4. `providers/weather/open_meteo_provider.py`: `get_current(lat, lng) -> dict | None`. Cache qua
   CachePort (`CacheKeys.weather`, `TTL_WEATHER`). Timeout ngắn (3s). Lỗi/timeout → `None`
   (degrade gracefully). Dùng `httpx` (check requirements; nếu chưa có → thêm).
5. Seed `user_demo`: 1 `user_profiles` row + 1 `chat_sessions` row (idempotent upsert). Đặt trong
   script seed hiện có (xem `scripts/`/seed Phase 0.5) hoặc `backend/scripts/seed_user_demo.py`.

## Related files
- CREATE: `backend/repositories/user_profile_repository.py`, `backend/repositories/session_repository.py`
- CREATE: `backend/providers/weather/open_meteo_provider.py`
- CREATE: `backend/services/preference_service.py` (delta logic, no persist)
- CREATE/EDIT: seed script cho `user_demo` (idempotent)
- CHECK: `backend/requirements.txt` — `httpx` present?

## Implementation steps
1. user_profile_repo + map ORM→`UserProfilePublic`.
2. session_repo `get_candidates` đọc snapshot JSON.
3. `preference_service.propose_deltas(...)` thuần logic (rule-based đơn giản: vd trời mưa →
   suggest "prefer delivery"; profile thiếu budget + query có "sinh viên" → suggest budget=student).
   KISS — vài rule, trả `ProfileDeltaSuggestion` list.
4. Open-Meteo provider + cache + timeout + None-on-error.
5. Seed user_demo idempotent (ON CONFLICT DO NOTHING / merge).
6. Verify: `python -c` import từng module; seed chạy 2 lần không lỗi (idempotent).

## Todo
- [ ] user_profile_repository
- [ ] session_repository (candidates từ snapshot)
- [ ] preference_service.propose_deltas (no persist)
- [ ] open_meteo_provider (+cache +timeout +None fallback)
- [ ] seed user_demo + chat_session (idempotent)
- [ ] httpx dependency confirmed

## Success criteria
- `get_by_id("user_demo")` trả `UserProfilePublic` sau seed.
- `open_meteo_provider.get_current(10.77,106.70)` trả dict (hoặc None khi offline — không raise).
- Gọi provider lần 2 → cache hit (không HTTP call).
- `propose_deltas` KHÔNG tạo row trong `preference_events`.

## Risks
- Open-Meteo downtime/CI offline → test phải monkeypatch HTTP, không gọi mạng thật.
- session candidates shape chưa chuẩn hoá → định nghĩa contract dict tối thiểu `{merchant_id, name, ...}`.

## Next
→ Phase 03 wrap các hàm này thành registered tools.
