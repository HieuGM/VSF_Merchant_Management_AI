# Stable-Fail Fixes — 5 GT Cases (260820)

> Đóng proposal #4. Commit `1ffe891`. Module mới `backend/flows/followup_resolution.py`.

## Kết quả per-case (live E2E /chat sau fix)

| Case | Trước (3-run stable) | Sau |
|---|---|---|
| TC-41 'Cái đầu tiên đó' | FAIL — "chưa gợi ý quán nào" vô căn cứ | ✅ Resolve ordinal → đúng quán đầu của turn trước, answer grounded (rating/giá/menu từ profile thật) |
| TC-25 'Quán này có ổn không?' | FAIL — trả list quán MỚI không liên quan | ✅ Nhớ context turn trước; prior data-thin → honest hỏi lại (không bịa) |
| TC-39 'Sao chỉ 1 quán...' | FAIL — **bịa 3 quán** phủ nhận tiền đề | ✅ Nhờ lại đúng tiền đề: "lượt tìm lẩu hải sản Hà Đông chưa có kết quả" |
| TC-10 'Rẻ hơn nữa...' | FAIL — hỏi lại vị trí dù đã có | ✅ Refine giá deterministic (40k→30k), trả 3 quán kèm giá, chỉ cheapest |
| TC-28 phủ định kép | FAIL — search literal 'không cay không chiên' = 0 | ✅ Strip negation khỏi search query + post-filter cay/chiên; 3 quán sạch + answer kể cả caveat giá |

## 3 seam deterministic (module mới `followup_resolution.py`, 18 unit test)

1. **Bare-referent follow-up**: anaphor KHÔNG cần từ thuộc tính (thêm 'ổn không/thế nào/tại sao/rẻ hơn' vào attr regex + rule riêng cho câu ngắn thuần referent) → skip fresh search, resolve theo prior results. Guard: food-token trong query vẫn đi search; câu dài >8 token không coi là bare.
2. **Cheaper-refinement cap**: 'rẻ hơn' + prior user turn có mức giá → max_price = 75% (floor 15k) injected thẳng vào query_search.
3. **Negation**: `strip_negations` bỏ mệnh đề 'không (phải) (đồ) X' khỏi query search (cả dạng có dấu/không dấu) + `carries_negated_term` post-filter theo name/cuisine/taste_tags.

## 2 latent bug tìm thấy trên đường (quan trọng hơn case!)

1. **User mới mất turn đầu**: `_ensure_session` INSERT `chat_sessions(user_id=...)` FK-violate khi `user_profiles` chưa có row — row đó chỉ được tạo bởi `maybe_persist` (no-op với tin nhắn thường). Nghĩa là: **mọi user mới gửi tin nhắn đầu tiên không khai báo gì → turn không persist → anaphora turn sau mất context**. Ăn khớp vì sao GT eval (seed profile trước) không thấy, E2E thật thấy. Fix: ensure minimal profile row trong `_ensure_session`.
2. **`max_execution_time` 15/20s quá thấp**: FPT slow-window (~27s latency) giết task **kể cả khi task đã trả Final Answer thành công** (CrewAI discard kết quả). Nâng 45/60s.

## Verify

- 358 unit tests pass (18 mới trong `test_followup_resolution.py`)
- E2E từng case qua `/chat` thật (script `scripts/e2e-stable-fail-cases.py`, tự poll FPT đến khi <8s)
- Không regression: full suite xanh; các guard cũ (OOD/clarify/sparse-food) không đổi

## Còn treo

1. **TC-41 residual**: turn-1 search 'phở Hà Nội' tự chọn quán bánh mì (ranking/query chọn món của search LLM) — ordinal resolution đúng nhưng referent gốc đã lệch. Thuộc vấn đề ranking riêng, không phải anaphora.
2. GT-eval multirun nên chạy lại để cập nhật band 62-79% (đề xuất: để riêng một buổi, FPT phải ổn định — sáng nay 2 slow-window).
3. `max_execution_time` 45/60s làm chậm worst-case latency khi FPT treo thật — cân nhắc retry/backoff ở level LLM sau này (YAGNI lúc này).
