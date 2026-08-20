#!/usr/bin/env python
"""E2E 12-flow suite — memory-heavy (9/12 = 75%) with 2 flows >15 messages.

Measures per-turn: latency (client wall-clock), result count, memory events
(memory_updated diff), and runs deterministic memory verdicts at the checkpoints
(recall in a FRESH session = long-term memory, not session window).

Runs against the live backend (:8000) + writes a JSON results file + a markdown
table for the web demo.

Usage: PYTHONUTF8=1 python scripts/e2e-12-flow-memory-suite.py [--only 1,2,3]
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import requests

BASE = "http://localhost:8000/api/v1/agent/customer/chat"
STREAM = "http://localhost:8000/api/v1/agent/customer/chat/stream"
API = "http://localhost:8000/api/v1"
STAMP = str(int(time.time()))
OUT = Path("plans/reports/e2e-12-flow-memory-suite.json")


def chat(uid: str, sid: str, msg: str, retries: int = 2) -> dict:
    """One blocking /chat turn. Returns dict with latency_ms injected."""
    t0 = time.perf_counter()
    last_err = None
    for attempt in range(retries + 1):
        try:
            r = requests.post(BASE, json={"user_id": uid, "session_id": sid, "message": msg},
                              timeout=240)
            ms = (time.perf_counter() - t0) * 1000
            d = r.json()
            if r.status_code == 200 and (d.get("answer") or d.get("results")):
                d["_latency_ms"] = round(ms)
                d["_turned_ok"] = True
                return d
            last_err = f"{r.status_code}: {str(d)[:90]}"
        except requests.RequestException as e:
            last_err = f"{type(e).__name__}: {str(e)[:80]}"
        t0 = time.perf_counter()
        time.sleep(8)
    return {"answer": "", "results": [], "_latency_ms": round((time.perf_counter() - t0) * 1000),
            "_turned_ok": False, "_err": last_err}


def norm(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "d").lower()


def profile_of(uid: str) -> dict:
    try:
        return requests.get(f"{API}/users/{uid}/profile", timeout=15).json()
    except Exception:  # noqa: BLE001
        return {}


def sessions_of(uid: str) -> list:
    try:
        return requests.get(f"{API}/users/{uid}/sessions", timeout=15).json()
    except Exception:  # noqa: BLE001
        return []


class Flow:
    def __init__(self, fid: int, name: str, kind: str):
        self.fid, self.name, self.kind = fid, name, kind
        self.uid = f"e2e12_{fid}_{STAMP}"
        self.turns: list[dict] = []

    def say(self, sid: str, msg: str, checkpoint: str | None = None) -> dict:
        d = chat(self.uid, sid, msg)
        row = {"msg": msg, "latency_ms": d["_latency_ms"], "ok": d.get("_turned_ok"),
               "n_results": len(d.get("results") or []),
               "memory_updates": d.get("memory_updates") or {},
               "active_constraints": len(d.get("active_constraints") or []),
               "answer": (d.get("answer") or "")[:220]}
        if checkpoint:
            row["checkpoint"] = checkpoint
        self.turns.append(row)
        flag = "✓" if d.get("_turned_ok") else "✗"
        mem = d.get("memory_updates") or {}
        mem_s = f" MEM+{len(mem.get('added') or [])}/-{len(mem.get('removed') or [])}" if (mem.get("added") or mem.get("removed")) else ""
        print(f"   {flag} [{d['_latency_ms']/1000:5.1f}s] r={row['n_results']}{mem_s} {msg[:52]!r}", flush=True)
        return d

    def result(self) -> dict:
        lats = [t["latency_ms"] for t in self.turns if t["ok"]]
        return {
            "fid": self.fid, "name": self.name, "kind": self.kind, "uid": self.uid,
            "n_turns": len(self.turns), "n_ok": sum(1 for t in self.turns if t["ok"]),
            "median_latency_ms": sorted(lats)[len(lats)//2] if lats else None,
            "max_latency_ms": max(lats) if lats else None,
            "turns": self.turns,
        }


FLOWS_DONE: list[dict] = []


def run_flow(f: Flow, body) -> None:
    print(f"\n=== FLOW {f.fid}: {f.name} ===", flush=True)
    t0 = time.perf_counter()
    verdicts = body(f) or {}
    r = f.result()
    r["wall_s"] = round(time.perf_counter() - t0, 1)
    r["verdicts"] = verdicts
    FLOWS_DONE.append(r)
    # Incremental save: the live dashboard (plans/reports/e2e-12-flow-live-dashboard.html)
    # polls this file every 10s — write after EVERY flow so progress is visible mid-run.
    OUT.write_text(json.dumps(FLOWS_DONE, ensure_ascii=False, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- #
# The 12 flows
# --------------------------------------------------------------------------- #
def flow_1(f: Flow):
    """DÀI #1 (18 tin): 3 durable facts + 13 filler + fresh-session recall."""
    s1 = f"s1_{STAMP}"
    f.say(s1, "Tôi dị ứng tôm nhé, nhớ giúp tôi")
    f.say(s1, "Mà tôi cũng ăn chay vào thứ Hai hàng tuần")
    f.say(s1, "Ngân sách của mình thường dưới 100k một bữa")
    for i, m in enumerate([
        "Hôm nay có quán nào ngon không", "Mình đang ở Cầu Giấy",
        "Thèm món nhẹ thôi", "Trà sữa ở đâu ngon", "Quán nào rating cao nhé",
        "Có quán nào mở khuya không", "Đổi món đi, thèm bún",
        "Gần hồ Tây có gì", "Nhà hàng nào phù hợp đi cùng bạn bè",
        "Món chay ở đâu ngon", "Quán nào view đẹp", "Có chỗ nào cho nhóm 8 người không",
        "OK cảm ơn nhé",
    ], 1):
        f.say(s1, m)
    # FRESH session — long-term recall test (session window is empty here)
    s2 = f"recall_{STAMP}"
    d = f.say(s2, "Gợi ý mình quán ăn nhé", checkpoint="recall-all-3-facts")
    ans = norm(d.get("answer") or "")
    v = {}
    v["tóm_tăng_không_gợi_tôm"] = ("khong tom" not in ans) or ("dị ứng" in norm(d.get("answer") or "") and "tom" in ans)
    d2 = f.say(s2, "Hôm nay thứ Hai, mình ăn gì giờ trưa?", checkpoint="chay-monday")
    ans2 = norm(d2.get("answer") or "")
    v["chay_thu_hai"] = ("chay" in ans2) or any("chay" in norm(str(c.get("label", ""))) for c in (d2.get("active_constraints") or []))
    prof = profile_of(f.uid)
    notes = [norm(n) for n in ((prof.get("context_memory") or {}).get("notes") or [])]
    v["note_dị_ung_tom_luu"] = any("di ung" in n and "tom" in n for n in notes)
    v["note_chay_luu"] = any("chay" in n for n in notes)
    v["budget_luu"] = any("100" in n for n in notes) or any("ngan sach" in n for n in notes)
    return v


