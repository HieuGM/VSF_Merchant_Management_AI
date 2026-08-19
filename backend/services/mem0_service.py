from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import httpx

from core.errors import ProviderError, TimeoutError
from core.settings import get_settings


@dataclass(frozen=True)
class MemoryIdentity:
    user_id: str
    agent_id: str
    run_id: str


@dataclass(frozen=True)
class MemoryHit:
    memory: str
    score: float | None = None


def memory_identity(
    user_id: str | None,
    merchant_id: str,
    session_id: str,
) -> MemoryIdentity:
    """Build canonical MemoryIdentity scoped to user/merchant/session."""
    effective_user_id = user_id or merchant_id
    return MemoryIdentity(
        user_id=effective_user_id,
        agent_id=f"merchant-advisor:{merchant_id}",
        run_id=session_id,
    )


class Mem0Service:
    """HTTP client communicating with self-hosted Mem0 REST API."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
        top_k: int | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.mem0_base_url).rstrip("/")
        self._api_key = api_key if api_key is not None else settings.effective_mem0_api_key
        self._timeout = timeout_seconds if timeout_seconds is not None else settings.mem0_timeout_seconds
        self._top_k = top_k if top_k is not None else settings.mem0_search_top_k
        self._client = client

    def _get_client(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        return httpx.Client(
            base_url=self._base_url,
            headers=headers,
            timeout=self._timeout,
        )

    def search(self, query: str, identity: MemoryIdentity) -> list[MemoryHit]:
        """Search relevant memories for the current query within user/agent boundary."""
        payload = {
            "query": query,
            "filters": {
                "user_id": identity.user_id,
                "agent_id": identity.agent_id,
            },
            "top_k": self._top_k,
        }
        client = self._get_client()
        headers = {}
        if self._api_key:
            headers["X-API-Key"] = self._api_key

        try:
            response = client.post("/search", json=payload, headers=headers)
            if response.status_code != 200:
                raise ProviderError("Mem0 search returned non-200 status")
            data = response.json()
        except httpx.TimeoutException as exc:
            raise TimeoutError("Mem0 search timed out") from exc
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("Mem0 search request failed") from exc

        results = data.get("results", [])
        hits = []
        for item in results:
            text = item.get("memory") or item.get("text") or ""
            if text:
                score = item.get("score")
                hits.append(MemoryHit(memory=text, score=float(score) if score is not None else None))
        return hits

    def add_turn(
        self,
        user_text: str,
        assistant_text: str,
        identity: MemoryIdentity,
    ) -> None:
        """Add user/assistant interaction turn to Mem0 in a structured format."""
        payload = {
            "messages": [
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": assistant_text},
            ],
            "user_id": identity.user_id,
            "agent_id": identity.agent_id,
            "run_id": identity.run_id,
        }
        client = self._get_client()
        headers = {}
        if self._api_key:
            headers["X-API-Key"] = self._api_key

        try:
            response = client.post("/memories", json=payload, headers=headers)
            if response.status_code not in (200, 201):
                raise ProviderError("Mem0 add_turn returned non-2xx status")
        except httpx.TimeoutException as exc:
            raise TimeoutError("Mem0 add_turn timed out") from exc
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("Mem0 add_turn request failed") from exc

    def health(self) -> bool:
        """Probe Mem0 health endpoint."""
        client = self._get_client()
        try:
            response = client.get("/api/health")
            return response.status_code == 200
        except Exception:
            return False


class Mem0WriteDispatcher:
    """Dispatches asynchronous non-blocking memory writes to Mem0."""

    def __init__(
        self,
        service: Mem0Service | None = None,
        executor: Any | None = None,
    ) -> None:
        from concurrent.futures import ThreadPoolExecutor
        self._service = service or Mem0Service()
        self._executor = executor or ThreadPoolExecutor(max_workers=2, thread_name_prefix="mem0-writer")

    def submit(
        self,
        user_text: str,
        assistant_text: str,
        identity: MemoryIdentity,
        origin_trace_id: str | None = None,
    ) -> None:
        """Submit background add_turn task."""
        self._executor.submit(
            self._write_turn,
            user_text,
            assistant_text,
            identity,
            origin_trace_id,
        )

    def _write_turn(
        self,
        user_text: str,
        assistant_text: str,
        identity: MemoryIdentity,
        origin_trace_id: str | None,
    ) -> None:
        from langfuse import get_client
        client = get_client()
        with client.start_as_current_observation(
            name="memory.add",
            as_type="span",
            input={"user": user_text, "assistant": assistant_text},
            metadata={
                "origin_trace_id": origin_trace_id,
                "user_id": identity.user_id,
                "agent_id": identity.agent_id,
                "run_id": identity.run_id,
            },
        ) as observation:
            try:
                self._service.add_turn(user_text, assistant_text, identity)
                observation.update(output={"status": "ok"})
            except Exception as exc:
                observation.update(
                    output={"status": "error", "error": str(exc)},
                    level="ERROR",
                    status_message="memory_add_failed",
                )

