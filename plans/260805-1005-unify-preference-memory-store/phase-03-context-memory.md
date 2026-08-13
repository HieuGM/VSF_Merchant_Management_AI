# Phase 03 — Implement context_memory

## Context Links
- Plan: `plans/260805-1005-unify-preference-memory-store/plan.md`
- Audit §7 M2. Files: `backend/database/models.py:337` (col), `backend/models/preference.py:32`, `backend/repositories/user_profile_repository.py`, `backend/tools/customer/customer_context_tools.py` (`get_user_profile`), `backend/flows/customer_flow.py` (`_persist_turns` L1152, `_load_profile` L1583), `core/pii.py`.

## Overview
- **Priority**: Medium | **Status**: Pending | **Effort**: M | **Depends**: 01
- Biến `context_memory` (JSONB, đang luôn `{}`) thành long-term cross-session memory thật: distilled free-text facts KHÔNG dẫn xuất từ structured fields. Inject qua output `get_user_profile` tool đã có (chỉ populate field).

## Key Insights
- **Boundary quan trọng**: `prior_context` (chat_messages, phase 01/02 đã tốt) = short-term in-session anaphora. `context_memory` = **long-term cross-session** — KHÔNG trùng lặp. Chỉ ghi facts free-text không có trong structured profile (vd "dị ứng đậu phộng", "thích quán yên tĩnh", "hay đi ăn nhóm").
- Output `get_user_profile` tool đã return `context_memory` → crew đã nhận → **không cần injection path mới**, chỉ cần POPULATE field đúng.
- PII: phải redact trước khi persist (dùng `core/pii.py` như turn memory).
- KISS/YAGNI: bắt đầu heuristic — phát hiện fact bền vững từ user turn (pattern "dị ứng X", "không ăn Y", "thích Z") → append note. Cap + FIFO.

## Requirements
- **FR-1**: Write path (post-run, F3-safe): phát hiện long-term fact từ user turn → redact → append vào `context_memory["notes"]` (list[str], cap N=8, FIFO). Không trùng structured field (skip nếu chỉ là cuisine/budget đã có structured).
- **FR-2**: Read: `get_user_profile` tool đã return — đảm bảo `_to_public` include (đã có). Crew prompt note rõ "ghi nhớ dài hạn, dùng nếu liên quan".
- **FR-3**: Cap size (≤8 notes, mỗi ≤120 char) + PII redact + dedupe (skip note trùng substring).
- **FR-4**: Không bao giờ break flow (swallow+log).
- **NFR**: ≤200 LOC module mới. Không grow `customer_flow.py`.

## Architecture
- New `services/context_memory_service.py` (thuần + DB): `extract_notes(user_text) -> list[str]` (heuristic patterns), `append_notes(user_id, notes)` (redact + dedupe + cap + persist, 1 tx, F3).
- `repositories/user_profile_repository.py`: `append_context_notes(user_id, notes, cap)` — read-modify-write `context_memory["notes"]`.
- `flows/customer_flow.py`: ở `_persist_user_turn` (flow entry) hoặc post-run — gọi `context_memory_service.maybe_persist(user_id, user_text)` (F3). **Quyết**: gọi tại `_persist_user_turn` (cùng lúc ghi user turn) — 1 điểm.
- `get_user_profile` tool: đã return context_memory; thêm dòng mô tả trong tool description cho crew biết dùng.

## Related Code Files
- **Create**: `services/context_memory_service.py`.
- **Modify**: `repositories/user_profile_repository.py` (+`append_context_notes`), `flows/customer_flow.py` (call 1 site), `tools/customer/customer_context_tools.py` (mô tả tool).
- **Delete**: — .

## Implementation Steps
1. `context_memory_service.py`: `extract_notes()` (regex VN: "dị ứng/tôi không ăn/thích...không"/"hay ... cùng"), `append_notes()` (redact via pii + dedupe + cap + persist).
2. `user_profile_repository.py`: `append_context_notes(user_id, notes, cap=8)` read-modify-write JSONB.
3. `customer_flow.py`: trong `_persist_user_turn`, sau khi append turn → `context_memory_service.maybe_persist(user_id, user_text)` (F3 wrap, log on err).
4. `customer_context_tools.py`: update `get_user_profile` description ("bao gồm ghi nhớ dài hạn cross-session — dùng khi liên quan").
5. (Optional) seed: script migrate/seed context_memory sample cho demo.

## Todo List
- [ ] context_memory_service (extract + append) + unit test
- [ ] repo append_context_notes
- [ ] wire vào _persist_user_turn (F3)
- [ ] update tool description
- [ ] py_compile + lint

## Success Criteria
- User nói "tôi dị ứng đậu phộng" → note (redact PII) lưu vào context_memory, query sau thấy lại qua `get_user_profile`.
- Cap 8, FIFO, dedupe. PII redact. Flow không crash nếu DB fail.
- Unit test: extract patterns, dedupe, cap, redact, F3 (DB fail → [] swallow).

## Risk Assessment
- Heuristic ồn/giả positive → notes rác. **Mitigation**: pattern chặt; cap; chỉ fact bền vững; cho user xem/xóa (FE Preference Center — phase 04).
- Bloat/leak PII. **Mitigation**: cap + redact + FIFO.
- Trùng structured profile. **Mitigation**: extract skip cuisine/budget keyword đã có structured.

## Security Considerations
- PII redact bắt buộc trước persist (reuse `core/pii.py`). context_memory là dữ liệu cá nhân — IDOR guard (phase 01) bảo vệ read/write.

## Next Steps
- Phase 04: FE cho user xem/xóa context_memory notes (Preference Center). Phase 05 test.
