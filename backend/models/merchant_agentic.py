"""Contracts shared by the native Merchant Advisor crew and tool gateway."""
from __future__ import annotations

import unicodedata
import re
from typing import Literal

from pydantic import BaseModel, Field


_CITY_ALIASES: dict[str, str] = {
    "da nang": "da_nang",
    "tp hcm": "tp_hcm",
    "ho chi minh": "tp_hcm",
    "sai gon": "tp_hcm",
    "ha noi": "ha_noi",
    "can tho": "can_tho",
    "hue": "hue",
    "vung tau": "vung_tau",
    "hai phong": "hai_phong",
    "khanh hoa": "khanh_hoa",
    "dong nai": "dong_nai",
}


def normalize_text(value: str) -> str:
    """Lowercase, accent-insensitive words for policy comparisons."""
    normalized = unicodedata.normalize("NFD", value.casefold()).replace("đ", "d")
    without_marks = "".join(
        character
        for character in normalized
        if unicodedata.category(character) != "Mn"
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", without_marks).split())


def normalize_city_slugs(value: str | None) -> str | None:
    """Canonicalize a comma-separated city name/slug list for runtime tools."""
    if value is None:
        return None
    normalized = []
    for raw_city in value.split(","):
        city = normalize_text(raw_city)
        if not city:
            continue
        normalized.append(_CITY_ALIASES.get(city, city.replace(" ", "_")))
    return ",".join(dict.fromkeys(normalized)) or None


class AgenticRunContext(BaseModel):
    trace_id: str
    session_id: str
    owner_merchant_id: str
    user_id: str | None = None
    user_query: str = ""


class NativeCrewOutcome(BaseModel):
    """The coordinator's terminal contract after native CrewAI delegation."""

    status: Literal["completed"]
    answer: str = Field(min_length=1)
