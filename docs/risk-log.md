# Risk Log — Synthetic Data & Profile Pipeline

Cập nhật: 2026-07-21. Phạm vi: kịch bản weak-merchant "câu chuyện 2 vế" (strength pins) + pipeline `operational.jsonl → build_profiles.py → import_dataset.py`.

Severity (S) / Likelihood (L): 🔴 cao · 🟡 vừa · 🟢 thấp.

| # | Rủi ro | S | L | Phương án giảm thiểu |
|---|---|---|---|---|
| R1 | **68814 (weak_service): price_level 0.49 < service 0.58** → diagnosis nêu sai điểm yếu chính (giá thay vì dịch vụ) | 🟡 | 🔴 (đang xảy ra) | Agent nêu **top-2** weakness (service vẫn lọt); hoặc exclude price_level khỏi "weak dim"; hoặc strengthen service khi cần demo chuẩn. Đã **chấp nhận** (giá 51k vs peer median 38k = 1.34× là tín hiệu thật) |
| R2 | **price_level peer-based dễ vỡ** — phụ thuộc median cùng cuisine; đổi dataset (thêm/bớt merchant) → score dao động, lật thứ hạng weak dim của **bất kỳ** hero | 🔴 | 🟡 | Snapshot `peer_median` lúc build; thêm assert invariant vào `validate_profiles.py`; cảnh báo khi ratio dao động > ngưỡng |
| R3 | **Không có invariant tự động** "intended weak = lowest" — chỉ verify tay, dễ trôi khi rebuild sau | 🔴 | 🟡 | Thêm check đọc `SCENARIO_ASSIGN` vào `validate_profiles.py`; fail nếu lệch |
| R4 | **Strength pin numeric nhưng text (complaints/reviews) không regen** — review cũ có thể mâu thuẫn (vd weak_delivery lại có review khen giao nhanh) | 🟡 | 🟡 | Grep text data 5 merchant tìm mâu thuẫn với strength; regen filled_reviews nếu lệch |
| R5 | **Late-penalty double-count** waiting_time (trừ cả late complaint) — tạo điểm yếu phụ giả ở weak_delivery/slow_prep | 🟡 | 🟡 | Fix pending tuần-2 (bỏ `− 0.03·late_complaint_count` khỏi `waiting_time`); hiện đã verify không lật lowest |
| R6 | **`apply_ops_override` cộng dồn `avg_delivery_add`** — chạy 2 lần trên cùng record → delivery_minutes sai lệch tích lũy | 🟡 | 🟡 | Luôn regen từ base record, KHÔNG apply lên record đã override; hoặc set tuyệt đối thay vì cộng |
| R7 | **Import TRUNCATE 7 bảng rồi insert** — fail giữa chừng → mất data | 🔴 | 🟢 | Bọc transaction (rollback nếu lỗi); dry-run trước; backup DB trước import lớn |
| R8 | **Strength pin nâng `overall_score` hero yếu** → đổi tier/ranking, ảnh hưởng competitor demo (UC-03, cụm 10344) | 🟡 | 🟡 | Kiểm `overall_score` + tier 5 hero sau rebuild; xác nhận thứ hạng cụm competitor không đảo |
| R9 | **Regen quên scenario** — chạy lại `generate_operational.py` không qua `apply_ops_override` → mất pins | 🟡 | 🟢 | Scenario-driven đã nhúng trong generator; giữ `SCENARIO_ASSIGN` là single source; smoke test sau regen |
| R10 | **Encoding cp1252 (Windows)** — print tiếng Việt crash nếu thiếu `PYTHONIOENCODING=utf-8` | 🟢 | 🟡 | Set env trong runbook; hoặc ép `sys.stdout.reconfigure(encoding="utf-8")` đầu script |

## Ưu tiên xử lý

1. **R3 + R2** — thêm invariant scenario vào `validate_profiles.py` (chốt chặn rẻ nhất, chặn regression toàn bộ hero).
2. **R7** — transaction wrap cho import.
3. **R4** — text consistency với strength pins.

## Liên quan

- `scripts/synth/scenarios.py` — `SCENARIO_ASSIGN`, `SCENARIOS` (strength pins), `apply_ops_override`.
- `scripts/profile/validate_profiles.py` — nơi nên thêm invariant R2/R3.
- `docs/scoring-methodology.md` — Decision log (peer-based price_level, waiting-time late-penalty).
