"""User profile repository — read access + confirmed-delta application (phase-04).

Read path maps the ``user_profiles`` ORM row to the public ``UserProfilePublic``
contract (§6.5) and stays side-effect free (the propose-only invariant, §7.1).
``apply_delta`` is the ONLY mutator, reached solely from the explicit user-confirm
route (§11.6) — never from the propose path. Repository receives a Session; it never
opens/closes one (the caller owns the SessionLocal lifecycle)."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from database.models import UserProfile
from models.preference import UserProfilePublic

# --- phase-04 confirmed-delta application (B5 typed validation + B6 list semantics) ---
# Fields a confirmed delta may touch (mirrors the route whitelist). Bounds WHAT mutates,
# not WHO (auth gates WHO). user_id/PK/updated_at are intentionally absent.
_APPLY_LIST_FIELDS: frozenset[str] = frozenset({"liked_cuisines", "disliked_cuisines", "dietary"})
_APPLY_ENUM_FIELDS: dict[str, frozenset[str]] = {
    "spice_tolerance": frozenset({"none", "mild", "medium", "hot"}),
    "budget_level": frozenset({"student", "standard", "premium"}),
}
_APPLY_FLOAT_FIELDS: frozenset[str] = frozenset({"distance_preference_km"})


def _coerce_str_list(value: Any) -> list[str]:
    """Coerce a scalar or list value into list[str] for add/remove on list fields.

    A bare scalar ('phở') is treated as a single element — the FE suggestion may carry
    either a scalar or a list. Raises ValueError on dict/number/other non-str-able shapes
    so the route can map it to 400 (B5 type guard)."""
    if isinstance(value, bool):
        raise ValueError(f"expected str or list, got bool: {value!r}")
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    raise ValueError(f"expected str or list, got {type(value).__name__}: {value!r}")


class UserProfileRepository:
    """Read access to confirmed user preference profiles + delta application."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, user_id: str) -> UserProfilePublic | None:
        row = self._db.get(UserProfile, user_id)
        if row is None:
            return None
        return self._to_public(row)

    def apply_delta(
        self,
        field: str,
        operation: str,
        value: Any,
        user_id: str | None = None,
    ) -> UserProfilePublic:
        """Apply ONE confirmed profile delta with per-field typed validation (B5) + upsert (R3).

        Validation runs BEFORE any DB touch, so rejection-path callers (route 400, unit
        tests) raise without supplying ``user_id``. Semantics: ``set`` replaces; ``add``
        appends-if-absent; ``remove`` filters out. List fields accept a scalar (one element)
        or a list; enum fields are ``set``-only with membership; the float field is
        ``set``-only in [0, 50]. Raises ValueError on a bad operation/field/type/enum/range —
        the route maps that to HTTP 400. Returns the updated public profile."""
        if operation not in ("set", "add", "remove"):
            raise ValueError(f"operation must be set/add/remove, got {operation!r}")
        if (field not in _APPLY_LIST_FIELDS
                and field not in _APPLY_ENUM_FIELDS
                and field not in _APPLY_FLOAT_FIELDS):
            raise ValueError(f"field not allowed: {field!r}")

        # --- per-field typed coercion (raises ValueError on mismatch; B5) ---
        if field in _APPLY_LIST_FIELDS:
            if operation == "set":
                # set on a list field requires a real list — a scalar would corrupt the
                # profile (_to_public iterates the JSONB list char-by-char if it were a str).
                if not isinstance(value, list):
                    raise ValueError(
                        f"{field} is a list[str]; 'set' needs a list, got {type(value).__name__}"
                    )
                resolved: Any = [str(v) for v in value]
            else:  # add / remove accept a scalar (single element) or a list
                resolved = _coerce_str_list(value)
        elif field in _APPLY_ENUM_FIELDS:
            allowed = _APPLY_ENUM_FIELDS[field]
            if operation != "set":
                raise ValueError(f"{field} is a scalar enum; only 'set' allowed, got {operation!r}")
            if not isinstance(value, str) or value not in allowed:
                raise ValueError(f"{field} must be one of {sorted(allowed)}, got {value!r}")
            resolved = value
        else:  # scalar float
            if operation != "set":
                raise ValueError(f"{field} is a scalar; only 'set' allowed, got {operation!r}")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{field} must be a number, got {type(value).__name__}")
            if not (0.0 <= float(value) <= 50.0):
                raise ValueError(f"{field} must be in [0, 50], got {value!r}")
            resolved = float(value)

        # --- apply (needs user_id; rejection paths raise above before reaching here) ---
        if user_id is None:
            raise ValueError("user_id is required to apply a delta")
        row = self._db.get(UserProfile, user_id)
        if row is None:  # R3 upsert: first-ever confirm creates a minimal row
            row = UserProfile(
                user_id=user_id,
                liked_cuisines=[],
                disliked_cuisines=[],
                dietary=[],
                distance_preference_km=5.0,
            )
            self._db.add(row)

        if field in _APPLY_LIST_FIELDS:
            current = list(getattr(row, field) or [])
            if operation == "set":
                current = list(resolved)
            elif operation == "add":
                for v in resolved:
                    if v not in current:
                        current.append(v)
            else:  # remove
                drop = set(resolved)
                current = [v for v in current if v not in drop]
            setattr(row, field, current)
        else:  # enum or scalar float — 'set' only, value already validated
            setattr(row, field, resolved)

        self._db.commit()
        self._db.refresh(row)
        return self._to_public(row)

    @staticmethod
    def _to_public(row: UserProfile) -> UserProfilePublic:
        return UserProfilePublic(
            user_id=row.user_id,
            liked_cuisines=row.liked_cuisines or [],
            disliked_cuisines=row.disliked_cuisines or [],
            spice_tolerance=row.spice_tolerance,
            dietary=row.dietary or [],
            budget_level=row.budget_level,
            distance_preference_km=(
                row.distance_preference_km if row.distance_preference_km is not None else 5.0
            ),
            current_lat=row.current_lat,
            current_lng=row.current_lng,
            context_memory=row.context_memory or {},
            updated_at=row.updated_at.isoformat() if row.updated_at else None,
        )
