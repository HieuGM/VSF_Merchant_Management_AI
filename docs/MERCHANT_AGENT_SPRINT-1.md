# Merchant Agent - Sprint 1

> Cap nhat: 2026-08-06  
> Trang thai: pipeline agentic hien hanh da hoat dong; Policy RAG da co retrieval
> foundation, con thieu ingestion va van hanh corpus production.

## Muc tieu

Sprint 1 chuyen Merchant Advisor sang mot pipeline Native CrewAI co dieu phoi
dong, data policy tap trung, Policy RAG va trace day du:

- hieu request va context truoc khi chon cach xu ly;
- coordinator chi goi specialist/tool can thiet;
- tach owner-private data khoi competitor-public data;
- moi claim phan tich duoc verify truoc khi tra loi;
- truy xuat tai lieu Green SM kem nguon;
- persist va stream agent/tool/LLM trace cho Developer UI.

## Cac moc chinh

| Giai doan | Ket qua |
|---|---|
| Week 1 | Native CrewAI, fixed crew, session, SSE va tool wrappers dau tien. |
| Week 2 | Multi-capability data contracts, privacy/evidence gates, cohort va image comparison. |
| Week 3 | Hierarchical coordinator, run-scoped gateway, Policy RAG, semantic tracing va prompt/tool budget. |

## Kien truc hien hanh

```text
Request + session
  -> Input Analyzer
  -> deterministic data-policy gate
  -> immutable fast answer hoac Native CrewAI Coordinator
  -> specialist agents
  -> RunScopedMerchantToolGateway
  -> PostgreSQL / Redis / Policy RAG (PostgreSQL + Chroma)
  -> Evidence Verifier
  -> Merchant Owner Answer Specialist
  -> persist run + semantic trace
  -> JSON/SSE + Developer UI
```

Python giu cac invariant ve scope, privacy, owner binding, schema, DB va cache.
LLM giu vai tro hieu yeu cau, dieu phoi, dien giai va tong hop tren evidence da
quan sat.

## Tai lieu lien quan

- [Week 1](./MERCHANT_AGENT_WEEK_1.md): kien truc fixed-crew ban dau.
- [Week 2](./MERCHANT_AGENT_WEEK_2.md): data contracts, privacy va evidence.
- [Week 3](./MERCHANT_AGENT_WEEK-3.md): pipeline moi, agents, tools, Policy RAG
  va ke hoach Policy Documents.

## Trang thai Policy Documents

Da co:

- schema PostgreSQL cho document va structure-aware chunk;
- contract retrieval co title, URL, category, section, ngay cap nhat va score;
- Chroma vector retrieval va category filter;
- `search_policy_documents` qua run-scoped gateway;
- Green SM Policy Document Specialist trong coordinator.

Con thieu de production-ready:

- source registry va quy trinh phe duyet tai lieu;
- downloader/parser/chunker va incremental ingestion;
- xoa vector stale, version index va index manifest;
- CLI/job dong bo, health check va metrics;
- golden retrieval dataset va end-to-end citation evaluation.
