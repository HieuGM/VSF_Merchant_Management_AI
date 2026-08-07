"""Shared Vietnamese text normalization (audit #15).

``fold_diacritics`` lowercases a string to ASCII by stripping Vietnamese combining marks
(NFD) and converting ``đ``/``Đ`` → ``d`` (which do NOT decompose under NFD and would be
DROPPED by ``encode('ascii', 'ignore')`` — the latent bug that was latent in phase-02's
``profile_ranking._fold`` until context_memory's 'tiểu đường' trigger surfaced it).

Single source of truth for diacritics-insensitive matching across the codebase. The former
copies — ``repositories._norm_text``, ``flows._norm_vi``, ``profile_ranking._fold``,
``context_memory_service._fold`` — now alias this. NOTE: ``_norm_text`` must keep agreeing
with the SQL-side ``_norm_col`` translate() in ``repositories/merchant_repository.py``."""
from __future__ import annotations

import unicodedata


def fold_diacritics(value: str | None) -> str:
    """Lowercase + strip Vietnamese diacritics → ASCII.

    'Món Việt' → 'mon viet', 'tiểu đường' → 'tieu duong', 'Đồ cay' → 'do cay'.
    Empty string for None/empty. ``đ``/``Đ`` → ``d`` (not dropped)."""
    if not value:
        return ""
    nfd = unicodedata.normalize("NFD", value)
    no_mark = "".join(ch for ch in nfd if not unicodedata.combining(ch))
    return no_mark.replace("đ", "d").replace("Đ", "d").lower()
