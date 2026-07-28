# Answer Streaming — Implementation Report

**Date:** 2026-07-28 | **Branch:** dev-a | **Status:** Implemented + live-verified (with caveat)

## Goal
Stream the explanation answer token-by-token over SSE to cut perceived wait (was: blank wait ~34s → full dump).

## What was built

**Backend:**
- `customer_crew.py`: `build_customer_crew(mode=...)` — "full" (3-task, blocking) | "search" | "preference" (1-task). Explanation dropped `output_pydantic` (free-text). Added `explanation_prompt_pieces()` (loads persona from agents/tasks YAML — single source).
- `customer_flow.py`: `search_restaurants_stream()` — runs **search + preference as two parallel single-task crews** (ThreadPoolExecutor + `copy_context` so run_scope/tool_call_scope/stream_scope propagate), then streams the explanation via a **direct DeepSeek streaming call** (`_stream_explanation_tokens`), yielding `answer_delta` per token + terminal `run_finished`. Helpers: `_build_explanation_messages` (grounds answer w/ candidates+signals), `_safe_format`, `_strip_answer_artifacts` (strips label/JSON residue), `_explanation_raw_answer` (blocking path).
- `customer_agent_routes.py`: `/chat/stream` worker iterates the flow generator.
- `tasks.yaml`: explanation `expected_output` → plain text + positive few-shot example.
- **FE** `use-customer-chat.ts`: `answer_delta` accumulate (replace→append, backward-compat); `run_finished` truthiness-guard reconcile; error/catch preserve partial answer.

## Critical deviation from plan
**CrewAI `Crew(stream=True)` is broken with tool-calling agents on FPT** (verified): streamed tool-call deltas come back empty → "Invalid response from LLM call". Affects search+preference (both use tools). So the plan's crew-level streaming was replaced with: search+preference non-streaming (reliable) + explanation via separate direct DeepSeek stream (plain-text streaming is reliable on FPT).

Also: a 2-task async crew can't satisfy CrewAI's "end with at most one async task" rule without serializing → ran search+preference as two parallel single-task crews instead.

## Live verification (real FPT, docker postgres up)
- Streaming: **works** — 72-83 `answer_delta` frames, `run_finished` received, results=3, consistent across 4 runs.
- Blocking `/chat`: works — good Vietnamese answers, results.
- Direct FPT streaming (gpt-oss-20b + DeepSeek): confirmed works (18 + 107 chunks).

## ⚠️ Latency caveat (honest)
Streaming TTFT **~19-21s**; blocking total **~8-15s**. Streaming is **NOT faster** than blocking on this stack:
- Answer can't start until search+preference complete (explanation needs their output to be grounded).
- **Preference task dominates** (~15s, 4 tool rounds) — that's the real bottleneck, not parallelism.
- CrewAI streaming+tools being broken blocks the "stream all 3 concurrently" path that would've given TTFT ~5s.

**Real perceived-latency win = progress events** (tool_started/finished → "Đang tìm quán…"), already shipping via StreamingListener. Answer token-streaming adds a typing effect at the end (~1s) — marginal.

## Review defects fixed (adversarial workflow, 10 confirmed)
Identity-match filter (moot after rearch), FE `??`→`||` reconcile, error-handler preserve partial, build-inside-try observability, `_explanation_raw_answer` object-repr bug, mock-crew contracts (integration + 2 scripts), tasks.yaml few-shot, `_safe_format`. 3 deferred: backpressure, client-disconnect cancel, (narration-leak — moot, explanation no longer tool-calls).

## Tests
71 backend tests pass (unit+integration+contract). FE build clean (tsc 0 err), oxlint clean.

## Recommended next (actual speed wins, from research report)
1. **Skip preference_task for pure-discovery queries** ("phở gần tôi") → cuts TTFT to ~search+DeepSeek (~7s). Biggest lever — preference is the bottleneck.
2. **Prompt-cache structuring** (DeepSeek context cache auto) — trim backstory, static prefix.
3. **Tool/semantic cache** for repeat queries.

## Unresolved
- Q1: Ship streaming as-is (functional, slight latency cost) or revert to blocking-only until skip-preference lands? Streaming's value here is UX (typing + progress), not speed.
- Q2: Commit this work?
