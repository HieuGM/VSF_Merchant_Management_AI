# Memory Architecture for Persistent-Constraint Honoring — Research

**Scope:** patterns for honoring PERSISTENT USER CONSTRAINTS (allergies, dietary, strong dislikes) across multi-turn recommendation chat. CrewAI + FastAPI + Postgres + FPT Cloud AI.

## TL;DR Recommendation

**Structured always-on constraint block (in-app, no new dep).** The bug is ENFORCEMENT, not storage. Project already has the right stores (`user_profiles` typed + `context_memory.notes` JSONB) but enforcement is reactive/scattered regex. Fix = (1) render an "ACTIVE CONSTRAINTS" block from typed fields + notes into EVERY task/explanation prompt; (2) generalize the hardcoded `_recalled_dietary_filter`/`_EXCLUDED_FOODS` into a single constraint catalog applied as a deterministic POST-search filter every turn. Vector DB is overkill for ~5-10 hard facts/user. This is the Letta core-memory-block pattern, built in-app on existing Postgres columns.

---

## Taxonomy Table

| System | Structure | Retrieval mode (per turn) | Fit for always-on constraints |
|---|---|---|---|
| **mem0** | Layered by lifetime (conversation/session/user/org) + factual/episodic/semantic map. Vector + metadata. | **Similarity-search pipeline** (`memory.search()`), dev-invoked, ranked user→session→history. NOT auto-injected. | Weak — must call search every turn; short queries skip LLM analysis. Hard constraint can be missed if not similar to query. |
| **Zep** | **Temporal knowledge graph** (Context Graph): entity nodes + fact edges with valid/invalid timestamps. Episodes, summaries. | **Hybrid**: `thread.get_user_context` = always-on **Context Block** (summary + relevant facts, sub-200ms); `graph.search` on-demand; also agentic tool. | **Strong** — Context Block is exactly the always-on pattern; Fact Invalidation handles "từ giờ không ăn chay". |
| **Letta / MemGPT** | **Core memory blocks** (persona, human, custom — string, pinned to system prompt) + archival (vector) + recall (message log). | Core = **always-on injected** (pinned). Archival = similarity-retrieved via `archival_search` tool. Recall = API. | **Strongest** — core block is the canonical "always-on facts" pattern. Agent self-edits via `core_memory_append/replace`. |
| **LangGraph Store + Checkpointer** | Checkpointer = thread state (short-term). Store = cross-thread KV w/ namespaces `(prefix..., key)` + optional vector index. | Store supports **BOTH**: exact `get(ns, key)` (deterministic) AND `asearch(ns_prefix, query)` (semantic). | **Strong** — exact get() for hard constraints (deterministic every turn), asearch() for soft. Clean separation. |
| **CrewAI native (unified `Memory`)** | Replaced old short/long/entity/user types → single Memory class. LanceDB vector store + composite scoring. | **Similarity-retrieved once per TASK** (not per turn): `0.5*semantic + 0.3*recency + 0.2*importance`. Consolidation at 0.85 sim. | **Weak — root cause of this project's bug.** Short query ("xin chào") → pure vector lookup → seafood-allergy note may not surface. |
| **A-MEM (NeurIPS 2025)** | Zettelkasten-linked notes: each memory = structured note (desc, keywords, tags) + LLM-forged links to related notes. | Link/tag navigation; LLM re-indexes old notes when new arrives. | Medium — powerful but heavy; links are LLM-judged, non-deterministic. Wrong tool for hard constraints. |
| **Generative Agents (Park 2023)** | Memory stream (natural-language observations) + reflections (synthesized higher-level insights). | **Weighted retrieval**: `importance × recency(decay) × relevance(similarity)`. Reflections periodically generated. | Weak for hard constraints — recency decay would de-emphasize an old allergy. Designed for believable simulation, not safety. |
| **Claude (Anthropic) memory** | Per-project **memory summary** (distilled, editable, user-facing). | Referenced each turn (injected); user steers focus. Hard project-scoped boundaries. | Medium — summary-based; not field-typed, so deterministic filtering still needs structured layer. |

---

## 3 Patterns Most Applicable to THIS Project

### Pattern A — Structured Always-On Constraint Block (Letta core-memory style, in-app) ★ RECOMMENDED

