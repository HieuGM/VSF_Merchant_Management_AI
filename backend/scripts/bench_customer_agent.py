"""Benchmark Customer Agent — end-to-end timing + quality over /chat/stream.

Measures, per query:
  - total_ms        submit -> run_finished (perceived wall-clock)
  - ttft_answer_ms  submit -> first answer_delta (time-to-first-token of the answer)
  - search_ms       server-side search_task duration (from agent_events, authoritative)
  - preference_ms   server-side preference_task duration (only when preference signals exist)
  - explain_ms      first answer_delta -> run_finished (the separate DeepSeek stream)
  - results_count, answer chars, token-chunk count
Then aggregates: slowest agent ranking, median TTFT/total.

Usage (env ai_restaurant):
  PYTHONUTF8=1 PYTHONPATH=backend python scripts/bench_customer_agent.py
Add --with-location to pin HN district coords to nearby queries.

Caveat: explanation runs as a DIRECT DeepSeek call (not a CrewAI task) in the streaming
path, so it has NO agent_events row — explain_ms is measured client-side (SSE timestamps).
"""
from __future__ import annotations

import io
import json
import statistics
import sys
import time
from dataclasses import dataclass, field

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

import requests

API = "http://localhost:8000/api/v1/agent/customer/chat/stream"

# HN district coords (truthful — used so nearby_merchant_search filters the right city).
LOC = {
    "Cầu Giấy": (21.036, 105.790),
    "Đống Đa": (21.004, 105.833),
    "Hà Đông": (20.960, 105.764),
    "Gia Lâm": (21.028, 105.948),
}


@dataclass
class Case:
    id: str
    query: str
    cat: str
    loc: tuple[float, float] | None = None


CASES: list[Case] = [
    Case("Q1", "Tìm quán phở gần Cầu Giấy", "happy", LOC["Cầu Giấy"]),
    Case("Q2", "Tìm quán cơm gần Cầu Giấy, giá dưới 50k, rating trên 4 sao", "happy", LOC["Cầu Giấy"]),
    Case("Q3", "Quán bún chả ngon nhất khu Đống Đa", "search+explain", LOC["Đống Đa"]),
    Case("Q4", "Tìm quán ăn chay ở Hà Đông", "pref-signal", LOC["Hà Đông"]),
    Case("Q5", "Gợi ý quán cay ngon cho buổi tối ở Cầu Giấy", "pref-signal", LOC["Cầu Giấy"]),
    Case("Q6", "Tìm quán trà sữa gần đây", "nearby(bug-case)", LOC["Gia Lâm"]),
    Case("Q7", "Tìm quán sushi Nhật Bản chính gốc ở Mộc Châu", "zero-result", None),
    Case("Q8", "Thời tiết Hà Nội hôm nay thế nào?", "out-of-domain", None),
    Case("Q9", "tim cho an ngon o cau giay gia duoi 50k nha", "no-diacritics", None),
    Case("Q10", "Tìm chỗ ăn ngon", "missing-slot", None),
]


@dataclass
class Timing:
    case: Case
    total_ms: float = 0.0
    ttft_ms: float | None = None
    explain_ms: float | None = None
    search_ms: float | None = None          # server-side (DB)
    preference_ms: float | None = None      # server-side (DB)
    preference_ran: bool = False
    results: int = 0
    suggestions: int = 0
    answer_chars: int = 0
    answer_text: str = ""
    top_results: list[str] = field(default_factory=list)  # top merchant names
    suggestion_fields: list[str] = field(default_factory=list)
    token_chunks: int = 0
    tools: dict[str, float] = field(default_factory=dict)  # tool_name -> server ms (sum)
    trace_id: str | None = None
    error: str | None = None
    warnings: list[str] = field(default_factory=list)  # CustomerChatResponse.warnings


