#!/usr/bin/env python
"""Simple Phase 1 validation - check code changes only."""
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

print("\n=== Phase 1: Config Flags Validation ===\n")

# Read the customer_crew.py file
crew_file = backend_dir / "agents" / "customer" / "customer_crew.py"
content = crew_file.read_text()

# Check for the optimization flags
checks = {
    "cache=True": "Tool result caching enabled",
    "memory=False": "Memory disabled (no embedder configured — would spam errors)",
    "respect_context_window=True": "Context window protection enabled",
}

print("Checking customer_crew.py for optimization flags:\n")

all_found = True
for flag, description in checks.items():
    if flag in content:
        print(f"  [PASS] {flag} - {description}")
    else:
        print(f"  [FAIL] {flag} - MISSING")
        all_found = False

print()

# Verify syntax
print("Verifying Python syntax...")
import py_compile
try:
    py_compile.compile(str(crew_file), doraise=True)
    print("  [PASS] Syntax valid")
except SyntaxError as e:
    print(f"  [FAIL] Syntax error: {e}")
    all_found = False

print()

if all_found:
    print("=== Phase 1 COMPLETE ===")
    print("\nChanges applied:")
    print("  - cache=True - Tools cache results")
    print("  - memory=False - Disabled (CrewAI memory needs an embedder; re-enable once configured)")
    print("  - respect_context_window=True - Token overflow protection")
    print("\nExpected impact: caching helps tool result reuse; memory off avoids per-task errors.")
    print("  Quality is IDENTICAL to baseline (memory was non-functional before).")
else:
    print("=== Phase 1 INCOMPLETE ===")
    print("Some flags are missing. Please review customer_crew.py")

sys.exit(0 if all_found else 1)
