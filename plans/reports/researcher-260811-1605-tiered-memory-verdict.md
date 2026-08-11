# Verdict: "Why Not the Production Tiered Approach?"

> Adversarial re-evaluation of the prior YAGNI memory recommendation. 4 agents (reference-archs / codebase-mapping / red-team-pro-production / synthesizer), ~207k tokens. Grounded in verified file:line refs.

---

## 1. Direct Answer — the prior rec IS the tiered approach

The presupposition is **false on two counts**:

1. **The codebase is already tiered today** — 5 distinct cognitive-memory tiers, composed per-request. The authors *name the boundary in source*: `context_memory_service.py:9-11` ("prior_context = SHORT-TERM, in-session anaphora / context_memory = LONG-TERM, cross-session").
2. **Every P1/P2 patch FILLS an existing tier — none creates a new one.** A "clean production-tiered rewrite" would re-implement 4 tiers that already exist. The prior rec is the *minimal Postgres-native path* to the one genuinely missing tier (episodic cross-conv distillate), not a flat patch.

What production has that Phase-1 lacks is **NOT a tier — it is the LLM memory-MANAGER**: the component that continuously *rewrites* the durable store via extract / consolidate-UPDATE / reflect / importance-decay / self-edit. The tiers are static plumbing; the manager is the brain. Building that brain now — at <50 convs, NO embedder configured, pgvector NOT installed, and a GT-gate that just reverted a net-neutral LLM addition (`7df007f`: gpt-oss coordinator, ask-F1 +0.03 within noise, **reverted**) — is theater.

The honest concession the adversary forced: the prior rec **under-acknowledged the affinity-breadth gap** (keto/halal/reducing-sugar silently dropped). That gap is real and deserves a *lightweight* answer now (P2.5 below), not mem0.

---

## 2. Tier-Map Table (production tier → our status → file:line → gap/fill)

| Tier | Status | Where (file:line) | Gap / Fill |
|---|---|---|---|
| **Working / current turn** | present | `customer_flow.py:1009-1012`; `active_constraints_loader.py:191` | None. Trivially the query. |
| **Short-term / within-conv** | partial | `chat_message_repository.py:66-101` (`get_recent_turns` limit=4, ttl=24h); `customer_flow.py:1272-1329` (`_format_prior_context`); `:1433-1443` (`_references_prior` gate) | **P1 fills**: 4→16, ~2000-char budget, tiered gate. Same store, same gate, bigger window. |
| **Episodic / cross-conv** | **MISSING** | `chat_message_repository.py:103-110` (`_ensure_session` hardcodes `user_id=None` → NOT per-user queryable); `models.py:350` (`context_snapshot_json` present, UNUSED); no summarizer | **P2 fills**: bind user_id + FE sends user_id; per-conv distillate via 1 LLM call at close → `context_snapshot_json`; folded-ILIKE recall; `list_recent_summaries`. Reuses dead column + dead FK. |
| **Semantic durable facts** | partial | `models.py:328-333` (cuisines/spice/dietary/budget/distance); `context_memory_service.py:35-53` (8 triggers, FIFO-8); `profile_ranking.py:47-94` | Durable FACTS present; SEMANTIC recall absent (keyword + JSONB-exact only). Cuisine-affinity already derived; price-band-from-likes fills via P2. Embeddings DEFERRED (YAGNI). |
| **Procedural constraints** | **present (production-grade)** | `active_constraints_loader.py:133-195` (`build_active_constraints`, `_SESSION_WINDOW=8`); `active_constraints_enforcer.py:44-56,98-128` (L1 DB / L2 post-search / confirm-gate); `core/constraint_catalog.py` (declarative add-a-row) | None material. **Strongest tier** — defense-in-depth + provenance + contradiction-handling. No patch touches it. |

---

## 3. Production-vs-Patch Gap Table (the 5 memory-MANAGER operations)

