"""Search-call instrumentation logger (Path A / phase-02).

Appends one JSON line per ``merchant_search`` / ``nearby_merchant_search`` call to
``logs/search_queries.jsonl``, capturing the LLM-decomposed args + result count + whether
empty. Purpose: a ~1-week recall-gap analysis to justify (or kill) a future vector leg.
The GT gate is structurally blind to recall (``compute_gt_metrics`` is a coordinator-action
metric), so this log is the instrument that surfaces REAL recall gaps the GT suite cannot.

PURE LOGGING — no ranking / filter / behavior change, GT-neutral. Every failure path is
swallowed (logging must never break a search). Gated by ``settings.search_call_logging_enabled``
(default True — it is pure telemetry, reversible by flipping the flag)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.logging import get_logger

_LOG = get_logger(__name__)
# logs/ at the repo root (services -> backend -> repo_root).
_LOG_FILE = Path(__file__).resolve().parents[2] / "logs" / "search_queries.jsonl"


def log_search_call(
    tool: str,
    args: dict[str, Any],
    result_count: int,
    *,
    was_empty: bool | None = None,
    hybrid_flag: Any = None,
) -> None:
    """Append one JSONL row for a search call. Best-effort — NEVER raises.

    ``args`` is the tool's input dict (query/cuisine/city/price/rating/geo/exclude) — empty
    values are dropped to keep rows compact. ``was_empty`` defaults to (result_count == 0).
    ``hybrid_flag`` is a placeholder for the future vector leg (None today)."""
    try:
        from core.settings import get_settings  # lazy (avoid import cycles)
        if not get_settings().search_call_logging_enabled:
            return
    except Exception:  # noqa: BLE001 — flag check must never break search
        return
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "tool": tool,
        "args": {k: v for k, v in args.items() if v not in (None, "", [], {})},
        "result_count": result_count,
        "was_empty": (result_count == 0) if was_empty is None else was_empty,
        "hybrid_flag": hybrid_flag,
    }
    try:
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as exc:  # noqa: BLE001 — log write must never break search
        _LOG.warning("search_call log write failed: %s", exc)
