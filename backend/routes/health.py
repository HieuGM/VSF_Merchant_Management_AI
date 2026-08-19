"""Health endpoint (design §11.1). Not under /api/v1 — stays at /health."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.cache import CachePort
from core.dependencies import get_cache, get_db_session, settings_dependency
from core.settings import Settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health(
    db: Session = Depends(get_db_session),
    cache: CachePort = Depends(get_cache),
    settings: Settings = Depends(settings_dependency),
) -> dict[str, object]:
    database = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - health must not raise
        database = "error"

    # Probes the active CachePort. With the Phase 0 memory adapter this always passes;
    # once the Redis adapter (D-02) lands it should ping the real Redis backend.
    redis = "ok"
    try:
        cache.set("health:ping", "1", ttl_seconds=5)
        redis = "ok" if cache.get("health:ping") == "1" else "error"
    except Exception:  # noqa: BLE001
        redis = "error"

    mem0 = "ok"
    try:
        from services.mem0_service import Mem0Service
        mem0 = "ok" if Mem0Service().health() else "error"
    except Exception:  # noqa: BLE001
        mem0 = "error"

    overall = "ok" if database == "ok" and redis == "ok" and mem0 == "ok" else "degraded"
    return {
        "status": overall,
        "database": database,
        "redis": redis,
        "mem0": mem0,
        "llm_configured": settings.llm_configured,
    }
