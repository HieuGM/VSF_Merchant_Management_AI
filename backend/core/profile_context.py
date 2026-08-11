"""Request-scoped user profile + active-constraints propagation (phase-02 + constraint layer).

The CrewAI search tools (``merchant_search`` / ``nearby_merchant_search``) take no
``user_id`` argument, so the profile cannot be passed explicitly into the search path.
Instead the flow sets the loaded profile into a ContextVar around ``crew.kickoff``
(``profile_scope``); ``MerchantSearchService`` reads it via ``get_current_profile()``.

``constraints_scope`` mirrors the same pattern for the unified active-constraints set (allergies /
diet), so ``should_hard_filter`` can drop restricted merchants at the DB-result level without a
tool signature change and without a coordinator.

Mirrors the run_scope / tool_call_scope / stream_scope ContextVar pattern already used for
listeners + tracing. Both the blocking kickoff and the stream path's
``contextvars.copy_context().run`` pool propagate the token (the stream worker sets the
scope inside ``_run_one``, so it holds within the worker thread regardless of the copy)."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Iterator

from models.preference import UserProfilePublic

if TYPE_CHECKING:  # runtime type-only — avoids a core→services import cycle
    from services.active_constraints_loader import ActiveConstraints

_current_profile: ContextVar[UserProfilePublic | None] = ContextVar(
    "current_profile", default=None
)
_current_constraints: ContextVar["ActiveConstraints | None"] = ContextVar(
    "current_constraints", default=None
)


def get_current_profile() -> UserProfilePublic | None:
    """The profile active for this request/crew run, or None (ranking becomes a no-op)."""
    return _current_profile.get()


def get_active_constraints() -> ActiveConstraints | None:
    """The active user constraints for this request/crew run, or None (no hard-filter)."""
    return _current_constraints.get()


@contextmanager
def profile_scope(profile: UserProfilePublic | None) -> Iterator[None]:
    """Set the active profile for the duration of a crew kickoff (token-based reset)."""
    token: Token[UserProfilePublic | None] = _current_profile.set(profile)
    try:
        yield
    finally:
        _current_profile.reset(token)


@contextmanager
def constraints_scope(constraints: ActiveConstraints | None) -> Iterator[None]:
    """Set the active user constraints for the duration of a crew kickoff (token-based reset)."""
    token: Token[ActiveConstraints | None] = _current_constraints.set(constraints)
    try:
        yield
    finally:
        _current_constraints.reset(token)