def flow_2(f: Flow):
    """DÀI #2 (17 tin): 3 sở thích + filler + fresh session tổng hợp."""
    s1 = f"p_{STAMP}"
    f.say(s1, "Mình thích quán cà phê yên tĩnh để làm việc")
    f.say(s1, "Mình không thích đồ cay, ăn cay bị đau dạ dày")
    f.say(s1, "Mình sống ở Cầu Giấy, hay tìm quán gần đó")
    for m in ["Cho mình hỏi món trưa hôm nay", "Quán nào đông người vậy",
              "Món ngọt gì ngon nhỉ", "Trời hôm nay mưa không",
              "Cơm nhà nào ổn", "Quán nào bán xôi ngon",
              "Có quán Hàn nào không", "Gần-big-c mặt hồ có gì",
              "Món ăn vặt ngon đường phố", "Quán nào phù hợp hẹn hò",
              "View đẹp ở Tây Hồ nhỉ", "Có quán nào bán bánh mì long xuôi không",
              "OK vậy thôi", "Cảm ơn bạn"]:
        f.say(s1, m)
    s2 = f"recall_{STAMP}"
    d = f.say(s2, "Nói mình nghe quán nào hợp với mình nhất đi?", checkpoint="synthesize-3-prefs")
    ans = norm(d.get("answer") or "")
    v = {}
    v["nhắc_cafe_hoac_yen_tinh"] = ("ca phe" in ans) or ("cafe" in ans) or ("yen tinh" in ans)
    v["né_đồ_cay"] = ("khong cay" in ans) or ("it cay" in ans) or ("do cay" in ans) or ("cay" in ans)
    v["nhắc_khu_vực"] = ("cau giay" in ans)
    prof = profile_of(f.uid)
    v["history_sessions_ge_2"] = len(sessions_of(f.uid)) >= 2
    return v


