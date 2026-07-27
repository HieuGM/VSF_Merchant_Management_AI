"""Registry → CrewAI BaseTool adapter (Phase 01) — the ONLY CrewAI coupling point.

Wraps a framework-agnostic `RegisteredTool` (ToolSpec + callable) into a
`crewai.tools.BaseTool`, so tools/services stay testable without CrewAI. Allow-list
enforcement lives in the registry (`registry.tools_for_agent`); this module only wraps
the tools an agent is already permitted to call.

CrewAI 1.15.5 BaseTool contract:
- `name`/`description`/`args_schema: Type[BaseModel]`, method `_run(**fields) -> str`.
- Tool MUST return a STRING (CrewAI feeds tool output to the LLM as text). Our internal
  tools return dict → we `json.dumps(...)`. Errors return a string, never raise, so the
  agent loop does not crash.
"""
from __future__ import annotations

import json
from typing import Any, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, create_model

from core.errors import AppError
from tools.registry import RegisteredTool, registry

# Loose mapping of input_schema string hints → python types (only used when a tool
# does not declare an explicit args_schema).
_TYPE_HINTS: dict[str, type] = {"str": str, "int": int, "float": float, "bool": bool}


def _args_model(spec) -> Type[BaseModel]:
    """Return the Pydantic args model for a tool.

    Prefers an explicit `spec.args_schema` (rich descriptions for the LLM); otherwise
    derives a permissive model from the informal `input_schema` dict."""
    if getattr(spec, "args_schema", None) is not None:
        return spec.args_schema

    fields: dict[str, Any] = {}
    for fname, hint in spec.input_schema.items():
        hint_str = str(hint).lower()
        base = next((t for k, t in _TYPE_HINTS.items() if k in hint_str), str)
        required = "required" in hint_str
        if required:
            fields[fname] = (base, ...)
        else:
            fields[fname] = (base | None, None)
    return create_model(f"{spec.name}_Args", **fields)  # type: ignore[call-overload]


class RegistryTool(BaseTool):
    """CrewAI BaseTool that delegates to a registered callable and returns a string."""

    reg_tool: RegisteredTool

    model_config = {"arbitrary_types_allowed": True}

    # Essential fields per tool — must match actual output schemas.
    # For wrapper dicts (merchant_search returns {merchants: [...], total, filters_applied}),
    # list items are filtered by _ESSENTIAL_LIST_ITEM_FIELDS.
    _ESSENTIAL_TOP_LEVEL: dict[str, list[str]] = {
        "merchant_search": ["merchants", "total", "filters_applied"],
        "nearby_merchant_search": ["merchants", "total", "radius_km"],
        "get_merchant_profile": [
            "merchant_id", "tier", "price_level", "dimensions", "ratings", "attributes",
        ],
        "get_user_profile": [
            "user_id", "liked_cuisines", "disliked_cuisines", "spice_tolerance",
            "dietary", "budget_level", "distance_preference_km",
        ],
        "get_session_candidates": ["session_id", "candidates", "total"],
        "get_weather_context": ["weather", "source", "cached"],
    }
    # Per-item fields for list values inside the top-level dict.
    _ESSENTIAL_LIST_ITEM_FIELDS: dict[str, list[str]] = {
        "merchant_search": [
            "merchant_id", "name", "cuisine", "address", "city",
            "distance_km", "avg_rating", "match_score",
        ],
        "nearby_merchant_search": [
            "merchant_id", "name", "cuisine", "distance_km", "avg_rating",
        ],
    }

    def _filter_essential_fields(self, data: dict) -> dict:
        """Keep only essential fields for agent decision-making.

        Handles two patterns:
        - Flat dicts (get_merchant_profile): filter top-level keys.
        - Wrapper dicts with lists (merchant_search): filter top-level keys AND
          filter each item in list values.
        """
        tool_name = self.reg_tool.spec.name
        top_keys = self._ESSENTIAL_TOP_LEVEL.get(tool_name)

        if not top_keys:
            return data  # unknown tool: pass through unfiltered

        filtered: dict = {}
        item_keys = self._ESSENTIAL_LIST_ITEM_FIELDS.get(tool_name)

        for k in top_keys:
            if k not in data:
                continue
            val = data[k]
            # If this is a list of dicts AND we have per-item field rules, trim each item.
            if item_keys and isinstance(val, list) and val and isinstance(val[0], dict):
                filtered[k] = [
                    {ik: item[ik] for ik in item_keys if ik in item}
                    for item in val
                ]
            else:
                filtered[k] = val
        return filtered

    def _run(self, **kwargs: Any) -> str:
        # Drop None AND empty-string kwargs so tool defaults apply. LLMs often pass explicit
        # nulls or "" for optional fields they skipped (e.g. min_rating=""), and "" would fail
        # pydantic float parsing inside the tool (validation error). Treat "" as "not provided".
        call_kwargs = {k: v for k, v in kwargs.items() if v is not None and v != ""}
        try:
            result = self.reg_tool.fn(**call_kwargs)
        except AppError as exc:
            return f"[tool_error:{type(exc).__name__}] {exc}"
        except Exception as exc:  # noqa: BLE001 - never crash the agent loop
            return f"[tool_error:{type(exc).__name__}] {exc}"

        # Filter large outputs to reduce token usage (threshold raised from 2k to 4k;
        # 2k was too aggressive for search results with 10+ merchants).
        if isinstance(result, dict):
            result_str = json.dumps(result, ensure_ascii=False, default=str)
            if len(result_str) > 4000:
                result = self._filter_essential_fields(result)

        return json.dumps(result, ensure_ascii=False, default=str)


def build_crewai_tool(reg_tool: RegisteredTool) -> BaseTool:
    """Wrap a single RegisteredTool as a CrewAI BaseTool."""
    spec = reg_tool.spec
    return RegistryTool(
        name=spec.name,
        description=spec.description,
        args_schema=_args_model(spec),
        reg_tool=reg_tool,
    )


def tools_for_crew_agent(agent_role: str) -> list[BaseTool]:
    """Return the allow-listed tools for an agent, wrapped as CrewAI BaseTools.

    Unknown / unlisted role → empty list (agent runs with no tools, never raises)."""
    return [build_crewai_tool(t) for t in registry.tools_for_agent(agent_role)]
