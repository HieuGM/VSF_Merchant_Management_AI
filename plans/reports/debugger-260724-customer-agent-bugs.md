# Customer Agent Bugs Analysis Report

**Date**: 2026-07-24
**Issue**: Customer Agent pipeline has variable declaration and parameter passing bugs
**Severity**: CRITICAL - Tests fail, cannot inject fake LLMs properly

---

## Bug #1: Missing `llm_nim` Parameter in `build_customer_crew`

**Location**: `backend/agents/customer/customer_crew.py:171-176`

### Problem

```python
def build_customer_crew(
    llm_large: LLM | None = None,
    llm_small: LLM | None = None,
) -> Crew:
    """Factory — returns a ready Crew. Pass fake LLMs in tests to avoid network/key."""
    return CustomerDiscoveryCrew(llm_large=llm_large, llm_small=llm_small).crew()
```

The `build_customer_crew` function:
- Only accepts `llm_large` and `llm_small` parameters
- Calls `CustomerDiscoveryCrew(llm_large=llm_large, llm_small=llm_small).crew()`
- **MISSING**: Does NOT pass `llm_nim` parameter

### Impact

1. When tests call `build_customer_crew(llm_large=fake_llm_large, llm_small=fake_llm_small)`:
   - `llm_nim` defaults to `None` in `CustomerDiscoveryCrew.__init__`
   - Line 90 executes: `self._llm_nim = llm_nim or _build_nim_llm("small")`
   - This calls `_build_nim_llm("small")` which requires a REAL NVIDIA_NIM_API_KEY
   - Tests fail because they cannot inject fake LLM for the `restaurant_search` agent

2. The `restaurant_search` agent (line 112) uses `self._llm_nim`, but tests cannot control it

### Root Cause

`CustomerDiscoveryCrew.__init__` (lines 79-90) accepts 3 parameters:
```python
def __init__(
    self,
    llm_large: LLM | None = None,
    llm_small: LLM | None = None,
    llm_nim: LLM | None = None,  # <-- This parameter exists
) -> None:
```

But `build_customer_crew` only accepts 2 and doesn't pass `llm_nim`.

---

## Bug #2: Incorrect LLM Assignment Logic

**Location**: `backend/agents/customer/customer_crew.py:87-90`

### Problem

```python
self._llm_large = llm_large or _build_llm("large")
self._llm_small = llm_small or _build_llm("small")
# NIM LLM for search agent (8B model - faster, doesn't need complex reasoning)
self._llm_nim = llm_nim or _build_nim_llm("small")
```

The `or` operator is problematic:
- If `llm_large` is a valid LLM object (truthy), it's used
- If `llm_large` is `None`, `_build_llm("large")` is called
- **BUT**: If `llm_large` is a fake LLM (Mock object), it's truthy, so this works

The real issue is that `_build_nim_llm` is only called when `llm_nim` is falsy.

### Expected Behavior

Tests should be able to inject fake LLMs for all three tiers:
- `llm_large` - for coordinator
- `llm_small` - for preference_reasoning and customer_explanation
- `llm_nim` - for restaurant_search

---

## Bug #3: Test Expectations vs Implementation Mismatch

**Location**: `backend/tests/unit/test_customer_crew.py:25-35`

### Problem

```python
def test_per_agent_llm_tier(fake_llm_large, fake_llm_small):
    _ensure_tools()
    crew = build_customer_crew(llm_large=fake_llm_large, llm_small=fake_llm_small)
    # restaurant_search uses the configured NIM small tier
    search = next(a for a in crew.agents if "Tìm kiếm" in a.role)
    assert "8b" in search.llm.model
```

The test expects to pass only 2 fake LLMs and have everything work, but:
- The test cannot inject a fake NIM LLM
- The `restaurant_search` agent tries to use a real NIM connection

---

## Fixes Required

### Fix #1: Update `build_customer_crew` signature and call

```python
def build_customer_crew(
    llm_large: LLM | None = None,
    llm_small: LLM | None = None,
    llm_nim: LLM | None = None,  # <-- ADD THIS
) -> Crew:
    """Factory — returns a ready Crew. Pass fake LLMs in tests to avoid network/key."""
    return CustomerDiscoveryCrew(
        llm_large=llm_large,
        llm_small=llm_small,
        llm_nim=llm_nim,  # <-- ADD THIS
    ).crew()
```

### Fix #2: Update tests to inject `fake_llm_nim`

```python
def test_crew_builds_without_network(fake_llm_large, fake_llm_small, fake_llm_nim):
    _ensure_tools()
    crew = build_customer_crew(
        llm_large=fake_llm_large,
        llm_small=fake_llm_small,
        llm_nim=fake_llm_nim,  # <-- ADD THIS
    )
    # ... rest of test
```

---

## Summary

| Bug | Location | Issue | Fix |
|-----|----------|-------|-----|
| #1 | `build_customer_crew()` | Missing `llm_nim` parameter | Add parameter and pass it |
| #2 | `build_customer_crew()` call | Not passing `llm_nim` to constructor | Add `llm_nim=llm_nim` |
| #3 | Tests | Cannot inject fake NIM LLM | Add `fake_llm_nim` fixture |

**Critical Path**: `build_customer_crew` → `CustomerDiscoveryCrew.__init__` → `restaurant_search` agent

---

## Fixes Applied

### 1. `backend/agents/customer/customer_crew.py` (line 171-178)
```python
def build_customer_crew(
    llm_large: LLM | None = None,
    llm_small: LLM | None = None,
    llm_nim: LLM | None = None,  # ADDED
) -> Crew:
    """Factory — returns a ready Crew. Pass fake LLMs in tests to avoid network/key."""
    return CustomerDiscoveryCrew(
        llm_large=llm_large,
        llm_small=llm_small,
        llm_nim=llm_nim,  # ADDED
    ).crew()
```

### 2. `backend/tests/conftest.py` (line 41-44)
```python
@pytest.fixture
def fake_llm_nim() -> "FakeLLM":
    """Fake NIM LLM for restaurant_search agent (8B model for speed)."""
    return FakeLLM("openai/meta/llama-3.1-8b-instruct")
```

### 3. `backend/tests/unit/test_customer_crew.py` (all test functions)
Updated all 4 tests to accept and pass `fake_llm_nim`:
- `test_crew_builds_without_network`
- `test_per_agent_llm_tier`
- `test_specialists_do_not_delegate`
- `test_agents_only_have_allowlisted_tools`

---

## Verification

```
======================= 4 passed, 53 warnings in 2.60s ========================
```

All tests pass with the fixes applied. The `build_customer_crew()` function now properly accepts and passes the `llm_nim` parameter, allowing tests to inject fake LLMs for all three tiers.
