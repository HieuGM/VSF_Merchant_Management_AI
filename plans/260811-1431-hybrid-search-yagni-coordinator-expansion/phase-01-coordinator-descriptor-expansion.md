# Phase 01 — Coordinator VN Vague-Descriptor → Structured-Tag Expansion (D1)

## Context Links

- Active plan: `plans/260811-1431-hybrid-search-yagni-coordinator-expansion/plan.md`
- Coordinator flow: `backend/flows/customer_flow.py` (lines 53–88 `_PREFERENCE_SIGNAL_KEYWORDS`; 961–1004 `_build_inputs` — injection point; 563–628 search kickoff)
- Crew config (single source of truth for prompts): `backend/agents/customer/config/tasks.yaml` (search_task lines 9–48 — the `{query_search}` / `{cuisine}` / `{city}` / `{budget}` placeholders the LLM sees)
- Search tool args schema (UNCHANGED): `backend/tools/customer/merchant_tools.py:24-58` (`MerchantSearchArgs`, `NearbyMerchantSearchArgs`)
- Fold SSoT: `backend/core/text_norm.py:17` `fold_diacritics`
- Settings pattern: `backend/core/settings.py:69-76` (`ranking_enabled` bool — template for new flag)
- Ranking/tag consumption: `backend/core/query_relevance.py:67-69` (cuisine/tags as folded-token haystack), `backend/services/profile_ranking.py:87-93` (dietary chay match against `taste_tags`)

## Overview

Priority: P2. Status: pending. Effort: 4h.

When a user types "ăn gì cho đỡ ngán" / "món thanh đạm" / "đổi gió" / "chill chill" / "nhẹ nhàng" / "ăn kiêng" / "đồ nhẹ" etc., the LLM coordinator currently does ad-hoc decomposition. Ship a deterministic dictionary module + a `{descriptor_hints}` YAML placeholder that gives the search agent a concrete gloss to map to `query`/`cuisine`/tag args. Feature-flagged default OFF; reversible via env flip.

## Key Insights

