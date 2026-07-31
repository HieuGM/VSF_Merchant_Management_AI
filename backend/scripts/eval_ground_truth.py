"""Measure Customer Agent on ground_truth_customer.json — skip coordinator-only cases.

For each kept case: seed user_profile (when GT provides one) + replay prior user turns
(faithful multiturn/memory/anaphora), then POST the test turn to /chat/stream and capture
PER-STEP timing (client SSE timestamps + server-side agent_events durations) plus
answer/results/suggestions/warnings. Dumps JSON for the quality-eval workflow.

Skip rule (user choice A): 12 coordinator-only cases —
  missing_slot (TC-03/04/05/37/44), out_of_scope_adjacent (TC-30/31/32/33/40),
  contradiction-flag (TC-12/13).

Usage (env ai_restaurant, server on :8000 with the fix):
  PYTHONUTF8=1 PYTHONPATH=backend python backend/scripts/eval_ground_truth.py

Limitations (faithfulness): current_datetime (server uses real now()), merchant_evidence
(explanation_specific — no endpoint injection) are not reproduced; noted per-case.
"""
from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

import requests

API_STREAM = "http://localhost:8000/api/v1/agent/customer/chat/stream"
API_CHAT = "http://localhost:8000/api/v1/agent/customer/chat"
GT_PATH = Path(__file__).resolve().parent.parent.parent / "ground_truth_customer.json"
OUT_PATH = Path(__file__).resolve().parent.parent.parent / "plans" / "reports" / "gt-eval-results.json"

# Per-run stamp → unique session/user ids (see run_case). Prevents stale chat_messages/profile
# from previous bench runs leaking into this run via _load_recent_turns/_load_profile.
_RUN_STAMP = str(int(time.time()))

# Coordinator-only cases the current (coordinator-less) system can't be fairly judged on.
SKIP_IDS = {"TC-03", "TC-04", "TC-05", "TC-37", "TC-44",      # missing_slot
            "TC-30", "TC-31", "TC-32", "TC-33", "TC-40",       # out_of_scope_adjacent
            "TC-12", "TC-13"}                                   # contradictory_boundary (flag)

# Map district/place mentions -> coords (production FE sends GPS; this avoids the text-search
# city-leak artifact so we test the real geo-filtered pipeline).
LOC_MAP = {
    "cầu giấy": (21.036, 105.790), "cau giay": (21.036, 105.790),
    "đống đa": (21.004, 105.833), "dong da": (21.004, 105.833),
    "hà đông": (20.960, 105.764), "ha dong": (20.960, 105.764),
    "gia lâm": (21.028, 105.948), "gia lam": (21.028, 105.948),
    "hai bà trưng": (21.005, 105.849), "hai ba trung": (21.005, 105.849),
    "tây hồ": (21.072, 105.830), "tay ho": (21.072, 105.830),
    "hoàn kiếm": (21.029, 105.852), "hoan kiem": (21.029, 105.852),
    "thanh xuân": (20.993, 105.811), "thanh xuan": (20.993, 105.811),
    "long biên": (21.039, 105.860), "long bien": (21.039, 105.860),
    "hà nội": (21.028, 105.834), "ha noi": (21.028, 105.834),
    "sài gòn": (10.763, 106.682), "sai gon": (10.763, 106.682),
}


def _coords_for(text: str) -> tuple[float, float] | None:
    t = (text or "").lower()
    for k, v in LOC_MAP.items():
        if k in t:
            return v
    return None


def _weather_override(ctx: dict) -> dict | None:
    w = (ctx or {}).get("weather")
    if not w:
        return None
    return {"is_rain": True} if "mưa" in w or "mua" in w.lower() else {"condition": w}


def _seed_profile(engine, user_id: str, profile: dict | None) -> None:
    """Upsert a user_profiles row from GT profile so preference/profile_conflict cases see it."""
    from sqlalchemy import text
    if not profile:
        return
    liked = profile.get("preferred_cuisine") or profile.get("liked_cuisines")
    dietary = profile.get("dietary")
    budget = profile.get("budget_avg") or profile.get("budget_level")
    if isinstance(budget, (int, float)):
        budget = "low" if budget < 40000 else "medium" if budget < 100000 else "high"
    with engine.begin() as c:
        c.execute(text("DELETE FROM user_profiles WHERE user_id=:u"), {"u": user_id})
        c.execute(text(
            "INSERT INTO user_profiles (user_id, liked_cuisines, dietary, budget_level, updated_at) "
            "VALUES (:u, :l, :d, :b, now())"), {
            "u": user_id,
            "l": json.dumps(liked) if liked else None,
            "d": json.dumps(dietary) if dietary else None,
            "b": budget,
        })


