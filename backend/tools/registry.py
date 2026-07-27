"""Tool registry core (design §9.1) — FROZEN SEAM (Feature F-01).

Framework-agnostic on purpose: metadata + callable + allow-list enforcement, with NO
hard CrewAI import so unit tests stay light. A thin CrewAI 1.15.5 adapter can wrap
`registry.get()` later.

Tool packages are split by ownership so the two devs never import each other's modules:
  tools/shared/    — frozen cross-domain tools (Phase 0)
  tools/customer/  — Dev A tools
  tools/merchant/  — Dev B tools
Each vertical discovers ONLY its own packages, e.g.:
  registry.auto_discover("tools.shared"); registry.auto_discover("tools.customer")
"""
from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from tools.allow_list import AGENT_TOOL_ALLOW_LIST


class ToolSpec(BaseModel):
    """Registry metadata — every field from design §9.1."""

    name: str
    version: str = "1.0"
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    allowed_agents: tuple[str, ...] = ()
    timeout_seconds: float = 10.0
    retry_policy: str = "none"
    cache_policy: str = "none"
    has_side_effect: bool = False
    source_kind: str = "real"
    # Optional explicit CrewAI args schema. When set, the CrewAI adapter (agents/
    # tool_adapter.py) uses it directly so the LLM gets rich field descriptions;
    # otherwise the adapter derives a loose model from `input_schema`. Additive
    # optional field — does not change existing registration behaviour.
    args_schema: type[BaseModel] | None = None
    # Required argument names the adapter enforces BEFORE calling the tool: if the LLM
    # omits any (e.g. calls nearby_merchant_search with no lat/lng because the query had
    # no coords), the adapter returns a friendly error nudging it to a better tool —
    # instead of letting the call fail with an opaque pydantic message. Defaults to none.
    required_args: tuple[str, ...] = ()


class RegisteredTool(BaseModel):
    spec: ToolSpec
    fn: Callable[..., Any]

    model_config = {"arbitrary_types_allowed": True}


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, spec: ToolSpec, fn: Callable[..., Any]) -> None:
        if spec.name in self._tools:
            raise ValueError(f"tool already registered: {spec.name}")
        # Cross-check allow-list so registration and §5.4 never drift.
        declared = tuple(
            a for a, tools in AGENT_TOOL_ALLOW_LIST.items() if spec.name in tools
        )
        if spec.allowed_agents and set(spec.allowed_agents) != set(declared) and declared:
            raise ValueError(
                f"allowed_agents for '{spec.name}' diverge from allow_list.py: "
                f"{spec.allowed_agents} vs {declared}"
            )
        self._tools[spec.name] = RegisteredTool(spec=spec, fn=fn)

    def get(self, name: str) -> RegisteredTool:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        return self._tools[name]

    def names(self) -> list[str]:
        return sorted(self._tools)

    def is_allowed(self, agent: str, tool_name: str) -> bool:
        return tool_name in AGENT_TOOL_ALLOW_LIST.get(agent, ())

    def tools_for_agent(self, agent: str) -> list[RegisteredTool]:
        return [
            self._tools[name]
            for name in AGENT_TOOL_ALLOW_LIST.get(agent, ())
            if name in self._tools
        ]

    def auto_discover(self, package_name: str) -> None:
        """Import every submodule of a domain package and call its `register(registry)`.

        Each vertical owns its own package (e.g. `tools`), so discovery never forces the
        two devs to co-edit a manifest. Modules opt in by exposing `register(registry)`."""
        package = importlib.import_module(package_name)
        for _, mod_name, _ in pkgutil.iter_modules(package.__path__):
            module = importlib.import_module(f"{package_name}.{mod_name}")
            register_fn = getattr(module, "register", None)
            if callable(register_fn):
                register_fn(self)


# Process-wide registry. Verticals call `registry.auto_discover("tools")` at startup.
registry = ToolRegistry()
