# Phase 05 — Crew assembly + LLM from settings

**Priority:** P1 · **Status:** ☐ · **Depends:** P01 (adapter) + P04 (yaml)

## Overview
Dựng `CustomerDiscoveryCrew`: đọc yaml → tạo `Agent` (gắn tool qua adapter + LLM từ settings) →
`Task` → `Crew`. Coordinator delegate 1-hop (hierarchical hoặc sequential + manager).

## Key insights
- **LLM = NVIDIA NIM, per-agent 2 tier** (litellm provider `nvidia_nim/`):
  - large `nvidia_nim/meta/llama-3.3-70b-instruct` → customer_coordinator (manager) + restaurant_search.
  - small `nvidia_nim/meta/llama-3.1-8b-instruct` → preference_reasoning + customer_explanation.
  - API key `NVIDIA_NIM_API_KEY` (.env). Base `https://integrate.api.nvidia.com/v1` (override `LLM_BASE_URL`).
- **[EDIT settings.py — additive, hợp lệ với contract]** thêm field (KHÔNG đổi/xoá field cũ):
  ```python
  llm_provider: str = "nvidia_nim"
  nvidia_nim_api_key: str | None = None      # đọc từ NVIDIA_NIM_API_KEY
  llm_model_large: str = "meta/llama-3.3-70b-instruct"
  llm_model_small: str = "meta/llama-3.1-8b-instruct"
  llm_base_url: str | None = None            # None = dùng default NIM hosted
  @property
  def llm_configured(self) -> bool: return bool(self.nvidia_nim_api_key)
  ```
  (Giữ `llm_api_key`/`llm_model` cũ để không vỡ seam; `nvidia_nim_api_key` là nguồn thật cho crew.)
- Adapter P01: `tools_for_crew_agent(role)` trả list BaseTool đúng allow-list.
- Process: **hierarchical**, `manager_agent = customer_coordinator`, agents = 3 specialist. §5.2 "1 hop".
- Dùng `@CrewBase` (chuẩn CrewAI) + factory `build_customer_crew(...) -> Crew` để dễ test/mock.

## Requirements
- `agents/customer/customer_crew.py`: factory dựng Crew.
- LLM builder: `_build_llm(settings) -> LLM` — nếu `not settings.llm_configured` → raise rõ ràng
  (`ConfigError`) HOẶC cho phép inject fake (test). Không để crew chạy live thiếu key mà lỗi mơ hồ.
- Gắn tool: mỗi agent `tools=tools_for_crew_agent(role)`.
- Delegation: coordinator `allow_delegation=True`; specialist `False` (đọc từ yaml).

## Reference impl (đúng format CrewAI @CrewBase)
```python
# backend/agents/customer/customer_crew.py
from crewai import Agent, Crew, Task, Process, LLM
from crewai.project import CrewBase, agent, task, crew
from agents.tool_adapter import tools_for_crew_agent
from core.settings import get_settings
from models.agent import CustomerChatResponse
from models.customer_tasks import SearchTaskOutput, PreferenceTaskOutput, ExplanationTaskOutput

def _nim_llm(model: str) -> LLM:
    s = get_settings()
    if not s.llm_configured:
        raise ConfigError("NVIDIA_NIM_API_KEY chưa set — không thể chạy crew live.")  # core.errors
    return LLM(
        model=f"{s.llm_provider}/{model}",          # vd nvidia_nim/meta/llama-3.3-70b-instruct
        api_key=s.nvidia_nim_api_key,
        base_url=s.llm_base_url,                     # None → default NIM hosted
    )

@CrewBase
class CustomerDiscoveryCrew:
    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    # llm_large/llm_small: test có thể inject fake để không gọi NIM.
    def __init__(self, llm_large: LLM | None = None, llm_small: LLM | None = None):
        s = get_settings()
        self._llm_large = llm_large or _nim_llm(s.llm_model_large)   # 70b: manager + search
        self._llm_small = llm_small or _nim_llm(s.llm_model_small)   # 8b: reasoning + explanation

    @agent
    def customer_coordinator(self) -> Agent:
        return Agent(config=self.agents_config["customer_coordinator"], llm=self._llm_large,
                     tools=tools_for_crew_agent("customer_coordinator"))
    @agent
    def restaurant_search(self) -> Agent:
        return Agent(config=self.agents_config["restaurant_search"], llm=self._llm_large,
                     tools=tools_for_crew_agent("restaurant_search"))
    @agent
    def preference_reasoning(self) -> Agent:
        return Agent(config=self.agents_config["preference_reasoning"], llm=self._llm_small,
                     tools=tools_for_crew_agent("preference_reasoning"))
    @agent
    def customer_explanation(self) -> Agent:
        return Agent(config=self.agents_config["customer_explanation"], llm=self._llm_small,
                     tools=tools_for_crew_agent("customer_explanation"))

    @task
    def search_task(self) -> Task:
        return Task(config=self.tasks_config["search_task"], output_pydantic=SearchTaskOutput)
    @task
    def preference_task(self) -> Task:
        return Task(config=self.tasks_config["preference_task"], output_pydantic=PreferenceTaskOutput)
    @task
    def explanation_task(self) -> Task:
        return Task(config=self.tasks_config["explanation_task"], output_pydantic=ExplanationTaskOutput)

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=[self.restaurant_search(), self.preference_reasoning(), self.customer_explanation()],
            tasks=[self.search_task(), self.preference_task(), self.explanation_task()],
            process=Process.hierarchical,
            manager_agent=self.customer_coordinator(),
            verbose=True,
        )

def build_customer_crew(llm_large: LLM | None = None, llm_small: LLM | None = None) -> Crew:
    return CustomerDiscoveryCrew(llm_large=llm_large, llm_small=llm_small).crew()
```
> `@CrewBase` yêu cầu tên method == key YAML (mismatch → KeyError). `manager_agent` KHÔNG nằm
> trong `agents=[...]` (nó là quản lý riêng). Tool gắn ở agent-level qua adapter (đã lọc allow-list).

