# Brainstorm Report — PRD Revision (Merchant Management & AI Agent Platform)

**Date:** 2026-07-20 | **Output:** `plans/prd-merchant-management-ai-v2.md`

## Problem
PRD v1.0 (`plans/PRD_Merchant_Management_AI.docx`, AI-generated) assumed 100% mock data, ignored existing real dataset, over-scoped for 6-week solo demo.

## Key findings (data audit `data/shopeefood_catalog.jsonl`)
- 3,277 records = 3,277 unique merchants, **1 item each** (not full menus) → Menu Diversity infeasible without synthetic menu expansion.
- `merchant_rating`/`review_count` junk values (1000.0/500/None ~50%) — unusable.
- Real & usable: name, address, lat/lng, image_url (3,197), category, open hours; 9 cities (HCM/HN/DN 700 each).
- Fully synthetic already: price, avg_prep_minutes; partial: taste/ingredient/diet tags.
- Missing entirely: reviews, complaints, delivery feedback, ops metrics (~80% of profile framework inputs).
- v1.0 referenced `Sprint_Tracking_6_Tuan.xlsx` — file absent from repo.

## Decisions (user-confirmed)
| Topic | Decision |
|---|---|
| Data strategy | Hybrid: hero-set 15–20 merchants deep data (crawl reviews timeboxed 3–4d → synthetic fallback); background 3,257 for search. Internal data (complaints/delivery/ops) always synthetic. |
| Dimensions | Keep all 13, restructured: 8 scored (pipeline) + 5 attributes (no scoring) — feasibility compromise. |
| Trending | Mine from own dataset (cross-merchant tags/review frequency per region/cuisine), not social media. User's idea, better than v1.0. |
| Backend | Python FastAPI (crawl + data pipeline + agent in one language). |
| LLM | Provider-agnostic OpenAI-compatible layer. User has OpenAI / NVIDIA NIM / FPT Cloud keys (NOT Claude as v1.0 proposed). Runtime agent = OpenAI; batch = NIM/FPT cheap models. |
| Weather | Open-Meteo free API + manual override button for demo control. |
| Output format | Markdown PRD v2 in plans/; docx kept as historical reference. |

## Rejected approaches
- Synthetic-everything for 3,277 merchants: LLM cost/time overkill (YAGNI).
- 100% mock 3–5 merchants (v1.0 original): wastes real crawled data.
- Runtime web-search trending: slow, unstable for live pitch.
- Keeping 13 scored dimensions: infeasible in 6 weeks solo.

## Risks flagged
- Review crawl fragile (anti-bot, internal API) → timeboxed, fallback ready.
- Legal note: crawled data internal demo only, contradicts v1.0 §9.2 constraint — accepted with documented mitigation (§3.6 of v2).
- LLM cost: vision limited to hero-set first, batch cached offline.

## Next steps
- User to review PRD v2.
- If approved → create implementation plan (`/plan`) from PRD v2, starting Sprint 1 (data foundation).

## Unresolved questions
- Which exact OpenAI model for agent runtime (budget-dependent).
- Hero-set city choice (suggest HCM — largest pool, 700 merchants).
- Whether to anonymize merchant names for public pitching.
