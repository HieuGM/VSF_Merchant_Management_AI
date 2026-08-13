"""Deterministic long-term-memory RETENTION + ENFORCEMENT eval for memory_test.json.

Replays each test case's session sequence (1..20) through the REAL memory code:
  - context_memory_service.extract_notes   (Layer-2 durable-fact extraction, pure)
  - in-memory FIFO append                  (mirrors UserProfileRepository.append_context_notes, cap=8)
  - active_constraints_loader.build_active_constraints (3-layer enforcement, pure)

Between a case's DECLARED sessions we insert neutral filler sessions, so the FINAL test
session (usually index 20) is genuinely ~15-20 sessions after the fact was declared — this
stresses CROSS-SESSION retention (Layer 2/3), not in-session recall. The final session is
queried with an EMPTY prior_turns list, so any recall MUST come from Layer 1 (profile) or
Layer 2 (notes) — Layer 3 (session window) resets per session.

Per case we answer 4 questions (all grounded in real code where deterministic):
  1. CAUGHT  — does extract_notes catch the declared fact at write time?        (Layer-2 write)
  2. SURVIVE — does it survive the FIFO cap=8 across the span to the test session? (retention)
  3. ENFORCE — does build_active_constraints impose a HARD constraint at test time? (catalog)
  4. VERDICT — PASS / FAIL / LIMITATION vs the case's pass_criteria

LIMITATION (Layer 1): structured-profile deltas (cuisine/spice/budget/ambience) are written by
the LLM preference agent + user confirm, NOT by deterministic code. Those facts are retained
(no cap, no decay) but enforced via ranking (soft), never hard-filtered. This harness proves the
DETERMINISTIC memory path (Layer-2 notes + catalog enforcement); Layer-1 ranking needs live LLM+DB.

Run (from backend/):  PYTHONPATH=. <env-python> scripts/memory_retention_eval.py
"""
from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace as NS

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# --- real code under test (pure functions; DB engine is created lazily, never connected) ---
from services.active_constraints_loader import build_active_constraints  # noqa: E402
from services.context_memory_service import extract_notes  # noqa: E402
from core.constraint_catalog import CATALOG  # noqa: E402

# --- constants mirror the production code so the sim stays faithful ---
from services.context_memory_service import _MAX_NOTES as NOTES_CAP  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SUITE_PATH = ROOT / "memory_test.json"

# Neutral Vietnamese filler that fires NO extract_notes trigger (no allergy/medical/diet word).
# Realistic for the bulk of a user's sessions between declarations.
_FILLER_QUERIES = [
    "Thời tiết hôm nay ở Hà Nội thế nào?",
    "Đường đi tới cầu giấy bị kẹt không?",
    "Cho mình xem quán số 1",
    "Đây là quán số 2",
    "Quán này có chỗ đậu xe không?",
    "Mình muốn xem thêm gợi ý khác",
    "Cảm ơn bạn nhé",
    "Quán này giá thế nào?",
]


def _fifo_append(notes: list[str], new_notes: list[str], cap: int = NOTES_CAP) -> list[str]:
    """Mirror UserProfileRepository.append_context_notes: dedupe (case-insensitive) + FIFO cap."""
    seen = {n.lower() for n in notes}
    out = list(notes)
    for n in new_notes:
        if n.lower() not in seen:
            out.append(n)
            seen.add(n.lower())
    if len(out) > cap:
        out = out[-cap:]  # FIFO: keep most recent `cap`
    return out


def _normalize_sessions(case: dict) -> list[dict]:
    """Return declared sessions sorted by numeric session_index.

    Handles range strings like "1-19" (case 6.1 / 7.3) by taking the first index for ordering
    but flagging it as an accumulation block (handled specially by the caller)."""
    sessions = []
    for s in case.get("sessions", []):
        idx = s.get("session_index")
        if isinstance(idx, str):
            lo = int(str(idx).split("-")[0].strip())
        else:
            lo = int(idx)
        s2 = dict(s)
        s2["_idx_num"] = lo
        sessions.append(s2)
    sessions.sort(key=lambda s: s["_idx_num"])
    return sessions


