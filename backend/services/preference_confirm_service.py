"""Preference confirm/reject orchestrator (phase-04) — the ONLY writer of ``user_profiles``.

Owns ONE ``SessionLocal`` tx per call. ``confirm`` is idempotent (``find_by_evidence`` on
the delta_id), upserts + applies the delta via ``UserProfileRepository.apply_delta``, then
appends a ``preference_events(confirmed)`` audit row. ``reject`` appends a
``preference_events(rejected)`` row only — no profile value mutation.

The propose-only invariant (§7.1) holds: ``preference_service.propose_deltas`` and the
``propose_profile_delta`` tool stay 100%% read-only; this service is the single confirmed-
write path. Audit logging (source IP + user_id + delta_id) is done at the route layer.
"""
from __future__ import annotations

from fastapi import HTTPException

from database.connection import SessionLocal
from database.models import UserProfile
from models.agent import ConfirmDeltaRequest
from models.preference import UserProfilePublic
from repositories.preference_event_repository import PreferenceEventRepository
from repositories.user_profile_repository import UserProfileRepository


class PreferenceConfirmService:
    """Apply confirmed profile deltas + append audit events. One SessionLocal tx per call."""

    def _ensure_user_row(self, db, user_id: str) -> None:
        """Create a minimal UserProfile if absent so the preference_events.user_id FK holds.

        No preference VALUES are mutated here (the reject path uses this — reject must not
        change the profile, but its audit row still needs a parent user_profiles row)."""
        if db.get(UserProfile, user_id) is None:
            db.add(UserProfile(
                user_id=user_id,
                liked_cuisines=[],
                disliked_cuisines=[],
                dietary=[],
                distance_preference_km=5.0,
            ))
            db.commit()

    def confirm(self, user_id: str, delta_id: str, body: ConfirmDeltaRequest) -> UserProfilePublic:
        """Idempotently apply a confirmed delta + audit it.

        Repeating the same ``delta_id`` is a no-op (returns the current profile, appends no
        second event) — B6 idempotency. Typed-validation failures from ``apply_delta`` (B5)
        surface as HTTP 400, not 500."""
        db = SessionLocal()
        try:
            events = PreferenceEventRepository(db)
            if events.find_by_evidence(delta_id, "confirmed"):
                # Already confirmed earlier — do not re-apply or re-audit.
                existing = UserProfileRepository(db).get_by_id(user_id)
                return existing if existing is not None else UserProfilePublic(user_id=user_id)
            try:
                profile = UserProfileRepository(db).apply_delta(
                    body.field, body.operation, body.value, user_id=user_id
                )
            except ValueError as exc:
                # B5 typed-validation failure -> 400 (not a 500 crash).
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            events.append(
                user_id=user_id,
                session_id=getattr(body, "session_id", None),
                field=body.field,
                operation=body.operation,
                value=body.value,
                scope="confirmed_global",
                source="user_confirm",
                status="confirmed",
                evidence_refs=[delta_id],
            )
            return profile
        finally:
            db.close()

    def reject(self, user_id: str, delta_id: str, body: ConfirmDeltaRequest | None) -> None:
        """Record an explicit rejection (audit only, no profile mutation). ``body`` may be
        None — the FE ``rejectDelta`` posts no body; field/op are logged as <none> at the route."""
        db = SessionLocal()
        try:
            self._ensure_user_row(db, user_id)  # FK parent for the audit row
            PreferenceEventRepository(db).append(
                user_id=user_id,
                session_id=getattr(body, "session_id", None) if body else None,
                field=body.field if body else "rejected",
                operation=body.operation if body else "reject",
                value=body.value if body else None,
                scope="confirmed_global",
                source="user_reject",
                status="rejected",
                evidence_refs=[delta_id],
            )
        finally:
            db.close()


# Singleton (the route imports this name).
preference_confirm_service = PreferenceConfirmService()
