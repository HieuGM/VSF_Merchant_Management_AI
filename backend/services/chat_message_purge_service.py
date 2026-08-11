"""Stale chat-message purge (memory-system storage).

Lazy-on-write delete of chat_messages older than the retention window. pg_cron is NOT
available on postgres:18-alpine, so the purge runs inline from
ChatMessageRepository.append_turn, time-gated (memory_purge_min_interval_hours) via a
process-local monotonic timestamp. Never raises (F3) — purge failures are logged +
swallowed, and the chat write already succeeded. Routing-neutral: rows >retention are
far outside the within-conversation recall window (memory_window_turns / TTL), so this
never changes what gets injected into a prompt.
"""
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

# Process-local last-run timestamp (monotonic seconds). Not shared across workers —
# acceptable for a single-process FastAPI deploy; the purge is idempotent + cheap, so a
# redundant run in another worker is harmless.
_last_purge_ts: float = 0.0
# Floor the gate at 60s even if the setting is 0, so a misconfig can't trigger a DELETE
# on every single append_turn.
_GATE_FLOOR_SECONDS = 60


def maybe_purge_stale_messages() -> int:
    """Run the purge if enabled AND the min interval has elapsed since the last run.
    Returns the number of rows deleted (0 if skipped or on any failure). Never raises."""
    global _last_purge_ts
    try:
        from core.settings import get_settings

        s = get_settings()
        if not s.memory_purge_enabled:
            return 0
        now = time.monotonic()
        min_interval = max(_GATE_FLOOR_SECONDS, int(s.memory_purge_min_interval_hours) * 3600)
        if (now - _last_purge_ts) < min_interval:
            return 0  # time-gated: not yet
        _last_purge_ts = now
        return _purge(int(s.memory_purge_max_age_days))
    except Exception as exc:  # noqa: BLE001 — purge must never break the flow
        logger.warning("maybe_purge_stale_messages failed: %s", exc)
        return 0


def purge_now(max_age_days: int) -> int:
    """Force a purge ignoring the time-gate (admin / test). Returns rows deleted.
    Never raises."""
    try:
        return _purge(int(max_age_days))
    except Exception as exc:  # noqa: BLE001
        logger.warning("purge_now failed: %s", exc)
        return 0


def _purge(max_age_days: int) -> int:
    """DELETE chat_messages older than `max_age_days` (DB-server time via make_interval)."""
    from sqlalchemy import text as sa_text

    from database.connection import SessionLocal

    if max_age_days <= 0:
        return 0
    db = SessionLocal()
    try:
        result = db.execute(
            sa_text(
                "DELETE FROM chat_messages "
                "WHERE timestamp < now() - make_interval(secs => :secs)"
            ).bindparams(secs=int(max_age_days) * 86400)
        )
        db.commit()
        return int(result.rowcount or 0)
    finally:
        db.close()
