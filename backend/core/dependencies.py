"""FastAPI dependency providers (DB session, cache, settings).

FROZEN SEAM: routes/services in both verticals resolve infra through these providers
so the backend can swap adapters (memory/redis) without touching call sites.
"""
from __future__ import annotations

from functools import lru_cache

from fastapi import HTTPException

from core.cache import CachePort
from core.logging import get_logger
from core.settings import Settings, get_settings
from database.connection import get_db_session  # re-export for route deps

__all__ = [
    "get_db_session",
    "get_settings",
    "get_cache",
    "settings_dependency",
    "require_dev_only",
]

_logger = get_logger(__name__)

# environment values treated as production. Profile write endpoints are IDOR-unsafe
# (path-only user_id trust) until real auth lands — the guard blocks these in prod.
_PROD_ENVS = frozenset({"production", "prod"})


@lru_cache
def get_cache() -> CachePort:
    """Return the process-wide cache adapter selected by settings.

    Phase 0 default is in-memory. Dev A's D-02 adds the Redis branch here (this is the
    single sanctioned edit point for cache backend selection)."""
    settings = get_settings()
    if settings.cache_backend == "redis" and settings.redis_url:
        from providers.cache.redis_adapter import RedisCache  # lazy: D-02 optional

        return RedisCache(settings.redis_url)
    from providers.cache.memory_adapter import InMemoryCache

    return InMemoryCache()


def settings_dependency() -> Settings:
    return get_settings()


def require_dev_only() -> bool:
    """IDOR guard for profile write endpoints (phase-01, finding M7).

    Profile confirm/reject/PATCH trust the path ``user_id`` only — without a real auth
    principal, anyone can mutate any user's profile. Until auth lands, allow ONLY outside
    production (dev/staging/test) and log a warning; in production, 403. This is a
    guardrail, not the final auth design (TODO(AUTH) at the route layer)."""
    env = get_settings().environment.strip().lower()
    if env in _PROD_ENVS:
        raise HTTPException(
            status_code=403,
            detail=(
                "Profile write endpoints are dev-only until authentication is wired "
                "(IDOR guard). Set environment!=production for local dev."
            ),
        )
    _logger.warning(
        "profile write allowed under dev-only IDOR guard (environment=%s); "
        "path user_id trusted without an auth principal",
        env,
    )
    return True
