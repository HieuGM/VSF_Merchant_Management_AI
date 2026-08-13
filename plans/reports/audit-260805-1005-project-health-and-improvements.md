# AI_Restaurant — Project Health & Quality Audit

- **Ngày**: 2026-08-05 | **Branch**: dev-a | **Phương pháp**: 6-dimension parallel audit (7 agents, 412K tok, 220 tool-calls) + live run/view
- **Verdict**: **Needs-work with a solid core — Score 61/100**
- **Evidence**: live FE (:5173) + BE (:8000, health=`ok/db/redis/llm_configured`); agent chat verified trustworthy; 0 console errors; pytest 106 passed.

---

## 1. View ( chạy thật )

| Mặt | Kết quả |
|---|---|
| Landing `/customer` | "GSM · Trợ lý ẩm thực" — UI tiếng Việt polish, quick-prompts, dark mode, ảnh quán thật, theme toggle, user-code |
| Chat end-to-end | Agent trả lời trung thực: *"chưa thấy quán phở nào cả"* → không bịa, hiển thị 3 quán thật (4.7/4.8/4.7) + match-score → **anti-confabulation/grounding đang hoạt động** |
| FE console | 0 error / 0 warning |
| BE health | `{status:ok, database:ok, redis:ok, llm_configured:true}` |
| Ảnh | `view-customer-landing.png`, `view-customer-chat-response.png` (repo root) |

---

## 2. Dimension Scorecard

| Dimension | Score | Health |
|---|---|---|
| Frontend | 78 | minor-issues |
| Code quality (BE) | 72 | minor-issues |
| Infra / security | 72 | minor-issues |
| Test & EVAL | 62 | needs-work |
| Backend architecture | 58 | needs-work |
| **Documentation** | **42** | **needs-work (worst)** |

---

## 3. Strengths ( giữ )

- **Seams đóng băng đúng**: tool registry = data artifact (allow-list); single CrewAI adapter; listener ContextVar w/ H8 contract test → swap-ready.
- **Security baseline tốt**: `.env` gitignored (chỉ `.env.example` track), 0 hardcoded secret, SQL parameterized (haversine = pure-Python), PII redaction 1-way, provider ngoài keyless (Open-Meteo) + graceful degrade.
- **Migration chain sạch + tuyến tính** (None→026b4a8e→a1b2c3d4→b1c2d3e4→c2d3e4f5a6b7, single head, full downgrades).
- **Reliability machinery mạch lạc**: pipeline anti-confabulation đầy đủ (OOD/dietary/price-clarify/sparse/grounding/prior-referent/attribute-absence); 5/5 GT target mới judge-confirmed.
- **BE code comment tốt** (intent + audit tags), type hint nhất quán, AST clean (0 lỗi).
- **FE hiện đại + modular**: Vite8+React19+TS6, build sạch 705ms/0 err, oxlint pass, mọi file <~210 LOC, a11y, SSE+geolocation.
- changelog cập nhật; contract guards vững (no-langchain, allow-list sync, API-stub fence).

---

## 4. Top Improvements ( ranked )

