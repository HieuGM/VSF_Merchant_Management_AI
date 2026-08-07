"""Vietnamese number-word → int parser + price-word normalizer (TC-34).

The search agent (gpt-oss-20b) understands a Vietnamese price *conversationally* ("năm chục
nghìn" → it says "dưới 50k") but does not reliably emit it as a numeric ``max_price`` tool param,
so the geo search returns proximity results unfiltered by price — even though ``nearby_search``
supports ``max_price`` as a hard filter. This module converts price-word phrases to DIGITS in the
query so the agent has an explicit number to pass.

Scope (deliberately narrow, high-precision):
- Only fires when a phrase ends in a price UNIT (``nghìn``/``ngàn`` = ×1000, ``triệu`` = ×1e6).
  A bare ``năm`` (in "năm người"/"năm sao") has no unit → never touched.
- Parses the common Vietnamese number grammar (1–999,999): ``[trăm][mươi/chục][đơn vị]`` groups
  under nghìn/triệu. ``mươi`` and ``mười`` both fold to ``muoi`` and are disambiguated by position
  (standalone = 10, after a digit = ×10 marker) — so "mười lăm"=15, "hai mươi lăm"=25.

Not a general Vietnamese NLU — just enough for price slots. Unknown tokens abort the run (returns
the phrase unchanged) rather than risk a wrong number.
"""
from __future__ import annotations

import re

from core.text_norm import fold_diacritics

# Single-digit words (folded). "mốt" folds to "mot" (=1, used in "hai mươi mốt"=21).
_DIGIT = {
    "khong": 0, "mot": 1, "hai": 2, "ba": 3, "bon": 4, "nam": 5,
    "sau": 6, "bay": 7, "tam": 8, "chin": 9,
}
# Unit-position words (1-9). Adds "lăm"=5 (unit in "hai mươi lăm") + "tư"=4 (regional).
_UNIT = {**_DIGIT, "lam": 5, "tu": 4}
# Tens markers (×10): "mươi" (X mươi = X0) and "chục" (X chục = X×10). "mười" (standalone 10)
# folds to "muoi" too — handled positionally in _parse_group.
_TEN_MARKER = {"muoi", "chuc"}
_HUNDRED = "tram"
_GROUP_K = ("nghin", "ngan")   # nghìn / ngàn → ×1000
_MILLION = "trieu"             # triệu → ×1e6

# A token is a vi-number word if it's a digit/unit/tens/hundred marker (used to find runs).
_NUM_TOKENS = set(_UNIT) | _TEN_MARKER | {_HUNDRED}


def _parse_group(toks: list[str], i: int) -> tuple[int, int]:
    """Parse one 0–999 group starting at index ``i``. Returns (value, next_index).

    Group = optional [digit 'trăm'] + optional tens + optional unit:
      - 'mười' (10) [+ unit]            → 10..19
      - 'X mươi'/'X chục' (X×10) [+ unit] → 20..99
      - bare unit                       → 1..9
    """
    val = 0
    n = len(toks)
    # Hundreds: 'X trăm' (X×100), or bare 'trăm' (=100).
    if i < n and toks[i] in _DIGIT and i + 1 < n and toks[i + 1] == _HUNDRED:
        val += _DIGIT[toks[i]] * 100
        i += 2
    elif i < n and toks[i] == _HUNDRED:
        val += 100
        i += 1
    # Tens.
    if i < n:
        t = toks[i]
        if t == "muoi":                                   # 'mười' (10) [+ unit] → 10..19
            val += 10
            i += 1
            if i < n and toks[i] in _UNIT:
                val += _UNIT[toks[i]]
                i += 1
        elif t in _DIGIT and i + 1 < n and toks[i + 1] in _TEN_MARKER:  # 'X mươi'/'X chục' → X0
            val += _DIGIT[t] * 10
            i += 2
            if i < n and toks[i] in _UNIT:                # 'X mươi Y' → X0+Y
                val += _UNIT[toks[i]]
                i += 1
        elif t in _UNIT:                                  # bare unit 1..9
            val += _UNIT[t]
            i += 1
    return val, i


