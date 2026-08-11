"""Live end-to-end memory/constraint test against the running backend (:8000).

Reproduces the user's two original bugs + the confirm-gate, through the REAL /chat path
(with yesterday's unified active-constraints code). Each scenario uses a fresh
user_id/session_id so no prior-run state leaks.

  A — chay recall (session-scoped): 'nay toi an chay' -> 'tim pho' => NO non-chay (bo) result.
  B — seafood recall (allergy):     'khong an duoc hai san' -> 'goi y quan' => NO sushi/seafood.
  C — confirm gate:                 after B, 'toi muon an tom' => confirm answer, no search.
"""
from __future__ import annotations

import io
import json
import sys
import time

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import requests

API = "http://localhost:8000/api/v1/agent/customer/chat"
CG = (21.036, 105.790)  # Cau Giay


def _fold(s: str | None) -> str:
    import unicodedata
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "d").lower()


def chat(uid: str, sid: str, message: str, loc=CG, timeout: int = 180) -> dict:
    payload = {"user_id": uid, "session_id": sid, "message": message}
    if loc:
        payload["location"] = {"lat": loc[0], "lng": loc[1]}
    r = requests.post(API, json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()


def show(tag: str, resp: dict) -> None:
    print(f"\n### {tag}")
    print(f"  intent : {resp.get('intent')}")
    print(f"  answer : {(resp.get('answer') or '')[:240]}")
    for m in (resp.get("results") or []):
        print(f"    - {m.get('name')} | cuisine={m.get('cuisine')} | match={m.get('match_score')}")


STAMP = str(int(time.time()))


def scenario_a() -> bool:
    uid = sid = f"liveA_{STAMP}"
    show("A.1 DECLARE chay (session)", chat(uid, sid, "Nay tôi ăn chay nhé"))
    r2 = chat(uid, sid, "Tìm quán phở gần Cầu Giấy")
    show("A.2 FIND pho (expect NO bo / non-chay)", r2)
    # FAIL if any result is a non-chay merchant whose folded name/cuisine carries 'bo' (beef).
    bad = []
    for m in (r2.get("results") or []):
        hay = _fold(f"{m.get('name')} {m.get('cuisine')}")
        if "bo" in hay.split() or "bo" in hay:  # 'bo' token anywhere = beef pho
            # but only count it bad if it's NOT a chay place
            if "chay" not in hay:
                bad.append(m.get("name"))
    ok = not bad
    print(f"  >> A RESULT: {'PASS' if ok else 'FAIL'} — non-chay beef results: {bad}")
    return ok


def scenario_b() -> bool:
    uid = sid = f"liveB_{STAMP}"
    show("B.1 DECLARE seafood allergy", chat(uid, sid, "Tôi không ăn được hải sản"))
    r2 = chat(uid, sid, "Gợi ý quán ăn ngon gần Cầu Giấy")
    show("B.2 SUGGEST (expect NO sushi/seafood)", r2)
    SEAFOOD = ("sushi", "sashimi", "hai san", "tom", "cua", "muc", "ngao", "oc", "so", "ghe")
    bad = []
    for m in (r2.get("results") or []):
        hay = _fold(f"{m.get('name')} {m.get('cuisine')}")
        if any(t in hay for t in SEAFOOD):
            bad.append(f"{m.get('name')}({m.get('cuisine')})")
    ok = not bad
    print(f"  >> B RESULT: {'PASS' if ok else 'FAIL'} — seafood/sushi leaked: {bad}")
    return ok


def scenario_c() -> bool:
    # Reuses B's persisted seafood constraint (same uid, new session to isolate the turn).
    uid = f"liveB_{STAMP}"
    sid = f"liveC_{STAMP}"  # fresh session; constraint comes from the durable profile note
    r = chat(uid, sid, "Tôi muốn ăn tôm nước sốt thái")
    show("C CONFIRM-GATE (expect confirm, no search)", r)
    ans = _fold(r.get("answer") or "")
    gated = ("kieng" in ans or "di ung" in ans or "chan chan" in ans or "hoac minh" in ans
             or "mon khac" in ans or "an toan" in ans)
    no_results = not (r.get("results") or [])
    ok = gated and no_results
    print(f"  >> C RESULT: {'PASS' if ok else 'FAIL'} — gated={gated} no_results={no_results}")
    return ok


def scenario_d() -> bool:
    # COLLISION FIX (live): 'không ăn được cơm của mẹ' must NOT create a false seafood allergy
    # ('của' folds to 'cua'=crab). So a later explicit crab request ('tìm cua') is NOT confirm-gated.
    uid = sid = f"liveD_{STAMP}"
    show("D.1 DECLARE false-seafood ('của'≠crab)", chat(uid, sid, "Tôi không ăn được cơm của mẹ nấu"))
    r2 = chat(uid, sid, "Tìm quán cua biển gần Cầu Giấy")
    show("D.2 FIND crab (expect NO false confirm-gate)", r2)
    # A false seafood allergy would gate this with dietary_conflict + no results. It must NOT.
    not_gated = r2.get("intent") != "dietary_conflict"
    ok = not_gated
    print(f"  >> D RESULT: {'PASS' if ok else 'FAIL'} — intent={r2.get('intent')!r} (must NOT be dietary_conflict)")
    return ok


if __name__ == "__main__":
    print(f"stamp={STAMP}  endpoint={API}")
    try:
        results = {"A": scenario_a(), "B": scenario_b(), "C": scenario_c(), "D": scenario_d()}
    except Exception as e:  # noqa: BLE001
        print(f"\n!! LIVE TEST ERROR: {type(e).__name__}: {e}")
        sys.exit(2)
    print("\n" + "=" * 60)
    print("SUMMARY: " + ", ".join(f"{k}={'PASS' if v else 'FAIL'}" for k, v in results.items()))
    print("=" * 60)
    sys.exit(0 if all(results.values()) else 1)
