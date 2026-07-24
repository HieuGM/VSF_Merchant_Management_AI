"""Typed errors + error envelope (design §11.10).

FROZEN SEAM: stable error codes are part of the API contract. Both verticals raise
`AppError` subclasses; the exception handler (registered in app/extensions.py)
renders the envelope. Do not change codes/HTTP mapping without the contract protocol.
"""
from __future__ import annotations

from typing import Any

# Stable error codes — design §11.10. code -> default HTTP status.
ERROR_HTTP_STATUS: dict[str, int] = {
    "validation_error": 422,
    "unauthorized": 401,
    "forbidden": 403,
    "not_found": 404,
    "insufficient_data": 422,
    "provider_error": 502,
    "timeout": 504,
    "conflict": 409,
    "config_error": 500,
    "internal_error": 500,
}


class AppError(Exception):
    """Base application error mapped to the §11.10 envelope."""

    code: str = "internal_error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        self.details = details or {}

    @property
    def http_status(self) -> int:
        return ERROR_HTTP_STATUS.get(self.code, 500)

    def to_envelope(self, trace_id: str | None = None) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
                "trace_id": trace_id,
            }
        }


class ValidationError(AppError):
    code = "validation_error"


class NotFoundError(AppError):
    code = "not_found"


class InsufficientDataError(AppError):
    code = "insufficient_data"


class ProviderError(AppError):
    code = "provider_error"


class TimeoutError(AppError):  # noqa: A001 - deliberate domain name
    code = "timeout"


class ConflictError(AppError):
    code = "conflict"


class UnauthorizedError(AppError):
    code = "unauthorized"


class ForbiddenError(AppError):
    code = "forbidden"


class ConfigError(AppError):
    """Misconfiguration (e.g. missing LLM API key) — surfaced clearly, not a vague 500."""

    code = "config_error"
