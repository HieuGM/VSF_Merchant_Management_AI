"""Structured-ish logging setup. Injects the current request id into every record.

FROZEN SEAM: call `configure_logging()` once from the app factory; use
`get_logger(__name__)` everywhere else.
"""
from __future__ import annotations

import logging
import sys

from core.tracing import get_request_id


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True


def _force_utf8_streams() -> None:
    """Reconfigure stdout/stderr to UTF-8 so non-ASCII output never crashes the process.

    On Windows the default console encoding is cp1252 (`charmap`); CrewAI's verbose agent /
    tool-usage console logging writes Vietnamese text + emoji, which otherwise raises
    `UnicodeEncodeError` inside the event bus and surfaces as `RuntimeError: Task execution
    failed`, killing an otherwise-successful crew run. `errors="replace"` is a belt-and-braces
    guard so a stray glyph degrades to `?` instead of raising."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass  # detached/redirected stream — nothing to reconfigure


_CONFIGURED = False


def configure_logging(level: int = logging.INFO) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    _force_utf8_streams()
    handler = logging.StreamHandler()
    handler.addFilter(_RequestIdFilter())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
