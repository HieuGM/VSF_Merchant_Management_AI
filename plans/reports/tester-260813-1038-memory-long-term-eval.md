# Memory Long-Term Eval — `memory_test.json` (28 case)

> Test retention xuyên session (15-20) của customer agent. Harness deterministic dùng **code production thật** (`extract_notes` + `build_active_constraints` + FIFO mirror). Date: 2026-08-13.

## ✅ UPDATE 2026-08-13 — Phase 1 fix IMPLEMENTED + verified

**3.1 (peanut safety): FAIL → PASS.** Fix generalize (không hard-code catalog): surface **mọi** allergy note cho explanation LLM (`ActiveConstraints.health_notes` → block "CẢNH BÁO SỨC KHOẺ"), LLM dùng world-knowledge cảnh báo. Fix thêm blocking-path asymmetry (block `/chat` vốn inject 0 constraint). Verify: 22/22 unit test PASS + live E2E 3.1 warn đúng (*"sốt satay hay trộn đậu phộng, mình dặn trước cho an tâm"*). Còn lại chưa fix: **7.2/3.4** (stale contradictory-note bug) + **6.3** (no TTL) — separate. Chi tiết + plan: `~/.claude/plans/glittery-mixing-thompson.md`.

**7.2 (selective delete) & 3.4 (allergy change): FAIL → PASS.** Fix stale-note bug: retraction ("quên chuyện dị ứng tôm", "bác sĩ nói hết dị ứng") giờ (1) không lưu thành note mâu thuẫn, (2) **xóa note allergy cũ** khớp (`maybe_persist` → `remove_notes_matching`), (3) loader `_RECOVERY_RE` broaden để retraction trong current msg cũng suppress. Verify: 25/25 unit test + live E2E 7.2 PASS (rút tôm xong hỏi hải sản → agent gợi ý *Hải Sản Huyền Thoại*, không gate).

**6.3 (no TTL): FAIL → PASS.** Fix: temporary constraint giờ có expiry. `context_memory_service` detect duration marker ("tuần này"→7 ngày, "tháng này"→30, "hôm nay"→1) → store `context_memory["note_expiries"]` (ISO tuyệt đối). `maybe_persist` **prune** note hết hạn mỗi call (chạy trước `_load_profile`); loader `_expired_note_keys` skip note hết hạn (defense). Verify: 28/28 unit test (duration detection + expired-not-enforced + valid-still-enforced) + DB prune spot-check (inject now). **→ Cả 4 FAIL thật đã fix (3.1 / 7.2 / 3.4 / 6.3).** Full unit suite 243 passed, 0 failed.

**Phase 2 (6.1 FIFO-eviction hardening): IMPLEMENTED.** Structured `allergens` JSONB field (NO FIFO cap, distinct from notes cap=8). Permanent allergy/avoid facts (`_is_permanent_avoid_note`: allergy-verb + no duration) mirrored there; temporary kiêng stays in notes (TTL). Loader xử lý `profile.allergens` giống notes (catalog hard-filter + health_notes) ⇒ allergy sống sót FIFO eviction. Migration `e4f5a6b7c8d9` applied. Verify: 30/30 memory unit test + DB spot-check (populate/retract/temp-exclusion) + loader no-cap surfacing. (Tìm + fix 1 root-cause bug: read/remove repo methods dùng `_get_or_create_row` gây double-INSERT cho user mới → đổi sang non-creating `_db.get`.)

## TL;DR — "Nhớ được 15-20 session không?"

**CÂU HỎI SAI.** Session KHÔNG phải đơn vị decay. Retention phụ thuộc **số lượng durable-fact tích lũy**, không phải số session:

| Layer | Lưu gì | Cap / Decay | Nhớ 20 session? |
|---|---|---|---|
| **L1 structured profile** | cuisine, spice, budget, diet | **không cap, không decay** | ✅ mãi mãi (nếu LLM extract + user confirm) |
| **L2 context_memory.notes** | allergy, medical, diet khai báo | **FIFO cap=8** | ⚠️ chỉ ≤8 fact; fact thứ 9 evict cũ nhất |
| **L3 session window** | turn gần đây (8 USER turn) | session-scoped, reset mỗi session | ❌ KHÔNG cross-session |

