# Hard-Constraint Enforcement for Restaurant Recommender (Allergies/Diet)

**Bug**: user says "Tôi không ăn được hải sản". Stored as free-text note. Re-checked ONLY when query mentions seafood. On "xin chào"/"gợi ý quán" → system proactively pushes sushi = allergy violation. Constraint captured but enforcement is REACTIVE (query-matched), not PROACTIVE (always-applied).

---

## 1. Hard vs Soft Constraint Model

Industry consensus (Min/Jiang/Jain 2019 survey; Fu 2026; Wang 2026; Chen 2021): recommenders separate constraints into tiers by **severity**, not by topic.

| Tier | Examples | Operator | Failure cost |
|---|---|---|---|
| **HARD (safety)** | allergy, medical diet (tiểu đường), religious kiêng, anaphylaxis risk | **absolute FILTER** — never in candidate set, never in output | health harm, liability |
| **SOFT (preference)** | taste (liked/disliked cuisine), budget, distance, spice | **RANK / penalty** — boost/deprioritize, not drop | user annoyance |
| **CONTEXT (transient)** | "ăn gì hôm nay", weather, time, mood | **RANK / reweight by session** | low |

Key principle (Fu 2026 "Agentic Critic"): hard constraints must be enforced by a mechanism **independent of the LLM**. The model can propose, a deterministic layer disposes. Prompt-only enforcement drifts under long context, adversarial phrasing, and proactive-suggestion turns (exactly the sushi-on-hello case).

### Recommended schema (this codebase)

Current state — captured but unenforceable:
- `user_profiles.context_memory["notes"]` = free-text VN strings ("Tôi dị ứng hải sản"). Unstructured.
- `user_profiles.dietary` = list[str], used only as a chay/vegetarian **boost** (`profile_ranking.profile_score`), never a filter.
- `user_profiles.disliked_cuisines` = list[str], only soft-penalized; `should_hard_filter` for it is **OFF by default**.
- `_detect_dietary_conflict()` in customer_flow.py is **REACTIVE** — fires only when query requests the very food the user restricted.

**Recommended** — add a structured HARD-constraint store, keep notes as the source signal:

```python
# models/preference.py — UserProfilePublic (new field)
restrictions: list[Restriction] = []   # HARD constraints, always-applied

class Restriction(BaseModel):
    type: Literal["allergy", "medical", "religious", "diet"]
    canonical_tag: str           # "seafood", "peanut", "beef", "pork" — ontology key
    display_label_vi: str        # "hải sản" — for prompt/answer rendering
    evidence_refs: list[str]     # traceability to source note/turn
    confidence: float
    status: Literal["candidate", "confirmed"]   # mirror §7.1 scope discipline
```

Why structured: a deterministic filter needs a **predicate**, not prose. Free-text "không ăn được hải sản" must map to `canonical_tag="seafood"` so a DB `WHERE`/post-filter can act. The existing `preference_events` append-only audit (§6.6) already supports a `field="restrictions"` row — reuse it; do NOT invent a parallel store.

The `context_memory["notes"]` stays as the **NLU intake buffer** (high-precision triggers already exist in `context_memory_service._TRIGGERS`), but on each match it should **also** produce a candidate `Restriction` (status=candidate, awaiting confirmation) — same propose-then-confirm flow already used for chay (TC-48).

---

## 2. Where to Enforce — Reliability Ranking

From most to least reliable (defense-in-depth: combine ALL) (OpenAI function-calling guide; NeMo Guardrails docs):

### (A) Tool-level pre-filter — MOST RELIABLE
Hard-code the constraint INTO the search tool. The LLM cannot talk the DB out of a row.

```python
# MerchantSearchService.search / nearby_search — auto-inject exclude
restrictions = _load_active_restrictions(profile)   # confirmed + recalled
exclude_predicates = _restrictions_to_predicates(restrictions)
# WHERE merchant_id NOT IN (SELECT m FROM merchants 
#   WHERE cuisine && :banned_cuisines
#   OR ingredient_tags && :banned_ingredients)
```

Pros: deterministic, single source of truth, LLM-independent. Cons: requires ingredient_tags population (see §4).

### (B) Service-layer post-filter — RELIABLE BACKSTOP
Drop results AFTER retrieval, BEFORE they reach the explanation agent. **Already proven in this codebase** for chay (`customer_flow._recalled_dietary_filter` generalizes cleanly to all restrictions):

```python
# Generalize _recalled_dietary_filter → _apply_hard_restrictions
results = [r for r in results 
           if not _merchant_violates(r, active_restrictions)]
```

Necessary because (A) needs populated tags; post-filter can fall back to **cuisine + name token match** as a coarse-but-always-on guard while tags mature.

### (C) Tool output schema enforcement
For `merchant_search`/`nearby_merchant_search` tool signatures, make `restrictions` an explicit passthrough param the agent is required to forward (mirror existing `exclude_merchant_ids`). OpenAI strict-mode JSON-schema validation enforces the agent forwards it. Weakest of the three deterministic layers (LLM may omit) — pair with (A)/(B).

