# Agent Performance Optimization - Gradual Implementation with Quality Validation

**Date:** 2026-07-24  
**Status:** In Progress  
**Risk Level:** Medium (quality validation required at each step)

---

## Overview

Implement CrewAI performance optimizations gradually, validating quality at each step. **Stop immediately if quality drops.**

### Optimizations (in priority order)

| Phase | Optimization | Expected Speed Gain | Quality Risk |
|-------|-------------|---------------------|--------------|
| 1 | CrewAI config flags | 10-20% | Very Low |
| 2 | Tool output filtering | 40-70% | Low |
| 3 | Semantic compression | 50-80% | Medium |
| 4 | Context caching | 20-40% | Very Low |

---

## Quality Baseline

**Current behavior (no optimizations):**
- All agents get full context
- Tools return complete objects
- No caching
- No compression

**Quality metrics:**
1. Structured output completeness (SearchTaskOutput fields)
2. Answer relevance (explanation quality)
3. Merchant ranking accuracy
4. No hallucinations

---

## Phase 1: CrewAI Config Flags (Very Low Risk)

### Changes
**File:** `backend/agents/customer/customer_crew.py`

```python
# In crew() method:
return Crew(
    agents=[...],
    tasks=[...],
    process=Process.hierarchical,
    manager_agent=self.customer_coordinator(),
    verbose=True,
    # ADD:
    cache=True,           # Cache tool results
    memory=True,          # Enable conversation memory
    respect_context_window=True,  # Prevent token overflow
)
```

**File:** `backend/agents/customer/config/agents.yaml`

Update each agent with:
```yaml
restaurant_search:
  # ... existing ...
  allow_delegation: false
  max_iter: 3
  max_execution_time: 300
  # ADD:
  respect_context_window: true
  cache: true
```

### Quality Validation
- Structured outputs still valid
- Answer quality same
- Merchant candidates still relevant

### Rollback Plan
Remove added flags if issues detected.

---

## Phase 2: Tool Output Filtering (Low Risk)

### Changes
**File:** `backend/agents/tool_adapter.py`

Add output size check in `RegistryTool._run()`:

```python
def _run(self, **kwargs):
    result = self.reg_tool.fn(**kwargs)
    
    # Filter large outputs to prevent context overload
    if isinstance(result, dict):
        result_str = json.dumps(result, ensure_ascii=False, default=str)
        if len(result_str) > 3000:  # 3k token threshold
            # Keep essential keys only
            result = self._filter_essential_fields(result, self.reg_tool.spec.name)
    
    return json.dumps(result, ensure_ascii=False, default=str)

def _filter_essential_fields(self, data: dict, tool_name: str) -> dict:
    """Keep only fields essential for agent decision-making."""
    ESSENTIAL_FIELDS = {
        "merchant_search": ["merchant_id", "name", "cuisine", "rating", "price_range", "distance_km"],
        "nearby_merchant_search": ["merchant_id", "name", "distance_km", "rating"],
        "get_merchant_profile": ["merchant_id", "name", "description", "address", "hours"],
        "get_user_profile": ["user_id", "preferences", "dietary_restrictions"],
        "get_session_candidates": ["merchant_id", "name", "match_score"],
    }
    
    allowed = ESSENTIAL_FIELDS.get(tool_name, list(data.keys())[:10])  # Max 10 fields
    return {k: v for k, v in data.items() if k in allowed and k in data}
```

### Quality Validation
- Filtered results still contain decision-critical data
- Agent can still rank/recommend properly
- No "field not found" errors

### Rollback Plan
Remove filtering logic if agent performance degrades.

---

## Phase 3: Semantic Compression (Medium Risk)

### Changes
**File:** `backend/agents/compression.py` (NEW)

```python
"""Semantic compression for verbose fields without losing decision-relevant info."""

MAX_LENGTHS = {
    "description": 150,      # Merchant description
    "address": 80,           # Full address
    "hours": 100,            # Operating hours
    "menu_highlights": 200,  # Menu items
}

def compress_field(field_name: str, value: str) -> str:
    """Compress a field value while preserving semantic meaning."""
    if not isinstance(value, str):
        return str(value)
    
    max_len = MAX_LENGTHS.get(field_name, 100)
    if len(value) <= max_len:
        return value
    
    # Truncate at word boundary
    truncated = value[:max_len]
    last_space = truncated.rfind(" ")
    if last_space > max_len * 0.8:  # If we can keep most of a word
        return truncated[:last_space] + "..."
    return truncated + "..."

def compress_merchant(data: dict) -> dict:
    """Compress verbose merchant fields."""
    compressed = {}
    for k, v in data.items():
        if k in MAX_LENGTHS:
            compressed[k] = compress_field(k, str(v))
        else:
            compressed[k] = v
    return compressed
```

