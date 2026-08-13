"""Live E2E confirmation for 3 memory_test.json cases through the REAL /chat pipeline.

Confirms the deterministic harness predictions end-to-end (LLM + DB hard-filter):
  1.1 (chay 1->20, proxy 2-session):  declare chay -> fresh-session lunch => expect chay-enforced, no re-ask.  [expect PASS]
  3.1 (peanut safety):                declare peanut allergy -> fresh-session "buffet" => expect NOT warned/filtered (peanut not in catalog).  [expect FAIL -> confirms gap]
  7.2 (selective delete):             declare shrimp+spicy -> retract shrimp -> fresh-session seafood => expect seafood STILL wrongly filtered (stale note).  [expect FAIL -> confirms gap]

The 20-session span is already proven (deterministic FIFO probe + harness); this uses a 2-session
proxy to confirm the ENFORCEMENT path end-to-end without 20 slow LLM calls.

Requires backend on :8000 (or :8001) with DB connected. Run from backend/:
  PYTHONPATH=. <env-python> scripts/memory_live_e2e_cases.py [--port 8000]
"""
from __future__ import annotations

import io
import sys
import time
import unicodedata

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import requests

PORT = "8001" if "--port" not in sys.argv else sys.argv[sys.argv.index("--port") + 1]
API = f"http://127.0.0.1:{PORT}/api/v1/agent/customer/chat"
CG = (21.036, 105.790)
STAMP = str(int(time.time()))


def _fold(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").lower()


def chat(uid, sid, msg):
    p = {"user_id": uid, "session_id": sid, "message": msg, "location": {"lat": CG[0], "lng": CG[1]}}
    r = requests.post(API, json=p, timeout=200).json()
    if r.get("error"):
        raise RuntimeError(f"chat error: {r['error'].get('message')}")
    return r


def show(tag, r):
    ans = r.get("answer") or ""
    res = r.get("results") or []
    print(f"  {tag}: intent={r.get('intent')} results={len(res)} answer={ans[:140]!r}")
    for m in res[:4]:
        print(f"      - {m.get('name')} | {m.get('cuisine')}")


def case_1_1():
    """chay cross-session recall (proxy for 1->20)."""
    print("\n### CASE 1.1 — chay recall cross-session")
    uid = f"live11_{STAMP}"
    show("declare chay", chat(uid, f"{uid}_s1", "Tôi ăn chay nhé"))
    r2 = chat(uid, f"{uid}_s2", "Tìm quán ăn trưa gần đây")
    show("fresh-session lunch", r2)
    meat = []
    for m in (r2.get("results") or []):
        hay = _fold(f"{m.get('name')} {m.get('cuisine')}")
        if any(t in hay.split() for t in ("bo", "ga", "heo", "thit")) and "chay" not in hay:
            meat.append(m.get("name"))
    ans = _fold(r2.get("answer") or "")
    reasked = any(p in ans for p in ("an chay khong", "co an chay", "ban co an chay"))
    ok = (not meat) and (not reasked)
    print(f"  >> 1.1 {'PASS' if ok else 'FAIL'} (meat_leaked={meat}, reasked={reasked})")
    return ok


def case_3_1():
    """peanut allergy safety — expect NOT enforced (gap)."""
    print("\n### CASE 3.1 — peanut allergy safety (EXPECT FAIL: not in catalog)")
    uid = f"live31_{STAMP}"
    show("declare peanut allergy", chat(uid, f"{uid}_s1", "Tôi dị ứng đậu phộng, ăn vào là nổi mề đay"))
    r2 = chat(uid, f"{uid}_s2", "Gợi ý quán buffet ngon nhất khu vực cho tôi")
    show("fresh-session buffet", r2)
    ans = _fold(r2.get("answer") or "")
    warned = "dau phong" in ans or "lac" in ans.split() or "di ung" in ans
    # pass_criteria wants proactive peanut warning/filter. gap => no warning.
    print(f"  >> 3.1 {'FAIL(confirmed gap)' if not warned else 'PASS(unexpected!)'} peanut_warned={warned}")
    return warned  # True = PASS (warned); False = FAIL (gap confirmed)


def case_7_2():
    """selective delete — expect seafood STILL filtered (stale note bug)."""
    print("\n### CASE 7.2 — selective delete (EXPECT FAIL: stale contradictory note)")
    uid = f"live72_{STAMP}"
    chat(uid, f"{uid}_s1", "Tôi dị ứng tôm")          # declare shrimp allergy
    chat(uid, f"{uid}_s2", "Tôi cũng không thích ăn cay")  # dislike spicy
    chat(uid, f"{uid}_s3", "Quên chuyện tôi dị ứng tôm đi, giờ ăn được bình thường rồi")  # retract
    r = chat(uid, f"{uid}_s4", "Gợi ý món hải sản cay cho tôi")
    show("fresh-session seafood-spicy after retract", r)
    ans = _fold(r.get("answer") or "")
    res = r.get("results") or []
    # pass_criteria: can suggest shrimp now (retraction honored). bug => seafood still blocked.
    blocked = len(res) == 0 or "di ung" in ans or "kieng" in ans or "khong de xuat" in ans or "khong goi y" in ans
    print(f"  >> 7.2 {'FAIL(confirmed stale)' if blocked else 'PASS(retraction honored!)'} seafood_blocked={blocked} results={len(res)}")
    return not blocked  # True = PASS; False = FAIL (stale confirmed)


if __name__ == "__main__":
    print(f"stamp={STAMP} endpoint={API}")
    try:
        r11 = case_1_1()
    except Exception as e:  # noqa: BLE001
        print(f"  !! 1.1 error: {type(e).__name__}: {e}"); r11 = None
    try:
        r31 = case_3_1()
    except Exception as e:  # noqa: BLE001
        print(f"  !! 3.1 error: {type(e).__name__}: {e}"); r31 = None
    try:
        r72 = case_7_2()
    except Exception as e:  # noqa: BLE001
        print(f"  !! 7.2 error: {type(e).__name__}: {e}"); r72 = None
    print("\n" + "=" * 64)
    print(f"LIVE E2E: 1.1={'PASS' if r11 else 'FAIL'}  3.1={'PASS' if r31 else 'FAIL(gap)'}  7.2={'PASS' if r72 else 'FAIL(stale)'}")
    print("(1.1 expected PASS; 3.1 & 7.2 expected FAIL = confirms deterministic findings)")
    print("=" * 64)