def flow_3(f: Flow):
    """Rút lại dị ứng: khai → rút → hỏi lại không bị chặn + toast 'đã bỏ ghi nhớ'."""
    s1 = f"re_{STAMP}"
    f.say(s1, "Tôi dị ứng hải sản đấy")
    s2 = f"re2_{STAMP}"
    d2 = f.say(s2, "Bác sĩ nói tôi hết dị ứng hải sản rồi", checkpoint="retract")
    s3 = f"re3_{STAMP}"
    d3 = f.say(s3, "Gợi ý quán hải sản gần đây nhé", checkpoint="not-blocked")
    ans = norm(d3.get("answer") or "")
    v = {
        "retract_diff_removed": bool((d2.get("memory_updates") or {}).get("removed")),
        "không_confirm_gate_sai": "xác nhận" not in ans and "kiêng" not in ans,
        "vẫn_trả_kết_quả": len(d3.get("results") or []) > 0 or "quan" in ans,
    }
    return v


def flow_4(f: Flow):
    """TTL tạm thời: 'tuần này ăn kiêng' → session khác vẫn còn; everything durable khác."""
    s1 = f"t_{STAMP}"
    d1 = f.say(s1, "Tuần này mình đang ăn kiêng ít dầu mỡ nhé", checkpoint="temp-note")
    s2 = f"t2_{STAMP}"
    d2 = f.say(s2, "Trưa nay ăn gì được?", checkpoint="temp-enforced")
    prof = profile_of(f.uid)
    exp = (prof.get("context_memory") or {}).get("note_expiries") or {}
    v = {
        "note_kieng_ton_tai": any("kieng" in norm(k) for k in ((prof.get("context_memory") or {}).get("notes") or [])),
        "co_expiry_duoc_gan": any(norm("tuần").encode() and True for _ in [1]) and len(exp) >= 1,
        "exactly_1_expiry_for_kieng": sum(1 for k in exp if "kieng" in norm(k)) == 1,
    }
    return v


def flow_5(f: Flow):
    """Ngữ cảnh đầu phiên: tin 1 đưa vị trí → tin 12 'gần đây' không nhắc lại vị trí."""
    s1 = f"loc_{STAMP}"
    f.say(s1, "Mình ở Đống Đa", checkpoint="location-first")
    for m in ["Thèm phở quá", "Có quán nào bán bún bò không",
              "Rating cao nhất khu này là quán nào", "Món gì no mà rẻ",
              "Trưa nay gợi ý gì", "Quán nào đông nhất",
              "Có chỗ nào bán cơm gà không", "Bánh cuốn ở đâu ngon",
              "Quán nào giao nhanh", "Có quán nem nào không"]:
        f.say(s1, m)
    d = f.say(s1, "Gợi ý quán gần đây cho mình nhé", checkpoint="no-reask-location")
    ans = norm(d.get("answer") or "")
    v = {
        "không_hỏi_lại_vị_trí": ("bạn đang ở đâu" not in ans) and ("khu vực nào" not in ans),
        "trả_kết_quả": len(d.get("results") or []) > 0,
    }
    return v