def _server_durations(trace_id: str) -> tuple[float | None, float | None, dict[str, float]]:
    """Query agent_events for this trace -> (search_task_ms, preference_task_ms, {tool: ms})."""
    from database.connection import engine
    from sqlalchemy import text
    sql = text(
        "SELECT event_type, task_name, tool_name, duration_ms FROM agent_events "
        "WHERE trace_id=:tid AND duration_ms IS NOT NULL"
    )
    search_ms = pref_ms = None
    tools: dict[str, float] = {}
    with engine.connect() as c:
        for et, tn, tn_tool, dur in c.execute(sql, {"tid": trace_id}):
            if et == "task_finished" and tn == "search_task":
                search_ms = float(dur)
            elif et == "task_finished" and tn == "preference_task":
                pref_ms = float(dur)
            elif et == "tool_finished" and tn_tool:
                tools[tn_tool] = tools.get(tn_tool, 0.0) + float(dur)
    return search_ms, pref_ms, tools


def run_one(case: Case) -> Timing:
    """POST one query to /chat/stream; timestamp every SSE event."""
    t = Timing(case=case)
    payload = {"message": case.query, "user_id": "bench", "session_id": "bench"}
    if case.loc:
        payload["location"] = {"lat": case.loc[0], "lng": case.loc[1]}
    t0 = time.perf_counter()

    try:
        with requests.post(API, json=payload, stream=True, timeout=180) as resp:
            event_type = None
            for raw in resp.iter_lines(decode_unicode=True):
                if not raw:
                    continue
                line = raw.strip()
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data:"):
                    data = json.loads(line[5:].strip())
                    _consume(t, event_type, data, t0)
                    event_type = None
    except Exception as exc:  # noqa: BLE001
        t.error = f"{type(exc).__name__}: {exc}"
        return t

    # Authoritative per-task durations from DB.
    if t.trace_id:
        try:
            t.search_ms, t.preference_ms, t.tools = _server_durations(t.trace_id)
        except Exception as exc:  # noqa: BLE001
            t.error = t.error or f"db: {exc}"
    return t


def _consume(t: Timing, event: str | None, data: dict, t0: float) -> None:
    now = (time.perf_counter() - t0) * 1000.0
    if event == "run_started":
        pass
    elif event == "task_finished":
        if data.get("task") == "preference_task" or "preference" in (data.get("agent") or ""):
            t.preference_ran = True
    elif event == "answer_delta":
        if t.ttft_ms is None:
            t.ttft_ms = now
        t.token_chunks += 1
        t.answer_chars += len(data.get("answer_delta", "") or "")
    elif event == "run_finished":
        t.total_ms = now
        if t.ttft_ms is not None:
            t.explain_ms = now - t.ttft_ms
        t.trace_id = data.get("trace_id")
        t.answer_text = (data.get("answer") or "").strip()
        t.answer_chars = len(t.answer_text)
        res = data.get("results") or []
        t.results = len(res)
        t.top_results = [
            f"{r.get('name')} ({r.get('distance_km')}km, {r.get('avg_rating')}★)"
            for r in res[:3]
        ]
        sugg = data.get("preference_suggestions") or []
        t.suggestions = len(sugg)
        t.suggestion_fields = [str(s.get("field")) for s in sugg[:4]]
        t.warnings = list(data.get("warnings") or [])
    elif event == "error":
        t.error = str(data)


def _pct(x: float | None) -> str:
    return f"{x/1000:5.2f}s" if x is not None else "    -  "


def main() -> None:
    print("=" * 92)
    print("CUSTOMER AGENT BENCHMARK — /chat/stream (FPT hybrid: gpt-oss + DeepSeek)")
    print("=" * 92)
    results: list[Timing] = []
    for c in CASES:
        print(f"\n→ {c.id} [{c.cat}] {c.query!r}" + (f"  @ {c.loc}" if c.loc else ""))
        t = run_one(c)
        results.append(t)
        if t.error and t.total_ms == 0:
            print(f"   ERROR: {t.error}")
            continue
        pref = f"pref={_pct(t.preference_ms)}({'ran' if t.preference_ran else 'SKIP'})"
        print(f"   total={_pct(t.total_ms)}  ttft(answer)={_pct(t.ttft_ms)}  "
              f"search={_pct(t.search_ms)}  {pref}  explain(stream)={_pct(t.explain_ms)}")
        print(f"   results={t.results}  suggestions={t.suggestions}  "
              f"answer={t.answer_chars}chars  tokens={t.token_chunks}")
        if t.top_results:
            print(f"   top: {' | '.join(t.top_results)}")
        if t.suggestion_fields:
            print(f"   suggestions: {', '.join(t.suggestion_fields)}")
        if t.answer_text:
            print(f"   ANSWER: {t.answer_text[:280]}")
        if t.warnings:
            print(f"   WARNINGS: {t.warnings}")
        if t.tools:
            top = ", ".join(f"{k}={v:.0f}ms" for k, v in
                            sorted(t.tools.items(), key=lambda x: -x[1])[:4])
            print(f"   tools(server): {top}")
        if t.error:
            print(f"   (note: {t.error})")

    _dump_json(results)

    _summarize(results)