| Operation | Production (mem0/Letta/Claude/ChatGPT) | Current + Prior-Rec Patch | Gap |
|---|---|---|---|
| **Extract** | LLM judges salience — pulls "prefers X" from ANY phrasing | 8 hardcoded folded-VN triggers (`context_memory_service.py:35-44`) + 2 catalog scopes (`constraint_catalog.py:70-73`: seafood, chay ONLY) | **HIGH for affinity** (keto/halal/reducing-sugar/cilantro/pregnancy/spice-level all dropped); **OK for safety** (catalog exhaustive + collision-safe) |
| **Consolidate / UPDATE** | `str_replace`/UPDATE on contradiction (Letta `core_memory_replace`, mem0 UPDATE, Claude `str_replace`) | append-only FIFO-8, dedupe case-insensitive only — CANNOT update | stale + new coexist; "ăn chay" then meat keeps BOTH; allergy can age out behind trivia |
| **Importance + decay** | `f(recency, importance, frequency)` with recency decay | none; `user_liked_merchants` positive-only, NO timestamp in ranking | 3-yr-old like == yesterday's; FIFO evicts by insertion not salience |
| **Reflect** | async LLM pass → semantic writeback (mem0 reflect, Letta nightly) | none; cuisine-affinity hand-derived ONCE by SQL | no cross-conv patterns ("always spicy on weekends"); `interaction_events` write-only, `interaction_history` dead |
| **Self-edit** | agent issues structured tool calls mid-turn (Claude view/create/delete, Letta `core_memory_replace` w/ inner_thoughts) | writes happen OUTSIDE the agent loop at ingest via regex | agents are memory-READERS, never memory-WRITERS |

**One-line distillation:** the patch makes each tier *wider and connected*; every operation on the durable store stays *deterministic and append-only*. Production tiered memory's claim to fame is that the durable store is continuously *rewritten* by an LLM brain. That brain — not the tiers — is the "phân tầng" the user is really asking about.

---

## 4. Where Production-Tiered Wins (concede honestly)

- **Implicit learning of open-ended durable preferences** — anything outside 8 triggers + 2 scopes vanishes. Verified: `constraint_catalog.py:70-73` (seafood, chay ONLY); `context_memory_service.py:35-44`. "Tôi giảm đường" / "ăn keto" / "halal" / "đang mang thai" / "ghét ngò" → NOTHING extracted. **Strongest production argument.**
- **VN semantic recall** — folded-ILIKE is lexical vs a synonym/hypernym-rich space. "Đồ thanh đạm" vs "gỏi cuốn salad": `fold_diacritics` → zero token overlap, pg_trgm similarity ~0, ILIKE miss. Same for nhẹ↔salad, ăn kiêng↔low carb. Folding solves toneless typing (pho bo→phở bò), NOT synonymy.
- **Consolidation/decay** — notes append-only FIFO-8; likes never decay. Stale dominates.
- **Cross-conv pattern detection** — structurally absent (atemporal ranking).
- **Scale >500 convs** — FIFO-8 + 2-scope catalog negligible; linear folded-ILIKE wrong shape (needs HNSW + decay + pagination). (Current = 39 GT TCs, <50 convs.)

---

## 5. Where YAGNI Holds (do NOT build full manager now)

- **Volume**: 39 GT TCs, <50 real convs. Linear scan of 50 distillates is sub-ms.
- **NO embedder**: `probe_fpt_embedding.py` UNRUN; pgvector NOT installed (needs image swap). mem0/Letta/Zep/LangMem ALL require an embedder → adopting one now = theater.
- **GT-gate flakiness on LLM-on-path**: `7df007f` — 1-call gpt-oss coordinator was net-neutral (ask-F1 +0.03) and **REVERTED**. Direct evidence the 0.82 routing_accuracy gate catches net-neutral/negative LLM additions. A per-turn auto-writing memory-manager is far riskier than a routing coordinator.
- **Key budget**: FPT returns 401 (not 429) when key exhausted — per-turn extraction risks outage.
- **Safety subset NOT lost**: allergen/chay catalog is exhaustive + collision-safe (homophone re-check `cua`≠`của`, `chay`≠`chạy`, `ghẹ`≠`ghế`, `mực`≠`mục`, `sò`⊂`sốt`) — enumeration is the CORRECT tool there. The gap is affinity-breadth ONLY.

