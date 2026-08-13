# Phase 01 — Backend Profile REST + IDOR Guard

## Context Links
- Plan: `plans/260805-1005-unify-preference-memory-store/plan.md`
- Audit §7 M4 (stub routes), M7 (IDOR). Files: `backend/routes/user_routes.py`, `backend/repositories/user_profile_repository.py`, `backend/services/preference_confirm_service.py`, `backend/models/preference.py`, `backend/models/agent.py`.

## Overview
- **Priority**: High | **Status**: Pending | **Effort**: M
- Un-stub `GET /api/v1/users/{user_id}/profile`; thêm `PATCH /api/v1/users/{user_id}/profile` (edit tay). Thêm IDOR guard. Repo method `apply_fields` (1 tx, B5 validation). Là nền cho phase 02/03/04.

## Key Insights
- Có sẵn `UserProfilePublic` (`models/preference.py`) + `UserProfileRepository.apply_delta` (B5 typed validation, per-field). Tái dùng cho PATCH.
- Confirm path (suggestion) giữ nguyên — PATCH là write path RIÊNG (edit toàn phần), không qua `preference_events` audit suggestion (nhưng vẫn log). Quyết: PATCH cũng append `preference_events(source="user_edit", status="confirmed")` để truy vết.
- `not_implemented` helper ở `routes/stub_helpers.py`.

## Requirements
- **FR-1**: `GET /{user_id}/profile` → 200 `UserProfilePublic` (404 nếu absent, hoặc 200 với default? → quyết: 404 để FE tạo on-demand; giữ nhất quán `get_user_profile` tool raise NotFoundError).
- **FR-2**: `PATCH /{user_id}/profile` body=`{field: value, ...}` (chỉ taste fields: liked/disliked_cuisines, spice_tolerance, dietary, budget_level, distance_preference_km) → 200 `UserProfilePublic`. Field sai → 400. Unknown field → bỏ qua hay 400? → 400 (strict, bắt lỗi FE sớm).
- **FR-3**: IDOR guard dependency `require_dev_only` (cho phép nếu `settings.app_env != "prod"`; prod → 403 + log). Comment TODO(AUTH) rõ ràng.
- **NFR**: 1 tx/req. Validate trước khi write (B5). Không surface `overall_score`/internal.

## Architecture
- Route layer: validate whitelist + gọi service. Service `UserProfileRepository.apply_fields(patch, user_id)` mở Session (hoặc nhận Session injected — nhưng theo contract hiện tại repo nhận Session; route mở Session). **Quyết**: thêm `with_session` helper ở route (như `preference_confirm_service` đang tự mở SessionLocal) — hoặc tốt hơn: route gọi 1 thin service `user_profile_service.update_profile(user_id, patch)` owns 1 tx (giảm trùng lặp, đúng hướng #12 audit). Tạo `services/user_profile_service.py`.
- `apply_fields`: lặp per-field qua cùng logic `_APPLY_*` validation của `apply_delta` (refactor: extract `_validate_and_resolve(field, op, value)` dùng chung). Mặc định op=`set` cho list/enum/float (PATCH = set toàn phần từng field); list field PATCH nhận list (replace).
- Guard: `core/dependencies.py` thêm `require_dev_only` (FastAPI Depends).

## Related Code Files
- **Modify**: `routes/user_routes.py` (un-stub GET, +PATCH, +guard), `repositories/user_profile_repository.py` (+`apply_fields`, refactor shared validation), `core/dependencies.py` (+guard), `core/settings.py` (+`app_env` nếu thiếu).
- **Create**: `services/user_profile_service.py` (thin: `get_profile`, `update_profile`), `models/agent.py` (+`ProfilePatchRequest` DTO).
- **Delete**: — (giữ `list_sessions`/`delete_preference` stub — out of scope; ghi TODO).

## Implementation Steps
1. `core/settings.py`: thêm `app_env: str = "dev"` (đọc `APP_ENV`).
2. `core/dependencies.py`: `require_dev_only(request)` — raise 403 nếu `settings.app_env == "prod"`; log warning + return True otherwise.
3. `repositories/user_profile_repository.py`: extract `_validate_and_resolve(field, operation, value) -> Any` từ `apply_delta`; thêm `apply_fields(patch: dict, *, user_id) -> UserProfilePublic` (1 tx: get-or-create row + per-field set + commit). List-field PATCH yêu cầu list (replace).
4. `models/agent.py`: `ProfilePatchRequest` (Pydantic, các taste field optional, validator whitelist).
5. `services/user_profile_service.py`: `get_profile(user_id)` (404 raise), `update_profile(user_id, patch)` (gọi `apply_fields`, append preference_event source=user_edit, F3-safe log).
6. `routes/user_routes.py`: GET → `user_profile_service.get_profile`; PATCH → validate + `update_profile`; cả 2 + confirm/reject thêm `Depends(require_dev_only)`.

## Todo List
- [ ] settings.app_env + require_dev_only guard
- [ ] extract _validate_and_resolve; apply_fields repo method
- [ ] ProfilePatchRequest DTO
- [ ] user_profile_service (get/update)
- [ ] un-stub GET + thêm PATCH + guard trên routes
- [ ] chạy `python -m py_compile` + lint

## Success Criteria
- GET trả profile thật (200/404). PATCH cập nhật field, trả profile mới.
- Field/value sai → 400. Whitelist chặn field lạ (không ghi user_id/PK).
- prod env → 403; dev → ok (log).
- Unit test: PATCH happy + 3 trường hợp 400 + idempotent-ish + guard.

## Risk Assessment
- PATCH ghi đè list (replace) khi FE gửi thiếu field → mất dữ liệu. **Mitigation**: PATCH = partial (chỉ field có trong body), FE gửi đúng field; test rõ.
- Guard chặn nhầm dev. **Mitigation**: default `app_env=dev`; test cả 2 nhánh.

## Security Considerations
- IDOR: guard là tạm thời; TODO(AUTH) rõ ràng + doc deployment. Whitelist field (không ghi PK/updated_at). PII: profile không lưu PII; preference_event log không ghi value nhạy.

## Next Steps
- Phase 02 (ranking) + 03 (context_memory) + 04 (FE) phụ thuộc GET/PATCH này.
