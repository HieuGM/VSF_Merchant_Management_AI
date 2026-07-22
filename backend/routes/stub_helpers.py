"""Helper for Phase 0 route stubs.

Each router below declares its FROZEN contract path (design §11) but returns HTTP 501
until the owning vertical implements it in Phase 1/2. Keeping the real paths here means
the frozen API surface is documented in OpenAPI at handoff time.
"""
from __future__ import annotations

from fastapi.responses import JSONResponse

from core.tracing import get_request_id


def not_implemented(endpoint: str) -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={
            "error": {
                "code": "internal_error",
                "message": f"'{endpoint}' chưa được cài đặt (Phase 0 stub).",
                "details": {"phase0_stub": True},
                "trace_id": get_request_id(),
            }
        },
    )
