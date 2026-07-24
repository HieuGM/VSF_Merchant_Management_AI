"""Seed a demo user profile + chat session (Phase 02, idempotent).

Provides `user_demo` so tools `get_user_profile` / `get_session_candidates` have data to
read in tests and the walking skeleton. Safe to run repeatedly (merge / skip if present).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from database.connection import SessionLocal
from database.models import ChatSession, UserProfile

DEMO_USER_ID = "user_demo"
DEMO_SESSION_ID = "session_demo"


def seed_user_demo() -> None:
    """Insert the demo user + session if they do not already exist (idempotent)."""
    db = SessionLocal()
    try:
        if db.get(UserProfile, DEMO_USER_ID) is None:
            db.add(
                UserProfile(
                    user_id=DEMO_USER_ID,
                    liked_cuisines=["Vietnamese", "Japanese"],
                    disliked_cuisines=[],
                    spice_tolerance="medium",
                    dietary=[],
                    budget_level="standard",
                    distance_preference_km=5.0,
                    current_lat=10.7769,
                    current_lng=106.7009,
                    context_memory={},
                )
            )
            print(f"[OK] Inserted user profile '{DEMO_USER_ID}'")
        else:
            print(f"[OK] User profile '{DEMO_USER_ID}' already exists")

        if db.get(ChatSession, DEMO_SESSION_ID) is None:
            db.add(
                ChatSession(
                    session_id=DEMO_SESSION_ID,
                    user_id=DEMO_USER_ID,
                    title="Demo discovery session",
                    context_snapshot_json={"candidates": []},
                )
            )
            print(f"[OK] Inserted chat session '{DEMO_SESSION_ID}'")
        else:
            print(f"[OK] Chat session '{DEMO_SESSION_ID}' already exists")

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed_user_demo()
