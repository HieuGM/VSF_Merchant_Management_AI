"""Request-scoped user profile propagation (phase-02).

The CrewAI search tools (``merchant_search`` / ``nearby_merchant_search``) take no
``user_id`` argument, so the profile cannot be passed explicitly into the search path.
Instead the flow sets the loaded profile into a ContextVar around ``crew.kickoff``
(``profile_scope``); ``MerchantSearchService`` reads it via ``get_current_profile()``.

Mirrors the run_scope / tool_call_scope / stream_scope ContextVar pattern already used for
listeners + tracing. Both the blocking kickoff and the stream path's
``contextvars.copy_context().run`` pool propagate the token (the stream worker sets the
scope inside ``_run_one``, so it holds within the worker thread regardless of the copy)."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator

from models.preference import UserProfilePublic

_current_profile: ContextVar[UserProfilePublic | None] = ContextVar(
    "current_profile", default=None
)


def get_current_profile() -> UserProfilePublic | None:
    """The profile active for this request/crew run, or None (ranking becomes a no-op)."""
    return _current_profile.get()


@contextmanager
def profile_scope(profile: UserProfilePublic | None) -> Iterator[None]:
    """Set the active profile for the duration of a crew kickoff (token-based reset)."""
    token: Token[UserProfilePublic | None] = _current_profile.set(profile)
    try:
        yield
    finally:
        _current_profile.reset(token)
