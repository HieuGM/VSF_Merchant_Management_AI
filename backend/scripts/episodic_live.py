"""Live episodic-memory verification (phase-05) — exercises the liked-merchant flow end-to-end.

  1. pick a real merchant via /merchants/search
  2. POST /liked-merchants {merchant_id}   (idempotent — safe to re-run)
  3. GET  /profile                          → liked_merchant_ids + liked_merchant_cuisines populated
  4. GET  /liked-merchants                  → the liked merchant appears (with name + cuisine)
  5. DELETE /liked-merchants/{id}           → removed; profile no longer lists it
Requires the backend on :8000 with the phase-05 code."""
from __future__ import annotations

import io
import sys
import time

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import requests

BASE = "http://localhost:8000/api/v1"
STAMP = str(int(time.time()))


def main() -> int:
    uid = f"ep_{STAMP}"
    # 1. find a real merchant
    s = requests.get(f"{BASE}/merchants/search", params={"cuisine": "Việt", "limit": 1}, timeout=30)
    s.raise_for_status()
    merchants = s.json().get("merchants") or []
    if not merchants:
        print("FAIL: no merchant found to like"); return 1
    mid = merchants[0]["merchant_id"]
    mcuisine = merchants[0].get("cuisine")
    print(f"target merchant: {mid} ({merchants[0].get('name')} | cuisine={mcuisine})")

    # 2. like it
    r = requests.post(f"{BASE}/users/{uid}/liked-merchants", json={"merchant_id": mid}, timeout=30)
    print(f"POST like: {r.status_code} {r.json() if r.ok else r.text}")
    assert r.status_code == 201, "like should succeed (201)"

    # 2b. idempotency: like again → still 201, no duplicate
    r2 = requests.post(f"{BASE}/users/{uid}/liked-merchants", json={"merchant_id": mid}, timeout=30)
    print(f"POST like again (idempotent): {r2.status_code}")

    # 3. profile enrichment
    p = requests.get(f"{BASE}/users/{uid}/profile", timeout=30).json()
    ids = p.get("liked_merchant_ids") or []
    cuises = p.get("liked_merchant_cuisines") or []
    print(f"GET profile: liked_merchant_ids={ids}  liked_merchant_cuisines={cuises}")
    ok_profile = mid in ids
    print(f"  >> profile enrichment: {'PASS' if ok_profile else 'FAIL'}")

    # 4. liked-merchants list
    lst = requests.get(f"{BASE}/users/{uid}/liked-merchants", timeout=30).json()
    listed = [m["merchant_id"] for m in lst.get("liked_merchants") or []]
    print(f"GET liked-merchants: {listed}")
    ok_list = mid in listed
    print(f"  >> liked-merchants list: {'PASS' if ok_list else 'FAIL'}")

    # 5. unlike → gone
    d = requests.delete(f"{BASE}/users/{uid}/liked-merchants/{mid}", timeout=30)
    print(f"DELETE unlike: {d.status_code}")
    p2 = requests.get(f"{BASE}/users/{uid}/profile", timeout=30).json()
    ok_unlike = mid not in (p2.get("liked_merchant_ids") or [])
    print(f"  >> unlike removes it: {'PASS' if ok_unlike else 'FAIL'}")

    allok = ok_profile and ok_list and ok_unlike
    print("\n" + ("=" * 50))
    print(f"EPISODIC LIVE: {'PASS' if allok else 'FAIL'}")
    print("=" * 50)
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
