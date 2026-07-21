# Review — Merchant AI Agent Complete Design (v1.1)

> Ngày: 2026-07-21 · Nguồn: `docs/2026-07-21-merchant-ai-agent-complete-design.md`
> Kiểu: brainstorm review · Trạng thái: đã chốt 2 fork lớn

## Quyết định đã chốt (user)
1. **Kiến trúc agent = Native CrewAI** (doc này, 10 agent) làm chuẩn. → `agent-tool-design.md` (2-agent function-calling) **bị thay thế**.
2. **Phạm vi = full target, phase-gate.** Giữ roadmap A–L đầy đủ; chỉ duyệt+làm Feature A trước, review từng feature.

## Must-fix trước khi team duyệt (blocking)

| # | Vấn đề | Hành động |
|---|---|---|
| C1 | ~~`agent-tool-design.md` mâu thuẫn doc chuẩn~~ | **RESOLVED**: file không tồn tại trên disk/git (chỉ ở context cũ). Đã ghi note [C1] khẳng định doc CrewAI là contract chuẩn duy nhất. |
| C2 | Contract 6.4 để `overall_score` top-level; nghịch rule cứng "không surface" | Ghi rõ trong doc: giữ nội bộ, **strip ở API `/profile` + mọi tool/agent output**. Đồng bộ với `scoring-methodology.md`. |
| M1 | `waiting_time` basis ghi `preparation_time+late_complaints` | Sync với quyết định 2026-07-21 (bỏ late penalty khỏi waiting_time). Xem [[waiting-time-remove-late-penalty]]. |
| M4 | References trỏ `docs/data-dictionary.md` (đã xoá) | Đổi → `data-pipeline-and-dictionary.md`. |
| M5 | Fixture "5–10 merchants" vs as-built **18 hero** | Thống nhất con số (dùng 18 hero hoặc nêu rõ subset demo). |

## Rủi ro CrewAI + full (phải quản)

- **R1 — Traceable guarantee.** 10 agent + LLM sinh nội dung dễ thủng "mọi số truy vết được". **Bắt buộc:** tool = service Python tất định (đã có `dimension_scoring.py`, `build_profiles.py`); LLM chỉ route + narrate, không tự tính số.
- **R2 — Evidence Verifier là LLM agent.** Nên hạ xuống **cổng kiểm tra tất định** (assert claim ↔ `evidence_refs`), không phải agent bịa/regenerate. Rẻ + chắc hơn.
- **R3 — CrewAI vs "no LangChain".** Verify version CrewAI standalone (bản cũ kéo LangChain). Nếu kéo → điều khoản "no LangChain in dependency graph" bất khả thi.
- **R4 — Scope thời gian.** Full A–L (Redis, agent_events trace, eval harness, Leafmap, coordination) rất nặng cho demo. Phase-gate giảm rủi ro nhưng vẫn cần cắt tàn nhẫn per-feature.
- **R5 — Projection debt.** Evidence shape mới (`evidence_id/ref_type/ref_ids/source_kind`) + cột `profile_json` mới vs `dimensions_json` as-built → cần bước import projection (B-04) + quy tắc legacy fallback rõ ràng.

## Điểm mạnh của doc (giữ nguyên, chín)
Error envelope + stable error codes · `insufficient_data` thay vì bịa · tách source-of-truth (jsonl ↔ Postgres) · append-only preference/interaction events · tool registry metadata + per-agent allow-list · dependency direction chặt (routes→services→tools→domain→repo). Dùng được bất kể kiến trúc agent.

## Thách thức "verified decisions" (không blocking, nên cân nhắc)
- **Leafmap server-render HTML → iframe React**: clunky DX; `react-leaflet` tự nhiên hơn cho stack Vite. Cân nhắc lại khi tới Feature K.
- **Redis cho demo**: memory adapter đã đủ chạy demo; Redis thêm gánh Docker. Có thể defer trong Feature D nếu timeline căng.

## Bước tiếp theo đề xuất
1. Sửa 5 must-fix (C1, C2, M1, M4, M5) vào doc trước khi gửi team review.
2. Chốt R2 (Evidence Verifier tất định) + R3 (CrewAI version) — ảnh hưởng Feature F/H.
3. Nếu đồng ý → lập implementation plan **Feature A** (backend foundation) theo phase-gate.

## Câu hỏi chưa giải
- CrewAI version thực tế dùng bản nào? (quyết định R3 — TBD trong doc)
- 18 hero hay subset 5–10 cho fixture demo? (M5 — TBD trong doc)
