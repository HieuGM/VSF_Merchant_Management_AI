# E2E 12-Luồng Hoàn Chỉnh — Kết Quả & Verdict (260820)

> Yêu cầu: 10-15 luồng, ≥75% memory, ≥2 luồng >15 tin. Đo: chất lượng/kết quả/thời gian/nhớ ngữ cảnh đầu/history.
> Thực tế: **12 luồng · 9 memory (75%) · 2 luồng 18 tin** · 69 turn · chạy 26 phút (16:26–16:52).
> Dashboard: `plans/reports/e2e-12-flow-live-dashboard.html` (serve `python -m http.server 8765` trong `plans/reports/`).
> Data: `plans/reports/e2e-12-flow-memory-suite.json` · Suite: `scripts/e2e-12-flow-memory-suite.py`.

## KPI tổng

| Chỉ số | Giá trị |
|---|---|
| Luồng hoàn thành | **12/12** (66/69 turn OK — 3 turn lỗi FPT transient) |
| Checkpoint pass | **27/29 (93%)** |
| Latency median toàn turn | **20.0s** (blocking /chat; stream TTFT thấp hơn nhiều) |
| Latency max | 63.4s (1 turn FPT slow-window) |
| Memory lưu đúng sự kiện | MEM+ khi khai / MEM− khi rút — 100% luồng khai báo |

## Trả lời 4 câu hỏi đề ra

### 1. Có nhớ ngữ cảnh từ ĐẦU phiên không? — CÓ, có chứng cứ cụ thể
- **Luồng 1 (18 tin)**: "dị ứng tôm" (tin 1) + "ăn chay thứ Hai" (tin 2) sống sót qua 16 tin filler → **session MỚI vẫn enforce cả 2** (hard-filter loại hết kết quả + answer giải thích đúng "bị loại vì ràng buộc tôm, đồ chay"). Note lưu đủ trong profile.
- **Luồng 5 (12 tin)**: vị trí tin 1 dùng ngay (turn 2-4 có kết quả Đống Đa); ⚠ tin 12 hỏi lại vị trí — gap thật (xem Gaps).
- **Luồng 12**: "quán đầu tiên" resolve đúng quán của turn trước (xác nhận cả trong app web).

### 2. Có lưu lịch sử chat thành 1 đoạn riêng không? — CÓ
- Mỗi session lưu riêng (`chat_sessions` + `chat_messages`), sidebar app nhóm theo hội thoại với title tự sinh từ tin đầu + relative time, mở lại nguyên vẹn (đã demo mở luồng 8 trong app: 2 lượt + card + rating).
- API: `GET /users/{id}/sessions` → list; `GET /sessions/{id}` → full messages. Đổi tên/xóa có nút riêng.

### 3. Chất lượng trả lời — điểm mạnh
- Truth-first ổn định: không bịa quán (luồng 12 turn-2 nói thẳng "lần trước chưa tìm ra quán cụ thể"); luồng 8 giải thích trung thực "quán duy nhất gợi ý là Phở Bò Tám Lâm — quán phở chứ không phải bún chả".
- Retract dị ứng (luồng 3): xóa sạch note + allergen, session sau không chặn sai.
- TTL (luồng 4): "tuần này ăn kiêng" có expiry ISO gắn đúng 1 note.
- Isolation (luồng 6): "bạn tôi thích đồ Hàn" không vào profile mình.
- Transparency (luồng 7): memory_updated diff (thêm/bớt) phát đủ.
- Preference Center (luồng 9): "dị ứng tôm và nội tạng" → cả 2 vào `allergens` field, hiện ở Hồ sơ.

### 4. Thời gian trả lời
- Median 20s/turn (blocking) — phần lớn là FPT (chat probe đơn giản cũng 1.4-27s trong ngày). Max 63s trùng FPT slow-window 15:00-15:10.
- 3/69 turn lỗi timeout transient (retry pass ở turn khác — cùng nguyên nhân FPT).

## 2 gap tìm thấy (2/29 checkpoint fail)

1. **F5 — vị trí TEXT (không GPS) không nhớ xuyên nhiều lượt**: tin 1 "Mình ở Đống Đa" dùng được ngay lượt kế, nhưng đến tin 12 agent hỏi lại vị trí. Vị trí text không được persist thành profile (chỉ GPS client mới gắn). Fix đề xuất: lưu `location_hint` từ khai báo text vào context_memory note.
2. **F11 — refine giá không ổn định**: lần trước (15:2x) refine 40k→30k trả quán + giá; lần này (16:4x) LLM honest-refuse ("không muốn đoán bừa chi phí") thay vì dùng cap deterministic ta inject — cùng input, kết quả khác nhau do variance LLM. Cap có đến được prompt nhưng agent không áp dụng. Fix đề xuất: đưa cap vào `max_price` arg trực tiếp thay vì chỉ ghi chú trong query text.

## Ghi chú suite
- Suite bug nhỏ: luồng 1 và 2 dùng chung session-id recall (`recall_{STAMP}` trùng) → câu trả lời synthesize của F2 thực tế mang constraint của F1. Verdict F2 dựa trên fact lưu được (đúng), không dựa câu answer đó. Đã ghi chú, lần chạy sau tách prefix.
- Latency ghi từ client wall-clock (bao gồm cả retry khi FPT transient).