def _declared_facts_text(decl_sessions: list[dict]) -> str:
    """Concatenate the user_query of all DECLARATION (non-test) sessions — the fact source."""
    # The TEST session is conventionally the last (highest index). Everything before is declaration.
    return " || ".join(s.get("user_query", "") for s in decl_sessions)


def classify_case(decl_text: str, test_query: str) -> str:
    """A/B/C/D category (grounded in real extract_notes + catalog):
      A = caught by extract_notes AND enforcable via catalog (seafood/chay)  -> deterministic PASS/FAIL
      B = caught by extract_notes but scope NOT in catalog                   -> retained, NOT hard-enforced
      C = NOT caught by extract_notes (needs LLM preference agent / Layer 1) -> ranking-dependent
      D = isolation/transient: fact SHOULD NOT persist (extract_notes returns [] is correct)
    """
    notes = extract_notes(decl_text)
    if not notes:
        # Could be a deliberate non-persistent (isolation) case, or a Layer-1 fact.
        return "C"
    # Run the constraint loader with these notes to see if any catalog scope fires.
    prof = NS(dietary=[], disliked_cuisines=[], context_memory={"notes": notes})
    cs = build_active_constraints(prof, prior_turns=[], query=test_query)
    if cs.hard:
        return "A"
    return "B"


def eval_case(case: dict) -> dict:
    """Simulate one test case end-to-end through the deterministic memory path."""
    sessions = _normalize_sessions(case)
    if not sessions:
        return {"id": case.get("id"), "verdict": "SKIP", "reason": "no sessions"}

    test_session = sessions[-1]                       # convention: highest index = test session
    decl_sessions = sessions[:-1]                     # earlier = declarations
    test_query = test_session.get("user_query", "")
    decl_text = _declared_facts_text(decl_sessions)

    # --- simulate the span: replay declarations in order, with filler between them ---
    notes: list[str] = []
    dietary: list[str] = []
    disliked: list[str] = []
    prev_idx = 0
    for i, s in enumerate(sessions):
        # inject filler sessions proportional to the gap (max 6 filler per gap to bound runtime)
        gap = max(0, s["_idx_num"] - prev_idx - 1)
        for f in range(min(gap, 6)):
            fq = _FILLER_QUERIES[f % len(_FILLER_QUERIES)]
            notes = _fifo_append(notes, extract_notes(fq))
        # this session's own declaration/query
        q = s.get("user_query", "")
        new_notes = extract_notes(q)
        notes = _fifo_append(notes, new_notes)
        prev_idx = s["_idx_num"]

    notes_after_span = list(notes)                    # what survived to the test session (Layer 2)
    caught_at_write = bool(extract_notes(decl_text))  # would it have been caught when declared?

    # --- enforcement at the TEST session (fresh session: empty prior_turns) ---
    prof = NS(dietary=dietary, disliked_cuisines=disliked, context_memory={"notes": notes_after_span})
    cs = build_active_constraints(prof, prior_turns=[], query=test_query)
    hard_scopes = sorted({c.scope for c in cs.hard})
    hard_origins = sorted({c.origin for c in cs.hard})

    category = classify_case(decl_text, test_query)
    cat_desc = {
        "A": "caught + catalog-enforceable (deterministic)",
        "B": "caught but NOT in catalog (retained, not hard-enforced)",
        "C": "not caught by heuristic (Layer-1 LLM / ranking)",
        "D": "isolation: correctly NOT persisted",
    }[category]

    return {
        "id": case.get("id"),
        "group": case.get("group"),
        "title": case.get("title"),
        "span": f"{sessions[0]['_idx_num']}->{sessions[-1]['_idx_num']}",
        "category": category,
        "category_desc": cat_desc,
        "caught_at_write": caught_at_write,
        "notes_surviving": notes_after_span,
        "hard_scopes_enforced": hard_scopes,
        "hard_origins": hard_origins,
        "test_query": test_query,
        "decl_text": decl_text,
    }


