# Catalog Enforcement Expansion — Verdict Report (260820)

> Đóng proposal #2 (audit 260820): memory-eval khuyến nghị #1 + #5. Commit `dd18a30`.

## Kết quả chính

| Chỉ số | Trước | Sau |
|---|---|---|
| Catalog scopes | 2 (seafood, chay) | 7 (+shrimp, peanut, dairy, gluten, organ_meat) |
| Memory eval deterministic | 16 PASS + 2 PARTIAL | **18/18 PASS (100%)** |
| Case 2.2 (tôm vs hải sản) | PARTIAL — over-exclude | PASS — shrimp riêng, seafood sống |
| Case 3.2 (3 constraint chồng) | PARTIAL — spice không tách | PASS — chay + peanut đều hard |
| Case 8.3 (viết tắt HS) | PARTIAL (matcher không giải mã) | PASS — expansion HS→hải sản |
| Unit tests | 327 | **340** (+13 mới) |

## Thiết kế then chốt (data-driven, không chọn term mù)

1. **Term selection theo corpus probe** (1625 merchants + 99k menu items):
   - `peanut`: bỏ "lạc" — fold `lac` đụng "lắc phô mai" (~1000 dish false) + tên đường Lạc Trung/Lạc Long Quân. Giữ "đậu phộng/peanut" (55 dish thật).
   - `organ_meat`: bỏ "lòng" — đụng trà Ô long + Hoàng Long (20 hit phần lớn false). Giữ "nội tạng/tiết canh/trứng vịt lộn".
   - `dairy`: "sữa" giữ nhưng làm homophone-canon (đòi dấu — "sửa xe" không fire).
   - `gluten`: chỉ phrase ("mì Ý", "spaghetti") — bỏ bare "mì" (quá rộng).

2. **Scope hierarchy 1 chiều**: `seafood ⊃ shrimp`. "Dị ứng hải sản" (chung) vẫn chặn quán tôm
   (an toàn y tế); "dị ứng tôm" (riêng) không chặn seafood khác — đúng intent 2.2.

3. **Allergy zone position-aware**: allergen phải nằm GIỮA verb và marker tương phản đầu tiên
   ("nhưng/vẫn thích/mà vẫn"). Hai dạng câu đều đúng:
   - "thích hải sản... nhưng dị ứng tôm" → chỉ shrimp
   - "dị ứng tôm nhưng vẫn thích hải sản" → chỉ shrimp (fix sau E2E — tail leak)

4. **Third-party tighten**: "gia đình" trần trụi = context, không suspend diet (3.2: user tự ăn
   trưa thứ Hai chay); chỉ cụm "hộ/cho ai/thay" mới suspend.

## Fix bổ sung tìm thấy khi test

- **Verb regex thiếu** "không uống được / không ăn X" (dạng declare dairy/organ tự nhiên) — thêm.
- **normalize_abbreviations lowercase cả câu** → phá health-note nguyên văn — sửa trả text
  nguyên khi không có abbreviation.

## Verify

- 340 unit tests pass (`pytest -m "not llm_required and not db_required"`)
- `memory_metrics.py`: 18/18 deterministic PASS, 0 PARTIAL, 0 FAIL
- Live E2E `/chat` (:8000, reload):
  - Peanut → buffet: kết quả bị hard-filter sạch + answer giải thích "bị loại vì ràng buộc đậu phộng" ✅
  - Shrimp-only → "hải sản gần Cầu Giấy": 3 kết quả (Bún Thái Hải Sản, Hadu Y...), **0 quán tôm**, không confirm-gate sai ✅

## Artifacts
- `plans/reports/memory-metrics-260813-results.json` (regenerated với verdict mới)

## Unresolved
1. Spice vẫn soft-only (warn, không hard-filter) — cố ý: "cay" là mức độ, hard-filter sẽ over-exclude
   mọi quán không có metadata spice. Nâng cấp cần taste_tags coverage trong DB.
2. FE chips constraint hiển thị label mới tự động từ `labels()` — không cần sửa FE, nhưng nên
   eyeball Preferences Center với allergen mới.
3. GT-eval multirun nên chạy lại 1 lần sau batch này để xác nhận không regression (đề xuất: gộp
   với lần chạy sau proposal #4).
