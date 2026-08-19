from __future__ import annotations

from pathlib import Path
import pytest


def test_no_legacy_routing_symbols_in_runtime_source():
    backend_root = Path(__file__).resolve().parents[2]
    forbidden_symbols = (
        "InputPreparationService",
        "decide_route(",
        "query_decision(",
        "NativeMerchantAdvisorCrew",
        "merchant_execution_mode",
    )
    for py_file in backend_root.rglob("*.py"):
        rel_str = str(py_file.relative_to(backend_root))
        if rel_str.startswith("tests/") or rel_str.startswith("evals/") or "alembic" in rel_str or ".venv" in rel_str:
            continue
        content = py_file.read_text(encoding="utf-8")
        for forbidden in forbidden_symbols:
            assert forbidden not in content, f"Found forbidden '{forbidden}' in {rel_str}"