---

## 6. Revised Recommendation — KEEP staged plan + ADD P2.5 middle path

Adversary changed the call **partially**: not "swap to mem0", but exposed that the prior rec under-acknowledged the affinity-breadth gap. The middle path = **lightweight LLM extraction tier ON TOP of deterministic tiers, WITHOUT mem0/pgvector**.

**KEEP**: P1 (4→16 window, ~2000-char budget, tiered gate); P2 (bind user_id, distillate-on-close → `context_snapshot_json`, folded-ILIKE recall, `list_recent_summaries`, price-band-from-likes); CrewAI `memory=False`; pgvector/mem0 DEFERRED.

**ADD P2.5 — "extraction lift"** (cheapest production operation; no new store, no embedder):
- (a) The SAME 1 LLM call that writes the P2 distillate at conv-close ALSO extracts free-text durable AFFINITY facts beyond the 8 triggers ("giảm đường", "ăn keto", "halal", "ghét ngò") → stored in EXISTING `context_memory.notes`. +1 LLM call/conv (not per-turn); reuses FPT key already in use.
- (b) Tag extracted notes `{kind:"affinity", source:"llm"}`; the safety catalog stays the authoritative deterministic path — LLM NEVER overwrites allergen/chay constraints.
- (c) **Instrument miss-rate NOW**: log every turn stating a durable preference matching NO trigger. This + a đồ-thanh-đạm/gỏi-cuốn recall eval = the empirical trigger for the full manager.
- (d) GT-eval checkpoint: if P2.5 drops routing_accuracy <0.82, REVERT (the `7df007f` precedent).

This layers the production "extract" operation onto existing tiers, directly answering the adversary's strongest point (implicit-learning gap), while deferring the 4 operations that genuinely require pgvector (consolidation-by-similarity, decay-ranked retrieval, reflection writeback, self-edit).

---

## 7. Precise Upgrade Trigger — when to build the FULL LLM memory-manager

ALL FOUR must fire:

1. **`probe_fpt_embedding.py` PASSES** — a Vietnamese-competent embedder reachable with user keys AND handles diacritics well enough to retire (or fall back) folded-ILIKE. **Hard blocker — run ASAP.**
2. **pgvector installed** (image swap `postgres:18-alpine` → pgvector-enabled, or extension enable).
3. **>50 real conversations** — justifies a retrieval tier over linear scan.
4. **MEASURED recall gap** — EITHER the P2.5 miss-rate instrument shows durable preferences dropped at a rate that hurts recommendations, OR a cross-conv recall eval exposes the đồ-thanh-đạm/gỏi-cuốn class at actual volume.

Until all four: **P2.5 only**. The đồ-thanh-đạm/gỏi-cuốn class is the CONCRETE trigger for Phase 3 (pgvector), not an abstract conv-count threshold. If probe fails or the embedder is VN-incompetent, folded-ILIKE + the catalog remain the permanent architecture and the full manager is never built.

---

## Unresolved Questions
- **Q1**: Is the GT-eval gate sensitive ONLY to routing_accuracy, or also to a memory-quality metric? If only routing, the memory-manager's upside is invisible to the gate → harder to justify even at scale.
- **Q2**: Is there an existing async worker/scheduler in the FastAPI deployment to host a reflection pass, or would it be cron/CLI? (Affects feasibility of Phase 4 reflection.)
- **Q3**: For Vietnamese, does the chosen embedder (when probe runs) handle diacritics well enough to retire folded-ILIKE, or will ILIKE stay as a permanent fallback? Determines whether mem0 retrieval is usable at parity.
- **Q4**: Should P2.5's LLM extraction share the FPT key with the crew, or get a separate budget/quota to isolate 401-exhaustion blast radius?