### (D) Output guardrail (post-generation)
Scan the **final answer text** for allergen terms; if present and the corresponding merchant isn't in the safe candidate set, strip / regenerate. NeMo Guardrails "output rails" pattern. For VN: a diacritics-folded keyword list per allergen (`{"seafood": ("hai san","tom","cua","muc","ngao","oc","so")}` — already literally defined in `customer_flow._EXCLUDED_FOODS`). Catches the "sushi-on-hello" proactive text even if (A)(B)(C) somehow pass through.

### (E) Prompt injection — LEAST RELIABLE (necessary, never sufficient)
Inject "RÀNG BUỘC KHÔNG ĐƯỢC gợi ý {display_label_vi}" into BOTH:
- `search_task` prompt (so the LLM-search forwards the constraint), AND
- `explanation_task` prompt (so the LLM doesn't free-associate a banned food).

Required because (A)-(D) only act on candidate **merchants**; the explanation can *mention* a banned food in conversation ("hôm nay nắng, ăn tôm tươi ngon…") without it being a result. Prompt is the only layer covering pure prose. But alone it is the weakest — models drift; never the sole mechanism.

**Ranking**: A > B > D > C > E. **Required combo**: A + B (deterministic merchant filter) + E (prompt for prose) + optional D (answer scan). C is nice-to-have.

---

## 3. The "Sushi on Hello" Problem — Concrete Fix

Root cause in this codebase: on a greeting/generic-suggest turn, the **search query is empty** (or "ăn gì"), so:
- `_detect_dietary_conflict()` finds no requested-food overlap → does nothing (correct, but irrelevant — there's nothing to conflict with).
- `search_task`/`nearby_search` run with **no constraint forward** → returns sushi merchants.
- `_recalled_dietary_filter` only handles `chay`; allergies pass through.
- Explanation agent sees sushi in candidates → proactively pitches it.

**Fix — three layers, all REQUIRED**:

1. **Intake** — generalize `context_memory_service._TRIGGERS` (already detects `di ung`/`khong an duoc`/`kien`) to ALSO emit a `Restriction(candidate)` event; surface for user confirmation (existing propose-then-confirm UX from TC-48). On confirm → `status=confirmed`, persistent across sessions.

2. **Always-on filter** — both `search()` and `nearby_search()` load `active_restrictions = profile.restrictions (confirmed) ∪ session-recalled` and post-filter results against `_merchant_violates()`. **This is independent of query content** — fires on "xin chào" exactly the same as on "tôi muốn sushi". Generalize the existing chay `_recalled_dietary_filter` slot.

3. **Explanation prompt injection** — pass an `active_constraints` block to `_build_explanation_messages`:

   ```
   RÀNG BUỘC KHÔNG ĐƯỢC VI PHẠM (mọi gợi ý, kể cả chủ động):
   - {display_label_vi}: không đề xuất, không nhắc tên như là lựa chọn.
   ```

   Plus output scan (D) as backstop for prose.

The decisive change vs today: step 2 runs on **every** turn, keyed off the profile, **not** off the query. That converts enforcement from REACTIVE to PROACTIVE.

---

## 4. Realistic Granularity for Vietnamese Food Restrictions

Three granularity tiers; reliability drops as you go coarser:

| Tier | Predicate source | Pros | Cons | Data readiness in this repo |
|---|---|---|---|---|
| **Ingredient-level** (best) | `merchants.ingredient_tags` / `menu_items.ingredient_tags` | catches "shrimp in a phở place's bún tôm" | needs full tag coverage | `diet_tags`/`ingredient_tags` columns exist but fixtures show `[]` — **unpopulated**. Needs tagging pass. |
| **Dish-level** | `menu_items.name` text match | keeps merchant if ≥1 safe dish | still token-matches names | menu_items table populated; feasible. |
| **Cuisine-level** (floor) | `merchants.cuisine`, `taste_tags`, name token | always available | over-filters (see §5) | **available now** — use as the always-on floor. |

**Realistic recommendation (YAGNI)**:
- **Now**: cuisine-level + merchant-name token match. `customer_flow._EXCLUDED_FOODS` already maps `"hải sản"→("hai san","tom","cua","ghe","muc","ngao","oc","so")` — extend it into a per-restriction canonical taxonomy and match against `_norm_vi(cuisine ∪ taste_tags ∪ name)`. Coverage: catches sushi/Nhật/hải sản merchants. Misses: a "Món Việt" place selling canh chua tôm.
- **Near-term**: dish-level scan on `menu_items.name` for the top-N candidates already loaded (`MerchantSearchService` batches `get_top_menu_items_batch`). Cheap.
- **Later**: populate `ingredient_tags` (NLU/LLM tagging pass over menu data) for true ingredient-level filtering.

VN-specific NLU coverage notes:
- Allergens commonly declared: hải sản (tôm/cua/ghẹ/mực/ngao/nghêu/ốc/sò), đậu phộng/lạc, sữa/lactose, gluten/bột mì, trứng, hải sản-vs-cá (some allergic only to shellfish, not fish — keep distinct).
- Religious/medical kiêng: heo (Hồi giáo), bò (Hindu), đường/tinh bột (tiểu đường), cay/đồ chiên (đau dạ dày — already a trigger in `_TRIGGERS`).
- Diets: chay (handled), eat-clean, keto.
- Phrasing variants the NLU must catch: "không ăn được X", "dị ứng X", "bị dị ứng với X", "kiêng X", "X làm tôi nổi mẩn", "bị đau bụng khi ăn X", "không hợp với X". The trigger list in `context_memory_service._TRIGGERS` is a good start but only catches the verb; pair with an allergen-noun lexicon to extract `canonical_tag`.

---

## 5. Partial-Overlap Handling (over-restriction trade-off)

**Problem**: a merchant that serves both beef phở AND shrimp — cuisine-level filter on "hải sản" drops them entirely, even though the phở is safe. Symmetric to the TC-30 / "must not over-restrict" principle already in this codebase (`_grounding_guard`, truth-first).

Patterns from literature (Pacifico 2021 ingredient substitution; Wang 2026 graded penalty):

1. **Dish-level, not merchant-level, filter when data allows** — keep merchant iff ≥1 menu item passes; surface ONLY safe dishes in the card. Changes the unit of recommendation from merchant→dish for restricted users. Most accurate; needs dish data.
2. **Graded penalty, not drop, for SOFT restrictions** — keep disliked cuisine in the set but down-rank (`should_hard_filter=False` default already does this for `disliked_cuisines`). Reserve absolute-drop for HARD only.
3. **"Has safe options" badge** — when partial overlap, keep the merchant but annotate (`safe_dishes: [...]`); explanation prompt can say "quán có cả đồ hải sản, nhưng món X/Y hoàn toàn không có hải sản — bạn cân nhắc". Honest, lets user decide. Useful when dish-level data is thin.
4. **Never silently expand to "everything's fine"** — if you can't verify safety (no ingredient data), be truthful: "mình chưa chắc quán này có món nào an toàn cho bạn, bạn cân nhắc". Same truth-first posture the codebase already enforces (`explanation_task` TRUNG THỰC block, TC-09/47 absence notes).

Recommendation: tier-matched — HARD + ingredient data → drop. HARD + only cuisine data + partial-overlap → keep with safe-dishes annotation OR drop with honest "không đủ dữ liệu an toàn". Never pretend safe.

---

## Citations

1. Min, W., Jiang, S., Jain, R. (2019). *Food Recommendation: Framework, Existing Solutions, and Challenges*. IEEE Trans. Multimedia / MDPI Foods survey, 220+ citations — foundational; allergies/diet framed as filter-out constraints.
2. Fu et al. (2026). *Query-to-Constraint Hard Filtering with Agentic Critic for Food Recommendation*. Foods (MDPI). Strict dietary constraint enforcement, 85% constraint satisfaction, critic independent of generator.
3. Wang & Wang (2026). *Allergen Filtering with Graded Penalty-Based Ranking*. Electronics — soft constraint via penalty rather than drop (partial-overlap handling).
4. Chen et al. (2021). *Personalized Food Recommendation as Constrained QA over a Large-Scale Food Knowledge Graph* — allergy/medical/diet as constraints on KG.
5. Pacifico et al. (2021). *Ingredient Substitute Recommendation for Allergy-Safe Recipe Generation* — collaborative filtering + ingredient substitution.
6. OpenAI. *Function Calling Guide* — strict mode, JSON-schema validation, enum constraints, "make invalid states unrepresentable" (tool-level enforcement).
7. NVIDIA. *NeMo Guardrails docs* — input/output/dialog/retrieval rails; output rails for blocking banned items via custom Python actions between generation and delivery.
8. Recommender systems (Wikipedia) — knowledge-based / constraint-satisfaction category distinction (background only; does not address allergens directly).

---

## Unresolved Questions

1. **Confirmation flow**: restrictions are health-sensitive — should a candidate restriction (one-turn utterance) auto-enforce immediately, or require explicit user confirmation first? Current chay handling (TC-48) confirms; allergies arguably need to enforce on FIRST mention (safety > convenience). Decision needed.
2. **Ingredient_tags population strategy**: who tags the merchants (NLU pass over menu_items.name? LLM extraction? manual?)? Until then, cuisine-level is the only always-on floor — known coverage gap.
3. **Scope of "active restrictions" recalled**: across all sessions (durable), or session-only? Allergies should be durable (profile-level), but transient "hôm nay hơi đau bụng, kiêng đồ cay" should NOT persist forever. Need a type-based scope rule.
4. **Disambiguation**: "không ăn được hải sản" vs "không ăn được đồ cay hải sản" vs "không ăn được tôm nhưng cá thì được" — shellfish-only vs all-seafood distinction. Current `_EXCLUDED_FOODS["hải sản"]` lumps all shellfish + sea creatures; needs finer taxonomy for partial-seafood allergies.
5. ** Liability / safety disclaimer**: should the system state it is not a medical device and the user should confirm with restaurant staff? Out of scope for enforcement but relevant to productize.
6. **Eval coverage**: GT eval suite (TC-07/48/49 touch dietary) — need new TC for "declare allergy turn 1 → hello turn 2 → assert no seafood in results or answer". No such proactive-case TC exists today.