1. **The LLM coordinator already does decomposition** (per `tasks.yaml` search_task rule 3: "tên món → `query`; loại ẩm thực rộng → `cuisine`"). The gap is VAGUE descriptors ("đỡ ngán", "chill") that don't obviously map to either field. A deterministic lookup that the LLM reads as a hint is the LEAST-invasive fix.
2. **Tool signatures MUST stay UNCHANGED** (constraint #1). So we cannot add a `taste_tags` arg to `merchant_search`. Instead: the LLM maps the hint to existing `query`/`cuisine` args (which `query_relevance` already scores against `merchant.cuisine` + `merchant.taste_tags`).
3. **Injection point choice** — three options:
   - (a) Modify the raw `query` string before the LLM sees it (BAD — distorts evidence, breaks truth-first rules in `explanation_task`).
   - (b) Add a new `{descriptor_hints}` placeholder to `search_task.description` filled by `_build_inputs` (BEST — additive, prompt-only, fully reversible, zero tool/ranking change).
   - (c) A new tool `expand_descriptors()` the LLM calls (REJECTED — adds a tool call round-trip + breaks the "1 tool 1 call" rule in search_task).
4. **Feature flag = env flip**: `COORDINATOR_DESCRIPTOR_EXPANSION_ENABLED=true/false`. When false, `_build_inputs` returns `descriptor_hints=""` and the YAML placeholder expands to empty — the search_task prompt is byte-identical to current behavior (no regression risk).
5. **Dictionary reuses `fold_diacritics`** SSoT — never duplicates fold logic. Match keys are pre-folded ASCII; lookup folds the incoming query.

## Requirements

### Functional
- FR1: Match ~20–25 VN vague descriptors (folded-ASCII keys) → emit a Vietnamese-language hint string naming suggested `cuisine` + `taste_tags` the LLM should prefer.
- FR2: When flag OFF → zero change to inputs/prompt/behavior.
- FR3: When flag ON and NO descriptor matches → `descriptor_hints=""` (prompt unchanged for that query).
- FR4: Multi-descriptor queries ("trời lạnh, đỡ ngán") → emit BOTH hints concatenated.

### Non-functional
- NFR1: <200 LOC for the dictionary module; pure function, no DB, no I/O.
- NFR2: Deterministic (folded-key lookup, no LLM in the loop).
- NFR3: No new dependencies.

## Architecture

```
User query
   │
   ▼
CustomerFlow.search_restaurants[_stream]
   │
   ▼
_build_inputs(query=...)         ◄── injection point (customer_flow.py:961)
   │  if settings.coordinator_descriptor_expansion_enabled:
   │      descriptor_hints = expand_vague_descriptors(query)  # "" when no match
   │  else:
   │      descriptor_hints = ""
   │
   ▼
tasks.yaml search_task.description  ◄── new {descriptor_hints} line (additive, "" = no-op)
   │  "GỢI Ý MỞ RỘNG (nếu có): {descriptor_hints}"
   │
   ▼
restaurant_search agent  ──► merchant_search/nearby_merchant_search (UNCHANGED sig)
```

No tool signature, repo, SQL, ranking, or filter change. The agent still produces `query`/`cuisine` args from its own reasoning — the hint just nudges it toward concrete terms.

## Related Code Files

### Modify
- `backend/core/settings.py` — add `coordinator_descriptor_expansion_enabled: bool = False` field (additive, follows `ranking_enabled` pattern at line 70).
- `backend/flows/customer_flow.py` — in `_build_inputs` (lines 961-1004): read flag, call `expand_vague_descriptors(query)`, add `"descriptor_hints"` key to inputs dict. ~5 lines.
- `backend/agents/customer/config/tasks.yaml` — `search_task.description`: append one additive line `\n    GỢI Ý MỞ RỘNG từ descriptor (nếu có, DÙNG để chọn cuisine/query): {descriptor_hints}`. Empty string → line shows "(không có)" → no-op.

### Create
- `backend/core/vn_food_descriptors.py` (NEW, <200 LOC) — the dictionary + `expand_vague_descriptors(query: str | None) -> str` returning a Vietnamese hint string ("đỡ ngán → ưu tiên cuisine Món Việt/Thanh đạm, taste_tags thanh đạm/nhẹ/chua"). Match logic: fold query, scan for each pre-folded key, collect non-empty entries, return joined string.

### Delete
- None.

## Implementation Steps

1. **Create `backend/core/vn_food_descriptors.py`** (~120 LOC):
   - Module docstring citing audit #15 SSoT.
   - `from core.text_norm import fold_diacritics`.
   - Constant `_DESCRIPTORS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...]` — entries `(folded_key, cuisine_hints, taste_tag_hints)`. Folded keys pre-computed at import time (or stored as already-ASCII literals).
   - Function `expand_vague_descriptors(query: str | None) -> str`: fold query, for each descriptor check `key in folded_query` (substring is fine — folded VN is ASCII, no false-positive on common words if keys are ≥2 tokens or unambiguous singles); collect matched; return joined Vietnamese gloss string or "".
2. **Add settings field**: `coordinator_descriptor_expansion_enabled: bool = False` in `core/settings.py` Settings class (after line 76 `ranking_hard_filter_disliked`).
3. **Wire into `_build_inputs`** in `customer_flow.py` (~5 lines after line 1003): 
   ```python
   from core.vn_food_descriptors import expand_vague_descriptors
   from core.settings import get_settings
   _hint = expand_vague_descriptors(query) if get_settings().coordinator_descriptor_expansion_enabled else ""
   inputs["descriptor_hints"] = _hint or "(không có)"
   ```
   Imports at module top; the function call inside `_build_inputs`.
4. **Edit `tasks.yaml` `search_task.description`** — append a new line before `{prior_context}`:
   ```yaml
       GỢI Ý MỞ RỘNG (chỉ tham khảo, dùng để chọn cuisine/query cho rõ hơn — bỏ qua nếu "(không có)"): {descriptor_hints}
   ```
5. **Unit test** `backend/tests/unit/test_vn_food_descriptors.py`: assert each key matches; assert multi-key; assert no-match → ""; assert flag-OFF path returns "".
6. **Run compile + tests** (env `ai_restaurant`): `PYTHONPATH=backend C:/Users/Laptop/miniconda3/envs/ai_restaurant/python.exe -m pytest backend/tests/unit/test_vn_food_descriptors.py -v`.

## Todo List

- [ ] Create `backend/core/vn_food_descriptors.py` with ~20 entries
- [ ] Add `coordinator_descriptor_expansion_enabled` to Settings
- [ ] Wire `descriptor_hints` into `_build_inputs`
- [ ] Append `{descriptor_hints}` line to `search_task.description` in tasks.yaml
- [ ] Unit tests for dictionary module
- [ ] Verify flag-OFF path = byte-identical prompt (no-op test)

## Initial Dictionary Entries (~22)

| Folded key | Cuisine hints | taste_tag hints | Notes |
|---|---|---|---|
| `do ngan` / `giam ngan` | Món Việt, Thanh đạm | thanh đạm, nhẹ, chua | "đỡ ngán" |
| `thanh dam` | Thanh đạm, Món Việt | nhẹ, tươi | "thanh đạm" |
| `doi gio` | (broaden) | mới, đa dạng | "đổi gió" — broaden hint |
| `chill chill` / `chill` | Café, Trà | nhẹ, thư giãn | ambiance hint |
| `nhe nhang` | Thanh đạm | nhẹ | "nhẹ nhàng" |
| `an kieng` | Healthy, Salad | healthy, ít calo | "ăn kiêng" + dietary eat-clean |
| `do nhe` | Snack, Café | nhẹ | "đồ nhẹ" |
| `eat clean` | Healthy, Salad | healthy | dietary eat-clean |
| `giam can` | Healthy, Salad | ít calo | "giảm cân" |
| `dai bo` / `bo duong` | Lẩu, Súp | bổ, đậm | "đại bổ" |
| `dam da` | (none) | đậm đà | prefer strong-flavor |
| `no ne` | Lẩu, Nướng, Buffet | no, thịnh so | "no nê" |
| `do cay` / `an cay` | Thái, Tứ Xuyên | cay | "đồ cay" |
| `do chua` | (none) | chua | "đồ chua" |
| `troi lanh` | Lẩu, Súp, Phở | nóng, ấm | weather-coupled |
| `troi nong` | Trà, Kem, Chè | mát, lạnh | weather-coupled |
| `troi mua` | Lẩu, Đồ giao | nóng, ấm | weather-coupled |
| `do chay` / `an chay` / `chay` | Chay | chay | dietary vegetarian (overlaps `_PREFERENCE_SIGNAL_KEYWORDS` — that gates preference_task, this expands search query; complementary, not duplicate) |
| `hen ho` | (none) | lãng mạn, sang | ambiance |
| `nhom` / `ban nhom` | Lẩu, Nướng | nhóm, không gian rộng | group dining |
| `khuen ruou` / `nhau` | Nhậu, Mồi | mồi, bia | "khuyên rượu" / "nhậu" |

(Final list subject to actual `taste_tags` distribution in DB — see Open Questions.)

## Success Criteria

- `coordinator_descriptor_expansion_enabled=False` (default): byte-identical search_task prompt vs current main (verified via diff test on `_build_inputs` output with `query="phở"`).
- Flag ON + vague query: `descriptor_hints` non-empty; agent emits a `query`/`cuisine` drawn from the hint (manual check on 3 sample queries).
- Flag ON + non-vague query: `descriptor_hints="(không có)"` → no-op.
- All existing customer_flow unit tests pass unchanged.
- Unit test coverage for `vn_food_descriptors` ≥90%.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Hint misleads agent on edge case (e.g. "đổi gió" → broaden too aggressively) | M | M | Default OFF; D4 GT gate catches regression; "đổi gió" hint is intentionally vague ("broaden") not prescriptive |
| False-positive key match (e.g. `chay` substring in "ngon_chay_quan") | L | L | Use `\b`-anchored token match (post-fold ASCII); audit keys for ambiguity |
| Hint leaks into `explanation_task` answer (prose mentions "descriptor") | L | M | `descriptor_hints` is ONLY in `search_task.description`; `explanation_task` has its own description. Belt-and-suspenders: keep the hint phrasing non-prose-friendly ("Cuisine: Món Việt/Thanh đạm, Tags: nhẹ,chua") |
| Overlap confusion with `_PREFERENCE_SIGNAL_KEYWORDS` | L | L | Different concerns: `_PREFERENCE_SIGNAL_KEYWORDS` gates whether preference_task runs (routing); `expand_vague_descriptors` adds hints to search_task prompt (query expansion). Document in module docstring. |

## Security Considerations

- Dictionary is static; no user input → no injection surface.
- Hint is treated as advisory text in the prompt — the truth-first rules in `search_task` already forbid fabricating results; the hint doesn't relax those rules.
- No PII in hints (they're cuisine/tag phrases, not user data).

## Next Steps

- Phase 04 (D4): A/B GT eval with flag ON vs OFF. Standing user constraint: if not improved or regressed → ROLLBACK (flip flag, no code revert needed since flag-default is OFF).
- Phase 02 (D2) can ship in parallel — pure logging, no interaction with this phase.

## Open Questions (resolve before implementation)

1. **Actual `taste_tags` distribution in DB**: are tags like `thanh đạm`, `nhẹ`, `chua` actually populated on merchants? Need a quick `psql` query (`SELECT DISTINCT unnest(taste_tags) FROM merchants ORDER BY 1`) to validate the dictionary emits tags that exist. If not, fall back to cuisine-only hints.
2. **Coordinator-side new tool vs prompt-only**: prompt-only is the chosen least-invasive option (decision (b) above). Confirm with lead before implementation — a tool-based option would let the preference agent also see the expansion but adds a round-trip.
3. **Should preference_task also receive `descriptor_hints`?** Currently only `search_task` gets it. Preference agent's job is profile/weather deltas, not query expansion — likely no. Confirm.
4. **Dictionary ownership/maintenance**: who owns adding entries once real-user logs (from D2) reveal gaps? Suggest: PR-reviewed, single file, append-only.