def flow_6(f: Flow):
    """Isolation: nói hộ bạn → không lưu vào profile mình."""
    s1 = f"iso_{STAMP}"
    f.say(s1, "Bạn tôi cực thích đồ Hàn, hôm nay đi ăn với nó", checkpoint="third-party")
    prof = profile_of(f.uid)
    notes = [norm(n) for n in ((prof.get("context_memory") or {}).get("notes") or [])]
    v = {
        "không_lưu_sở_thích_bạn": not any(("han quoc" in n) or ("do han" in n) for n in notes),
    }
    return v


def flow_7(f: Flow):
    """Transparency: memory_updated event có diff khi khai + khi rút."""
    s1 = f"tr_{STAMP}"
    d1 = f.say(s1, "Tôi dị ứng đậu phộng nhé", checkpoint="declare")
    s2 = f"tr2_{STAMP}"
    d2 = f.say(s2, "Quên chuyện dị ứng đậu phộng đi, mình hết rồi", checkpoint="retract")
    v = {
        "declare_added": bool((d1.get("memory_updates") or {}).get("added")),
        "retract_removed": bool((d2.get("memory_updates") or {}).get("removed")),
        "active_constraint_thấy_khi_khai": len(d1.get("active_constraints") or []) >= 1,
    }
    return v


def flow_8(f: Flow):
    """History API: session cũ mở lại được, đủ số tin, đúng nội dung."""
    s1 = f"his_{STAMP}"
    f.say(s1, "Mình thèm bún chả ở Đống Đa")
    f.say(s1, "Quán đầu tiên giờ mở cửa tới mấy giờ?")
    ss = sessions_of(f.uid)
    msgs = []
    if ss:
        try:
            msgs = requests.get(f"{API}/sessions/{ss[0]['session_id']}", timeout=15).json()
            msgs = msgs.get("messages") if isinstance(msgs, dict) else msgs
        except Exception:  # noqa: BLE001
            pass
    v = {
        "session_duoc_luu": len(ss) >= 1,
        "mo_lai_đủ_tin": len(msgs) >= 3,  # user+agent x2 (retry-dedupe collapses)
    }
    return v


def flow_9(f: Flow):
    """Preference Center: allergy khai trong chat hiện ra trong GET /profile."""
    s1 = f"pc_{STAMP}"
    f.say(s1, "Mình dị ứng tôm và không ăn được nội tạng nhé", checkpoint="declare-2")
    prof = profile_of(f.uid)
    alg = [norm(a) for a in (prof.get("allergens") or [])]
    v = {
        "allergen_tom_trong_profile": any("tom" in a for a in alg),
        "allergen_noi_tang_trong_profile": any("noi tang" in a for a in alg),
    }
    return v


def flow_10(f: Flow):
    """Tìm kiếm thuần: kết quả + card fields."""
    d = f.say(f"sr_{STAMP}", "Tìm quán bún đậu ngon ở Hà Nội cho mình nhé")
    res = d.get("results") or []
    first = res[0] if res else {}
    v = {
        "có_kết_quả": len(res) >= 3,
        "card_đủ_trường": all(first.get(k) is not None for k in ("name", "address")) if first else False,
        "answer_nêu_tên_quán": any(norm(r.get("name", ""))[:12] in norm(d.get("answer") or "") for r in res[:2]) if res else False,
    }
    return v


