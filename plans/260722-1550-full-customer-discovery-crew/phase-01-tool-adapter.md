# Phase 01 — Adapter Registry→CrewAI BaseTool (CORE ENABLER)

**Priority:** P0 (blocker cho mọi thứ) · **Status:** ☐ · **Depends:** none

## Overview
Cầu nối duy nhất giữa registry (framework-agnostic) và CrewAI. Bọc `RegisteredTool`
(`ToolSpec` + callable) thành `crewai.tools.BaseTool`, enforce allow-list runtime. Đây là
điểm coupling DUY NHẤT với CrewAI → tool/service vẫn test được không cần CrewAI.

## Key insights (CrewAI 1.15.5 format — verified from crewai-skills)
- `tools/registry.py` đã có `registry.tools_for_agent(agent)` + `is_allowed(agent, tool)`.
- **BaseTool contract (bắt buộc đúng):** subclass `crewai.tools.BaseTool` với `name: str`,
  `description: str`, `args_schema: Type[BaseModel]`, method `_run(self, **fields) -> str`.
  Tên field trong `_run` PHẢI khớp field của `args_schema`.
- **[QUAN TRỌNG] Tool phải TRẢ VỀ STRING** — CrewAI feed output tool vào LLM dưới dạng text.
  Tool nội bộ của ta trả `dict` → adapter phải `json.dumps(result, ensure_ascii=False, default=str)`.
- **Lỗi → trả string, KHÔNG raise** (best practice CrewAI: `return f"[error] {msg}"`), tránh crash loop agent.
- `ToolSpec.input_schema` là `dict[str,str]` (informal). CrewAI cần `args_schema` Pydantic thật →
  adapter build model động từ input_schema (field + description), HOẶC ToolSpec khai `args_schema` optional.
- KHÔNG hard-import crewai ở registry.py (giữ frozen). Import crewai CHỈ trong file adapter.
- `description` của BaseTool = `ToolSpec.description` (LLM dựa vào đây chọn tool → giữ rõ ràng).

## Requirements
- `build_crewai_tool(reg_tool: RegisteredTool) -> BaseTool` — wrap 1 tool.
- `tools_for_crew_agent(agent_role: str) -> list[BaseTool]` — trả list tool 1 agent được phép
  (đọc allow-list qua `registry.tools_for_agent`), đã wrap.
- Guard: nếu agent role không có trong allow-list → trả `[]` (không raise, agent chạy không tool).
- Wrapper `_run(**kwargs)` gọi callable, emit event `tool_started`/`tool_finished` (optional hook
  — nhưng CrewAI event bus tự bắn tool events; giữ đơn giản, để listener Phase 06 bắt).
- Map lỗi tool → CrewAI tool error (trả string message, không crash crew).

## Related files
- CREATE: `backend/agents/tool_adapter.py` (<150 dòng)
- (optional) EDIT `backend/tools/registry.py`: thêm field `args_schema: type[BaseModel] | None = None`
  vào `ToolSpec` NẾU chọn hướng schema tường minh (contract-change → cần note, nhưng đây là
  additive optional field, low-risk).

## Reference implementation (đúng format CrewAI 1.15.5)
```python
# backend/agents/tool_adapter.py
from __future__ import annotations
import json
from typing import Any, Type
from pydantic import BaseModel, create_model
from crewai.tools import BaseTool
from core.errors import AppError
from tools.registry import RegisteredTool, registry

# map string hint trong input_schema -> python type (lỏng, optional)
_TYPE_HINTS = {"str": str, "int": int, "float": float, "bool": bool}

def _args_model(spec) -> Type[BaseModel]:
    if getattr(spec, "args_schema", None):
        return spec.args_schema
    fields: dict[str, Any] = {}
    for fname, hint in spec.input_schema.items():
        base = next((t for k, t in _TYPE_HINTS.items() if k in hint), str)
        required = "required" in hint
        default = ... if required else None
        ann = base if required else (base | None)
        fields[fname] = (ann, default)
    return create_model(f"{spec.name}_Args", **fields)  # type: ignore

class RegistryTool(BaseTool):
    reg_tool: RegisteredTool
    def _run(self, **kwargs: Any) -> str:
        try:
            result = self.reg_tool.fn(**{k: v for k, v in kwargs.items() if v is not None})
            return json.dumps(result, ensure_ascii=False, default=str)
        except AppError as e:
            return f"[tool_error:{type(e).__name__}] {e}"

def build_crewai_tool(reg_tool: RegisteredTool) -> BaseTool:
    spec = reg_tool.spec
    return RegistryTool(
        name=spec.name, description=spec.description,
        args_schema=_args_model(spec), reg_tool=reg_tool,
    )

def tools_for_crew_agent(agent_role: str) -> list[BaseTool]:
    return [build_crewai_tool(t) for t in registry.tools_for_agent(agent_role)]
```
> Lưu ý: `RegistryTool` khai `reg_tool` là field Pydantic (BaseTool là pydantic model) —
> cần `model_config = {"arbitrary_types_allowed": True}` nếu Pydantic phàn nàn về `RegisteredTool`.

## Implementation steps
1. Tạo `agents/tool_adapter.py` theo reference trên.
2. Verify `_args_model` sinh đúng field optional/required từ `input_schema`.
3. `_run` trả STRING (json.dumps), lỗi `AppError` → string (không raise).
4. Chạy `python -c "import agents.tool_adapter"` (PYTHONPATH=backend) verify import sạch, no LangChain.

## Todo
- [ ] `tool_adapter.py` với `RegistryTool`, `build_crewai_tool`, `tools_for_crew_agent`
- [ ] Dynamic Pydantic args schema từ `input_schema`
- [ ] Error mapping AppError → tool string (không crash crew)
- [ ] Import check pass, no LangChain pulled

## Success criteria
- `tools_for_crew_agent("restaurant_search")` trả 2 BaseTool (`merchant_search`, `nearby_merchant_search`).
- `tools_for_crew_agent("unknown")` trả `[]`.
- Gọi `._run()` 1 tool trả đúng dict như callable gốc.

## Risks
- CrewAI 1.15.5 `BaseTool` API khác bản mới → verify signature (`ck:docs-seeker` crewai nếu cần).
- args_schema quá lỏng → LLM truyền sai kiểu. Chấp nhận ở P1, siết ở P3 nếu tool cần.

## Next
→ Phase 02 (data/providers) song song được; Phase 05 (crew) dùng `tools_for_crew_agent`.