**File:** `backend/agents/tool_adapter.py`

Import and use compression:
```python
from agents.compression import compress_merchant

def _run(self, **kwargs):
    result = self.reg_tool.fn(**kwargs)
    
    if isinstance(result, dict):
        result_str = json.dumps(result, ensure_ascii=False, default=str)
        if len(result_str) > 3000:
            result = self._filter_essential_fields(result, self.reg_tool.spec.name)
            # Apply compression to merchant data
            if "merchant" in self.reg_tool.spec.name.lower():
                result = compress_merchant(result)
    
    return json.dumps(result, ensure_ascii=False, default=str)
```

### Quality Validation
- Compressed text still conveys key information
- Agent explanations remain coherent
- No critical info lost

### Rollback Plan
Remove compression if explanations become generic or incomplete.

---

## Phase 4: Context Caching with TTL (Very Low Risk)

### Changes
**File:** `backend/agents/cache.py` (NEW)

```python
"""Simple TTL cache for tool results."""

import time
from functools import wraps
from typing import Any, Callable

_TTL_SECONDS = 300  # 5 minutes
_cache: dict[str, tuple[Any, float]] = {}

def cached(ttl: int = _TTL_SECONDS):
    """Cache decorator with TTL."""
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # Create cache key from function name and args
            key = f"{fn.__name__}:{args}:{kwargs}"
            
            now = time.time()
            if key in _cache:
                result, timestamp = _cache[key]
                if now - timestamp < ttl:
                    return result  # Cache hit
            
            result = fn(*args, **kwargs)
            _cache[key] = (result, now)
            return result
        return wrapper
    return decorator
```

Apply to expensive tools in `backend/tools/customer/merchant_tools.py`:
```python
from agents.cache import cached

@cached(ttl=300)
def merchant_search(...) -> dict:
    # Existing implementation
    ...
```

### Quality Validation
- Cache doesn't return stale data
- Same results for identical queries within TTL

### Rollback Plan
Remove decorator if stale data issues.

---

## Testing Strategy

### Baseline Test
```python
# scripts/benchmark_agent_performance.py
def measure_baseline():
    queries = [
        "phở gần đây",
        "quán cà phê giá rẻ quận 1",
        "nhà hàng ăn cơm gia đình",
    ]
    
    for query in queries:
        start = time.perf_counter()
        result = customer_flow.search_restaurants(query=query, ...)
        duration = time.perf_counter() - start
        
        print(f"Query: {query}")
        print(f"  Duration: {duration:.2f}s")
        print(f"  Results: {len(result.results)}")
        print(f"  Answer length: {len(result.answer)}")
```

### Quality Check After Each Phase
1. Run same queries
2. Compare duration (should decrease)
3. Compare result count (should stay same)
4. Compare answer quality (should not degrade)

---

## Success Criteria

### Phase passes if:
- ✅ Duration reduced by expected amount
- ✅ Same number of merchant results
- ✅ Answer quality maintained (manual review)
- ✅ No new errors/hallucinations

### Phase fails if:
- ❌ Agent produces fewer results
- ❌ Answer becomes generic/vague
- ❌ Structured output missing fields
- ❌ Agent makes incorrect recommendations

---

## Timeline

| Phase | Implementation | Testing | Decision |
|-------|---------------|---------|----------|
| 1 | 15 min | 10 min | Continue/Stop |
| 2 | 30 min | 15 min | Continue/Stop |
| 3 | 45 min | 20 min | Continue/Stop |
| 4 | 30 min | 15 min | Finalize |

**Total:** ~3 hours if all phases pass

---

## Rollback Strategy

If any phase fails quality check:
1. Revert changes for that phase
2. Document findings
3. Decide: skip or adjust approach
4. Continue to next phase only if independent

---

## Unresolved Questions

1. **What is "acceptable" quality degradation?** → None. Stop if ANY drop detected.
2. **How to measure answer quality objectively?** → Manual review + structured output validation.
3. **Cache TTL appropriate for merchant data?** → Start with 5min, adjust if stale.