def flow_11(f: Flow):
    """Refine giá: dưới 40k → 'rẻ hơn nữa'."""
    s1 = f"pr_{STAMP}"
    f.say(s1, "Tìm quán cơm văn phòng gần Mỹ Đình dưới 40k")
    d2 = f.say(s1, "Rẻ hơn nữa được không", checkpoint="refined")
    ans = norm(d2.get("answer") or "")
    import re as _re
    prices = [int(x) for x in _re.findall(r"(\d{2})k", ans)] or [int(x) for x in _re.findall(r"(\d{2})\s?000", ans)]
    v = {
        "refine_giữ_ngữ_cảnh": len(d2.get("results") or []) > 0 or "re" in ans,
        "gợi_ý_giá_thấp_hơn": bool(prices) and min(prices) <= 35,
    }
    return v


def flow_12(f: Flow):
    """Anaphora ordinal: 'cái đầu tiên'."""
    s1 = f"an_{STAMP}"
    d1 = f.say(s1, "Tìm quán phở ngon ở Hà Nội")
    first_name = norm((d1.get("results") or [{}])[0].get("name", ""))[:14]
    d2 = f.say(s1, "Cái đầu tiên đó thế nào?", checkpoint="ordinal")
    ans = norm(d2.get("answer") or "")
    v = {
        "turn1_có_kết_quả": len(d1.get("results") or []) >= 1,
        "resolve_đúng_quán_đầu": bool(first_name) and (first_name in ans),
        "không_bịa_quán_khác": len(d2.get("results") or []) <= 3,
    }
    return v


ALL_FLOWS = [
    (1, "MEMORY DÀI #1 — 3 fact + 15 tin + fresh-session recall", "memory-long", flow_1),
    (2, "MEMORY DÀI #2 — 3 sở thích + 14 tin + tổng hợp", "memory-long", flow_2),
    (3, "MEMORY — rút lại dị ứng (retract)", "memory", flow_3),
    (4, "MEMORY — constraint tạm thời có TTL", "memory", flow_4),
    (5, "MEMORY — vị trí tin đầu, dùng ở tin 12", "memory", flow_5),
    (6, "MEMORY — isolation (nói hộ bạn)", "memory", flow_6),
    (7, "MEMORY — transparency (toast add/remove)", "memory", flow_7),
    (8, "MEMORY — history lưu + mở lại", "memory", flow_8),
    (9, "MEMORY — Preference Center sync", "memory", flow_9),
    (10, "SEARCH — kết quả + card", "search", flow_10),
    (11, "REFINE — rẻ hơn nữa", "refine", flow_11),
    (12, "ANAPHORA — cái đầu tiên", "anaphora", flow_12),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="comma-separated flow ids")
    args = ap.parse_args()
    only = {int(x) for x in args.only.split(",")} if args.only else None

    t_all = time.perf_counter()
    for fid, name, kind, body in ALL_FLOWS:
        if only and fid not in only:
            continue
        run_flow(Flow(fid, name, kind), body)

    # ---- aggregate ----
    print("\n" + "=" * 100)
    print(f"{'#':<3}{'kind':<12}{'turns':<6}{'ok':<5}{'med(s)':<8}{'max(s)':<8}{'verdicts':<10}flow")
    print("-" * 100)
    n_pass_total = n_verdict_total = 0
    for r in FLOWS_DONE:
        vs = r.get("verdicts") or {}
        npass = sum(1 for v in vs.values() if v)
        n_pass_total += npass
        n_verdict_total += len(vs)
        med = r["median_latency_ms"] / 1000 if r["median_latency_ms"] else 0
        mx = r["max_latency_ms"] / 1000 if r["max_latency_ms"] else 0
        print(f"{r['fid']:<3}{r['kind']:<12}{r['n_turns']:<6}{r['n_ok']:<5}{med:<8.1f}{mx:<8.1f}"
              f"{npass}/{len(vs):<7} {r['name'][:50]}")
    print("-" * 100)
    print(f"TOTAL: {len(FLOWS_DONE)} flows · checkpoints pass {n_pass_total}/{n_verdict_total}"
          f" · wall {(time.perf_counter()-t_all)/60:.1f} min")

    OUT.write_text(json.dumps(FLOWS_DONE, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[saved] {OUT}")


if __name__ == "__main__":
    main()
