"""Narrow event listener for specialist CrewAI LLM calls."""
from __future__ import annotations

import threading
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

from langfuse import get_client

_capability: ContextVar[str | None] = ContextVar("merchant_trace_capability", default=None)
_prompt: ContextVar[Any | None] = ContextVar("merchant_trace_prompt", default=None)
_observations_lock = threading.Lock()
_observations: dict[tuple[str, str], Any] = {}


@contextmanager
def bind_specialist_generation(capability: str, prompt: Any) -> Iterator[None]:
    token_cap = _capability.set(capability)
    token_prompt = _prompt.set(prompt)
    try:
        yield
    finally:
        _capability.reset(token_cap)
        _prompt.reset(token_prompt)


def on_specialist_llm_start(event: Any) -> None:
    capability = _capability.get()
    if not capability:
        return
    client = get_client()
    trace_id = getattr(event, "trace_id", None) or getattr(client, "get_trace_id", lambda: None)()
    parent_id = getattr(event, "parent_id", None)
    call_id = getattr(event, "call_id", str(id(event)))

    trace_ctx = {"trace_id": str(trace_id), "parent_span_id": str(parent_id)} if trace_id and parent_id else None
    obs = client.start_observation(
        trace_context=trace_ctx,
        name=f"specialist.{capability}.llm",
        as_type="generation",
        input=getattr(event, "messages", []),
        model=getattr(event, "model", None),
        model_parameters={
            "temperature": getattr(event, "temperature", None),
            "top_p": getattr(event, "top_p", None),
            "max_tokens": getattr(event, "max_tokens", None),
        },
        prompt=_prompt.get(),
    )
    with _observations_lock:
        _observations[(str(trace_id), str(call_id))] = obs


def on_specialist_llm_end(event: Any) -> None:
    client = get_client()
    trace_id = getattr(event, "trace_id", None) or getattr(client, "get_trace_id", lambda: None)()
    call_id = getattr(event, "call_id", str(id(event)))
    with _observations_lock:
        obs = _observations.pop((str(trace_id), str(call_id)), None)
    if obs:
        output = getattr(event, "response", "")
        usage = getattr(event, "usage", None)
        obs.update(output=output, usage=usage)
        if hasattr(obs, "end"):
            obs.end()


def on_specialist_llm_error(event: Any) -> None:
    client = get_client()
    trace_id = getattr(event, "trace_id", None) or getattr(client, "get_trace_id", lambda: None)()
    call_id = getattr(event, "call_id", str(id(event)))
    with _observations_lock:
        obs = _observations.pop((str(trace_id), str(call_id)), None)
    if obs:
        obs.update(level="ERROR", status_message="specialist_llm_failed")
        if hasattr(obs, "end"):
            obs.end()
