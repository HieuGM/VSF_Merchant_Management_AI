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

    def _run(self, **kwargs: Any) -> str:
        # Drop None kwargs so tool defaults apply (LLM often passes explicit nulls).
        call_kwargs = {k: v for k, v in kwargs.items() if v is not None}
        try:
            result = self.reg_tool.fn(**call_kwargs)
        except AppError as exc:
            return f"[tool_error:{type(exc).__name__}] {exc}"
        except Exception as exc:  # noqa: BLE001 - never crash the agent loop
            return f"[tool_error:{type(exc).__name__}] {exc}"
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
