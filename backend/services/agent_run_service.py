"""Safe Langfuse observation projection for the application UI."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from langfuse import get_client
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import ChatMessage

OBSERVATION_FIELDS = "core,basic,time,model,usage,prompt,metrics"


class TracePending(Exception):
    pass


class TraceNotFound(Exception):
    pass


class TraceUpstreamError(Exception):
    pass


def _dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    return dict(value)


def _value(data: dict[str, Any], camel: str, snake: str | None = None) -> Any:
    return data.get(camel, data.get(snake or camel))


def _milliseconds(value: Any) -> float | None:
    return round(float(value) * 1000, 3) if isinstance(value, (int, float)) else None


class AgentRunService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_run_trace(self, trace_id: str) -> dict[str, Any]:
        message = self._db.execute(
            select(ChatMessage)
            .where(ChatMessage.trace_id == trace_id)
            .order_by(ChatMessage.timestamp.desc())
            .limit(1)
        ).scalar_one_or_none()
        if message is None:
            raise TraceNotFound

        try:
            observations = self._fetch_observations(trace_id)
        except (TraceUpstreamError, TracePending, TraceNotFound):
            raise
        except Exception as error:
            raise TraceUpstreamError from error
        if not observations:
            timestamp = message.timestamp
            if timestamp is not None:
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                if (datetime.now(timezone.utc) - timestamp).total_seconds() <= 60:
                    raise TracePending
            raise TraceNotFound
        projected = self._project(trace_id, observations)
        if projected["status"] == "running" or not any(
            item["parent_id"] is None for item in projected["observations"]
        ):
            raise TracePending
        return projected

    @staticmethod
    def _fetch_observations(trace_id: str) -> list[dict[str, Any]]:
        client = get_client()
        cursor: str | None = None
        rows: dict[str, dict[str, Any]] = {}
        for _page in range(5):
            response = client.api.observations.get_many(
                trace_id=trace_id,
                fields=OBSERVATION_FIELDS,
                limit=1000,
                cursor=cursor,
            )
            for item in response.data:
                row = _dump(item)
                identifier = str(_value(row, "id"))
                rows[identifier] = row
            meta = _dump(response.meta) if hasattr(response.meta, "model_dump") else vars(response.meta)
            cursor = meta.get("cursor")
            if not cursor:
                return list(rows.values())
        raise TraceUpstreamError

    @staticmethod
    def _project(trace_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        projected: list[dict[str, Any]] = []
        input_tokens: int | None = None
        output_tokens: int | None = None
        total_tokens: int | None = None
        total_cost: float | None = None
        starts: list[str] = []
        ends: list[str] = []
        failed = running = False
        for row in rows:
            usage = _value(row, "usageDetails", "usage_details") or {}
            costs = _value(row, "costDetails", "cost_details") or {}
            observation_type = str(_value(row, "type") or "SPAN").upper()
            level = str(_value(row, "level") or "DEFAULT").upper()
            start = _value(row, "startTime", "start_time")
            end = _value(row, "endTime", "end_time")
            if start:
                starts.append(str(start))
            if end:
                ends.append(str(end))
            else:
                running = True
            failed = failed or level == "ERROR"
            if observation_type in {"GENERATION", "EMBEDDING"}:
                if isinstance(usage.get("input"), (int, float)):
                    input_tokens = (input_tokens or 0) + int(usage["input"])
                if isinstance(usage.get("output"), (int, float)):
                    output_tokens = (output_tokens or 0) + int(usage["output"])
                if isinstance(usage.get("total"), (int, float)):
                    total_tokens = (total_tokens or 0) + int(usage["total"])
                if isinstance(costs.get("total"), (int, float)):
                    total_cost = (total_cost or 0) + float(costs["total"])
            projected.append(
                {
                    "id": str(_value(row, "id")),
                    "parent_id": None if _value(row, "isRootObservation", "is_root_observation")
                    else _value(row, "parentObservationId", "parent_observation_id"),
                    "name": str(_value(row, "name") or "observation"),
                    "type": observation_type,
                    "status": "failed" if level == "ERROR" else ("running" if not end else "completed"),
                    "model": _value(row, "providedModelName", "provided_model_name"),
                    "prompt_name": _value(row, "promptName", "prompt_name"),
                    "prompt_version": _value(row, "promptVersion", "prompt_version"),
                    "started_at": start,
                    "finished_at": end,
                    "latency_ms": _milliseconds(_value(row, "latency")),
                    "time_to_first_token_ms": _milliseconds(
                        _value(row, "timeToFirstToken", "time_to_first_token")
                    ),
                    "input_tokens": int(usage["input"]) if isinstance(usage.get("input"), (int, float)) else None,
                    "output_tokens": int(usage["output"]) if isinstance(usage.get("output"), (int, float)) else None,
                    "total_tokens": int(usage["total"]) if isinstance(usage.get("total"), (int, float)) else None,
                    "cost_usd": costs.get("total") if isinstance(costs.get("total"), (int, float)) else None,
                }
            )
        latency_ms = None
        if starts and ends:
            latency_ms = round(
                (datetime.fromisoformat(max(ends).replace("Z", "+00:00"))
                 - datetime.fromisoformat(min(starts).replace("Z", "+00:00"))).total_seconds()
                * 1000,
                3,
            )
        return {
            "trace_id": trace_id,
            "status": "failed" if failed else ("running" if running else "completed"),
            "started_at": min(starts) if starts else None,
            "finished_at": max(ends) if ends else None,
            "totals": {
                "latency_ms": latency_ms,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "total_cost_usd": total_cost,
            },
            "observations": sorted(projected, key=lambda item: item["started_at"] or ""),
        }
