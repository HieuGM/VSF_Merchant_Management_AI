# Customer Memory Wire-up — COMPLETE (260730)

**Goal:** agent had no memory → ~28/51 ground_truth cases untestable. Wired existing (disconnected) memory infra into the live flow. **9/10 targeted TCs now achievable** (TC-49 out-of-scope — coordinator removed).

## Delivered (4 goals)
1. **Conversation memory** — persist user+agent turns/session (`chat_messages`, get-or-create `ChatSession`). Load last-N into crew for anaphora.
2. **Anaphora resolution** (no coordinator) — `NGỮ CẢNH PHIÊN TRƯỚC` prompt block + `exclude_merchant_ids` tool-arg (deterministic TC-30).
3. **Weather threading** — `weather_override` → preference reasoning + server-side short-circuit (deterministic TC-06).
4. **Profile confirm** — `/confirm`/`/reject` routes + `apply_delta` (typed) + audit; propose stays read-only.

## Verified
- **Unit/integration: 32/32 green** (`test_customer_memory_wireup.py` 18 + propose-only canary 3 + crew 11). No regressions; outage fixed (app imports).
- **Multiturn e2e smoke** (real LLM, same session_id): turn-2 "quán đầu tiên..." → correctly resolved to turn-1's #1 (Thanh Hằng Quán, exact address) + truth-first (no fabricated price). Memory persisted with `result_merchant_ids`.
- **Confirm/reject e2e smoke** (HTTP): apply + idempotent repeat + reject(body) + reject(no-body, FE-style) + 400-on-bad-field all correct. DB: confirmed=1/rejected=2.

## Blocker scorecard (audit → impl)
| B | Status |
|---|---|
| B1 get-or-create ChatSession (anon-safe) | ✅ verified |
| B2 TTL filter 24h (TC-11) | ✅ unit |
| B3 weather server-side short-circuit (TC-06) | ✅ unit |
| B4 exclude_merchant_ids tool-arg (TC-30) | ✅ unit + e2e (backend deterministic; flow→tool forward LLM-dependent) |
| B5 typed validation + dietary rule (TC-48) | ✅ 400 on scalar-on-list/bad-field; GT diet→dietary |
| B6 evidence_refs_json mapping + idempotency | ✅ idempotent confirm verified |
| B7 auth audit-log + P1 TODO (user choice: not 403-gate) | ✅ route logs IP+user |

## Known limitations (non-blocking, documented)
- **FPT explanation transient flakiness** — pre-existing (F3); graceful fallback fires on the DeepSeek stream drop (saw 1/3 multiturn turns hit it, clean on retry). NOT a regression.
- **Double user-turn persistence** — by-design disconnect-safety (entry + post-run); `get_recent_turns` collapses consecutive dupes on read. Cosmetic DB redundancy.
- **B4 flow→tool determinism** — `exclude_merchant_ids` reaches the tool via prior_context prompt instruction; works in practice (turn-2 results differ) but LLM-dependent, not 100%. Hard guard = future.
- **Turn-1 prompt** gains a blank line where `{prior_context}` sits (semantic unchanged; F4 softened to "no semantic change").
- **Auth** — confirm/reject route ships with audit-log + same-user guard comment + P1 TODO (no real auth principal in codebase yet). Per user decision.

## Files (created / modified)
**BE created:** `repositories/chat_message_repository.py`, `repositories/preference_event_repository.py`, `services/preference_confirm_service.py`, `core/pii.py`, `tests/integration/test_customer_memory_wireup.py`
**BE modified:** `flows/customer_flow.py`, `agents/customer/config/tasks.yaml`, `routes/customer_agent_routes.py`, `routes/user_routes.py`, `repositories/user_profile_repository.py`, `services/preference_service.py`, `services/merchant_search_service.py`, `tools/customer/merchant_tools.py`, `models/agent.py`, `tests/integration/test_customer_context_tools_db.py`
**FE modified:** `api/customer-agent-client.ts`, `hooks/use-customer-identity.ts`, `hooks/use-customer-chat.ts`, `components/chat-message.tsx`, `components/chat-message.css`
**Data:** `ground_truth_customer.json` (TC-07/29/48 `diet`→`dietary` list)
**Plan/audit:** `plans/260730-customer-agent-memory-wireup/` (plan + audit report + impl workflow)

## Unresolved
- FE not browser-smoked (tsc-clean; Lưu button + session_id logic compiled, BE confirm path HTTP-verified). Optional visual follow-up.
- B4 hard deterministic guard (server-side tool-arg injection) if TC-30 must be 100% scorer-deterministic.
- Preference Center GET + real auth on user routes (future phases).
