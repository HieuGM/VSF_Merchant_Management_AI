"""Structured-ish logging setup. Injects the current request id into every record.

FROZEN SEAM: call `configure_logging()` once from the app factory; use
`get_logger(__name__)` everywhere else.
"""
from __future__ import annotations

import logging
import traceback

from core.tracing import get_request_id


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True


_CONFIGURED = False


def configure_logging(level: int = logging.INFO) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
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


def safe_exception_trace(error: BaseException) -> str:
    """Render traceback locations and exception type without untrusted messages."""
    frames = traceback.extract_tb(error.__traceback__)
    locations = "\n".join(
        f'  File "{frame.filename}", line {frame.lineno}, in {frame.name}'
        for frame in frames
    )
    prefix = f"Traceback (most recent call last):\n{locations}\n" if locations else ""
    return f"{prefix}{type(error).__name__}: <message redacted>"
