#!/usr/bin/env python3
"""Interactive Mini-CLI for testing Policy RAG Retrieval Phase."""

from __future__ import annotations

import sys
from pathlib import Path

# Add backend directory to sys.path
ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database.connection import get_db_session
from services.policy_rag_service import PolicyRagService


def main():
    print("==================================================")
    print("   Green SM Policy RAG Interactive Tester (v2)   ")
    print("==================================================")

    db_gen = get_db_session()
    db = next(db_gen)

    try:
        rag_service = PolicyRagService(db=db)

        while True:
            query = input("\nType your query (type 'q' to quit): ").strip()
            if not query or query.lower() == "q":
                print("Exiting RAG Tester. Goodbye!")
                break

            print(f"\n[RAG Service] Searching for: '{query}'...")
            res = rag_service.search(query=query, top_k=5)
            results = res.get("results", [])

            if not results:
                print(" -> No matching policy evidence found.")
                continue

            print(f" -> Found {len(results)} relevant evidence chunk(s):\n")

            for idx, item in enumerate(results, start=1):
                title = item.get("title", "N/A")
                url = item.get("source_url", "N/A")
                sec_path = " > ".join(item.get("section_path", [])) or "Top Level"
                score = item.get("relevance", 0.0)
                text = item.get("text", "").strip()

                print(f"--- Chunk #{idx} (Score: {score:.4f}) ---")
                print(f" Document Title : {title}")
                print(f" Source URL     : {url}")
                print(f" Section Path   : {sec_path}")
                print(f" Content Snippet:\n{text}..." if len(text) > 300 else f" Content Snippet:\n{text}")
                print("-" * 50)
    finally:
        db.close()


if __name__ == "__main__":
    main()