## Related files
- CREATE: `backend/agents/customer/customer_crew.py` (theo reference trên)
- CREATE: `backend/models/customer_tasks.py` (output models — xem P04)
- (LLM: đọc từ settings, không tạo file mới.)

## Implementation steps
1. **Edit settings.py** thêm field NVIDIA NIM (xem Key insights) — additive, giữ field cũ.
2. `_nim_llm(model)` → `LLM(model="nvidia_nim/<model>", api_key=nvidia_nim_api_key, base_url=llm_base_url)`.
   Guard `llm_configured` (thiếu key → ConfigError rõ ràng).
3. `@CrewBase` với 4 `@agent`: **coordinator+search dùng `_llm_large` (70b), reasoning+explanation dùng `_llm_small` (8b)**.
   Tool gắn qua `tools_for_crew_agent(role)`.
4. 3 `@task` với `output_pydantic` (SearchTaskOutput / PreferenceTaskOutput / ExplanationTaskOutput).
5. `@crew`: `Process.hierarchical`, `manager_agent=coordinator`, `agents=[3 specialist]`.
6. `build_customer_crew(llm_large=None, llm_small=None)` — cho test inject 2 fake LLM.
7. Verify: dựng crew với 2 fake LLM (monkeypatch) KHÔNG gọi NIM/mạng.

## Todo
- [ ] Edit settings.py: nvidia_nim_api_key, llm_model_large/small, llm_base_url, llm_provider="nvidia_nim", llm_configured
- [ ] customer_crew.py (@CrewBase agents/tasks/crew factory)
- [ ] 2 LLM builder NIM + gán per-agent (70b manager+search, 8b reasoning+explanation)
- [ ] guard llm_configured (thiếu NVIDIA_NIM_API_KEY → ConfigError)
- [ ] tool binding qua adapter + output_pydantic per task
- [ ] hierarchical, manager=coordinator, specialist no-delegation
- [ ] dựng crew với 2 fake LLM không cần key/mạng

## Success criteria
- `build_customer_crew()` trả `Crew`: manager=coordinator(70b), 3 specialist đúng tier LLM.
- customer_coordinator + restaurant_search → model `nvidia_nim/meta/llama-3.3-70b-instruct`;
  preference_reasoning + customer_explanation → `nvidia_nim/meta/llama-3.1-8b-instruct`.
- Mỗi agent chỉ có tool trong allow-list của nó.
- Thiếu `NVIDIA_NIM_API_KEY` → ConfigError rõ ràng, không traceback mơ hồ.
- Test dựng crew với fake LLM pass (no network).

## Risks
- **Verify litellm provider string** `nvidia_nim/meta/llama-3.3-70b-instruct` + env `NVIDIA_NIM_API_KEY`
  đúng bản litellm crewai kéo về (nếu sai → `crewai-skills:ask-docs` hoặc litellm docs). Self-host NIM thì set `LLM_BASE_URL`.
- CrewAI 1.15.5 hierarchical/manager_agent signature → verify.
- Hierarchical manager (70b) gọi LLM nhiều → cost. max_iter chặt (đã set ở agents.yaml).

## Next
→ Phase 06 gọi `build_customer_crew(...).kickoff(inputs)` trong customer_flow + persist.
