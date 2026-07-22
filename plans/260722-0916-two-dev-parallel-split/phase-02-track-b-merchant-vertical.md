# Phase 2 — Track B: Merchant Advisor Vertical (Dev B)

> Owner: Dev B. Branch từ `phase0-freeze`. Chạy SONG SONG với Phase 1. Full-stack (BE + FE).
> Scope UC: UC-01 (diagnosis), UC-02 (recommendation), UC-03 (competitor).

## File ownership (glob — chỉ Dev B sửa)
```
backend/repositories/{merchant_profile,evidence}_repository.py
backend/services/{merchant_profile,evidence,recommendation,competitor,agent_run}_service.py
backend/tools/{merchant_profile,evidence,competitor,trend}_tool.py
backend/agents/merchant/*   (+ agents/merchant/config/*.yaml)
backend/agents/listeners/*
backend/flows/merchant_flow.py
backend/routes/{merchant_profile,merchant_agent,trace}_routes.py
frontend/src/merchant/*
```

## Deliverables (map task doc)
### Data/domain
- [ ] C-02 profile + evidence repositories (§11.3 lookup)
- [ ] C-05 diagnosis + recommendation services (deterministic causes/actions §5.3)
- [ ] B-03 merchant profile fixtures 5-10 (target shape §6.4) — weak + strong + competitor cluster (§6.3)

### Tools/providers
- [ ] F-02(merchant) wrap: get_merchant_profile, get_profile_evidence, get_trending_dishes, compare_competitors, diagnose_merchant, recommend_improvements

### Merchant Agent (Feature H)
- [ ] H-01 merchant agents/tasks config (`agents/merchant/config/*.yaml`)
- [ ] H-02 diagnosis + recommendation tasks → evidence-backed structured output (§5.3)
- [ ] H-03 competitor task + **2-layer evidence check**: Layer 1 structural guardrail (deterministic, trong merchant_flow.py §5.3) + Layer 2 semantic Evidence Verifier agent
- [ ] H-04 merchant chat API (`POST /agent/merchant/chat` §11.5, UC-01→03)
- [ ] H-05 scenario tests UC-01, UC-02, UC-03

### Observability (Feature J) — owner
- [ ] J-01 CrewAI event listener (`agents/listeners/*`) — subscribe event của CẢ 2 flow (event schema freeze Phase 0)
- [ ] J-02 persist agent_runs + agent_events (§6.2)
- [ ] J-03 trace inspection API (`GET /agent/runs/{trace_id}` §11.9, dev/admin-only)
- [ ] J-04 optional CrewAI AMP config (env-gated)

### Merchant profile read routes
- [ ] `merchant_profile_routes.py`: `GET /merchants/{id}/profile` + evidence (§11.3) — **strip overall_score** (C2), trả per-dimension + evidence

### Frontend (merchant)
- [ ] Merchant chat page + SSE
- [ ] Profile dashboard 8 chiều (score + evidence drill-down, KHÔNG hiện overall_score — C2)
- [ ] Diagnosis / recommendation / competitor views (§11.5 response)
- [ ] Trace inspector view (dev) dùng §11.9

## Contract cứng (không được vi phạm)
- **C2**: overall_score internal-only — strip khỏi API/tool/agent output/UI. Luôn trả per-dimension + evidence.
- **Layer 1 evidence check** là guardrail deterministic trong `merchant_flow.py` (không phải tool agent); Layer 2 mới là Evidence Verifier agent.
- Diagnosis ≤ 5 nguyên nhân, mỗi nguyên nhân ≥ 1 evidence_ref resolve được; thiếu → `insufficient_data`.
- Chỉ coordinator được delegate (1 hop); specialist tắt delegation (§5.3).

## Depends on / seam contracts (từ Phase 0, KHÔNG sửa)
- models/profile.py + agent.py, tool registry, event schema, CachePort + **memory adapter (đã ship Phase 0 — [H4], test không cần Redis, không chờ Dev A)**.
- **[C1]** `get_merchant_profile` + `get_trending_dishes` là **shared read-only tool interface frozen ở Phase 0**; Dev B cung cấp impl thật nhưng SCHEMA cố định → Customer (Dev A) consume không vỡ. Đổi schema → qua contract-change protocol.
- **[H7]** Consume `nearby_merchant_search` (đã front-load Phase 0.5) qua registry cho Competitor — không chờ, không sửa file A.
- **[H8]** Listener (J-01) verify bằng contract test Phase 0 với event của CẢ 2 flow — không đợi merge mới biết flow A thiếu field.

## Success criteria
- 8 dimension hiển thị đủ score + evidence + basis (§6.4)
- Diagnosis/recommendation/competitor có evidence, thiếu → insufficient_data
- Trace từ HTTP request → response inspect được; tool call ghi input hash/duration/status
- Secret không lộ trong log (§17)
- UC-01→03 pass end-to-end với fixture nhỏ

## Note
- `waiting_time` = prep time thuần (M1 đã fix xong 2026-07-22 trong `scripts/profile/dimension_scoring.py`).