def parse_vi_int(phrase: str | None) -> int | None:
    """Parse a Vietnamese number phrase (1–999,999,999) → int, or None if unparseable/zero.

    Handles nhóm nghìn (×1k) and nhóm triệu (×1e6). Returns None on any unknown token so the
    normalizer leaves the phrase untouched rather than emitting a wrong number."""
    if not phrase:
        return None
    toks = [t for t in fold_diacritics(phrase).replace(",", " ").split() if t]
    if not toks or any(t not in _NUM_TOKENS and t not in _GROUP_K and t != _MILLION for t in toks):
        return None  # unknown word → refuse to guess

    # Split on the largest group multiplier present (triệu, then nghìn).
    if _MILLION in toks:
        mi = toks.index(_MILLION)
        hi, _ = _parse_group(toks[:mi], 0)
        lo, _ = _parse_group(toks[mi + 1:], 0)
        total = hi * 1_000_000 + lo
        return total or None
    k_idx = next((idx for idx, t in enumerate(toks) if t in _GROUP_K), None)
    if k_idx is not None:
        hi, _ = _parse_group(toks[:k_idx], 0)
        lo, _ = _parse_group(toks[k_idx + 1:], 0)
        total = hi * 1000 + lo
        return total or None
    val, _ = _parse_group(toks, 0)
    return val or None


# Maximal run of vi-number tokens (greedy). Used to locate a price phrase; the run must be
# immediately followed by a price unit (nghìn/ngàn/triệu) to count as a price.
_RUN_RE = re.compile(
    r"(?:khong|mot|hai|ba|bon|nam|lam|tu|sau|bay|tam|chin|muoi|chuc|tram)(?:\s+(?:khong|mot|hai|ba|bon|nam|lam|tu|sau|bay|tam|chin|muoi|chuc|tram))*"
)
_UNIT_RE = re.compile(r"^(nghin|ngan|trieu)\b")


def normalize_price_words(query: str | None) -> str | None:
    """Replace Vietnamese price-word phrases in ``query`` with their digit value.

    Only phrases ending in a price unit (nghìn/ngàn/triệu) are converted — a bare ``năm`` (in
    "năm người") is never touched. Operates token-by-token on the ORIGINAL query so non-matched
    words keep their diacritics. Unknown tokens inside a run abort just that run (left unchanged).

    >>> normalize_price_words("giá khoảng năm chục nghìn đổ lại")
    'giá khoảng 50000 đổ lại'
    """
    if not query:
        return query
    words = query.split()
    if not words:
        return query
    out: list[str] = []
    i = 0
    n = len(words)
    while i < n:
        folded = fold_diacritics(words[i])
        # Try to anchor a number run at i that is immediately followed by a price unit.
        if _RUN_RE.fullmatch(folded):
            # Greedily extend the run while the next word is still a num token AND not itself a unit.
            j = i
            run_words: list[str] = []
            while j < n:
                fj = fold_diacritics(words[j])
                if _RUN_RE.fullmatch(fj) and not _UNIT_RE.match(fj + " "):
                    run_words.append(words[j])
                    j += 1
                else:
                    break
            # The word at j must be a price unit for this to be a price phrase. Parse the run
            # TOGETHER with the unit (the unit is the ×1000/×1e6 multiplier — "năm chục" alone is
            # 50, but "năm chục nghìn" is 50000).
            if j < n and _UNIT_RE.match(fold_diacritics(words[j]) + " "):
                unit_word = fold_diacritics(words[j])
                run_phrase = " ".join(fold_diacritics(w) for w in run_words)
                value = parse_vi_int(f"{run_phrase} {unit_word}") if run_phrase else None
                if value:
                    out.append(str(value))
                    i = j + 1  # consume run + unit
                    continue
        out.append(words[i])
        i += 1
    return " ".join(out)
