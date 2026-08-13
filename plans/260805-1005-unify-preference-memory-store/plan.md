# Plan A — Unify Customer Preference/Memory Store

- **Created**: 2026-08-05 | **Branch**: dev-a | **Owner**: HieuGM
- **Source**: audit `plans/reports/audit-260805-1005-project-health-and-improvements.md` §7 (findings M1–M7)
- **Goal**: biến lời hứa "ghi nhớ sở thích người dùng" thành hiện — 1 store chuẩn mực (`user_profiles`), ranking tất định theo profile, + `context_memory` thực sự hoạt động.

## Why
Hiện: FE Preference Center ghi localStorage (M1), backend profile không shape search (M3), `context_memory` chết luôn `{}` (M2), 3 route REST = stub 501 (M4). → 2 store rời rạc, sở thích mất khi clear browser, LLM có thể bỏ qua sở thích.

## Hard Invariants (NON-NEGOTIABLE)
1. **§7.1 propose-only**: propose path (`propose_profile_delta`/`propose_deltas`) giữ 100% read-only. Confirm route vẫn là writer duy nhất cho *suggestion*. PATCH (edit tay) = write path riêng, tái dùng B5 typed validation.
2. **IDOR fix**: mọi endpoint ghi profile phải có guard (`require_dev_only` cho đến khi có auth thật) — không ship path-only trust.
3. **Ranking cộng dồn (additive)**: profile-score = boost/penalty cộng vào `_calculate_match_score`, gated by config, **default off/no-profile → behavior không đổi**. Không phá pipeline scoring hiện tại (`docs/scoring-methodology.md`). `overall_score` vẫn nội bộ, không surface.
4. **Memory không bao giờ break flow** (F3: swallow+log) — áp dụng cho mọi write path mới (context_memory).
5. Files ≤200 LOC (không phình `customer_flow.py` — god-object rồi; logic mới vào `services/`/`repositories/`/`core/`). Kebab-case. YAGNI/KISS/DRY.
6. Test thật, không mock/cheat. GT eval không regress (baseline 39/39 clean).

## Phases
| # | Phase | Status | Effort | Deps |
|---|---|---|---|---|
| 01 | [Backend profile REST + IDOR guard](phase-01-backend-profile-rest.md) | ✅ Done | M | — |

**Phase-01 result (2026-08-05)**: py_compile clean · pytest **107/0** · GT eval **PARITY** (39/39 clean, 0 err/0 interrupt; quality 87.2% rolled forward; 5 capability fixes TC-09/35/41/47/51 reproduced). Gate passed → KEPT (no rollback). Harness-only fix to `eval_ground_truth.py` (`_ensure_prior_referent` seeding: `CAST(:p AS jsonb)` + `message_id`) — latent dormant bugs, not agent code. Report: `plans/reports/tester-260805-1040-phase01-gt-eval.md`.
| 02 | [Deterministic profile-based ranking](phase-02-deterministic-profile-ranking.md) | ✅ Done | L | 01 |

**Phase-02 result (2026-08-05)**: ranking unit tests **10/10** · pytest **119/0** · GT eval **PARITY** 39/39 (1 unrelated FPT stream flake on non-profiled TC-28 where ranking unreachable; profiled cases parity-or-better). Review APPROVE-WITH-NITS (1 MEDIUM fixed: fallback path now forwards profile). Capability live (ranking_enabled=True, conservative). Report: `plans/reports/tester-260805-phase02-gt-eval.md` + `code-review-260805-phase02-ranking.md`.
| 03 | [Implement context_memory](phase-03-context-memory.md) | ✅ Done | M | 01 |

**Phase-03 result (2026-08-05)**: context_memory tests **10 unit + 2 integration** · pytest **127/0** · GT eval **PARITY** 39/39 (1 unrelated FPT stream flake TC-02; profiled cases parity). Review APPROVE-WITH-NITS (H1 fixed: F3 wrap in `maybe_persist`; M1 fixed: narrowed "dạ dày"→"đau/viêm" to avoid "đã đầy" false-positive; + `_fold` đ-bugfix). Live-verified: allergy message persists `context_memory.notes` (field was always `{}`). Reports: `tester-260805-phase03-gt-eval.md`.
| 04 | [FE cutover localStorage → profile API](phase-04-frontend-cutover.md) | ✅ Done | L | 01 |

