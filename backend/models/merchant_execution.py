"""Execution plan contracts produced by the coordinator.

The coordinator is the only entity that produces an ExecutionPlan.
Runtime code validates and executes it as-is — it never re-interprets
user prose to change mode, capability, or task content.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


CapabilityName = Literal[
    "owner",
    "market",
    "policy",
    "review",
    "cohort",
]


class PlannedTask(BaseModel):
    """One unit of work assigned to a single registered capability."""

    model_config = ConfigDict(extra="forbid")

    capability: CapabilityName
    instruction: str = Field(min_length=1, max_length=600)


class ExecutionPlan(BaseModel):
    """A bounded, validated coordinator plan.

    Validation rules (enforced by Pydantic validators):
      direct       -> exactly 1 task
      parallel     -> 2 to 4 tasks with distinct capabilities
      hierarchical -> 2 to 4 tasks (capabilities may repeat across agents)
      fact         -> direct only
      analysis     -> direct or hierarchical; parallel may return summary only
    """

    model_config = ConfigDict(extra="forbid")

    mode: Literal["direct", "parallel", "hierarchical"]
    tasks: list[PlannedTask] = Field(min_length=1, max_length=4)
    response_type: Literal["fact", "summary", "analysis"]

    @model_validator(mode="after")
    def validate_plan(self) -> "ExecutionPlan":
        tasks = self.tasks
        mode = self.mode
        response_type = self.response_type

        if mode == "direct":
            if len(tasks) != 1:
                raise ValueError(
                    f"direct mode requires exactly 1 task, got {len(tasks)}"
                )

        elif mode == "parallel":
            if len(tasks) < 2:
                raise ValueError(
                    f"parallel mode requires 2-4 tasks, got {len(tasks)}"
                )
            capabilities = [t.capability for t in tasks]
            if len(capabilities) != len(set(capabilities)):
                raise ValueError(
                    "parallel mode tasks must have distinct capabilities"
                )

        elif mode == "hierarchical":
            if len(tasks) < 2:
                raise ValueError(
                    f"hierarchical mode requires 2-4 tasks, got {len(tasks)}"
                )

        # response_type constraints
        if response_type == "fact" and mode != "direct":
            raise ValueError(
                f"response_type 'fact' is only allowed with direct mode, got mode='{mode}'"
            )
        if response_type == "analysis" and mode == "parallel":
            raise ValueError(
                "response_type 'analysis' is not allowed with parallel mode; use 'summary'"
            )

        return self
