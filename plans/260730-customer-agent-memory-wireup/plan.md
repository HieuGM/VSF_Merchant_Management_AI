---
title: "Customer Agent Memory Wire-up"
description: "Wire existing memory infra (chat_messages, preference_events, weather_override) into the live customer flow for multiturn refinement + confirmed profile persistence."
status: pending (audit-supplemented)
priority: P2
effort: 17h
branch: dev-a
tags: [customer-agent, memory, multiturn, preference, weather]
created: 2026-07-30
audit: 260730-supplemented (23 findings → 18 supplements)
audit_report: reports/audit-260730-0952-memory-plan.md
---

# Customer Agent Memory Wire-up

## Problem
Memory infra exists but is DISCONNECTED from the live flow:
- `chat_messages` table has NO backend writer → turns never persist → anaphora ("quán đầu tiên", "rẻ hơn nữa", "món đó") unresolved.
- `preference_suggestions` are propose-only forever → TC-48 "ăn chay trường" never persists.
- `CustomerChatRequest.weather_override` exists but flow drops it → TC-06 rain reasoning lost.
- No coordinator (permanently removed) → resolution must be prompt-injected, not classified.

## Scope (DECIDED — do not expand)
1. **Conversation memory**: persist user+agent turns + result merchant_ids per session; load last N turns into crew for anaphora resolution.
2. **Profile persistence**: explicit user-confirm path writes `preference_events` (append) + upserts `user_profiles`. Propose stays propose-only.
3. **Weather threading**: `weather_override` → preference reasoning + streamed explanation.
4. Keep `/chat` + `/chat/stream` working; TTFT/stream behavior intact.

## Design Decisions (Q1–Q5 resolved)
- **Q1 Anaphora (no coordinator)**: prompt-inject `NGỮ CẢNH PHIÊN TRƯỚC` block (last 4 msgs + prior result merchant_id/name/cuisine) into `search_task` + `explanation_task`. TC-47 "món đó" resolves via prior user text. **TC-30 exclude-prior → DETERMINISTIC tool-arg** (`exclude_merchant_ids` on merchant_search/nearby, flow-built from prior_turns) — NOT prompt-only (GT scores it as a tool-call param). [audit B4]
- **Q2 Turn shape**: REUSE `chat_messages` (fields fit). New `ChatMessageRepository` (append_turn + get_recent_turns). result_merchant_ids → `structured_payload_json`. No migration.
- **Q3 Confirm**: implement EXISTING stub `POST /api/v1/users/{user_id}/profile/deltas/{delta_id}/confirm` (+reject). Body carries {field,operation,value}. New `PreferenceEventRepository` + `UserProfileRepository.apply_delta()`.
- **Q4 Weather**: thread `weather_override` → `_build_inputs` `{weather_hint}` → `preference_task` prompt + `_build_explanation_messages`. Keep `get_weather_context` tool (override takes precedence when present).
- **Q5 Load point**: `ChatMessageRepository.get_recent_turns()` at flow entry → `_build_inputs` + `_build_explanation_messages`.

## Audit resolutions (260730 — 23 findings; full detail `reports/audit-260730-0952-memory-plan.md`)
- **[BLOCKER B1] phase-01**: `append_turn` MUST get-or-create parent `ChatSession` (anonymous-safe, user_id=None if no profile) before insert — else FK violation swallowed → memory never persists → all multiturn TCs no-op.
- **[BLOCKER B2] phase-02**: TTL filter in `get_recent_turns` (`timestamp > NOW() - INTERVAL '24h'`, <1wk) — else TC-11 stale turns fabricate.
- **[BLOCKER B3] phase-03**: weather server-side short-circuit — call `preference_service.propose_deltas(weather=override)` directly; don't rely on agent re-serializing VN string→dict.
- **[BLOCKER B5] phase-04**: per-field typed validation (list/enum/float) + `dietary` contract (list, `["chay"]`, add) + add `dietary` rule to `preference_service`. GT `diet`→`dietary`.
- **[BLOCKER B6] phase-04**: explicit `evidence_refs_json` mapping + add=append-if-absent — else idempotency breaks.
- **phase-02**: SSE prior_context inject ONCE (YAML `{prior_context}` via `_safe_format`; do NOT also append-to-lines). Gate "LƯU Ý ĐA LƯỢT" rule behind non-empty prior_context (turn-1 unchanged).
- **phase-03**: gate pref-crew build on `has_signals or weather_override is not None`; sig_bits insert conditional on no `preference.weather_summary`.
- **phase-04**: extend propose-only canary to also assert `user_profiles` unchanged.
- **phase-05**: FE session_id BOTH invariants (localStorage reload-safe + regenerate on New chat). Add FK-prereq integration test + no-history diff assertion.
- **TC-49 → OUT-OF-SCOPE** (coordinator removed); cheap prompt-rule only.

## Phases
| # | Phase | Status | Depends | Effort |
|---|-------|--------|---------|--------|
| 01 | [Conversation memory storage](phase-01-conversation-memory-storage.md) | pending | — | 3h |
| 02 | [Anaphora context injection](phase-02-anaphora-context-injection.md) | pending | 01 | 3h |
| 03 | [Weather override threading](phase-03-weather-override-threading.md) | pending | — | 1.5h |
| 04 | [Profile confirm persistence](phase-04-profile-confirm-persistence.md) | pending | — | 4h |
| 05 | [Integration validation + FE wire](phase-05-integration-validation.md) | pending | 01–04 | 3h |

Parallelizable: {01+03+04} independent; 02 after 01; 05 after all.

## Key Files (verified)
- Flow: `backend/flows/customer_flow.py` (2 entry pts, `_build_inputs`, `_build_explanation_messages`)
- Crew: `backend/agents/customer/customer_crew.py`; prompts: `config/tasks.yaml`, `config/agents.yaml`
- Models: `backend/database/models.py` (L324–407), `backend/models/{agent,preference}.py`
- Repos: `session_repository.py`, `user_profile_repository.py` (read-only)
- Routes: `customer_agent_routes.py`, `user_routes.py` (confirm/reject STUBS)
- FE: `api/customer-agent-client.ts`, `hooks/use-customer-chat.ts`, `components/chat-message.tsx`

## Guardrails
- propose-only invariant preserved (§7.1) — confirm is a SEPARATE explicit user action.
- Truth-first: prior-context is reference only, never license to fabricate.
- No new storage when existing fits (YAGNI/KISS/DRY).

## Success = ground-truth cases unblocked
TC-09,10,11,30,41,47 (multiturn) · TC-06,29,48 (pref/weather) → **9/10 achievable-with-supplement**. **TC-49 out-of-scope** (no coordinator/clarification path). Multiturn answer-quality = wiring-only (assert prompt/persistence/tool-args; manual/browser smoke for resolution). See `reports/audit-260730-0952-memory-plan.md`.

## Open Forks (lead sign-off before implement)
1. **phase-04 auth**: ship audit-log + same-user guard + P1 TODO (recommended) vs hard 403-gate (blocks demo/eval). [security]
2. **TC-48 GT `diet`→`dietary`**: edit `ground_truth_customer.json` to match DB column (recommended) vs backend alias.
3. **Session TTL**: 24h default — confirm < TC-11 1wk gap + doesn't break same-session continuity.
4. **Weather short-circuit merge**: pref crew still runs for non-weather reasoning? merge point = crew output.