def _post_sse(payload: dict, t0: float) -> dict:
    """POST to /chat/stream; return captured timing + answer + results + trace_id."""
    out = {"total_ms": 0.0, "ttft_ms": None, "explain_ms": None, "answer": "",
           "results": [], "suggestions": [], "warnings": [], "trace_id": None,
           "token_chunks": 0, "error": None}
    event_type = None
    try:
        with requests.post(API_STREAM, json=payload, stream=True, timeout=180) as resp:
            for raw in resp.iter_lines(decode_unicode=True):
                if not raw:
                    continue
                line = raw.strip()
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data:"):
                    data = json.loads(line[5:].strip())
                    now = (time.perf_counter() - t0) * 1000.0
                    if event_type == "answer_delta":
                        if out["ttft_ms"] is None:
                            out["ttft_ms"] = now
                        out["token_chunks"] += 1
                        out["answer"] += data.get("answer_delta", "") or ""
                    elif event_type == "run_finished":
                        out["total_ms"] = now
                        if out["ttft_ms"] is not None:
                            out["explain_ms"] = now - out["ttft_ms"]
                        out["trace_id"] = data.get("trace_id")
                        out["answer"] = (data.get("answer") or "").strip()
                        out["results"] = data.get("results") or []
                        out["suggestions"] = data.get("preference_suggestions") or []
                        out["warnings"] = list(data.get("warnings") or [])
                    elif event_type == "error":
                        out["error"] = str(data)
                    event_type = None
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def _server_durations(trace_id: str) -> tuple[float | None, float | None, dict]:
    """(search_task_ms, preference_task_ms, {tool: ms}) from agent_events — authoritative."""
    from database.connection import engine
    from sqlalchemy import text
    search = pref = None
    tools: dict[str, float] = {}
    if not trace_id:
        return search, pref, tools
    with engine.connect() as c:
        for et, tn, tn_tool, dur in c.execute(text(
            "SELECT event_type, task_name, tool_name, duration_ms FROM agent_events "
            "WHERE trace_id=:tid AND duration_ms IS NOT NULL"), {"tid": trace_id}):
            if et == "task_finished" and tn == "search_task":
                search = float(dur)
            elif et == "task_finished" and tn == "preference_task":
                pref = float(dur)
            elif et == "tool_finished" and tn_tool:
                tools[tn_tool] = tools.get(tn_tool, 0.0) + float(dur)
    return search, pref, tools


def run_case(case: dict, engine) -> dict:
    cid = case["id"]
    # Unique per-run session/user id so prior runs' persisted chat_messages + user_profiles
    # can't leak into this run (_load_recent_turns / _load_profile would otherwise read STALE
    # prior turns from earlier bench rounds → confabulation). Same stamp across the case so
    # multiturn seeding + the test turn share a clean session.
    sid = f"gt_{cid}_{_RUN_STAMP}"
    uid = f"gt_{cid}_{_RUN_STAMP}"
    msg = case["user_message"]
    ctx = case.get("session_context") or {}

    _seed_profile(engine, uid, ctx.get("user_profile"))
    coords = _coords_for(msg)
    wov = _weather_override(ctx)

    base = {"user_id": uid, "session_id": sid}
    if coords:
        base["location"] = {"lat": coords[0], "lng": coords[1]}
    if wov:
        base["weather_override"] = wov

    # Replay prior USER turns (real /chat) so memory + anaphora see them.
    for turn in (ctx.get("prior_turns") or []):
        if turn.get("role") == "user":
            try:
                requests.post(API_CHAT, json={**base, "message": turn["text"]}, timeout=180)
            except Exception:  # noqa: BLE001 - best-effort seeding
                pass

    # Test turn (timed).
    t0 = time.perf_counter()
    res = _post_sse({**base, "message": msg}, t0)
    search_ms, pref_ms, tools = _server_durations(res["trace_id"])
    res.update({"id": cid, "category": case["category"], "difficulty": case.get("difficulty"),
                "query": msg, "expected": case.get("expected"),
                "search_ms": search_ms, "preference_ms": pref_ms, "tools": tools,
                "coords_sent": coords is not None, "weather_sent": wov is not None,
                "had_prior_turns": bool(ctx.get("prior_turns"))})
    return res


def _s(x: float | None) -> str:
    return f"{x / 1000:5.2f}s" if x else "    -  "


def main() -> None:
    import statistics
    from database.connection import engine

    cases = [c for c in json.loads(GT_PATH.read_text(encoding="utf-8"))["test_cases"]
             if c["id"] not in SKIP_IDS]
    print("=" * 96)
    print(f"GROUND-TRUTH EVAL — {len(cases)} cases (skipped {len(SKIP_IDS)} coordinator-only)")
    print("=" * 96)
    results = []
    for c in cases:
        r = run_case(c, engine)
        results.append(r)
        err = f" ERR={r['error']}" if r["error"] else ""
        warn = f" WARN={r['warnings']}" if r["warnings"] else ""
        print(f"\n→ {r['id']} [{r['category']}] {r['query'][:50]!r}"
              f"{' +prior' if r['had_prior_turns'] else ''}{err}{warn}")
        if r["total_ms"]:
            print(f"   total={_s(r['total_ms'])} ttft={_s(r['ttft_ms'])} "
                  f"search={_s(r['search_ms'])} pref={_s(r['preference_ms'])} "
                  f"explain(stream)={_s(r['explain_ms'])} | results={len(r['results'])} "
                  f"tok={r['token_chunks']}")
            if r["answer"]:
                print(f"   ANS: {r['answer'][:200]}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[saved] {OUT_PATH}")

    ok = [r for r in results if r["total_ms"]]
    print("\n" + "=" * 96)
    print("AGGREGATE TIMING (per-step)")
    print("=" * 96)
    for key, label in [("total_ms", "total submit->run_finished"),
                       ("ttft_ms", "ttft (first answer token)"),
                       ("search_ms", "search_task (server)"),
                       ("preference_ms", "preference_task (server)"),
                       ("explain_ms", "explain stream (first->last)")]:
        vals = [r[key] for r in ok if r.get(key)]
        print(f"  median {label:32s}: {_s(statistics.median(vals) if vals else None)}  "
              f"(n={len(vals)})")
    interrupted = sum(1 for r in results if any("explanation_stream_interrupted" in w for w in r["warnings"]))
    print(f"\n  explanation_stream_interrupted: {interrupted}/{len(results)}")
    print(f"  errors: {sum(1 for r in results if r['error'])}/{len(results)}")


if __name__ == "__main__":
    main()
