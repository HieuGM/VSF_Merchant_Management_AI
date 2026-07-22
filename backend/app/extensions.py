"""App-factory extension seam (red-team H5).

`app/main.py` is FROZEN. To let each vertical attach lifespan hooks, middleware,
exception handlers, and CrewAI listeners WITHOUT editing main.py, they register
callables here. main.py only iterates these registries.

Ownership: this file is edited only by the contract owner. Verticals append to the
registries from their OWN module import side-effects (or via the register_* helpers).
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.errors import AppError
from core.logging import get_logger
from core.tracing import get_request_id, new_id, set_request_id

logger = get_logger(__name__)

# --- Registries populated before create_app() runs (import-time or explicit call) ---
STARTUP_HOOKS: list[Callable[[FastAPI], Awaitable[None] | None]] = []
SHUTDOWN_HOOKS: list[Callable[[FastAPI], Awaitable[None] | None]] = []
ROUTERS: list[Any] = []  # APIRouter instances contributed by each domain


def register_startup(hook: Callable[[FastAPI], Awaitable[None] | None]) -> None:
    STARTUP_HOOKS.append(hook)


def register_shutdown(hook: Callable[[FastAPI], Awaitable[None] | None]) -> None:
    SHUTDOWN_HOOKS.append(hook)


def register_router(router: Any) -> None:
    ROUTERS.append(router)


def install_middleware(app: FastAPI) -> None:
    """CORS (FE) + X-Request-ID propagation.

    Origins come from Settings.cors_origin_list — never wildcard-with-credentials
    (that reflects any origin). Add FE origins via the CORS_ORIGINS env var."""
    from core.settings import get_settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Request-ID") or new_id("req")
        set_request_id(request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


def install_exception_handlers(app: FastAPI) -> None:
    """Render the §11.10 error envelope for typed + unexpected errors."""

    @app.exception_handler(AppError)
    async def _app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=exc.to_envelope(trace_id=get_request_id()),
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", exc_info=exc)
        err = AppError("Đã xảy ra lỗi nội bộ.", code="internal_error")
        return JSONResponse(status_code=500, content=err.to_envelope(get_request_id()))
