# Phase 02 — Anaphora Context Injection

## Context Links
- Depends: [Phase 01](phase-01-conversation-memory-storage.md) (provides `prior_turns`)
- Flow: `backend/flows/customer_flow.py` (`_build_inputs`, `_build_explanation_messages`)
- Prompts: `backend/agents/customer/config/tasks.yaml` (`search_task`, `explanation_task`)

## Overview
- Priority: P2 | Status: pending | Effort: 3h
- Resolve anaphora ("quán đầu tiên", "rẻ hơn nữa", "món đó", "còn quán nào khác") WITHOUT a coordinator by prompt-injecting a `NGỮ CẢNH PHIÊN TRƯỚC` block built from prior turns.

## Key Insights
- No coordinator → resolution is the LLM's job; we only SUPPLY grounded context. Truth-first still holds: prior-context is reference, never license to fabricate.
- TC-47 "món đó" references a DISH (not merchant) → prior block MUST include prior user text (carries the dish name), not just merchant results.
- TC-30 "còn quán nào khác" = exclude already-shown merchants → prompt instruction to not re-suggest prior merchant_ids (prompt-only, no tool change — keeps YAGNI).
- TC-41 "cái đầu tiên" = ordinal over prior results → prior results MUST be ordered + named.
- `prior_context` is a preformatted Vietnamese string; empty string when no history (first turn) so `{prior_context}` resolves cleanly via `_safe_format`.

## Requirements
- F1: New input var `{prior_context}` available to `search_task` + `explanation_task` (and the streamed explanation messages).
- F2: Block format (when non-empty):
  ```
  NGỮ CẢNH PHIÊN TRƯỚC (dùng để hiểu đại từ "quán đầu tiên", "rẻ hơn nữa", "món đó", "còn quán khác"):
  - Bạn: "<user text>"
    → Quán đã gợi ý: <name>(<merchant_id>, cuisine=<c>) [, ...]
  - Bạn: "<next user text>"
    → (chưa có kết quả / Quán đã gợi ý: ...)
  ```
  Last N=4 turns, most recent last. Agent answer text omitted (merchant list carries the signal + keeps prompt short).
- F3: search_task gets an added rule: "KHÔNG gợi ý lại quán đã liệt kê trong NGỮ CẢNH PHIÊN TRƯỚC trừ khi user hỏi lại rõ."
- F4: First turn (empty history) → `prior_context=""`, zero behavior change (regression-safe).

## Architecture
```
_build_inputs(..., prior_turns) -> adds "prior_context": _format_prior_context(prior_turns)
_format_prior_turns(turns) -> str          # NEW module helper, "" when empty
_build_explanation_messages(..., prior_turns) -> appends prior_context block to user msg
tasks.yaml: search_task + explanation_task reference {prior_context}
```
Stream path: pass `prior_turns` (loaded in Phase 01) into both `_build_inputs` and `_build_explanation_messages`.

## Related Code Files
- MODIFY `backend/flows/customer_flow.py`:
  - `_build_inputs` signature + dict: add `prior_context` key.
  - `_build_explanation_messages` signature: add `prior_turns`; append formatted block to the user message `lines`.
  - ADD `_format_prior_context(turns) -> str`.
  - Both entry points: pass loaded `prior_turns` through.
- MODIFY `backend/agents/customer/config/tasks.yaml`:
  - `search_task.description`: append a line referencing `{prior_context}` + the exclude-prior rule.
  - `explanation_task.description`: append a line referencing `{prior_context}` (so streamed answer resolves "quán đầu tiên" naturally).
- CREATE / DELETE: none.

## Implementation Steps
1. Add `_format_prior_context(turns)`:
   - Empty list → `""`.
   - Else build header + per-turn lines. For each turn: user text always; agent turn's merchant list from `payload.result_merchant_ids` + name/cuisine — but the stored payload only has merchant_ids. **Decision**: in Phase 01, store `result_merchant_ids` only; here, we have ids but not names. Two options: (a) enrich payload with name+cuisine at write time, or (b) lookup names now. **Pick (a)** — update Phase 01 payload to `{"result_merchant_ids":[...], "results":[{"merchant_id","name","cuisine"}...]}` (top 3). Re-open Phase 01 file's payload spec to match. Keep it lean: top 3 results only.
   - Render each agent turn as `→ Quán đã gợi ý: Phở Lệ (m_123, phở); ...`. No agent prose.
2. Update `_build_inputs`: accept `prior_turns`, add `"prior_context": _format_prior_context(prior_turns)`.
3. Update `search_task` prompt: add
   ```
   {prior_context}
   LƯU Ý ĐA LƯỢT: nếu câu hiện tại dùng đại từ ("quán đầu tiên", "rẻ hơn", "món đó", "còn quán khác"), dùng NGỮ CẢNH PHIÊN TRƯỚC để giải mã. KHÔNG gợi ý lại quán đã liệt kê ở đó trừ khi người dùng hỏi lại rõ.
   ```
4. Update `explanation_task` prompt: add `{prior_context}` + "Giải mã đại từ dựa trên ngữ cảnh phiên trước khi trả lời."
5. Update `_build_explanation_messages`: accept `prior_turns`, append `_format_prior_context(prior_turns)` (if non-empty) to the user content `lines` before results block — so streamed answer resolves anaphora.
6. Thread `prior_turns` through both entry points (already loaded in Phase 01) into `_build_inputs` + `_build_explanation_messages`.
7. Coordinate Phase 01 payload change (store top-3 results meta). Update phase-01 F1/step 3 to include `results` meta.
8. py_compile + manual trace: first turn → `prior_context=""` → unchanged.

## Todo List
- [ ] Align Phase 01 payload to carry top-3 result meta (name/cuisine)
- [ ] Implement `_format_prior_context`
- [ ] Add `{prior_context}` to `_build_inputs` + both prompts
- [ ] Add prior block to `_build_explanation_messages`
- [ ] Thread `prior_turns` through both entry points
- [ ] Verify empty-history path = no-op (regression)
- [ ] py_compile

## Success Criteria
- TC-09: "quán đầu tiên" → search excludes/identifies the first prior merchant correctly in answer.
- TC-41: ordinal "cái đầu tiên" resolved from ordered prior list.
- TC-47: "món đó" resolves to a DISH carried in prior user text (not a merchant).
- TC-30: "còn quán nào khác" → no merchant from prior list reappears.
- TC-10: "rẻ hơn nữa" → budget tightens relative to prior turn.
- TC-11: session_expired (no history) → honest empty, no fabricated carry-over.
- First-turn regression: output identical to pre-change when `prior_context=""`.

## Risk Assessment
- **R1 Prompt bloat / context window**: mitigate — cap N=4, top-3 merchants, no agent prose. Monitor token use.
- **R2 LLM ignores exclude instruction**: prompt-only is best-effort; if TC-30 flakes, follow-up adds an `exclude_merchant_ids` arg to search tools (out of scope here — note as future).
- **R3 Anaphora misfires on ambiguous history**: acceptable — truth-first + honest fallback already in prompts.
- **R4 Stream TTFT**: prior block adds ~100 tokens to explanation user-msg — negligible vs DeepSeek TTFT (~5s).

## Security Considerations
- Prior text is user-supplied, injected into a prompt → prompt-injection surface. Mitigation: it's data inside the SAME user's session (no cross-user), and truth-first/grounding rules already forbid the agent from acting on injected instructions as commands. No new vector vs. current single-turn.

## Next Steps
- Phase 05 runs the TC-09/10/11/30/41/47 assertions.
