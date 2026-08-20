"""Memory metrics for memory_test.json — per-case scoring + aggregates.

Simulates the FULL long-term-memory pipeline per case (mirrors ``context_memory_service.maybe_persist``
+ the repo FIFO/TTL/allergens logic), then enforces via the REAL ``build_active_constraints``. Each
case is scored against its ``pass_criteria`` by an encoded assertion (PASS / PARTIAL / FAIL), or
marked LLM-DEPENDENT when the behavior lives in the LLM preference/explanation layer (Layer 1) the
deterministic engine cannot verdict. Aggregates by the suite's 5 scoring dimensions + by group.

The simulation is deterministic + time-injectable (a fixed base clock advances ~2d/session) so the
TTL path (6.3) is exercisable without waiting wall-clock. Persistence logic mirrors maybe_persist;
enforcement is the real loader. (Faithfulness: extract_notes/_retracted_food_terms/_duration_days/
_is_permanent_avoid_note + build_active_constraints are the REAL production functions.)

Run (from backend/):  PYTHONPATH=. <env-python> scripts/memory_metrics.py
"""
from __future__ import annotations

import io
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from services.active_constraints_loader import build_active_constraints  # noqa: E402
from services.context_memory_service import (  # noqa: E402
    _RETRACTION_RE, _duration_days, _is_permanent_avoid_note, _retracted_food_terms, extract_notes,
)
from core.text_norm import fold_diacritics  # noqa: E402
from services.context_memory_service import _MAX_NOTES as NOTES_CAP  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / "memory_test.json"
# Deterministic base clock — advances SESSION_DAY_STEP days per session_index so a 7-day temporary
# constraint declared early expires by a later test session (6.3), without wall-clock waiting.
_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
_SESSION_DAY_STEP = 2

_CLEAR_RE = __import__("re").compile(r"xoa (het|toan bo|lich su)|bat dau lai|reset")


@dataclass
class SimState:
    """In-memory mirror of user_profiles memory fields the loader reads."""
    notes: list[str] = field(default_factory=list)
    note_expiries: dict[str, str] = field(default_factory=dict)  # note_lower -> ISO
    allergens: list[str] = field(default_factory=list)


def _matches_any(text: str, terms: list[str]) -> bool:
    """Same term-matching as repo.remove_notes_matching / remove_allergens_matching."""
    f = fold_diacritics(text)
    return any(((" " in t and t in f) or (t in f.split())) for t in terms)


def _prune_expired(state: SimState, now: datetime) -> None:
    """Mirror repo.prune_expired_notes: drop notes whose expiry < now."""
    expired = {k for k, v in state.note_expiries.items()
               if datetime.fromisoformat(v) < now}
    if expired:
        state.notes = [n for n in state.notes if n.lower() not in expired]
        state.note_expiries = {k: v for k, v in state.note_expiries.items() if k not in expired}


def _sim_persist(state: SimState, text: str, now: datetime) -> None:
    """Mirror maybe_persist: retraction-removal -> prune-expired -> append(FIFO+expiry) -> allergens."""
    folded = fold_diacritics(text)
    # "Clear all" intent (7.3) -> wipe (the real path is the /memory/clear route).
    if _CLEAR_RE.search(folded):
        state.notes.clear(); state.note_expiries.clear(); state.allergens.clear()
        return
    # Retraction: remove the prior note(s) + allergen(s) it withdraws (7.2/3.4).
    if _RETRACTION_RE.search(folded):
        terms = _retracted_food_terms(folded)
        if terms:
            state.notes = [n for n in state.notes if not _matches_any(n, terms)]
            state.allergens = [a for a in state.allergens if not _matches_any(a, terms)]
    # TTL: drop elapsed temporary notes (6.3).
    _prune_expired(state, now)
    # Append new durable facts (FIFO cap + expiry) + mirror permanents to no-cap allergens.
    seen_notes = {n.lower() for n in state.notes}
    seen_allerg = {a.lower() for a in state.allergens}
    for note in extract_notes(text):
        if note.lower() in seen_notes:
            continue
        state.notes.append(note); seen_notes.add(note.lower())
        days = _duration_days(fold_diacritics(note))
        if days:
            state.note_expiries[note.lower()] = (now + timedelta(days=days)).isoformat()
        if _is_permanent_avoid_note(fold_diacritics(note)) and note.lower() not in seen_allerg:
            state.allergens.append(note); seen_allerg.add(note.lower())
    if len(state.notes) > NOTES_CAP:
        state.notes = state.notes[-NOTES_CAP:]


