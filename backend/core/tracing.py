"""Request / trace identifiers (design §11 — every response carries X-Request-ID;
agent responses carry trace_id).

FROZEN SEAM: both verticals read the current request id from here via contextvar so
logging/tracing stay consistent. Middleware in app/extensions.py sets it per request.
"""
from __future__ import annotations

import uuid
from contextvars import ContextVar

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def new_id(prefix: str = "trace") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def set_request_id(request_id: str) -> None:
    _request_id.set(request_id)


def get_request_id() -> str | None:
    return _request_id.get()
