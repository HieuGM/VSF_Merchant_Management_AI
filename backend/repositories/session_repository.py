"""Chat session repository (Phase 02) — read session candidate list + distillates.

Candidates are the merchant shortlist already generated in a session, persisted in
`chat_sessions.context_snapshot_json` (Redis stays the hot copy — §6.2). Returning
them lets the crew refine an existing list instead of re-searching.

memory-system P2b: `list_recent_distillates` reads the per-conversation `distillate`
object (written by conversation_distillate_service) for cross-conversation recall.

Contract for a candidate dict (minimal): `{merchant_id, name, cuisine, ...}`.
Missing session / empty snapshot → empty list (never raises)."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from database.models import ChatSession


class SessionRepository:
    """Read access to session context snapshots + distillates."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_candidates(self, session_id: str) -> list[dict[str, Any]]:
        row = self._db.get(ChatSession, session_id)
        if row is None or not row.context_snapshot_json:
            return []
        snapshot = row.context_snapshot_json
        candidates = snapshot.get("candidates") if isinstance(snapshot, dict) else None
        if not isinstance(candidates, list):
            return []
        # Keep only dict entries — defensive against malformed snapshots.
        return [c for c in candidates if isinstance(c, dict)]

    def list_recent_distillates(
        self,
        user_id: str,
        limit: int = 20,
        exclude_session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Recent per-conversation distillates for a user (memory-system P2b recall).

        Returns the `distillate` object from each of the user's chat_sessions that has
        one, newest-first (by updated_at). `exclude_session_id` skips the current
        conversation (its context is already covered by prior_context). Returns [] on
        any failure — never raises."""
        try:
            q = self._db.query(ChatSession).filter(ChatSession.user_id == user_id)
            if exclude_session_id:
                q = q.filter(ChatSession.session_id != exclude_session_id)
            rows = q.order_by(ChatSession.updated_at.desc()).limit(int(limit)).all()
        except Exception:
            return []
        out: list[dict[str, Any]] = []
        for r in rows:
            snap = r.context_snapshot_json
            dist = snap.get("distillate") if isinstance(snap, dict) else None
            if isinstance(dist, dict):
                out.append(dist)
        return out
