# Phase 03 — Weather Override Threading

## Context Links
- Plan: `plans/260730-customer-agent-memory-wireup/plan.md`
- Flow: `backend/flows/customer_flow.py`
- Request model: `backend/models/agent.py` (L92 `weather_override`)
- Weather tool: `backend/tools/customer/weather_tools.py` (exists, registered, allow-listed)
- Prompts: `backend/agents/customer/config/tasks.yaml` (`preference_task`)

## Overview
- Priority: P2 | Status: pending | Effort: 1.5h
- Thread `CustomerChatRequest.weather_override` (currently dropped at the route) into preference reasoning + the streamed explanation. Independent of 01/02/04.

## Key Insights
- `weather_override: dict|None` ALREADY exists on `CustomerChatRequest` (L92) — purely dropped: routes never forward it, flow signatures lack it, `_build_inputs` never sets it.
- `get_weather_context(lat,lng)` tool works + is allow-listed for `preference_reasoning`; agent calls it itself. Override is for when the CLIENT/test harness supplies weather (no coords, or forced scenario TC-06). Override should take PRECEDENCE so the agent skips the tool call.
- `propose_profile_delta(weather=...)` already accepts a weather dict — the agent passes whatever weather it gathered. Giving the agent the override via prompt makes it forward the right value.
- `_build_explanation_messages` already renders a `weather_summary` from the preference task output — but in the SSE path the preference crew's weather_summary must reflect the override too.
- Shape of override (TC-06 "mưa"): `{"is_rain": true, "summary": "trời mưa", ...}` — already what `preference_service.propose_deltas` reads (`weather.get("is_rain")`).

## Requirements
- F1: Route forwards `request.weather_override` → both flow entry points.
- F2: `_build_inputs` adds `{weather_hint}` = formatted Vietnamese string from override, or `""` when absent.
- F3: `preference_task` prompt references `{weather_hint}` and instructs: if present, use it INSTEAD OF calling `get_weather_context`.
- F4: `_build_explanation_messages` appends the override summary to the weather signal bit (so streamed answer reflects rain reasoning even on the no-pref-crew path).
- F5: No-op when `weather_override is None` (regression-safe; agent still calls the tool as today).

## Architecture
```
route → flow.search_restaurants[_stream](..., weather_override=...)
_build_inputs(..., weather_override) -> "weather_hint": _format_weather_hint(weather_override)
_format_weather_hint(d) -> str   # "" when None
preference_task prompt: {weather_hint} block
_build_explanation_messages(..., weather_override): append hint to sig_bits
```

## Related Code Files
- MODIFY `backend/routes/customer_agent_routes.py`:
  - `/chat` + `/chat/stream`: add `weather_override=request.weather_override` to flow call / params.
- MODIFY `backend/flows/customer_flow.py`:
  - `search_restaurants` + `search_restaurants_stream` signatures: add `weather_override: dict | None = None`.
  - `_build_inputs`: add `weather_override` param + `"weather_hint"` key.
  - `_build_explanation_messages`: add `weather_override` param; if present, prepend to `sig_bits`.
  - ADD `_format_weather_hint(d) -> str`.
- MODIFY `backend/agents/customer/config/tasks.yaml`:
  - `preference_task.description`: in step 3, add `{weather_hint}` precedence rule.
- CREATE / DELETE: none.

## Implementation Steps
1. Add `_format_weather_hint(d)`:
   - None → `""`.
   - Else: `f"THỜI TIẾT (từ client, DÙNG THAY vì gọi get_weather_context): {d.get('summary') or _summarize(d)}"` where `_summarize` maps `is_rain`/temp to a short VN phrase. Keep minimal.
2. `_build_inputs`: accept `weather_override`, set `"weather_hint": _format_weather_hint(weather_override)`.
3. `preference_task` step 3 becomes:
   ```
   3. Thời tiết: {weather_hint}
      (Nếu weather_hint rỗng VÀ có toạ độ → gọi get_weather_context({lat},{lng}). Nếu weather_hint có giá trị → DÙNG nó, KHÔNG gọi lại tool.)
   ```
4. `_build_explanation_messages`: accept `weather_override`; if present, `sig_bits.insert(0, f"thời tiết (client): {summary}")` so the rain rationale flows into the streamed answer.
5. Routes: forward `weather_override` on both endpoints.
6. py_compile `customer_flow.py`, `customer_agent_routes.py`; reload YAML sanity (no broken braces).

## Todo List
- [ ] `_format_weather_hint` helper
- [ ] Thread param through 2 flow entry points
- [ ] Add `weather_hint` to `_build_inputs`
- [ ] Update `preference_task` prompt (precedence rule)
- [ ] Add override to `_build_explanation_messages`
- [ ] Forward from both routes
- [ ] py_compile + YAML brace check

## Success Criteria
- TC-06: `weather_override={"is_rain":true}` + profile → preference crew proposes nearby/distance delta with rain rationale; streamed answer mentions rain.
- No-override request → preference agent still calls `get_weather_context` when coords present (unchanged).
- `/chat/stream` TTFT unchanged (hint is a few tokens).

## Risk Assessment
- **R1 Override ignored by agent**: best-effort prompt control; if agent still calls the tool, the tool result just confirms — not correctness-breaking. Acceptable.
- **R2 Malformed override dict**: `_format_weather_hint` must tolerate missing keys → fall back to `""` or raw repr. Never raise.
- **R3 Double-application**: guard — explanation uses override summary, not both override + tool output.

## Security Considerations
- Override is trusted client/test input feeding a prompt — same trust boundary as `message`. No new surface; truth-first rules still govern output.

## Next Steps
- Phase 05 asserts TC-06 + TC-29 (explicit weather override of profile).
