# Code Review Report: 3 Critical Bug Fixes

**Date:** 2026-07-22
**Files Reviewed:**
- `backend/tests/contract/test_api_stubs.py`
- `backend/routes/merchant_search_routes.py`
- `backend/repositories/merchant_repository.py`
- `backend/tests/unit/test_merchant_search_validation.py`

**Focus:** Security vulnerabilities, correctness, edge cases

---

## Fix 1: Test Expectation Mismatch

**File:** `backend/tests/contract/test_api_stubs.py`

**Changes:**
- Removed `/api/v1/merchants/search` from stub routes list (was expecting 501)
- Added `test_merchant_search_endpoint_implemented()` to verify 200 response

**Assessment:** ✅ **CORRECT**

### Analysis
The new test properly validates the implemented endpoint:
- Verifies 200 status code (not 501 stub)
- Validates response structure: `trace_id`, `merchants`, `cache_status`
- Clear, focused test purpose

### Issues Found
None. Test is adequate and correctly implemented.

---

## Fix 2: Input Validation

**File:** `backend/routes/merchant_search_routes.py`

**Changes:**
- Added Pydantic validators to `MerchantSearchRequest` model and Query parameters:
  - `lat`: `ge=-90, le=90` (latitude bounds)
  - `lng`: `ge=-180, le=180` (longitude bounds)
  - `radius_km`: `gt=0, le=500` (positive, max 500km)
  - `limit`: `ge=1, le=100` (results limit)

**Assessment:** ✅ **CORRECT** (with 1 minor observation)

### Analysis

#### Validators Applied Correctly
Validators are properly applied in both locations:
1. **MerchantSearchRequest model** (lines 25-28) - for potential future use
2. **Query parameters** (lines 47-50) - actual route implementation

**Validator correctness:**
- Latitude (-90 to 90): ✅ Correct range
- Longitude (-180 to 180): ✅ Correct range
- Radius (0 < r ≤ 500): ✅ Reasonable bounds, prevents abuse
- Limit (1-100): ✅ Prevents excessive result sets

#### Test Coverage
The `test_merchant_search_validation.py` file provides comprehensive test coverage:
- Invalid lat/lng values
- Negative radius
- Radius exceeding max
- Missing required parameters (nearby endpoint)
- Both `/search` and `/nearby` endpoints tested

**Tests are:** ✅ Thorough and well-structured

### Issues Found

#### ⚠️ MINOR: Missing `budget` Parameter Validation

**Location:** `merchant_search_routes.py:46`
```python
budget: str | None = Query(None, description="Budget level")
```

**Issue:** No validation that `budget` must be one of: `student`, `standard`, `premium`

**Impact:** Invalid values are silently ignored (not security risk, data quality issue)

**Analysis:**
- In `customer_flow._budget_to_price_range()`: `budget_ranges.get(budget.lower(), (None, None))`
- Invalid budget → returns `(None, None)` → no price filtering applied
- No error raised, user gets unfiltered results

**Recommendation (LOW priority):**
```python
from enum import Enum

class BudgetLevel(str, Enum):
    STUDENT = "student"
    STANDARD = "standard"
    PREMIUM = "premium"

budget: BudgetLevel | None = Query(None, description="Budget level")
```

**Severity:** LOW - Not a security issue, just poor user experience for invalid input

---

## Fix 3: SQL Injection Protection

**File:** `backend/repositories/merchant_repository.py`

**Changes:**
- Escaped LIKE special characters in query parameter:
  ```python
  escaped_query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
  ```
- Used `escape="\\"` parameter in `ilike()` calls

**Assessment:** ✅ **SECURE** (verified no other LIKE vulnerabilities exist)

### Analysis

#### Escaping Implementation (lines 68-77)
```python
# Escape backslash first, then % and _ to prevent SQL injection
escaped_query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
query_pattern = f"%{escaped_query}%"

conditions.append(
    or_(
        Merchant.name.ilike(query_pattern, escape="\\"),
        Merchant.cuisine.ilike(query_pattern, escape="\\"),
    )
)
```

**Correctness analysis:**

1. **Escape order is correct:** ✅
   - Backslash escaped first (prevent double-escaping)
   - Then wildcards `%` and `_`
   - Final pattern: `%escaped_query%`

2. **Escape character consistency:** ✅
   - Used `escape="\\"` in both `ilike()` calls
   - Matches the escape character used in replace operations