- **User điển hình** (vài allergy/medical, phần lớn là cuisine/budget → L1): **CÓ nhớ đủ 20 session.**
- **User nhiều allergy/medical** (>8 durable note): fact cũ nhất bị **FIFO evict** → rủi ro safety.
- **Retention ≠ Enforcement.** Đây mới là bottleneck thật: chỉ **2 scope** được hard-enforce (`seafood`, `chay`). 8/28 case **lưu được fact nhưng không filter được** → vẫn gợi ý món vi phạm.

## Phương pháp

1. **Harness** `backend/scripts/memory_retention_eval.py`: replay 28 case xuyên span 15-20 session (có filler trung gian), test session cuối = fresh session (Layer 3 rỗng → recall phải từ L1/L2). Dùng `extract_notes` thật + FIFO mirror y hệt `append_context_notes` + `build_active_constraints` thật.
2. **FIFO probe** `scripts/memory_fifo_db_probe.py`: chèn N durable note, xem fact #1 sống đến bao nhiêu.
3. **Unit test sẵn có** `test_memory_spec.py` + `test_context_memory.py`: **16/16 PASS** → xác nhận code production khớp harness.
4. **Live end-to-end** (`scripts/memory_live_e2e_cases.py`, `/chat` thật, 1625 merchant): fix root-cause env trước (native `postgresql-x64-18` tranh port 5432 với Docker → host trúng native, auth fail; reset pass user postgres trong Docker + stop service native). 3 case:
   - **3.1 peanut safety → FAIL (gap xác nhận live)**: khai báo dị ứng đậu phộng → session mới hỏi buffet → agent gợi ý buffet (The Grand Buffet…) **không cảnh báo** peanut.
   - **7.2 selective delete → FAIL (stale xác nhận live)**: rút dị ứng tôm → session mới hỏi hải sản → agent VẪN *"bạn có vẻ đang kiêng/dị ứng hải sản"* + confirm-gate → seafood bị chặn sai (note mâu thuẫn).
   - **1.1 chay recall → agent nhớ (không re-ask) ✅**, nhưng search trả 0 + prose vẫn nhắc "Phở Bò" → enforcement **không kết luận** (mixed; có thể do không có merchant chay gần Cầu Giấy).
   - Intermittent `internal_error` trên 1 số call = FPT 401 theo load (per memory note), retry với delay thì qua.

## Kết quả từng case

Verdict realism (grounded trong code enforcement thật, không đoán):

