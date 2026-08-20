"""Follow-up resolution helpers — deterministic anaphora/refinement/negation handling.

Extracted from customer_flow (audit 260820 proposal #4) so the 5 stable-fail GT cases have a
testable seam:

  - ``is_bare_referent_followup`` — TC-41 'Cái đầu tiên đó' / TC-25 'Quán này có ổn không?' /
    TC-39 'quán này thế nào?': an ANAPHOR with NO attribute word still refers to the prior
    list. The old gate required an attribute token, so these fell to a fresh search and the
    answer confabulated ('ba quán đáng thử' for TC-39) or claimed amnesia (TC-41).
  - ``refined_max_price`` — TC-10 'Rẻ hơn nữa được không': the prior USER turn carried a price
    ('dưới 40k'); the refinement asks for cheaper. The search LLM gets the prior context but
    does not reliably LOWER max_price — so we derive it deterministically (75% of the prior
    cap, floored at 15k so it stays a real budget band).
  - ``negation_filter_terms`` — TC-28 'không cay, không phải đồ chiên': extract the negated
    food terms from the query so the caller can post-filter results whose name/cuisine/taste
    carry them (the search tool has no exclude_tags param; post-filter is the seam).
"""
from __future__ import annotations

import re

from core.text_norm import fold_diacritics

# Attribute/question markers that turn an anaphor into an explanation follow-up. Extended
# (audit 260820): 'ổn không', 'thế nào', 'tại sao', 'vậy', 'được không', 'rẻ hơn' were missing —
# 3 stable-fail cases (TC-25/39/41) carry exactly these.
_FOLLOWUP_ATTR_RE = re.compile(
    r"\b(gia|bao nhieu|cay|ngon|mo cua|dong cua|gio mo|dia chi|o dau|danh gia|review"
    r"|co gi|chuyen|dac biet|phuc vu|khong gian|cho ngoi|dat ban|giao hang|tuong|chua"
    r"|so sanh|so voi|khac nhau|khac giua|tot hon|hay hon|ngon hon|duoc diem"
    r"|on khong|the nao|tai sao|sao|vay|duoc khong|co tot|re hon|dat hon)\b"
)

# Anaphor patterns (same shape as the flow's _ANAPHORA_RE; kept here so this module is
# self-contained and unit-testable without importing the whole flow).
_ANAPHOR_RE = re.compile(
    r"\b(quan\s*(do|nay|kia)|mon\s*(do|nay|kia)|cai\s*(dau tien|thu hai|thu ba|thu tu|cuoi)"
    r"|quan dau tien|hai quan|ba quan)\b"
)
_REFINEMENT_RE = re.compile(
    r"\b(khac|re hon|dat hon|gan hon|xa hon|mo rong|them|con\s*(quan|nao|gi)"
    r"|lai nua|it hon|nhieu hon|phu hop hon)\b"
)
# A fresh-search food token in the query means the user wants NEW results even when a
# demonstrative is present ('đồ chiên ở đâu ngon' → search, not follow-up).
_FOOD_TOKEN_RE = re.compile(
    r"\b(pho|bun|com|lau|sushi|banh mi|nuong|chien|xao|chao|mi|mien|banh|tra sua|ca phe|do an)\b"
)

# Cheaper-refinement price derivation (TC-10): pull the last explicit cap from the prior USER
# text ('dưới 40k', '<=50000', '50k') and lower it.
_PRIOR_PRICE_RE = re.compile(r"(?:duoi|nho hon|<=?)\s*(\d+)(k|nghin|ngan)?", re.IGNORECASE)


def _fold(query: str | None) -> str:
    return fold_diacritics(query or "")


def is_bare_referent_followup(query: str | None) -> bool:
    """True when the query is (almost) ONLY a referent to the prior list — an anaphor with
    no attribute AND no fresh-search food token, e.g. 'Cái đầu tiên đó', 'Quán này có ổn
    không?'. Such a turn must resolve against prior results, never trigger a fresh search
    (which returns unrelated merchants and invites confabulation). Guarded to SHORT queries:
    a long sentence with an anaphor plus other content still goes through the normal gates."""
    q = _fold(query)
    if not q or not _ANAPHOR_RE.search(q):
        return False
    if _FOOD_TOKEN_RE.search(q):
        return False  # names a dish → wants fresh results
    tokens = q.split()
    if len(tokens) > 8:
        return False  # long sentence — other intent markers likely present
    return not _REFINEMENT_RE.search(q)


