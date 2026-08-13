# Phase 04 — FE Cutover localStorage → Profile API

## Context Links
- Plan: `plans/260805-1005-unify-preference-memory-store/plan.md`
- Audit §7 M1, M5, M6. Files: `frontend/src/customer/hooks/use-preferences.ts`, `frontend/src/customer/pages/preference-center.tsx`, `frontend/src/customer/api/customer-agent-client.ts`, `frontend/src/customer/pages/customer-chat.tsx`, `frontend/src/customer/hooks/use-customer-identity.ts`.

## Overview
- **Priority**: High | **Status**: Pending | **Effort**: L | **Depends**: 01
- Preference Center ghi thẳng backend `user_profiles`; tách taste (API) khỏi geo UI state (local); bỏ query-appending `preferencesToContext` (M5) khi ranking on; xử lý profile trả về từ confirmDelta (M6).

## Key Insights
- **Storage split**: taste (budget/dietary/liked/disliked/spice) → backend. **Geo UI state** (useLocation/locationReady/lat/lng/accuracy) → giữ localStorage (trạng thái thiết bị, không portable). Tách `usePreferences` → `useTasteProfile` (API-backed) + `useGeolocation` (đã có `use-geolocation.ts` — tái dùng/kết nối).
- Resilient: read-through cache — load từ API, cache localStorage; offline fallback đọc cache; migrate prefs localStorage cũ lên API lần đầu thành công.
- Sau phase 02 (ranking deterministic server-side) → `preferencesToContext` (append text query) **không còn cần** → xóa (M5). Trước khi 02 done, giữ tạm làm fallback.
- `confirmDelta` trả profile (M6) → cập nhật local cache taste profile để UI đồng bộ ngay (đang ignore).

## Requirements
- **FR-1**: API client `getProfile(userId)` + `patchProfile(userId, patch)` (dùng `shared/api-client` hoặc raw fetch nhất quán với `confirmDelta`).
- **FR-2**: `useTasteProfile(userId)`: load on mount (API → cache localStorage), update via PATCH (debounced ~400ms), optimistic + rollback on error. Migration: nếu API trả empty VÀ localStorage có prefs cũ → PATCH lên 1 lần.
- **FR-3**: `preference-center.tsx` bind vào `useTasteProfile`; thêm section xem/xóa `context_memory.notes` (sau phase 03).
- **FR-4**: `customer-chat.tsx`: xóa `preferencesToContext` append (sau 02); giữ geo (lat/lng/locationReady) gửi như cũ.
- **FR-5**: chat-message `confirmDelta` success → refetch/merge taste profile vào cache.
- **NFR**: không flash trắng (skeleton khi loading). Loi~ handling (toast/inline). TypeScript strict.

## Architecture
- `api/customer-agent-client.ts`: +`getProfile`, `patchProfile` (return UserProfilePublic-ish; map field camelCase: liked_cuisines→likedCuisines).
- `hooks/use-taste-profile.ts` (mới, ~120 LOC): state + API + cache + migrate. Field map taste↔backend.
- `hooks/use-preferences.ts`: giữ chỉ geo state (rename `use-geolocation-prefs` hoặc gộp vào `use-geolocation.ts`). Hoặc giữ `usePreferences` nhưng chỉ geo — quyết: tách sạch ra 2 hook cho rõ.
- `preference-center.tsx`: dùng `useTasteProfile`.
- Type share: tạo `frontend/src/customer/api/profile-types.ts` (UserProfile FE shape).

## Related Code Files
- **Create**: `hooks/use-taste-profile.ts`, `api/profile-types.ts`.
- **Modify**: `api/customer-agent-client.ts` (+getProfile/patchProfile), `pages/preference-center.tsx` (bind API + context_memory view), `pages/customer-chat.tsx` (drop preferencesToContext after 02), `components/chat-message.tsx` (confirmDelta → merge profile), `hooks/use-preferences.ts` (reduce to geo only) hoặc xóa nếu gộp.
- **Delete**: `preferencesToContext` (sau 02).

## Implementation Steps
1. `profile-types.ts`: FE UserProfile shape (camelCase) + map fn.
2. `customer-agent-client.ts`: `getProfile`/`patchProfile`.
3. `use-taste-profile.ts`: load/cache/update/migrate (debounced PATCH, optimistic+rollback).
4. `preference-center.tsx`: bind `useTasteProfile`; skeleton; (phase 03 xong) section context_memory notes (xóa note → PATCH).
5. `customer-chat.tsx`: sau 02 on → xóa `preferencesToContext`; giữ geo.
6. `chat-message.tsx`: `confirmDelta` ok → merge profile vào cache `useTasteProfile`.
7. Build: `npm run build` (0 error) + oxlint.

## Todo List
- [ ] profile-types + API client getProfile/patchProfile
- [ ] use-taste-profile (load/cache/update/migrate)
- [ ] preference-center bind + skeleton + context_memory view
- [ ] chat-message merge profile sau confirm
- [ ] (sau 02) xóa preferencesToContext
- [ ] reduce use-preferences → geo only
- [ ] npm run build + oxlint pass

## Success Criteria
- Edit Preference Center → PATCH backend → reload trang/tabs khác → thấy đồng bộ (không còn chỉ localStorage).
- Clear browser → reload → prefs vẫn (từ backend). Offline → fallback cache.
- Migrate: prefs localStorage cũ tự đẩy lên API lần đầu.
- Build sạch, 0 console error (verify Playwright như audit).

## Risk Assessment
- Mất prefs cũ khi cutover. **Mitigation**: migrate one-time; cache fallback; không xóa localStorage cho đến khi API confirm.
- PATCH debounced race với confirmDelta. **Mitigation**: 1 source of truth (cache), PATCH rebase trên cache mới nhất.
- Backend chưa sẵn sàng (phase 01 chưa xong) → FE build break. **Mitigation**: phase 04 chạy SAU 01; feature flag tạm.

## Security Considerations
- userId từ `use-customer-identity` (localStorage anon id) — IDOR backend guard (phase 01) bảo vệ. Không hardcode userId.

## Next Steps
- Phase 05 test e2e; Phase 06 doc.