| ID | Nhóm | Span | Retention | Enforcement | Verdict |
|---|---|--|---|---|---|
| 1.1 | Temporal | 1→20 | ✅ note chay sống | ✅ hard-filter chay | **PASS** |
| 1.2 | Temporal | 5→20 | ✅ note cay sống | ❌ spice ngoài catalog | **PARTIAL** |
| 1.3 | Temporal | 8→16 | ✅ note tỏi sống | ❌ garlic ngoài catalog | **PARTIAL** |
| 1.4 | Temporal | 9→20 | ✅ note đậu phộng sống | ❌ peanut ngoài catalog | **PARTIAL** (safety) |
| 2.1 | Conflict | 3→15→20 | ✅ (L1 spice) | — phụ thuộc LLM overwrite | **LLM-dep** |
| 2.2 | Conflict | 10→20 | ✅ note tôm sống | ⚠️ bucket seafood over-exclude | **PARTIAL** (không tách tôm) |
| 2.3 | Conflict | 4→12 | ✅ temp ko lưu, chay durable | ✅ chay enforced | **PASS** |
| 2.4 | Conflict | 7→20 | — (L1 dislike) | — | **LLM-dep** |
| 3.1 | Safety | 2→20 | ✅ note đậu phộng sống | ❌ peanut ko catalog → KO cảnh báo | **FAIL** (safety) |
| 3.2 | Safety | 2→20 | ✅ 3 note sống | ⚠️ chỉ chay (1/3) | **PARTIAL** |
| 3.3 | Safety | 6→20 | ✅ câu đùa ko lưu | ✅ ko false constraint | **PASS** |
| 3.4 | Safety | 3→17→20 | ⚠️ note allergy cũ còn | ❌ seafood vẫn enforce sau rút | **FAIL** (stale) |
| 4.1 | Isolation | 3→4 | ✅ ctx nhóm ko lưu | ✅ ko leak | **PASS** |
| 4.2 | Isolation | 5→6 | ✅ pref người khác ko vào note | ✅ (L1 LLM) | **PASS** |
| 4.3 | Isolation | 2→11 | — (L1 location/GPS) | — | **LLM-dep** |
| 5.1 | Multi-hop | 2→20 | ✅ (L1, ko cap) | — ranking conjunction | **LLM/DB-dep** |
| 5.2 | Multi-hop | 4→20 | — (L1+episodic) | — | **LLM-dep** |
| 5.3 | Multi-hop | 3→20 | — (episodic rating) | — | **LLM-dep** |
| 6.1 | Weight | 1→20 | ⚠️ FIFO=8 ko chứa 40 fact | — weighting LLM | **PARTIAL** |
| 6.2 | Weight | 1→18→20 | ✅ (L1 spice set-overwrite) | — phụ thuộc LLM overwrite | **LLM-dep** |
| 6.3 | Weight | 10→15 | ✅ note sống | ❌ KO TTL → tồn tại vĩnh viễn | **FAIL** (no expiry) |
| 7.1 | Transparency | 20 | — (LLM liệt kê note) | — | **LLM-dep** |
| 7.2 | Transparency | 3→20 | ⚠️ rút lại thành note mâu thuẫn | ❌ seafood vẫn enforce sai | **FAIL** (stale) |
| 7.3 | Transparency | 1→20 | ✅ `clear_memory` wipe hết | ✅ nếu LLM trigger clear | **PASS** (cần LLM) |
| 8.1 | Stress | 9→20 | ✅ note nội tạng sống | ❌ organ-meat ngoài catalog | **PARTIAL** |
| 8.2 | Stress | 6→20 | — (L1 self-correction) | — | **LLM-dep** |
| 8.3 | Stress | 11→20 | ✅ note sống | ❌ "HS" matcher ko giải mã | **PARTIAL** (viết tắt) |
| 8.4 | Stress | 20 | — (LLM fallback) | ✅ memory trả rỗng sạch | **LLM-dep** (no crash) |

**Tally (28):** PASS 5 · PARTIAL 8 · FAIL 4 · LLM-dependent 10 · (7.3 = PASS có điều kiện)

## Bottleneck & bug thật (tìm thấy trong code)

1. **Catalog chỉ 2 scope** (`constraint_catalog.CATALOG` = `seafood` + `chay`). Đậu phộng/tỏi/nội tạng/sữa/cay… được **lưu vào note nhưng KHÔNG hard-filter**. **3.1 (peanut buffet)** là FAIL safety nghiêm trọng nhất — note sống 18 session nhưng agent vẫn gợi ý buffet ko cảnh báo. Đây là gap lớn nhất, **lớn hơn cả vấn đề retention**.

2. **Không TTL/expiry** (`context_memory_service` lưu mọi durable note vĩnh viễn). **6.3**: "tuần này ăn kiêng ít dầu mỡ" → trigger `kieng` → lưu durable, **không bao giờ hết hạn**. Trái với ý đồ "constraint tạm thời".

3. **Note mâu thuẫn → stale allergy** (3.4, 7.2). Câu rút lại ("quên chuyện dị ứng tôm đi", "bác sĩ nói hết dị ứng") **bản thân chứa từ "dị ứng"/"tôm"** → bị `extract_notes` lưu thành note MỚI. `_RECOVERY_RE` ("không con|đã hết|het roi…") khớp câu rút lại nhưng KHÔNG khớp câu khai báo gốc → mâu thuẫn: allergy VẪN được enforce ở session 20 dù user đã rút. **7.2 xóa 1 fact fail**; **3.4 xóa allergy fail**.