def followup_needs_skip_search(query: str | None) -> bool:
    """Combined gate: the classic attr-gated anaphor OR a bare-referent follow-up. Neither
    may carry a refinement marker ('rẻ hơn' stays on the search path — TC-10)."""
    q = _fold(query)
    if not q or not _ANAPHOR_RE.search(q):
        return False
    if _REFINEMENT_RE.search(q):
        return False
    return bool(_FOLLOWUP_ATTR_RE.search(q)) or is_bare_referent_followup(query)


def refined_max_price(query: str | None, prior_user_texts: list[str]) -> int | None:
    """Deterministic cheaper-refinement cap (TC-10). When the current query asks 'rẻ hơn' and
    the most recent prior USER text carried an explicit price cap, return 75% of it (floored
    at 15k so it stays a real band). None → caller keeps its normal behavior."""
    q = _fold(query)
    if not q or not re.search(r"\b(re hon|rẻ hơn|re nua|giam gia|re nhat)\b".replace("rẻ hơn", "re hon"), q):
        return None
    for text in reversed(prior_user_texts or []):
        m = _PRIOR_PRICE_RE.search(_fold(text))
        if m:
            cap = int(m.group(1))
            if m.group(2):  # 'k'/'nghìn' suffix
                cap *= 1000
            return max(15000, int(cap * 0.75))
    return None


# Negated food terms (TC-28): 'không cay, không phải đồ chiên' → ['cay', 'chien'].
_NEGATED_TERM_RE = re.compile(
    r"\bkhong\s+(phai\s+)?(do\s+)?(cay|chien|nuong|bo|ngot|dau|hua|hai san|chay)\b"
)


def negation_filter_terms(query: str | None) -> list[str]:
    """Terms the user explicitly excluded ('không cay, không phải đồ chiên'). The caller
    post-filters result dicts whose folded name+cuisine+taste_tags contain one of them."""
    q = _fold(query)
    return [m.group(3) for m in _NEGATED_TERM_RE.finditer(q)]


def carries_negated_term(result: dict, terms: list[str]) -> bool:
    """True if the result's name/cuisine/taste_tags text contains one of the negated terms."""
    if not terms:
        return False
    hay = fold_diacritics(
        " ".join(str(x) for x in [
            result.get("name"), result.get("cuisine"),
            *(result.get("taste_tags") or []),
        ] if x)
    )
    return any(t in hay for t in terms)


def strip_negations(query: str | None) -> str:
    """Remove 'không X / không phải X' clauses from the SEARCH-side query (TC-28).

    The keyword leg matches merchant NAMES/cuisines — feeding it the literal string 'không cay
    không chiên' finds nothing (no merchant is named that). The affirmative remainder
    ('Tìm quán ăn ... ở Thanh Xuân') is what should reach merchant_search; the EXCLUSION is
    enforced post-search by ``carries_negated_term`` instead. The user-facing {query} keeps
    the original phrasing. Patterns cover BOTH diacritic and toneless forms."""
    if not query:
        return query or ""
    # Same alternation as _NEGATED_TERM_RE but written for the RAW text (diacritics kept),
    # plus its folded twin — users type both 'không cay' and 'khong cay'.
    raw_pat = re.compile(
        r"(?:không|khong)\s+(?:(?:phải|phai)\s+)?(?:(?:đồ|do)\s+)?(cay|chiên|chien|nuống|nuong|ngọt|ngot)\b[^,;.]*",
        re.IGNORECASE,
    )
    out = raw_pat.sub(" ", query)
    out = re.sub(r"(nhưng cũng\s*)?(đừng|dung)\s+quá\s+(rẻ|re)\b[^,;.]*", " ", out, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", out).strip(" ,")
