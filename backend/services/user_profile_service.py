"""User profile service — read + explicit-edit write (phase-01).

Thin orchestrator owning ONE SessionLocal tx per call. ``update_profile`` applies a
partial taste-profile patch via ``UserProfileRepository.apply_fields`` (B5 typed
validation, atomic), then appends one ``preference_events`` audit row per changed field
(source=user_edit, status=confirmed). Mirrors the propose/confirm split (§7.1): this is
the explicit-edit write path, DISTINCT from the suggestion confirm path.
"""
from __future__ import annotations

from fastapi import HTTPException

from core.logging import get_logger
from database.connection import SessionLocal
from models.preference import UserProfilePublic
from repositories.preference_event_repository import PreferenceEventRepository
from repositories.user_profile_repository import UserProfileRepository

_LOG = get_logger(__name__)


class UserProfileService:
    """Read + explicit-edit write for the canonical user profile."""

    def get_profile(self, user_id: str) -> UserProfilePublic:
        """Return the confirmed profile. 404 when the user has no profile row yet."""
        db = SessionLocal()
        try:
            profile = UserProfileRepository(db).get_by_id(user_id)
            if profile is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Không tìm thấy hồ sơ user '{user_id}'.",
                )
            return profile
        finally:
            db.close()

    def clear_memory(self, user_id: str) -> UserProfilePublic:
        """Wipe remembered memory (context_memory notes + taste fields the constraint layer
        reads) — the FE 'clear memory' test control. Returns the reset profile (or 404 if the
        user has no row, matching get_profile)."""
        db = SessionLocal()
        try:
            repo = UserProfileRepository(db)
            repo.clear_memory(user_id)
            profile = repo.get_by_id(user_id)
            if profile is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Không tìm thấy hồ sơ user '{user_id}'.",
                )
            return profile
        finally:
            db.close()

    def update_profile(self, user_id: str, patch: dict) -> UserProfilePublic:
        """Apply a partial taste-profile patch (PATCH /profile) + audit it.

        Atomic: apply_fields validates + resolves ALL fields before any DB write, so a bad
        field surfaces as HTTP 400 with no partial mutation. One audit event per changed
        field (source=user_edit) preserves the per-field audit trail used by confirm/reject.
        """
        db = SessionLocal()
        try:
            repo = UserProfileRepository(db)
            try:
                profile = repo.apply_fields(patch, user_id=user_id)
            except ValueError as exc:
                # B5 typed-validation failure -> 400 (not a 500 crash).
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            # Audit: one preference_events row per changed field (source=user_edit). Each
            # append() self-commits; wrapped so an audit failure NEVER surfaces as a 500
            # after the profile was already committed (truly best-effort — at worst a
            # partial audit trail, tolerable given idempotent 'set' semantics).
            events = PreferenceEventRepository(db)
            for field, value in patch.items():
                try:
                    events.append(
                        user_id=user_id,
                        session_id=None,
                        field=field,
                        operation="set",
                        value=value,
                        scope="confirmed_global",
                        source="user_edit",
                        status="confirmed",
                        evidence_refs=[],
                    )
                except Exception as exc:  # noqa: BLE001 — audit must never break the edit
                    _LOG.warning(
                        "profile audit append failed (user=%s field=%s): %s",
                        user_id, field, exc,
                    )
            return profile
        finally:
            db.close()


# Singleton (the route imports this name; mirrors preference_confirm_service).
user_profile_service = UserProfileService()
