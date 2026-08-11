"""Cross-conversation recall (memory-system P2b).

Folded-Vietnamese keyword match of the current query against a user's recent
conversation distillates (stored under chat_sessions.context_snapshot_json['distillate']
by conversation_distillate_service). No embedder — YAGNI at <50 conversations; linear
scan + fold-ILIKE on intent / last_query / cuisines. Returns the top-k recalled
distillate dicts (most query-token overlap first; newest breaks ties).

Best-effort; the caller (flows.customer_flow._cross_conv_hint) gates this on
memory_cross_conv_enabled and swallows all errors.
"""
from __future__ import annotations

from core.text_norm import fold_diacritics

_MIN_TOKEN = 3  # skip 1-2 char tokens (noise) when scoring overlap


def recall_cross_conv(
    user_id: str,
    query: str,
    k: int = 5,
    exclude_session_id: str | None = None,
) -> list[dict]:
    """Return up to `k` past-conversation distillates matching the query.

    Match = folded-token overlap between the query and each distillate's
    intent + last_query + cuisines. Ranked by overlap desc, then newest first.
    Empty query / no user / no overlap → []. Never raises (DB errors → [])."""
    from database.connection import SessionLocal
    from repositories.session_repository import SessionRepository

    qfold = fold_diacritics(query or "")
    qtokens = {t for t in qfold.split() if len(t) >= _MIN_TOKEN}
    if not qtokens or not user_id:
        return []

    try:
        db = SessionLocal()
        try:
            recent = SessionRepository(db).list_recent_distillates(
                user_id, limit=20, exclude_session_id=exclude_session_id
            )
        finally:
            db.close()
    except Exception:
        return []

    scored: list[tuple[int, int, dict]] = []  # (overlap, -order_index, dist)
    for idx, d in enumerate(recent):
        hay = fold_diacritics(
            " ".join(
                [
                    str(d.get("intent") or ""),
                    str(d.get("last_query") or ""),
                    " ".join(str(c) for c in (d.get("cuisines") or [])),
                ]
            )
        )
        overlap = sum(1 for t in qtokens if t in hay)
        if overlap > 0:
            # -idx so a newer distillate (lower idx, since list is newest-first) wins ties.
            scored.append((overlap, -idx, d))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [d for _, _, d in scored[:k]]