| # | Mục | Sev | Effort | Impact |
|---|---|---|---|---|
| 1 | **Bỏ 66MB SQL dump khỏi git** (`merchant_platform.sql`+.gz, commit 47279a8). `.gitignore` tự ghi "do not commit" nhưng file gốc vẫn uncovered → phình clone + lộ dataset live-shaped. `git rm --cached` + thêm pattern. | critical | s | high |
| 2 | **`pack-for-transfer.sh` gói `.env` (FPT/NIM keys) vào archive** di động (USB/Drive). Mã hóa (gpg/7z) HOẶC strip `.env`. | critical | s | high |
| 3 | **IDOR `user_routes` confirm_delta/reject_delta** (L84-88,114): whitelist bound WHAT không phải WHO → forge `user_id` mutate profile người khác. Gate bằng auth dependency. | high | m | high |
| 4 | **Tách `customer_flow.py` (1865 LOC, 9.3× rule 200)** → package `flows/customer/` (~10 concern). God-object: classify/guards/memory/anaphora/orchestration/streaming/norm_vi lẫn lộn; guard không có unit test vì chôn sâu. | critical | xl | high |
| 5 | **Thống nhất `/chat` vs `/chat/stream`** (behavioral drift): anaphora follow-up routing + post-search grounding guard **chỉ** ở path stream → cùng query kết quả khác nhau theo transport. Extract `_run_pipeline(sink)`. | high | l | high |
| 6 | **Wrap `AgentRunRepository` commits trong try/except**: hiện DB blip (constraint/conn drop) crash crew kickoff. Rollback+log như `chat_message_repository`. | high | s | high |
| 7 | **Rewrite README + tạo `docs/system-architecture.md` + unfreeze roadmap**: README chỉ mô tả merchant DB (bỏ sót CrewAI/FE/layered BE); roadmap ghi Track A "NOT STARTED 0%" trong khi commit 39/39; 7 doc CLAUDE.md-mandated MISSING. | critical | l | high |
| 8 | **Đính chính claim "39/39"**: cơ học TRUE (0 err/0 interrupt) nhưng quality chỉ 5/5 mới judge; 34/39 roll-forward từ baseline 87.2%. 30+ regex guard không unit test; eval harness (SSE live-server) không trong pytest/CI; `coverage.json` stale (233 stmt). | high | l | high |
| 9 | **Merchant stub = vaporware**: `agents/merchant/` chỉ config YAML (no `crew.py`); allow-list khai 6 role + 5 tool nhưng chưa register → `registry.tools_for_agent()` silently drop; `/api/v1/agent/merchant/chat` = 501. Implement HOẶC thêm `registry.health_check()` + STUB.md. | high | l | medium |
| 10 | **`requirements.txt` (loose `>=`) vs `environment.yml` (locked) drift**: `pip install -r` resolve stack khác chưa validate. Pin freeze hoặc mark env.yml authoritative. | medium | s | medium |
| 11 | **Dead code**: 7+ method chết `MerchantRepository`; `SearchPage.tsx`+`SearchPage.css`+`lib/api.ts` orphan (~330 LOC FE); `providers/geocode`+`routing` rỗng. Xóa sau grep. | medium | s | medium |
| 12 | **DB Session ownership lệch**: 7+ helper mỗi cái mở `SessionLocal` riêng (vi phạm contract "repo nhận Session, không mở"); `AgentRunRepository` cũng tự mở. 1 request → 7+ connection. Inject 1 Session/UnitOfWork. | medium | m | medium |
| 13 | **Tailwind v4 no-op + `shared/api-client` chết**: Tailwind trong deps nhưng postcss không register, không `@import` → silently unstyled; `shared/api-client` (FROZEN seam, trace-id) không ai dùng (client gọi raw `fetch`). Commit hoặc drop. | medium | s | medium |
| 14 | **Doc stale**: testing-guide ghi NVIDIA_NIM (thực tế FPT); evaluation-plan trỏ artifact không tồn tại; 3 doc onboarding xung đột backend tree/install/env. | high | m | high |
| 15 | **Trừu tượng `GuardPipeline` + kill `_norm_vi` dup**: guard order encode trong comment không phải typed pipeline (gốc drift #5); `_norm_vi`(flow) ≡ `_norm_text`(repo) → extract `core/text_norm.py`. | medium | m | medium |

---

## 5. Quick Wins ( xs–s, làm ngay )

- `git rm --cached merchant_platform.sql(.gz)` + `.gitignore` (#1)
- try/except + rollback `AgentRunRepository` (#6)
- warning echo / mã hóa `pack-for-transfer.sh` (#2)
- xóa `SearchPage.tsx/.css` + `lib/api.ts` (#11, ~330 LOC)
- fix/drop config Tailwind (#13)
- extract `_norm_vi` → `core/text_norm.py` (#15)
- `get_customer_flow()` @lru_cache thay singleton import-time side-effect
- bump roadmap: Phase 0.5 COMPLETE, Track A IN PROGRESS 39/39, Last Updated 2026-08-05 (#7)
- bỏ `version:'3.8'` legacy trong 3 docker-compose + `pg_isready` healthcheck
- React.lazy+Suspense 4 page customer (code-split, ~5 dòng)
- `sendingRef` thay state `sending` trong `use-customer-chat.ts:101`
- SUPERSEDED callout doc `dimensions_json` drop (migration c2d3e4f5a6b7)
- xóa PRD duplicate trong `plans/`

---

## 6. Unresolved Questions ( cần user quyết )

1. Merchant agent: trong scope (Dev B) hay freeze vĩnh viễn? → quyết định #9 implement vs surface-stub.
2. 7 method chết `MerchantRepository` thuộc Dev B? An toàn xóa?
3. Anaphora routing + grounding guard có áp dụng BOTH `/chat` + `/chat/stream`? (gần chắc yes — quyết định product trước unify #5).
4. `_norm_vi` hay `_norm_text` canonical cho helper chung (#15)?
5. `pack-for-transfer.sh` còn workflow active hay one-off? → harden vs delete.
6. Tailwind: commit (v4) hay drop (#13)?
7. `.env` trong archive transfer: rủi ro chấp nhận hay bắt buộc mã hóa/strip?
8. Khi nào re-run full 39-case LLM judge để biến baseline 87.2% thành số hiện tại (#8)?
9. LLM-judge model + pass-threshold có pin/doc không (hiện manual)?
10. `providers/geocode`+`routing` rỗng: xóa (YAGNI) hay giữ placeholder?

---

## 7. Memory & Preference — Deep-Dive (kiểm tra chuyên sâu theo yêu cầu)

Hệ thống có **2 lớp memory**:

**A. Turn memory (ngắn hạn)** — `chat_messages` → `prior_context` cho anaphora
**B. Preference memory (dài hạn)** — `user_profiles` (liked/disliked cuisines, spice, dietary, budget, distance, `context_memory`)

### Đánh giá

| Lớp | Verdict |
|---|---|
| **A. Turn memory** | ✅ **Xuất sắc** — wired + test đầy đủ |
| **B. Preference memory** | ⚠️ **Primitive tốt NHƯNG có khoảng trống chức năng nghiêm trọng** |

**A. Turn memory — điểm mạnh (giữ):**
- Anaphora resolution: `_format_prior_context` ghép user-turn + top-3 merchant đề xuất trước đó → giải mã "quán đầu tiên/món đó/rẻ hơn".
- `exclude_merchant_ids` (`_collect_exclude_ids`): không gợi ý lại quán cũ (TC-30).
- TTL 24h (`get_recent_turns`), PII redaction trước khi ghi (`test_append_turn_redacts_pii`).
- **`_NO_PRIOR_NOTE`**: turn-1 inject note "CHƯA có lịch sử" → chặn confabulation "hồi nãy mình gợi ý…" (TC-01/07/47/50).
- Test: B1 (FK get-or-create), B2 (TTL), B4 (exclude), prior_context, idempotency — phủ kỹ.

**B. Preference memory — khoảng trống (mới phát hiện):**

| # | Vấn đề | Sev |
|---|---|---|
| M1 | **FE Preference Center ↔ backend `user_profiles` MẤT KẾT NỐI.** `use-preferences.ts:2-5` (comment chính tội phạm): *"backend profile endpoints still stubbed → preferences live in **localStorage**"*. Trang Sở thích ghi `localStorage` (`cust_preferences`), KHÔNG ghi backend → **mất khi clear browser, không đồng bộ thiết bị**, và `get_user_profile` tool (đọc backend) **không thấy** sở thích user tự chỉnh. | critical |
| M2 | **`context_memory` (JSONB) = field CHẾT.** Đúng nghĩa "ghi nhớ hội thoại" trong README §41 nhưng **không bao giờ được ghi**, luôn `{}` (chỉ read ở `_to_public`, set `{}` ở seed/test). Promise chưa implement. | high |
| M3 | **Backend profile KHÔNG dùng cho filter/rank search.** `_load_profile` (L1583) chỉ feed **weather merge (B3)**; grep `profile\.\b` trong flow gần như rỗng. `budget_level/dietary/liked_cuisines/spice_tolerance` chỉ tới LLM qua tool `get_user_profile` (LLM-có-thể-bỏ-quên), KHÔNG deterministic trong `MerchantSearchService`. | high |
| M4 | **3 route REST = stub 501**: `GET /{user_id}/profile`, `list_sessions`, `delete_preference` (`user_routes.py:51,124,119`). FE không thể REST-đọc profile backend (chỉ tool LLM đọc được). | high |
| M5 | **`preferencesToContext(prefs)` nối thẳng vào text query** (`customer-chat.tsx:46`: `text + preferencesToContext(prefs)`) → sở thích localStorage tới LLM dưới dạng prompt text, không cấu trúc → không deterministic, dễ bị ignore. | medium |
| M6 | **`confirmDelta` trả profile cập nhật nhưng FE bỏ qua** (`customer-agent-client.ts:149`: *"unused by the UI today"*) → không re-validate/hiển thị client-side sau khi lưu. | low |
| M7 | IDOR confirm/reject (đã #3) + mỗi helper mở `SessionLocal` riêng (đã #12) — cũng áp dụng layer này. | high/medium |

**Nguyên gốc thiết kế (tốt):** propose/confirm split (§7.1 — agent chỉ đề xuất, chỉ route confirm mới ghi), typed validation B5, idempotency B6, upsert R3, audit trail `preference_events`. Chat-suggestion flow (crew → `preference_suggestions` → FE "Lưu/Bỏ qua" → `confirmDelta` → `user_profiles`) **đã kín server-side**.

**Tóm:*/ primitive memory/preference vững nhưng **lời hứa "ghi nhớ sở thích người dùng" chưa thành hiện**: Preference Center (chỉnh tay) lưu localStorage, profile backend không shape search, `context_memory` chết. → Cần統 nhất 1 store + deterministic profile-based ranking + (tùy chọn) implement `context_memory`.

---

## 8. Ghi chú phương pháp

- Audit chạy song song 6 chiều (backend-arch, code-quality, test-eval, frontend, docs, infra-security) + 1 synthesis. 2 agent (test-eval, frontend) retry do stall nhưng hoàn tất (attempt 3).
- test-eval agent: safety-classifier tạm không khả dụng lúc review → verify trước khi hành động theo #8.
- "View" = chạy thật FE+BE, test chat end-to-end qua Playwright (không mock).