**Mechanism:** deterministic render of typed profile fields + notes → compact "RÀNG BUỘC ĐANG HOẠT ĐỘNG" block injected into EVERY prompt (search task, preference task, explanation) + applied as POST-search result filter. No LLM in the recall loop for hard constraints.

**Pros:**
- Zero new deps. Uses existing `user_profiles` columns + `context_memory.notes` JSONB.
- Deterministic — a seafood allergy fires on "xin chào" / "gợi ý quán" too, not only on explicit seafood asks. Health-risk safe.
- Small N (~5-10 facts/user) — vector embeddings give no benefit, add latency + false negatives.
- Replaces ~6 scattered regex heuristics in `customer_flow.py` (already 1977 lines) with ONE constraint catalog.
- Matches Letta/Zep "always-on block" industry pattern.

**Cons:**
- Block consumes tokens every turn (small — capped notes already ≤8 × 120 chars).
- Constraint catalog must be maintained (cuisine synonym map) — but already implicit in current code, just consolidated.
- No semantic generalization (a novel spelling of an allergen won't match) — mitigable w/ diacritic-fold + synonym list.

### Pattern B — LangGraph-style Store: exact-get + semantic-asearch split

**Mechanism:** hard constraints → exact key (`get(("user", uid, "constraints"))`) every turn; soft/episodic → semantic search on-demand. Add pgvector OR keep soft side as JSONB scan (small N).

**Pros:**
- Clean canonical separation (hard=deterministic, soft=similarity).
- Future-proof if soft-pref volume grows past ~50/user.

**Cons:**
- Adds a Store abstraction layer (LangGraph dependency) the project doesn't currently use.
- pgvector would be a new Postgres extension + embedding calls — overkill at current scale.
- CrewAI is the orchestrator; bolting LangGraph Store alongside = 2 memory models. Violates KISS.

### Pattern C — mem0/Zep similarity-only (NOT recommended)

**Mechanism:** drop-in memory layer; `memory.search(query)` each turn.

**Pros:**
- Turnkey, framework-agnostic.
- Handles contradiction/staleness (Zep Fact Invalidation is best-in-class).

**Cons:**
- **Defeats the purpose:** similarity retrieval has false negatives on hard constraints — exactly this project's bug. "xin chào" embeds nowhere near "dị ứng hải sản".
- New external dep (mem0 service or Zep server) → infra burden, FPT-only constraint, on-prem data residency unclear.
- Adds latency (~200ms Zep, more for mem0 deep mode) to every turn.
- Project already stores the data natively; would duplicate into a sidecar.

---

## Contradiction / Staleness Handling (RQ4)

| System | Mechanism |
|---|---|
| **Zep** | **Fact Invalidation** — edges carry `valid_at` + `invalid_at`; old fact retained (time-aware reasoning) but excluded from "current truth". Strongest. |
| **CrewAI native** | consolidation_threshold 0.85 → LLM decides keep/update/delete/insert on save. |
| **Letta** | agent self-edits via `core_memory_replace` / `delete`; developer can edit via API. |
| **mem0** | layered lifetimes — session auto-expires, user persists; no explicit conflict resolution in OSS. |
| **Generative Agents** | recency decay only (no explicit invalidation — old facts just fade). |

**Fit for this project:** typed-field update is already atomic via `UserProfileService.update_profile` (PATCH overwrites). For free-text notes, project already has FIFO cap + dedupe — needs an explicit "break diet" detector (already prototyped: `_DIET_BREAK_RE`). Generalize to a `notes_invalidate(pattern)` that marks/removes superseded notes on profile change. No new dep.

---

## Canonical Separation (RQ3)

| Memory class | Storage | Retrieval | Reason |
|---|---|---|---|
| **Hard constraints** (allergy, diet, medical, "từ giờ X") | Structured typed fields (`dietary`, `disliked_cuisines`) + narrow JSONB notes | **Always-on, every turn** — injected into prompt + deterministic post-filter | Health risk. Must NEVER be skipped. Similarity has false negatives. Small N → no embedding benefit. |
| **Soft preferences** (liked cuisines, budget, spice tol, weather mood) | Structured typed fields | Typed-field read at ranking time (already done via `profile_scope`) | Small N, typed → deterministic join beats semantic. |
| **Episodic / session** (prior turns, anaphora refs) | `chat_messages` (24h TTL) | Window scan + anaphora match (already done) | Short-lived, exact match needed for "quán đầu tiên". |
| **Cross-session episodic** (past visits, long-ago convos) | (not yet built) | Semantic search IF volume grows | Only justified when N > ~50/user. YAGNI for now. |

Key principle: **structured beats semantic when N is small and false-negatives are costly.** Embeddings earn their cost at scale and for fuzzy/semantic matching — neither applies to "dị ứng hải sản".

---

## Concrete Recommendation for THIS Codebase

**Build a single constraint catalog + always-on block renderer.** Replace the scattered regex in `customer_flow.py`:

1. **New module** `backend/services/constraint_catalog.py`:
   - `Constraint = {type: allergy|diet|medical|religion, terms: [synonyms-folded], severity: hard|soft, source_field}`
   - Catalog maps profile fields + note-trigger words → constraints (generalizes `_TRIGGERS` in `context_memory_service` + `_EXCLUDED_FOODS` in flow).
2. **`build_active_constraints_block(profile, notes) -> str`** — renders compact "RÀNG BUỘC" string; injected via `{active_constraints}` placeholder into search_task / preference_task / explanation prompts (mirrors existing `{prior_context}` injection in `_build_inputs`).
3. **`filter_results_by_constraints(results, constraints) -> results`** — deterministic POST-search filter; generalizes `_recalled_dietary_filter` beyond just "chay".
4. **`detect_constraint_conflict(query, constraints) -> str|None`** — pre-search confirm gate; generalizes `_detect_dietary_conflict` beyond just "hải sản".
5. **Invalidation hook** in `UserProfileService.update_profile`: when `dietary` changes, drop matching notes (generalize `_DIET_BREAK_RE`).

Net effect: every prompt carries the user's hard constraints → LLM cannot "forget"; every result list is deterministically filtered → sushi never appears for a seafood-allergy user even on "gợi ý quán". Zero new dependencies.

---

## Unresolved Questions

1. **Catalog maintenance:** who owns the cuisine-synonym map (Vietnamese dialectal variants, brand names)? Risk of drift between catalog and search-agent's own `_FOOD_TERMS` list — should they share one source? (DRY)
2. **Notes-to-typed promotion:** when should a free-text note ("dị ứng tôm") graduate into a typed `dietary=["shellfish"]` field vs stay as JSONB? Current `_TRIGGERS` keeps them split; a promotion path may reduce dual-source-of-truth risk.
3. **Multi-user / shared-session:** if a group chat ("nhóm 6 người") has users w/ conflicting allergies, whose constraints win? Current `_detect_dietary_conflict` only reads the single caller's profile.
4. **Confidence decay for medical facts:** should a gastritis note ("đau dạ dày") auto-expire after N months (transient condition), while allergy persists? Zep's temporal-validity model addresses this; current FIFO cap doesn't.
5. **Token budget:** if notes grow to the 8-cap and each is 120 chars, the always-on block is ~1k chars/user — acceptable, but worth measuring against the FPT context limit and the existing `{prior_context}` block (combined).
6. **Soft-pref promotion to semantic:** at what N (per-user preference-events) does the JSONB scan start losing to pgvector? Needs a benchmark before introducing the dep.

---

## Citations

- mem0 memory types & layered lifetimes: https://docs.mem0.ai/core-concepts/memory-types
- mem0 vs Letta/Zep comparison: https://mem0.ai/llms.txt
- Zep Context Graph + Fact Invalidation + Context Blocks: https://help.getzep.com/
- Letta core memory blocks (always-on pinned) + archival/recall + MemFS: https://docs.letta.com/ , https://docs.letta.com/configuration/memory , https://docs.letta.com/guides/agents/memory
- LangGraph Store (exact get + semantic asearch) vs Checkpointer: https://langchain-ai.github.io/langgraph/concepts/memory/ , https://langchain-ai.github.io/langgraph/concepts/persistence/
- CrewAI unified Memory (similarity, composite 0.5/0.3/0.2, NOT always-on): https://docs.crewai.com/concepts/memory
- A-MEM (Zettelkasten, NeurIPS 2025): https://arxiv.org/abs/2502.12110
- Generative Agents (importance × recency × relevance + reflection): https://arxiv.org/abs/2304.03442
- Claude memory (per-project editable summary): https://claude.com/blog/memory
- LangChain blog (LangGraph w/ memory agents): https://www.langchain.com/blog/using-langgraph-with-memory-agents