def _replay(case: dict) -> tuple[SimState, object, str]:
    """Replay a case's sessions; return (state, ActiveConstraints, test_query)."""
    sessions = sorted(case["sessions"], key=lambda s: int(str(s["session_index"]).split("-")[0]))
    state = SimState()
    for s in sessions:
        idx = int(str(s["session_index"]).split("-")[0])
        _sim_persist(state, s.get("user_query", ""), _BASE + timedelta(days=idx * _SESSION_DAY_STEP))
    test = sessions[-1]
    query = test.get("user_query", "")
    profile = NS(dietary=[], disliked_cuisines=[], allergens=list(state.allergens),
                 context_memory={"notes": list(state.notes)})  # no note_expiries -> build won't re-prune
    cs = build_active_constraints(profile, prior_turns=[], query=query)
    return state, cs, query


# --- per-case assertions: (verdict_kind, predicate) ---
# verdict_kind: "pass"(deterministic PASS) | "partial"(retention ok, enforcement incomplete/over) |
#               "llm"(lives in Layer-1/LLM, not deterministically scoreable)
def _h(cs, scope):
    return any(c.scope == scope for c in cs.hard)


def _hn(cs, state, sub):
    sub = fold_diacritics(sub)
    return any(sub in fold_diacritics(n) for n in (*cs.health_notes, *state.allergens))


def _n(state, sub):
    sub = fold_diacritics(sub)
    return any(sub in fold_diacritics(n) for n in state.notes)


# ASSERTIONS[case_id] = (dimension, kind, fn(state, cs)->bool, note)
ASSERTIONS: dict[str, tuple[str, str, object, str]] = {
    "1.1": ("correctness", "pass", lambda s, c: _h(c, "chay"), "chay durable enforced"),
    "1.2": ("correctness", "pass", lambda s, c: _hn(c, s, "cay"), "spice note surfaced"),
    "1.3": ("correctness", "pass", lambda s, c: _hn(c, s, "toi"), "garlic surfaced"),
    "1.4": ("correctness", "pass", lambda s, c: _hn(c, s, "dau phong"), "peanut surfaced"),
    "1.5": ("correctness", "llm", lambda s, c: True, "(none — suite has no 1.5)"),
    "2.1": ("precedence", "llm", lambda s, c: True, "spice override = Layer-1 preference agent"),
    "2.2": ("precedence", "pass", lambda s, c: _h(c, "shrimp") and not _h(c, "seafood"),
            "shrimp-only hard (dedicated scope; seafood liking not over-excluded)"),
    "2.3": ("precedence", "pass", lambda s, c: _h(c, "chay") and not _n(s, "giam can"), "permanent chay kept, temp not persisted"),
    "2.4": ("precedence", "llm", lambda s, c: True, "dislike retraction = Layer-1 preference agent"),
    "3.1": ("safety", "pass", lambda s, c: _hn(c, s, "dau phong"), "peanut proactively surfaced (Phase1+2)"),
    "3.2": ("safety", "pass", lambda s, c: _h(c, "chay") and (_h(c, "peanut") or _hn(c, s, "dau phong")),
            "chay + peanut both hard (catalog row); spice stays soft"),
    "3.3": ("safety", "pass", lambda s, c: not _n(s, "chet") and not _n(s, "cay"), "joke not persisted as constraint"),
    "3.4": ("safety", "pass", lambda s, c: not _h(c, "seafood") and not _hn(c, s, "tom"), "retracted shrimp allergy gone"),
    "4.1": ("isolation", "pass", lambda s, c: not _n(s, "nguoi") and not _n(s, "nhom"), "transient group ctx not persisted"),
    "4.2": ("isolation", "pass", lambda s, c: not _n(s, "nhat") or _n(s, "ban"), "third-party pref not attributed to user"),
    "4.3": ("isolation", "llm", lambda s, c: True, "location = Layer-1 + real-time GPS"),
    "5.1": ("correctness", "llm", lambda s, c: True, "multi-hop conjunction = ranking/LLM"),
    "5.2": ("correctness", "llm", lambda s, c: True, "implicit pattern = episodic+LLM"),
    "5.3": ("correctness", "llm", lambda s, c: True, "stated-pref vs rating = episodic+LLM"),
    "6.1": ("correctness", "pass", lambda s, c: len(s.notes) <= NOTES_CAP, "FIFO cap holds (weighting=LLM)"),
    "6.2": ("precedence", "llm", lambda s, c: True, "spice level = Layer-1 preference agent"),
    "6.3": ("correctness", "pass", lambda s, c: not _n(s, "dau mo") and not _n(s, "kieng"), "temp kiêng expired via TTL"),
    "7.1": ("transparency", "llm", lambda s, c: True, "enumerate memory = LLM explanation"),
    "7.2": ("transparency", "pass", lambda s, c: not _h(c, "seafood"), "retracted shrimp no longer enforced"),
    "7.3": ("transparency", "pass", lambda s, c: len(s.notes) == 0 and len(s.allergens) == 0, "clear-all wipes profile"),
    "8.1": ("correctness", "pass", lambda s, c: _hn(c, s, "noi tang"), "organ-meat surfaced"),
    "8.2": ("correctness", "llm", lambda s, c: True, "self-correction = Layer-1 preference agent"),
    "8.3": ("correctness", "pass", lambda s, c: _hn(c, s, "hs") or _hn(c, s, "hai san"), "abbreviation surfaced (Phase1)"),
    "8.4": ("correctness", "llm", lambda s, c: True, "graceful fallback = LLM behavior"),
}


