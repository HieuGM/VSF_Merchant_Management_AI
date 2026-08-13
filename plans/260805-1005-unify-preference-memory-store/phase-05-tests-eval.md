# Phase 05 — Tests + GT Eval Regression

## Context Links
- Plan: `plans/260805-1005-unify-preference-memory-store/plan.md`
- Files: `backend/tests/integration/test_customer_memory_wireup.py`, `backend/tests/unit/`, `backend/scripts/eval_ground_truth.py`, `ground_truth_customer.json`, `plans/reports/gt-eval-results-*.json` (baseline).

## Overview
- **Priority**: High | **Status**: Pending | **Effort**: M | **Depends**: 01–04
- Mở rộng test cho 3 thay đổi (REST profile, ranking, context_memory) + chạy GT eval xác nhận KHÔNG regress (baseline 39/39 clean execution; quality 87.2%).

## Key Insights
- Test wiring hiện có rất tốt (`test_customer_memory_wireup.py`) — mở rộng theo cùng style (real PG, deterministic, _require_db skip).
- Ranking = thuần (`profile_ranking.py`) → unit test table-driven không cần DB.
- GT eval = SSE live-server harness (cần BE chạy :8000). Baseline snapshots đã có trong `plans/reports/`.

## Requirements
- **FR-1**: Unit `tests/unit/services/test_profile_ranking.py` — table-driven: empty profile, budget match/mismatch, liked overlap, disliked hard-filter, dietary soft, cap/score range.
- **FR-2**: Unit `tests/unit/services/test_context_memory.py` — extract patterns, dedupe, cap, PII redact, F3 (DB fail swallow).
- **FR-3**: Integration mở rộng `test_customer_memory_wireup.py`: PATCH `/profile` happy + 400 + guard (dev ok / prod 403); ranking end-to-end (profile disliked → merchant drop); context_memory round-trip.
- **FR-4**: Regression: chạy `pytest -q` toàn bộ → green (không break 106 baseline). Chạy `eval_ground_truth.py` → 39/39 clean (0 err/0 stream_interrupted); so snapshot vs `gt-eval-results-before-arch.json`.
- **NFR**: Real data/PG, không mock/cheat (rule). Coverage tăng cho module mới.

## Architecture
- Theo cấu trúc test hiện tại: `_require_db`, `_new_uid/_new_sid`, cleanup. Ranking test thuần (không DB). FE: smoke test build + (optional) Playwright Pref Center flow.
- Thêm `tests/integration/test_profile_rest.py` (hoặc gộp wireup) cho PATCH/GET/guard.

## Related Code Files
- **Create**: `tests/unit/services/test_profile_ranking.py`, `tests/unit/services/test_context_memory.py`, `tests/integration/test_profile_rest.py`.
- **Modify**: `tests/integration/test_customer_memory_wireup.py` (+ranking/context_memory cases nếu gộp).
- **Run**: `pytest -q`; `eval_ground_truth.py`.

## Implementation Steps
1. `test_profile_ranking.py` — table-driven unit (10+ case).
2. `test_context_memory.py` — extract/dedupe/cap/redact/F3.
3. `test_profile_rest.py` — GET 200/404, PATCH happy/400(strict)/guard dev+prod.
4. Mở rộng wireup: ranking e2e (disliked drop), context_memory round-trip qua get_user_profile.
5. `conda run -n ai_restaurant python -m pytest -q` → green.
6. Start BE :8000 → `eval_ground_truth.py` → so snapshot baseline; ghi `plans/reports/gt-eval-results-after-unify-memory.json`.
7. (FE) `npm run build` + Playwright smoke Pref Center.

## Todo List
- [ ] test_profile_ranking (unit)
- [ ] test_context_memory (unit)
- [ ] test_profile_rest (integration)
- [ ] mở rộng wireup (ranking + context_memory)
- [ ] pytest toàn bộ green
- [ ] GT eval 39/39 clean + snapshot compare
- [ ] FE build + smoke

## Success Criteria
- Toàn bộ pytest green (≥106 cũ + mới). Coverage module mới >80%.
- GT eval: 0 err / 0 stream_interrupted trên N=39; thứ tự kết quả KHÔNG đảo xấu vs baseline (ranking additive default-safe).
- Snapshot report ghi rõ before/after.

## Risk Assessment
- Ranking đổi thứ tự → GT case cụ thể fail. **Mitigation**: default off; nếu on, kiểm từng case; kill-switch.
- BE không start được (env) → eval skip. **Mitigation**: _require_db pattern; report skip rõ.
- Test chậm (integration). **Mitigation**: cleanup triệt để; parallel où hợp lệ.

## Security Considerations
- Test không hardcode secret/key. Guard test verify prod=403.

## Next Steps
- Phase 06 doc snapshot kết quả eval mới.