3. **Special characters handled:** ✅
   - `\` (backslash) → Prevents escape sequence injection
   - `%` (percent) → Prevents wildcard matching
   - `_` (underscore) → Prevents single-char wildcard

#### Test Coverage
Tests in `test_merchant_search_validation.py:61-93` cover:
- Special characters: `\`, `%`, `_`
- Mixed special chars: `test%_%_\%_%`
- SQL injection attempt: `'; DROP TABLE--`
- Wildcard in search term: `pho%20restaurant`

**Test expectation:**
```python
assert resp.status_code in (200, 404), f"Failed for query: {query}"
```
Should return 200 (with empty results) or 404, NOT 500 error.

**Tests are:** ✅ Comprehensive and correct

### Verification: No Other LIKE Vulnerabilities

**Searched:** All `.ilike()` and `.like()` calls in codebase

**Result:** Only 2 occurrences found, both in `merchant_repository.py:74-75`
Both properly escaped with `escape="\\"`

✅ **No remaining SQL injection vulnerabilities via LIKE clauses**

---

## Edge Case Testing

Additional edge cases considered:

### Test Coverage Gaps

#### 1. Unicode/International Characters
**Not tested:** Unicode strings, emoji, accented characters
**Impact:** LOW - SQLAlchemy should handle UTF-8 correctly
**Recommendation:** Optional test with Vietnamese characters (given Vietnam context)

#### 2. Very Long Query Strings
**Not tested:** Query length limits
**Impact:** LOW - Pydantic/SQLAlchemy have reasonable defaults
**Recommendation:** Consider max_length validator if concerned about DoS

#### 3. NULL/Empty Strings
**Not explicitly tested:** Empty query parameter behavior
**Impact:** LOW - Code handles `if query:` condition correctly (line 67)
**Observation:** Empty string → condition false → no LIKE query → safe

#### 4. Numeric Edge Cases
**Tested:** lat=91, lng=181, radius=-1, radius=501
**Not tested:** Boundary values exactly at limits (lat=90, lng=180, radius=500)
**Impact:** LOW - Pydantic validates boundaries correctly (inclusive)
**Observation:** Validators use `ge`/`le` (inclusive), so 90, 180, 500 are valid

---

## Positive Observations

1. **Comprehensive test coverage** for input validation edge cases
2. **Correct SQL escaping** - prevents injection attacks
3. **Consistent validation** across model and query parameters
4. **Clear test intent** - well-named test functions with docstrings
5. **Proper HTTP status expectations** - 422 for validation errors, 200 for success
6. **Security-first approach** - LIKE escaping applied correctly

---

## Code Quality Assessment

| Aspect | Rating | Notes |
|--------|--------|-------|
| **Security** | ✅ Excellent | SQL injection properly prevented |
| **Correctness** | ✅ Good | Validators correct, minor budget gap |
| **Test Coverage** | ✅ Good | Comprehensive edge case testing |
| **Readability** | ✅ Excellent | Clear, well-documented code |
| **Maintainability** | ✅ Good | Consistent patterns, easy to extend |

---

## Summary of Issues

| ID | Severity | Issue | Location | Fix Status |
|----|----------|-------|----------|------------|
| 1 | LOW | Missing `budget` enum validation | `merchant_search_routes.py:46` | Not part of original fixes |

**Total Critical Issues:** 0
**Total High Issues:** 0
**Total Medium Issues:** 0
**Total Low Issues:** 1

---

## Recommendations

### For Immediate Action
**None** - All 3 critical fixes are correctly implemented and secure.

### For Future Consideration (LOW Priority)
1. **Add enum validation for `budget` parameter** to improve user feedback
   ```python
   class BudgetLevel(str, Enum):
       student = "student"
       standard = "standard"
       premium = "premium"
   ```
2. **Optional:** Add test for boundary values (lat=90, lng=180, radius=500)
3. **Optional:** Add test with Vietnamese/Unicode characters (given domain context)

---

## Conclusion

✅ **All 3 critical bug fixes are correctly implemented.**

- **Fix 1 (Test):** Properly validates implemented endpoint
- **Fix 2 (Validation):** Geo validators correct and comprehensive
- **Fix 3 (SQL Injection):** Escaping correct and complete

**Security Assessment:** ✅ No SQL injection vulnerabilities found
**Code Quality:** ✅ High quality, well-tested, maintainable

**The 1 minor issue found (budget validation) is:** Not part of the 3 critical fixes and has LOW severity.

---

## Unresolved Questions

None. All fixes verified as correct and complete.
