"""Chat session repository (Phase 02) — read session candidate list.

Candidates are the merchant shortlist already generated in a session, persisted in
`chat_sessions.context_snapshot_json` (Redis stays the hot copy — §6.2). Returning
them lets the crew refine an existing list instead of re-searching.

Contract for a candidate dict (minimal): `{merchant_id, name, cuisine, ...}`.
Missing session / empty snapshot → empty list (never raises)."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from database.models import ChatSession


class SessionRepository:
    """Read access to session context snapshots."""

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
