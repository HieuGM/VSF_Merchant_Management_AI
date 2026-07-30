# Coordinate Config Fixes Summary

**Date**: 2026-07-24
**Issue**: Coordinate config typos in customer agent task descriptions
**Severity**: LOW - Typos only, no functional impact
**Status**: FIXED

---

## Issue Found

### Typo in `backend/agents/customer/config/tasks.yaml` (lines 36-37)

**Original:**
```yaml
Quyết định tool:
- Nếu lat="" hoặc lat bỏ TRỐNG hoặc lng="" hoặc lng bỏ TRỐNG → DỤNG SỐ merchant_search
- Nếu lat CÓ GIÁ TRỊ (10.xxxxx) VÀ lng CÓ GIÁ TRỊ (106.xxxxx) → DỤNG SỐ nearby_merchant_search
```

**Fixed:**
```yaml
Quyết định tool:
- Nếu lat="" hoặc lat bỏ TRỐNG hoặc lng="" hoặc lng bỏ TRỐNG → DÙNG merchant_search
- Nếu lat CÓ GIÁ TRỊ (10.xxxxx) VÀ lng CÓ GIÁ TRỊ (106.xxxxx) → DÙNG nearby_merchant_search
```

**Change**: Corrected typo "DỤNG SỐ" → "DÙNG" (Vietnamese: "USE")

---

## Coordinate Config Rules (Verified)

### Task Selection Logic (`tasks.yaml`)
- `nearby_merchant_search` → CHỈ DÙNG KHI có CẢ HAI: lat KHÁC RỖNG VÀ lng KHÁC RỖNG
- `merchant_search` → Dùng cho TẤT CẢ trường hợp khác
- Tool decision: If `lat=""` or `lat` is empty → use `merchant_search`
- Tool decision: If `lat` has value (10.xxxxx) AND `lng` has value (106.xxxxx) → use `nearby_merchant_search`

### Agent Tool Selection (`agents.yaml`)
- `nearby_merchant_search` → CHỈ dùng khi lat CÓ GIÁ TRỊ VÀ lng CÓ GIÁ TRỊ
- `merchant_search` → Dùng cho TẤT CẢ trường hợp KHÁC
- QUY TẮC VÀNG: Nếu `lat=""` hoặc `lat` bỏ TRỐNG → DÙNG `merchant_search`

---

## Verification Results

### Unit Tests
```
tests/unit/test_customer_crew.py .... 4 passed
tests/unit/test_merchant_search_validation.py .......... 10 passed
```

### Integration Tests
```
tests/integration/test_customer_flow_crew.py .. 2 passed
```

---

## Related Files Verified

| File | Status | Notes |
|------|--------|-------|
| `backend/agents/customer/config/tasks.yaml` | FIXED | Typo corrected |
| `backend/agents/customer/config/agents.yaml` | OK | Rules consistent |
| `backend/tools/customer/merchant_tools.py` | OK | Tool signatures correct |
| `backend/flows/customer_flow.py` | OK | Coordinate handling correct |
| `backend/agents/customer/customer_crew.py` | OK | LLM config fixed previously |

---

## Summary

The coordinate configuration had a minor typo in the Vietnamese language instructions. The typo did not affect functionality since the LLM understands both correct and incorrect spellings, but it has been fixed for correctness and consistency.

**Total issues fixed**: 1 typo
**Tests passing**: All 16 tests related to customer crew and merchant search
**Status**: COMPLETE
