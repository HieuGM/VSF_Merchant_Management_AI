"""Customer Discovery chat (Dev A). FROZEN path — design §11.4.

Two entry points, same crew:
- POST /chat         — blocking; returns the full CustomerChatResponse when the crew finishes.
- POST /chat/stream  — Server-Sent Events; emits live progress (task/tool started/finished)
  while the crew runs AND streams the explanation agent's answer token-by-token
  (answer_delta deltas), then the terminal run_finished with results. Kills the
  "blank 20-55s wait then full dump" feel — text starts flowing at TTFT ~5s.

Both run `CustomerFlow.search_restaurants` (CrewAI kickoff + run/event persistence). Typed/
unexpected errors on /chat are rendered by the global handlers in app/extensions.py (§11.10);
/chat/stream surfaces errors as a terminal `error` SSE event instead (the stream has begun).
"""
from __future__ import annotations

import json
import queue
import threading
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from models.agent import CustomerChatRequest, CustomerChatResponse

router = APIRouter(prefix="/api/v1/agent/customer", tags=["customer-agent"])

# Sentinel pushed to the queue when the worker thread finishes (success or error).
_DONE = object()


@router.post("/chat", response_model=CustomerChatResponse)
def customer_chat(request: CustomerChatRequest) -> CustomerChatResponse:
    """Run the Customer Discovery Crew for a chat message (UC-04/UC-05).

    Maps the chat contract (§11.4) to the flow: the free-text `message` becomes the
    discovery `query`; the LLM extracts cuisine/budget/etc. from it. Location (if sent)
    enables geo/weather reasoning."""
    # Lazy import: constructing CustomerFlow triggers tool discovery + listener install,
    # so defer it to first request rather than app startup.
    from flows.customer_flow import customer_flow

    location = request.location
    return customer_flow.search_restaurants(
        query=request.message,
        lat=location.lat if location else None,
        lng=location.lng if location else None,
        session_id=request.session_id,
        user_id=request.user_id,
    )


def _sse(event: str, data: Any) -> str:
    """Format one Server-Sent Event frame (UTF-8 JSON payload)."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/chat/stream")
def customer_chat_stream(request: CustomerChatRequest) -> StreamingResponse:
    """Stream crew progress + final answer as SSE (design §11.4).

    The blocking `crew.kickoff` runs in a worker thread; a per-request sink (stream_scope)
    forwards CrewAI task/tool events into a thread-safe queue, which the SSE generator drains.
    The sink is bound inside the worker thread so bus callbacks (fired synchronously during
    kickoff) see it."""
    from agents.listeners.streaming_listener import install_streaming_listener, stream_scope
    from flows.customer_flow import customer_flow

    install_streaming_listener()

    events: queue.Queue[Any] = queue.Queue()
    location = request.location
    params = {
        "query": request.message,
        "lat": location.lat if location else None,
        "lng": location.lng if location else None,
        "session_id": request.session_id,
        "user_id": request.user_id,
    }

    def worker() -> None:
        try:
            # stream_scope binds the StreamingListener's progress events (tool/task
            # started/finished) to the SSE queue. The flow's streaming generator yields the
            # explanation agent's answer_delta chunks + the terminal run_finished — both
            # feed the same queue. Answer now streams token-by-token (TTFT ~5s) instead of
            # being dumped once at the end.
            with stream_scope(events.put):
                for evt in customer_flow.search_restaurants_stream(**params):
                    events.put(evt)
        except Exception as exc:  # noqa: BLE001 - stream already open; report, don't 500
            events.put({
                "event": "error",
                "data": {"error_code": type(exc).__name__, "message": str(exc)},
            })
        finally:
            events.put(_DONE)

    threading.Thread(target=worker, daemon=True).start()

    def generate() -> Iterator[str]:
        yield _sse("run_started", {})
        while True:
            item = events.get()
            if item is _DONE:
                break
            yield _sse(item["event"], item["data"])

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