**Phase-04 result (2026-08-05)**: FE build clean (`tsc -b && vite build` 0 err, oxlint pass) · **live round-trip verified** (Preference Center toggle → backend `user_profiles` row created, `liked_cuisines` persisted) · review APPROVE-WITH-NITS (H-1 fixed: MIGRATED_KEY race-safe vs StrictMode; H-2 fixed: patchTimer cleared on unmount). The 3 backend phases are now **user-visible + cross-device**. No GT impact (eval POSTs raw messages). Report: `code-review-260805-phase04-fe-cutover.md`.
| 05 | [Tests + GT eval regression](phase-05-tests-eval.md) | ✅ Done (incremental) | M | 01–04 |
| 06 | [Docs sync](phase-06-docs.md) | ✅ Done | S | 01–04 |

**Phase-05 (incremental):** each phase added its own tests + ran the GT gate — pytest grew 106→109→119→127 (0 fail), GT eval 39/39 PARITY every phase, FE build clean, live round-trip verified. Carryover: `apply_fields` repo-level test (L3) deferred.
**Phase-06 result (2026-08-06, `6fe6eab`):** docs-manager synced 5 docs — `system-architecture.md` (NEW, 3-layer memory model), README (Customer AI Agent section), roadmap (M2.7 COMPLETE), changelog (phases 1-4), testing-guide (NVIDIA→FPT fix + GT harness section). All refs grep-verified, links resolve.

---

## ✅ PLAN A COMPLETE (6/6 phases, 2026-08-05/06)

**Outcome:** the "remember the user's taste" promise is now real — one canonical backend profile, deterministic ranking, long-term context_memory, FE-cutover to the API. 3-layer memory (structured profile / context_memory / prior_context) with crisp boundaries. 6 commits on `dev-a` (local): `a4170d7 a9530c0 51520c5 dadda4b 9e72e7b 6fe6eab`. pytest 127/0; GT 39/39 PARITY; FE build clean; live round-trip verified.

**Carryover (non-blocking):** apply_fields repo test (L3); FE AbortSignal on patchProfile + cross-tab notes freshness (M-1/M-2); `_fold` centralize to core/text_norm.py (audit #15); evaluation-plan/database-schema doc addenda; re-run standalone LLM quality judge to refresh the rolled-forward 87.2%.

Order: 01 → (02, 03, 04 song song) → 05 → 06. 04 cần 01; 02/03 độc lập với 04.

## Key Design Decisions (xem chi tiết trong phase files)
- **FE storage split**: taste (budget/dietary/cuisines/spice) → backend `user_profiles`; **geolocation UI state** (useLocation/lat/lng/accuracy) → giữ localStorage (trạng thái thiết bị, không portable). Tách `usePreferences` → `useTasteProfile` (API) + geo ở lại.
- **PATCH vs confirm**: PATCH = edit toàn phần/từng field (explicit user edit); confirm = áp 1 suggestion. Cùng B5 validation qua 1 repo method `apply_fields(dict, user_id)` chạy trong 1 tx.
- **Ranking**: `_profile_score(merchant, profile)` cộng dồn (±≤0.15) vào match_score; hard-filter tùy chọn (mặc định: disliked_cuisines exclude, dietary=chay soft-only khi thiếu signal). Profile load server-side ở search entry.
- **context_memory boundary**: `prior_context` (chat_messages) = short-term in-session anaphora; `context_memory` (user_profiles JSONB) = **long-term cross-session distilled facts** (free-text notes KHÔNG dẫn xuất được từ structured fields, vd "dị ứng đậu phộng"). Inject qua output `get_user_profile` tool đã có (chỉ cần populate field). Cap ~500 chars + FIFO + PII redact.
- **No migration**: mọi cột đã tồn tại (`context_memory`, `budget_level`, `spice_tolerance`, …).

## Risks (top)
- Ranking additive sai trọng số → thay đổi thứ tự kết quả, regress GT eval. Mitigation: default off, config weights, A/B vs baseline snapshot.
- context_memory ghi ồn / bloat / leak PII. Mitigation: cap+redact+FIFO, F3 swallow.
- FE cutover mất prefs cũ (localStorage). Mitigation: one-time migrate on first API success; read-through cache fallback offline.
- IDOR guard vô tình chặn dev flow. Mitigation: `require_dev_only` cho phép env dev/staging, block+log prod.

## Unresolved Questions (cần user/mentor)
1. Auth: `require_dev_only` đủ tạm, hay schedule tích hợp auth thật (Out of scope plan này)?
2. dietary=chay hard-filter: merchant có signal "vegetarian" không? (cuisine/taste_tags) — nếu không, soft-only. Verify ở phase-02.
3. context_memory: auto-extract (heuristic/LLM) hay chỉ ghi khi user confirm 1 note? (KISS → bắt đầu auto heuristic + cap).
4. FE offline fallback: giữ localStorage cache hay hard cutover? (Recommend: read-through cache).