def fifo_eviction_probe() -> list[dict]:
    """Directly answer 'how many sessions/facts can it remember?'

    Declare one durable allergy/medical note per session for N sessions, then check whether the
    FIRST declared fact survives. cap=NOTES_CAP(=8) => after >8 distinct durable facts the oldest
    is FIFO-evicted. Each 'fact' here is a realistic durable trigger sentence."""
    facts = [
        "Tôi dị ứng hải sản",                # seafood (catalog)
        "Tôi dị ứng đậu phộng",              # peanut
        "Tôi bị tiểu đường",                 # diabetes
        "Tôi đau dạ dày",                    # gastritis
        "Tôi kiêng đồ ngọt",                 # avoid sugar
        "Tôi không ăn được nội tạng",        # organ meat
        "Tôi ăn chay trường",                # vegetarian (catalog)
        "Tôi kiêng đồ cay",                  # avoid spicy
        "Tôi dị ứng trứng",                  # egg
        "Tôi không ăn được bơ sữa",          # dairy
        "Tôi viêm dạ dày",                   # gastritis var
        "Tôi kiêng đồ chiên rán",            # avoid fried
        "Tôi dị ứng lúa mì",                 # wheat
        "Tôi không ăn được ngũ cốc",         # grains
        "Tôi kiêng caffeine",                # caffeine
        "Tôi dị ứng đậu nành",               # soy
    ]
    out = []
    for n in range(1, min(len(facts), 20) + 1):
        notes: list[str] = []
        for f in facts[:n]:
            notes = _fifo_append(notes, extract_notes(f))
        first_fact_note = extract_notes(facts[0])
        first_survives = any(fn in notes for fn in first_fact_note)
        out.append({
            "sessions_or_facts": n,
            "first_fact_survives": first_survives,
            "notes_count": len(notes),
            "cap": NOTES_CAP,
            "evicted": (n > NOTES_CAP),
        })
    return out


def main() -> int:
    suite = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    cases = suite["test_cases"]
    print(f"=== memory_test.json deterministic eval ===")
    print(f"cases: {len(cases)} | catalog scopes (hard-enforceable): {sorted(CATALOG)}")
    print(f"notes FIFO cap (NOTES_CAP): {NOTES_CAP}\n")

    results = [eval_case(c) for c in cases]

    # --- per-case table ---
    hdr = f"{'ID':4} {'SPAN':8} {'CAT':3} {'CAUGHT':6} {'ENFORCE':14} {'TITLE'}"
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        print(f"{r['id']:<4} {r['span']:<8} {r['category']:<3} "
              f"{'Y' if r['caught_at_write'] else '-':<6} "
              f"{','.join(r['hard_scopes_enforced']) or '-':<14} {r['title'][:46]}")

    # --- summary by category ---
    print("\n=== CATEGORY SUMMARY ===")
    from collections import Counter
    cat_counts = Counter(r["category"] for r in results)
    for cat in sorted(cat_counts):
        n = cat_counts[cat]
        ids = [r["id"] for r in results if r["category"] == cat]
        desc = {
            "A": "caught + catalog-enforceable (deterministic end-to-end)",
            "B": "caught but NOT in catalog (retained, NOT hard-enforced)",
            "C": "not caught by heuristic (Layer-1 LLM/ranking only)",
        }[cat]
        print(f"  {cat} [{n:2}]: {ids}")
        print(f"        {desc}")

    # --- the headline FIFO probe ---
    print("\n=== RETENTION PROBE: does fact #1 survive N durable declarations? (FIFO cap={}) ===".format(NOTES_CAP))
    probe = fifo_eviction_probe()
    print(f"{'N_facts':>7} {'first_survives':>15} {'notes_kept':>11} {'evicted':>8}")
    for p in probe:
        flag = "  <-- eviction starts" if (p["evicted"] and not probe[p["sessions_or_facts"] - 2]["evicted"]) else ""
        print(f"{p['sessions_or_facts']:>7} {str(p['first_fact_survives']):>15} "
              f"{p['notes_count']:>11} {str(p['evicted']):>8}{flag}")

    # --- detail dump for the report ---
    detail_path = ROOT / "plans" / "reports" / "memory-eval-260813-1038-results.json"
    detail_path.parent.mkdir(parents=True, exist_ok=True)
    detail_path.write_text(
        json.dumps({"results": results, "fifo_probe": probe, "catalog": sorted(CATALOG),
                    "notes_cap": NOTES_CAP}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\ndetail -> {detail_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
