# Phase 06 — Docs Sync

## Context Links
- Plan: `plans/260805-1005-unify-preference-memory-store/plan.md`
- Audit §7 + §4 (docs=42 worst). Files: `README.md`, `docs/development-roadmap.md`, `docs/system-architecture.md` (MISSING — tạo), `docs/customer-agent-testing-guide.md`, `docs/evaluation-plan.md`, `docs/database-schema.md`.

## Overview
- **Priority**: Medium | **Status**: Pending | **Effort**: S | **Depends**: 01–04
- Cập nhật docs phản ánh memory đã thống nhất: 1 store chuẩn mực, ranking tất định, context_memory hoạt động. Giảm gap docs=42.

## Key Insights
- Audit §7 + §4: README merchant-only, system-architecture MISSING, roadmap stale, testing-guide sai provider (NVIDIA→FPT). Phase này sửa phần memory + góp phần sửa docs tổng thể.
- Ghi rõ boundary: `prior_context` (short-term, chat_messages) vs `context_memory` (long-term, user_profiles) vs structured profile — 3 lớp memory.

## Requirements
- **FR-1**: Tạo `docs/system-architecture.md` (nếu chưa) — section memory: 3 lớp (structured profile / context_memory / prior_context), propose/confirm/PATCH write paths, ranking additive, IDOR guard.
- **FR-2**: Update `README.md`: mention CrewAI customer agent + memory thống nhất + link setup-guide.
- **FR-3**: Update `docs/development-roadmap.md`: milestone "Unify preference memory" COMPLETE (sau 05), Last Updated 2026-08-05.
- **FR-4**: Update `docs/customer-agent-testing-guide.md`: provider FPT (không NVIDIA); section test memory (PATCH/ranking/context_memory); eval harness thực `eval_ground_truth.py`.
- **FR-5**: Update `docs/evaluation-plan.md` (hoặc rename merchant-eval) + ghi snapshot eval mới (từ 05).
- **FR-6**: `docs/database-schema.md`: confirm `context_memory` JSONB đã dùng; note write path.
- **NFR**: Ngắn gọn, chính xác; sacrifice grammar cho concision.

## Architecture
- Docs thuần markdown. Theo `documentation-management.md`. Không code.

## Related Code Files
- **Modify**: `README.md`, `docs/development-roadmap.md`, `docs/customer-agent-testing-guide.md`, `docs/evaluation-plan.md`, `docs/database-schema.md`, `docs/project-changelog.md` (+entry "Unify preference memory").
- **Create**: `docs/system-architecture.md` (nếu MISSING) hoặc section mới.

## Implementation Steps
1. Tạo/cập nhật `docs/system-architecture.md` — memory section (3 lớp + write paths + ranking + guard).
2. `README.md` — overview + memory thống nhất + quickstart link.
3. `development-roadmap.md` — milestone + date.
4. `customer-agent-testing-guide.md` — FPT + memory test section.
5. `evaluation-plan.md` — harness thực + snapshot after.
6. `database-schema.md` — context_memory active note.
7. `project-changelog.md` — entry.

## Todo List
- [ ] system-architecture memory section
- [ ] README overview
- [ ] roadmap milestone + date
- [ ] testing-guide FPT + memory
- [ ] evaluation-plan + snapshot
- [ ] database-schema note
- [ ] changelog entry

## Success Criteria
- Docs phản ánh đúng as-built memory (3 lớp, write paths, ranking).
- Không còn claim sai (NVIDIA, stub profile, roadmap stale).
- Cross-link đúng, date 2026-08-05.

## Risk Assessment
- Docs lại stale nhanh nếu code đổi. **Mitigation**: gắn doc update vào definition-of-done mỗi phase sau.

## Security Considerations
- Không ghi key/secret vào docs. Ghi IDOR là TODO(AUTH) rõ.

## Next Steps
- Plan hoàn thành. Tiếp: implement theo phase 01 → 06.