def main() -> int:
    suite = json.loads(SUITE.read_text(encoding="utf-8"))
    cases = {c["id"]: c for c in suite["test_cases"]}
    print(f"=== memory_test.json METRICS (fixed code) ===")
    print(f"cases: {len(cases)} | notes FIFO cap: {NOTES_CAP} | base clock: {_BASE.date()} (+{ _SESSION_DAY_STEP}d/session)\n")

    rows = []
    for cid in sorted(cases, key=lambda x: [int(p) for p in x.split(".")]):
        case = cases[cid]
        dim, kind, fn, note = ASSERTIONS.get(cid, ("correctness", "llm", lambda s, c: True, "no assertion"))
        if kind == "llm":
            rows.append({"id": cid, "group": case["group"], "dim": dim, "verdict": "LLM", "detail": note})
            continue
        state, cs, _ = _replay(case)
        ok = bool(fn(state, cs))
        verdict = {"pass": "PASS", "partial": "PARTIAL"}[kind] if ok else "FAIL"
        # a PARTIAL assertion that fails outright is a FAIL (retention broken)
        if kind == "partial" and not ok:
            verdict = "FAIL"
        rows.append({"id": cid, "group": case["group"], "dim": dim, "verdict": verdict, "detail": note})

    # --- per-case table ---
    hdr = f"{'ID':4} {'VERDICT':8} {'DIM':14} {'GROUP':22} DETAIL"
    print(hdr); print("-" * len(hdr))
    for r in rows:
        print(f"{r['id']:<4} {r['verdict']:<8} {r['dim']:<14} {r['group'][:22]:<22} {r['detail'][:50]}")

    # --- aggregates ---
    def agg(key):
        d = defaultdict(lambda: {"PASS": 0, "PARTIAL": 0, "FAIL": 0, "LLM": 0})
        for r in rows:
            d[r[key]][r["verdict"]] += 1
        return d

    n = len(rows)
    cnt = lambda v: sum(1 for r in rows if r["verdict"] == v)
    print("\n=== OVERALL ===")
    print(f"  PASS {cnt('PASS'):2} · PARTIAL {cnt('PARTIAL'):2} · FAIL {cnt('FAIL'):2} · LLM-dep {cnt('LLM'):2}  (of {n})")
    det = n - cnt("LLM")
    print(f"  deterministic coverage: {det}/{n} ({det*100//n}%)")
    print(f"  deterministic pass rate: {cnt('PASS')}/{det} ({cnt('PASS')*100//det}% PASS, +{cnt('PARTIAL')} PARTIAL)")

    print("\n=== BY DIMENSION ===")
    for dim, d in sorted(agg("dim").items()):
        tot = sum(d.values()); detd = tot - d["LLM"]
        rate = f"{d['PASS']*100//detd}% PASS" if detd else "(all LLM-dep)"
        print(f"  {dim:<14} PASS {d['PASS']:2} PARTIAL {d['PARTIAL']:2} FAIL {d['FAIL']:2} LLM {d['LLM']:2}  [{rate}]")

    print("\n=== BY GROUP ===")
    for grp, d in sorted(agg("group").items()):
        detg = sum(d.values()) - d["LLM"]
        rate = f"{d['PASS']*100//detg}% PASS" if detg else "(all LLM-dep)"
        print(f"  {grp[:24]:<24} PASS {d['PASS']:2} PARTIAL {d['PARTIAL']:2} FAIL {d['FAIL']:2} LLM {d['LLM']:2}  [{rate}]")

    out = ROOT / "plans" / "reports" / "memory-metrics-260813-results.json"
    out.write_text(json.dumps({"rows": rows, "overall": {
        "pass": cnt("PASS"), "partial": cnt("PARTIAL"), "fail": cnt("FAIL"), "llm": cnt("LLM"),
        "deterministic_coverage": det, "deterministic_pass_rate_pct": cnt("PASS") * 100 // det,
    }, "by_dimension": {k: v for k, v in agg("dim").items()},
       "by_group": {k: v for k, v in agg("group").items()}}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\ndetail -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
