---
title: "Path A — VN vague-descriptor expansion + search instrumentation + FPT embedding probe"
description: "YAGNI follow-up after hybrid-search research: ship descriptor→tag expansion at coordinator, instrument every search call, probe FPT embeddings — no vector leg yet."
status: in-progress
priority: P2
effort: 10h
branch: dev-a
tags: [coordinator, search, instrumentation, embeddings, yagni]
created: 2026-08-11
---

# Path A — Coordinator Descriptor Expansion + Search Instrumentation

## Context

7-agent research rejected BM25 (existing `query_relevance.py` + tone-aware ILIKE strictly stronger for VN), rejected RRF (overkill for 2-leg system where one leg dominates and final ranker IS `query_relevance`), and DEFERRED the vector leg — the CrewAI coordinator already decomposes vague text into structured `cuisine`/`query`/tag fields BEFORE search, and the GT gate (`routing_accuracy`) is structurally blind to semantic-recall gains (only exposed to vector-leg downside). User decision (Path A, YAGNI): (1) ship vague→tag expansion at coordinator now, (2) instrument every search call to find a REAL recall gap over ~1 wk, (3) only then consider a vector leg; (4) parallel cheap prep — probe whether FPT_API_KEY authorizes the FPT `/embeddings` endpoint.

## Phases

| # | Phase | Status | Effort | Owner | File |
|---|-------|--------|--------|-------|------|
| 1 | Coordinator VN descriptor→tag expansion (D1) | pending | 4h | dev-a | [phase-01](phase-01-coordinator-descriptor-expansion.md) |
| 2 | Search-call instrumentation logger (D2) | pending | 2h | dev-a | [phase-02](phase-02-search-instrumentation.md) |
| 3 | FPT embedding API probe script (D3) | pending | 2h | dev-a | [phase-03](phase-03-fpt-embedding-probe.md) |
| 4 | GT eval gate ≥0.82 + rollback guard (D4) | pending | 2h | dev-a | [phase-04](phase-04-gt-eval-gate.md) |

## Key Dependencies

- **D1 → D4**: descriptor expansion MUST be feature-flagged OFF by default, A/B'd on GT, rolled back on regression (standing user constraint).
- **D2 independent** of D1: pure logging, GT-neutral, ships anytime.
- **D3 independent**: standalone script, no backend wiring, does not block D1/D2.
- **D4 blocks merge of D1**: GT gate ≥0.82 (baseline 0.8205, 32/39) + zero-result/clarify/tone cases unchanged.

## Hard Constraints (carried into every phase)

1. **Keep UNCHANGED**: `query_relevance.py`, `repositories/merchant_repository.search_merchants` (keyword leg), `profile_ranking.py` + `ranking_config.py` (additive profile_score), always-on L1 `active_constraints` layer, CrewAI tool signatures in `tools/customer/merchant_tools.py`.
2. **D1 feature-flagged** default OFF, env-flip reversible.
3. **D2 pure logging** — no ranking/filter behavior change, GT-neutral.
4. **File-size rule**: <200 LOC, kebab-case descriptive filenames; **reuse `core.text_norm.fold_diacritics`** SSoT — do not duplicate fold logic.
5. No AI references in commits; conventional commits.
6. **DO NOT read/write `.env`** — D3 reads `FPT_API_KEY`/`FPT_BASE_URL` from `os.environ` only.

## Open Questions (resolve before D1 implementation)

- Descriptor dictionary coverage (full list + actual `taste_tags` distribution in merchant DB) — see phase-01 §"Open Questions".
- Log retention policy (rotate weekly? cap size?) — see phase-02.
- Coordinator-side new tool vs prompt-only gloss — see phase-01 §"Decision: prompt-only".

## Status

In planning. Awaiting lead approval before implementation.
