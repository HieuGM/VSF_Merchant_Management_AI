"""Focused live probe of the 5 open GT cases (TC-09/41/47/35/51).

Replays prior user turns (multiturn), reads back the persisted AGENT turn's results payload,
then posts the test turn to /chat/stream. Prints diagnostics to decide whether the anaphora
resolver has a target and how TC-35/51 currently behave (search vs clarify).

Env ai_restaurant, server on :8000:
  PYTHONUTF8=1 PYTHONPATH=backend python backend/scripts/probe_5_cases.py
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
STAMP = str(int(time.time()))
PROBE_IDS = {"TC-09", "TC-41", "TC-47", "TC-35", "TC-51"}

LOC_MAP = {
    "hai bà trưng": (21.005, 105.849), "hoàn kiếm": (21.029, 105.852),
    "long biên": (21.039, 105.860), "bờ hồ": (21.029, 105.852),
}


def _coords(text: str):
    t = (text or "").lower()
    for k, v in LOC_MAP.items():
        if k in t:
            return v
    return None


def _persisted_agent_results(sid: str):
    """Read back the last agent turn's results payload for this session."""
    from database.connection import engine
    from sqlalchemy import text
    with engine.connect() as c:
        rows = list(c.execute(text(
            "SELECT sender, text, structured_payload_json FROM chat_messages "
            "WHERE session_id=:s ORDER BY timestamp ASC"), {"s": sid}))
    out = []
    for sender, txt, payload in rows:
        pl = payload if isinstance(payload, dict) else (json.loads(payload) if payload else {})
        out.append({"sender": sender, "text": (txt or "")[:120],
                    "results": (pl or {}).get("results") or []})
    return out


def _post_stream(payload, t0):
    ans = ""
    results = []
    warnings = []
    err = None
    etype = None
    try:
        with requests.post(API_STREAM, json=payload, stream=True, timeout=180) as resp:
            for raw in resp.iter_lines(decode_unicode=True):
                if not raw:
                    continue
                line = raw.strip()
                if line.startswith("event:"):
                    etype = line[6:].strip()
                elif line.startswith("data:"):
                    data = json.loads(line[5:].strip())
                    if etype == "answer_delta":
                        ans += data.get("answer_delta", "") or ""
                    elif etype == "run_finished":
                        ans = (data.get("answer") or "").strip()
                        results = data.get("results") or []
                        warnings = list(data.get("warnings") or [])
                    elif etype == "error":
                        err = str(data)
                    etype = None
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    return {"ms": (time.perf_counter() - t0) * 1000, "answer": ans, "results": results,
            "warnings": warnings, "err": err}


def main():
    cases = {c["id"]: c for c in json.loads(GT_PATH.read_text(encoding="utf-8"))["test_cases"]
             if c["id"] in PROBE_IDS}
    for cid in ["TC-09", "TC-41", "TC-47", "TC-35", "TC-51"]:
        case = cases[cid]
        ctx = case.get("session_context") or {}
        sid = f"probe_{cid}_{STAMP}"
        uid = sid
        msg = case["user_message"]
        coords = _coords(" ".join([t["text"] for t in (ctx.get("prior_turns") or [])] + [msg]))
        base = {"user_id": uid, "session_id": sid}
        if coords:
            base["location"] = {"lat": coords[0], "lng": coords[1]}

        print(f"\n{'='*90}\n{cid} [{case['category']}] msg={msg!r}")
        for turn in (ctx.get("prior_turns") or []):
            if turn.get("role") == "user":
                try:
                    requests.post(API_CHAT, json={**base, "message": turn["text"]}, timeout=180)
                except Exception as e:  # noqa: BLE001
                    print(f"  [replay err] {e}")

        if ctx.get("prior_turns"):
            persisted = _persisted_agent_results(sid)
            print(f"  PERSISTED turns ({len(persisted)}):")
            for p in persisted:
                r = p["results"]
                print(f"    {p['sender']:6} text={p['text']!r}")
                if r:
                    print(f"           results={[{'id': x.get('merchant_id'), 'name': x.get('name')} for x in r]}")

        t0 = time.perf_counter()
        res = _post_stream({**base, "message": msg}, t0)
        print(f"  TEST TURN ({res['ms']/1000:.1f}s) err={res['err']} warns={res['warnings']}")
        print(f"    results={[{'id': r.get('merchant_id'), 'name': r.get('name')} for r in res['results']]}")
        print(f"    ANSWER: {res['answer'][:400]}")


if __name__ == "__main__":
    main()