def _dump_json(results: list[Timing]) -> None:
    """Persist the full run (answers + timings) for the report."""
    from pathlib import Path
    out = Path(__file__).resolve().parent.parent.parent / "plans" / "reports" / "bench-customer-agent-results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for r in results:
        rows.append({
            "id": r.case.id, "query": r.case.query, "cat": r.case.cat,
            "total_s": round(r.total_ms / 1000, 2),
            "ttft_s": round(r.ttft_ms / 1000, 2) if r.ttft_ms else None,
            "search_s": round(r.search_ms / 1000, 2) if r.search_ms else None,
            "preference_s": round(r.preference_ms / 1000, 2) if r.preference_ms else None,
            "preference_ran": r.preference_ran,
            "explain_s": round(r.explain_ms / 1000, 2) if r.explain_ms else None,
            "results": r.results, "top_results": r.top_results,
            "suggestions": r.suggestion_fields,
            "answer": r.answer_text, "error": r.error, "trace_id": r.trace_id,
        })
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  [saved] {out}")


def _summarize(results: list[Timing]) -> None:
    ok = [r for r in results if r.total_ms and not (r.error and r.total_ms == 0)]
    print("\n" + "=" * 92)
    print("AGGREGATE")
    print("=" * 92)

    def med(key):
        vals = [getattr(r, key) for r in ok if getattr(r, key) is not None]
        return statistics.median(vals) if vals else None

    for key, label in [("total_ms", "total"), ("ttft_ms", "ttft(answer)"),
                       ("search_ms", "search_task"), ("preference_ms", "preference_task"),
                       ("explain_ms", "explain(stream)")]:
        m = med(key)
        print(f"  median {label:18s}: {_pct(m)}")

    pref_ran = sum(1 for r in ok if r.preference_ran)
    print(f"\n  preference ran on {pref_ran}/{len(ok)} queries "
          f"(skip-preference optimization active on the rest)")

    # Stream-reliability: count queries where the FPT explanation stream dropped/timed out
    # and surfaced the explanation_stream_interrupted warning (target: 0 after the fix).
    interrupted = [r for r in results
                   if any("explanation_stream_interrupted" in w for w in r.warnings)]
    print(f"  explanation_stream_interrupted: {len(interrupted)}/{len(results)} queries "
          f"(FPT stream drop) -> {sorted(r.case.id for r in interrupted) or 'NONE'}")

    # Slowest agent ranking (server-side medians across queries where it ran).
    print("\n  Slowest-agent ranking (server-side median per task):")
    ranks = []
    for key, label in [("search_ms", "search_task (gpt-oss)"),
                       ("preference_ms", "preference_task (gpt-oss)"),
                       ("explain_ms", "explanation (DeepSeek stream)")]:
        m = med(key)
        if m is not None:
            ranks.append((label, m))
    for label, m in sorted(ranks, key=lambda x: -x[1]):
        print(f"    {label:34s}: {_pct(m)}")

    print("\n  Per-query totals:")
    for r in results:
        flag = "  " if not r.error else "!!"
        print(f"   {flag} {r.case.id} total={_pct(r.total_ms)} ttft={_pct(r.ttft_ms)} "
              f"results={r.results} [{r.case.cat}]")


if __name__ == "__main__":
    main()
