# Phase 02 — Deterministic Profile-Based Ranking

## Context Links
- Plan: `plans/260805-1005-unify-preference-memory-store/plan.md`
- Audit §7 M3. Files: `backend/services/merchant_search_service.py`, `backend/repositories/merchant_repository.py`, `backend/flows/customer_flow.py` (`_load_profile` L1583, search call sites L503/698), `docs/scoring-methodology.md`.

## Overview
- **Priority**: High | **Status**: Pending | **Effort**: L | **Depends**: 01
- `MerchantSearchService` nhận `profile` tùy chọn → cộng `_profile_score` additive vào `match_score`; hard-filter tùy chọn (disliked cuisines). Default no-profile → behavior không đổi.

## Key Insights
- `_calculate_match_score` hiện additive (0-1, max clamp). Thêm 1 thành phần `profile_bonus` (range ± configurable, mặc định ≤0.15) — KHÔNG phá tổng thể.
- `merchant.profile.price_level` (student/standard/premium) match `profile.budget_level`. `merchant.cuisine`/`taste_tags` match liked/disliked.
- dietary=chay: merchant thiếu signal veg rõ → **soft only** (không hard-filter) trừ khi có tag/cuisine chay (verify data). spice_tolerance: merchant không có dimension spice → skip (YAGNI) hoặc soft qua taste_tags.
- Profile load server-side ở flow entry (`_load_profile` đã có) → truyền vào `search()`/`nearby_search()`. Giảm phụ thuộc LLM tool.

## Requirements
- **FR-1**: `search(*, profile=None)` + `nearby_search(*, profile=None)` accept `UserProfilePublic | None`.
- **FR-2**: `_profile_score(merchant, profile) -> float`: budget match (±0.06), liked_cuisines overlap (+0.05/cuisine, cap), disliked_cuisines overlap (−0.08), dietary=chay & merchant veg-tag (+0.05). Trọng số trong `core/` config constant, configurable.
- **FR-3**: Hard filter (config flag, default ON cho disliked only): `disliked_cuisines` overlap → drop before rank. dietary chay hard-filter → OFF mặc định (thiếu signal).
- **FR-4**: profile=None → `_profile_score=0`, không filter → ranking y hệt hiện tại.
- **NFR**: Không N+1 (merchant.cuisine/profile đã eager-loaded). Không surface overall_score.

## Architecture
- New module `services/profile_ranking.py` (thuần, ≤200 LOC): `profile_score(merchant, profile, weights) -> float` + `should_hard_filter(merchant, profile, flags) -> bool`. Testable độc lập.
- `MerchantSearchService.__init__` nhận optional `ranking_config` (weights/flags) default từ settings.
- `search()`/`nearby_search()`: nếu profile + config enabled → apply hard-filter trong candidate loop + cộng `profile_score` vào match_score (trước sort).
- `customer_flow.py`: tại search entry, `_load_profile(user_id)` (đã có) → truyền `profile=` vào service call (cả search + stream path — đóng góp #5 audit: 2 path giữ đồng bộ).

## Related Code Files
- **Create**: `services/profile_ranking.py`, `core/ranking_config.py` (weights/flags dataclass + settings parse).
- **Modify**: `services/merchant_search_service.py` (+profile param, +wiring), `flows/customer_flow.py` (truyền profile vào service call — minimal edit, 2 site).
- **Delete**: — .

## Implementation Steps
1. `core/ranking_config.py`: `RankingConfig` dataclass (`enabled`, `w_budget`, `w_liked`, `w_disliked`, `w_dietary`, `hard_filter_disliked`, …) + loader từ settings (default off/conservative).
2. `services/profile_ranking.py`: `profile_score()` + `should_hard_filter()` thuần + unit test table-driven.
3. `merchant_search_service.py`: `search`/`nearby_search` +`profile=None`; trong loop, hard-filter rồi `match_score += profile_score` (chỉ khi config.enabled & profile).
4. `customer_flow.py`: `_load_profile` → truyền vào cả 2 service call site (search_restaurants + search_restaurants_stream). Giữ F3.
5. Verify data: grep merchant có tag/cuisine "chay"/"vegetarian" không → quyết dietary hard-filter.

## Todo List
- [ ] RankingConfig + settings
- [ ] profile_ranking.py thuần + unit test
- [ ] wire vào search/nearby_search
- [ ] truyền profile từ flow (2 site)
- [ ] verify veg signal → dietary filter decision
- [ ] py_compile + lint

## Success Criteria
- profile=None → ranking ĐÚNG hệt trước (snapshot test cùng query/top-k).
- profile có disliked cuisine → merchant đó drop/penalty; liked → boost. budget match rõ.
- Unit test `profile_ranking` phủ: empty profile, budget match/mismatch, liked overlap, disliked filter, dietary.
- GT eval: 39/39 clean execution không regress (chạy phase 05).

## Risk Assessment
- Trọng số sai → đảo thứ tự, regress GT eval. **Mitigation**: default off; config; snapshot compare vs baseline trước/sau; có kill-switch env.
- disliked hard-filter loại sạch kết quả (user disliked cuisine phổ biến). **Mitigation**: chỉ filter khi profile explicitly set; fallback soft-penalty nếu result<3.
- 2 path (search/stream) lệch. **Mitigation**: cùng helper, test đồng bộ.

## Security Considerations
- Profile là dữ liệu user; không leak cross-user (profile load by user_id đã đúng). Không surface internal scores.

## Next Steps
- Phase 05 validate regress. Sau khi ranking on, phase 04 có thể bỏ `preferencesToContext` (M5).