4. **FIFO evict safety-critical** (6.1). cap=8: >8 durable fact → allergy cũ nhất bị dropped. Probe xác nhận fact #1 chết ở fact thứ 9.

5. **Granularity + viết tắt** (2.2, 8.3). Bucket `seafood` = toàn bộ shellfish+sushi → **2.2** (dị ứng tôm nhưng thích seafood nói chung) bị over-exclude cả seafood. **8.3** viết tắt "HS" = hải sản: note lưu nhưng matcher catalog (`scope_present`) tìm token `hải sản`/`tôm`… ko giải mã "HS" → không enforce.

## Điểm PASS đáng tin cậy (xác nhận cả deterministic + unit test)

- **1.1** chay 1→20: note sống, hard-filter. → **trả lời đúng câu hỏi gốc: CÓ nhớ cross-session cho scope được hỗ trợ.**
- **2.3** phân biệt temp/permanent: "giảm cân" (không trigger) ko lưu; "chay trường" durable.
- **3.3** nhận diện câu đùa: "ăn cay chết mất" → ko tạo hard constraint (đúng).
- **4.1/4.2** isolation: context tạm thời / pref người thứ 3 → ko leak vào profile.

## Khuyến nghị (theo ưu tiên)

1. **Mở rộng catalog** (P0, safety): thêm `peanut` (` ConstraintDef("peanut","đậu phộng",("đậu phộng","lạc","peanut"),"avoid")`), `dairy`, `gluten`, `organ_meat`, `spice`. Thêm 1 hàng catalog = tự enforce, không sửa loader. Giải quyết 3.1/3.2/1.2/1.3/1.4/8.1.
2. **Sửa note mâu thuẫn** (P1): khi extract gặp câu chứa `_RECOVERY_RE`/rút lại → **xóa note allergy cũ** thay vì append. Hoặc lưu allergy vào field structured riêng (có timestamp) để reconcile. Giải quyết 3.4/7.2.
3. **TTL cho constraint tạm thời** (P1): thêm `expires_at` vào note/constraint; `build_active_constraints` bỏ qua note hết hạn. Giải quyết 6.3.
4. **Tăng NOTES_CAP hoặc tách store allergy** (P2): allergy nên vô cap (safety), note thường giữ FIFO. Giảm rủi ro 6.1.
5. **Granularity seafood** (P2): tách `shrimp` riêng để 2.2 đúng. Normalize viết tắt ("HS"→"hải sản") ở `text_norm` để 8.3 bắt được.
6. **Validate live** sau khi refresh FPT_API_KEY + restart backend (xong chạy lại `scripts/memory_retention_eval.py` đã cover; bổ sung `/chat` E2E cho 1.1/3.1/7.2 khi key sống).

## File tạo
- `backend/scripts/memory_retention_eval.py` — harness chính (28 case).
- `backend/scripts/memory_fifo_db_probe.py` — probe FIFO (DB auth fail trong env này, code đúng).
- `plans/reports/memory-eval-260813-1038-results.json` — detail JSON từng case.

## Câu hỏi chưa giải quyết
1. **Layer-1 structured profile** (cuisine/spice/budget/ambience) viết qua LLM `propose_profile_delta` + user confirm — 10 case "LLM-dep" cần live test để verdict (yêu cầu FPT key sống + data merchant). Harness KHÔNG verdict được phần này deterministic.
2. Multi-hop (5.1: conjunction Italian+budget+outdoor qua ranking) — cần DB merchant thật + ranking để xác nhận kết quả có thỏa cả 3 fact.
3. 7.3 `clear_memory` route `/users/{id}/memory/clear` tồn tại — nhưng có được LLM trigger tự động khi user nói "xóa hết lịch sử" không? Cần test intent flow.
4. ~~DB auth mismatch~~ → RESOLVED: root cause = native `postgresql-x64-18` service tranh port 5432 với Docker (host trúng native). Fix: reset pass user postgres trong Docker + stop service native. Live E2E chạy OK (1625 merchant).
5. Service native `postgresql-x64-18` đang **stop** (StartType=Automatic → sẽ tự lại sau reboot). Nên đặt StartType=Manual hoặc disable nếu chỉ dùng Docker DB.
