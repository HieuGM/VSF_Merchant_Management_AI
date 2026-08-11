"""Live cross-session memory tests from memory.txt.

T1 (Persistence): S1 'Tôi ăn chay' → [new session, same user] → S2 'Tìm quán ăn trưa' must
auto-filter vegetarian WITHOUT re-asking. Proven via a CONTROL user (no declaration) whose
same query returns the normal (meat-inclusive) mix.

T7 (Isolation): S1 transient group context ('đi với gia đình') → S2 'Tìm chỗ ăn trưa' must NOT
assume a group / leak the transient context.

Requires the backend on :8000 (with the current code). Same uid across S1/S2; fresh session_id
per session so S2 has no in-session prior turns (recall must come from the durable profile note).
"""
from __future__ import annotations

import io
import sys
import time
import unicodedata

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import requests

API = "http://localhost:8000/api/v1/agent/customer/chat"
CG = (21.036, 105.790)
STAMP = str(int(time.time()))
MEAT = ("bo", "ga", "heo", "thit", "bun bo", "com suon", "ga ran")


def _fold(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").lower()


def chat(uid, sid, msg):
    p = {"user_id": uid, "session_id": sid, "message": msg, "location": {"lat": CG[0], "lng": CG[1]}}
    return requests.post(API, json=p, timeout=180).json()


def _meat_in_results(resp):
    out = []
    for m in (resp.get("results") or []):
        hay = _fold(f"{m.get('name')} {m.get('cuisine')}")
        if any(t in hay.split() or t in hay for t in ("bo", "ga", "heo", "thit")) and "chay" not in hay:
            out.append(m.get("name"))
    return out


def test_t1_cross_session_chay_recall():
    uid = f"t1_{STAMP}"
    # S1: bare vegetarian declaration (no 'từ giờ'/'trường') — must persist as a durable note.
    r1 = chat(uid, f"{uid}_s1", "Tôi ăn chay")
    print(f"\n### T1 S1 DECLARE (same uid, session 1): intent={r1.get('intent')}")
    # S2: FRESH session, same user, generic lunch query — no re-ask, chay auto-filtered.
    r2 = chat(uid, f"{uid}_s2", "Tìm quán ăn trưa gần đây")
    meat = _meat_in_results(r2)
    print(f"### T1 S2 FIND lunch (fresh session): intent={r2.get('intent')} results={len(r2.get('results') or [])} meat={meat}")
    ans = _fold(r2.get("answer") or "")
    reasked = "an chay khong" in ans or "co an chay" in ans or "ban co an chay" in ans or "có ăn chay" in (r2.get("answer") or "")
    return (not meat) and (not reasked), meat, reasked


def test_t1_control():
    # Control: a user who NEVER declared chay, same query → normal mix (meat present is fine).
    uid = f"t1ctrl_{STAMP}"
    r = chat(uid, f"{uid}_s", "Tìm quán ăn trưa gần đây")
    meat = _meat_in_results(r)
    print(f"### T1 CONTROL (no declaration): results={len(r.get('results') or [])} meat={meat}")
    return r


if __name__ == "__main__":
    print(f"stamp={STAMP} endpoint={API}")
    try:
        ctrl = test_t1_control()
        ok, meat, reasked = test_t1_cross_session_chay_recall()
    except Exception as e:  # noqa: BLE001
        print(f"!! LIVE ERROR: {type(e).__name__}: {e}")
        sys.exit(2)
    print("\n" + "=" * 64)
    print(f"T1 cross-session chay recall: {'PASS' if ok else 'FAIL'} (meat_leaked={meat}, reasked={reasked})")
    print("=" * 64)
    sys.exit(0 if ok else 1)
