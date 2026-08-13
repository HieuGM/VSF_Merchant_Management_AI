"""Live DB-level probe of the context_memory.notes FIFO cap (the 15-20 session retention limit).

Uses the REAL UserProfileRepository.append_context_notes against the REAL Postgres to insert 9
distinct durable allergy/medical notes one session at a time, then checks whether the FIRST
fact survived. cap=8 => the first note MUST be FIFO-evicted by the 9th. No LLM involved — this
isolates the storage/retention layer exactly as production uses it.

Run (from backend/):  PYTHONPATH=. <env-python> scripts/memory_fifo_db_probe.py
"""
from __future__ import annotations

import io
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from database.connection import SessionLocal  # noqa: E402
from repositories.user_profile_repository import UserProfileRepository  # noqa: E402
from services.context_memory_service import _MAX_NOTES as NOTES_CAP  # noqa: E402

UID = f"fifo_probe_{int(time.time())}"

# 9 distinct durable-fact sentences (each fires a real extract_notes trigger).
FACTS = [
    "Tôi dị ứng hải sản",            # 1 — seafood (catalog)
    "Tôi dị ứng đậu phộng",          # 2 — peanut
    "Tôi bị tiểu đường",             # 3
    "Tôi đau dạ dày",                # 4
    "Tôi kiêng đồ ngọt",             # 5
    "Tôi không ăn được nội tạng",    # 6
    "Tôi ăn chay trường",            # 7 — chay (catalog)
    "Tôi kiêng đồ cay",              # 8
    "Tôi dị ứng trứng",              # 9 — this one should evict fact #1
]


def _notes(uid: str) -> list[str]:
    db = SessionLocal()
    try:
        row = UserProfileRepository(db).get_by_id(uid)
    finally:
        db.close()
    # get_by_id returns UserProfilePublic whose context_memory holds the notes
    return list((row.context_memory or {}).get("notes") or []) if row else []


def main() -> int:
    print(f"UID={UID}  NOTES_CAP={NOTES_CAP}  facts_to_insert={len(FACTS)}")
    print(f"{'step':>4} {'insert':46} {'notes_count':>12} {'#1_survives':>12}")
    survived_at_end = None
    for i, fact in enumerate(FACTS, 1):
        db = SessionLocal()
        try:
            UserProfileRepository(db).append_context_notes(UID, [fact], cap=NOTES_CAP)
        finally:
            db.close()
        notes = _notes(UID)
        first_alive = FACTS[0] in notes
        if i == len(FACTS):
            survived_at_end = first_alive
        print(f"{i:>4} {fact[:46]:46} {len(notes):>12} {str(first_alive):>12}")
    notes = _notes(UID)
    print("\n--- result ---")
    print(f"facts inserted      : {len(FACTS)}")
    print(f"notes kept          : {len(notes)} (cap {NOTES_CAP})")
    print(f"FIRST fact survived : {survived_at_end}")
    print(f"eviction happened   : {not survived_at_end}  (expected True since {len(FACTS)} > cap {NOTES_CAP})")
    print(f"first {NOTES_CAP} evicted, tail kept: {notes}")
    # cleanup so we don't pollute the profile table
    db = SessionLocal()
    try:
        UserProfileRepository(db).clear_memory(UID)
    finally:
        db.close()
    print(f"cleanup: cleared memory for {UID}")
    return 0 if (not survived_at_end and len(notes) == NOTES_CAP) else 1


if __name__ == "__main__":
    sys.exit(main())
