"""Preference event repository — append-only audit log (design §6.6 preference_events).

Every confirm/reject appends ONE row; user_profiles is mutated separately by
UserProfileRepository.apply_delta. This module never reads/writes user_profiles.

evidence_refs_json carries delta_ids used for idempotency lookups. The pydantic
PreferenceEvent field is named `evidence_refs` but the ORM column is
`evidence_refs_json` — append() MUST map explicitly or find_by_evidence never
matches (audit B6) and idempotency silently breaks.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from core.tracing import new_id
from database.models import PreferenceEvent


class PreferenceEventRepository:
    """Session-scoped append-only access to preference audit events."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def append(
        self,
        user_id: str,
        session_id: str | None,
        field: str,
        operation: str,
        value: Any,
        scope: str,
        source: str,
        status: str,
        evidence_refs: list[str],
    ) -> str:
        """Insert one audit event; return its event_id."""
        event_id = new_id("evt")
        self._db.add(
            PreferenceEvent(
                event_id=event_id,
                user_id=user_id,
                session_id=session_id,
                field=field,
                operation=operation,
                value_json=value,
                scope=scope,
                source=source,
                status=status,
                evidence_refs_json=list(evidence_refs or []),  # B6: explicit *_json mapping
            )
        )
        self._db.commit()
        return event_id

    def find_by_evidence(self, delta_id: str, status: str) -> bool:
        """True iff an event with `status` references `delta_id` in evidence_refs.

        JSONB containment (evidence_refs_json @> '["<delta_id>"]') — delta_ids are
        globally unique (new_id uuid hex), so no user_id scoping is required.
        """
        needle = sa_text("CAST(:needle AS JSONB)").bindparams(
            needle=json.dumps([delta_id])
        )
        row = (
            self._db.query(PreferenceEvent)
            .filter(PreferenceEvent.evidence_refs_json.op("@>")(needle))
            .filter(PreferenceEvent.status == status)
            .first()
        )
        return row is not None
