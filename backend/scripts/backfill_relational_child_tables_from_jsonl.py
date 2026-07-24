"""Backfill merchant child tables from data/profiles.jsonl.

Repopulates the four relational tables that the schema-cutover migration
(`c2d3e4f5a6b7`) created but could not backfill from the DB (the legacy
`dimensions_json` source was already emptied/dropped):

- merchant_dimension_calculations  (8 rows / merchant: basis + provenance)
- merchant_dimension_evidence       (typed scalar evidence facts)
- merchant_complaints               (first-class complaint rows)
- market_trending_dishes            (current market aggregate per city/cuisine)

`data/profiles.jsonl` is the canonical import artifact (design §3). This script
is the relational importer path described in §10 for these child tables.

Idempotent: each run fully rebuilds the four tables (DELETE + INSERT) inside one
transaction. Safe to re-run.

Run:  python backend/scripts/backfill_relational_child_tables_from_jsonl.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from database.connection import engine  # noqa: E402

PROFILES_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "profiles.jsonl")
)

# JSON dimension key -> relational dimension name (design §6.3 rename)
DIMENSION_RENAME = {"price_level": "price_competitiveness"}
VALID_DIMENSIONS = {
    "food_quality", "image_quality", "delivery_quality", "packaging",
    "service", "waiting_time", "menu_diversity", "price_competitiveness",
}
SOURCE_KIND = "synthetic"          # demo/heuristic corpus (design canonical set)
SCORING_VERSION = "legacy"         # matches merchant_profiles.scoring_version backfill


def _parse_ts(value: str | None) -> dt.datetime:
    if value:
        try:
            return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return dt.datetime.now(dt.timezone.utc)


def _route_value(v):
    """Return (numeric, text, boolean) with exactly one non-null, or None to skip.

    bool is checked before int/float (bool is a subclass of int in Python)."""
    if isinstance(v, bool):
        return (None, None, v)
    if isinstance(v, (int, float)):
        return (v, None, None)
    if v is None:
        return None
    return (None, str(v), None)


def build_rows(profiles, merchant_map):
    calc_rows, evidence_rows, complaint_rows = [], [], []
    trend_max: dict[tuple[str, str, str], float] = {}

    for p in profiles:
        mid = str(p["merchant_id"])
        calculated_at = _parse_ts(p.get("updated_at"))

        # --- dimension calculations + evidence ---
        for raw_dim, dim_val in (p.get("dimensions") or {}).items():
            dim = DIMENSION_RENAME.get(raw_dim, raw_dim)
            if dim not in VALID_DIMENSIONS:
                continue
            calc_rows.append({
                "merchant_id": mid, "dimension": dim,
                "basis": dim_val.get("basis") or "unknown",
                "source_kind": SOURCE_KIND, "scoring_version": SCORING_VERSION,
                "calculated_at": calculated_at,
            })
            seen: dict[str, int] = {}
            for ev in dim_val.get("evidence") or []:
                etype = ev.get("type")
                if not etype:
                    continue
                routed = _route_value(ev.get("value"))
                if routed is None:
                    continue
                # deterministic id; disambiguate duplicate types within a dimension
                seen[etype] = seen.get(etype, 0) + 1
                suffix = "" if seen[etype] == 1 else f":{seen[etype]}"
                num, txt, boo = routed
                evidence_rows.append({
                    "evidence_id": f"ev:{mid}:{dim}:{etype}{suffix}",
                    "merchant_id": mid, "dimension": dim, "evidence_type": etype,
                    "value_numeric": num, "value_text": txt, "value_boolean": boo,
                    "source_kind": SOURCE_KIND,
                })

        # --- complaints ---
        for i, c in enumerate(p.get("complaints") or []):
            complaint_rows.append({
                "complaint_id": f"cmp:{mid}:{i}",
                "merchant_id": mid,
                "category": c.get("category"),
                "severity": c.get("severity"),
                "text": c.get("text") or "",
                "occurred_on": c.get("date"),
                "source_kind": SOURCE_KIND,
            })

        # --- trending (aggregate to max likes per city/cuisine/dish) ---
        loc = merchant_map.get(mid)
        if loc:
            city_slug, cuisine = loc
            for td in (p.get("attributes") or {}).get("trending_dishes") or []:
                dish = (td.get("dish") or "").strip()
                if not dish:
                    continue
                likes = td.get("total_likes") or 0
                key = (city_slug, cuisine, dish)
                trend_max[key] = max(trend_max.get(key, 0), float(likes))

    # rank trending dishes within each (city_slug, cuisine) market
    by_market: dict[tuple[str, str], list[tuple[str, float]]] = {}
    for (cs, cu, dish), score in trend_max.items():
        by_market.setdefault((cs, cu), []).append((dish, score))
    trend_rows = []
    for (cs, cu), dishes in by_market.items():
        dishes.sort(key=lambda t: (-t[1], t[0]))
        for rank, (dish, score) in enumerate(dishes, start=1):
            trend_rows.append({
                "city_slug": cs, "cuisine": cu, "dish_name": dish,
                "trend_score": score, "rank": rank,
            })

    return calc_rows, evidence_rows, complaint_rows, trend_rows


def main() -> None:
    with open(PROFILES_PATH, encoding="utf-8") as f:
        profiles = [json.loads(line) for line in f if line.strip()]
    print(f"loaded {len(profiles)} profiles from {PROFILES_PATH}")

    with engine.begin() as conn:
        merchant_map = {
            r[0]: (r[1], r[2])
            for r in conn.execute(text(
                "SELECT merchant_id, city_slug, cuisine FROM merchants"))
        }

        calc, evidence, complaints, trending = build_rows(profiles, merchant_map)
        print(f"rows: calc={len(calc)} evidence={len(evidence)} "
              f"complaints={len(complaints)} trending={len(trending)}")

        # full rebuild (idempotent)
        conn.execute(text("DELETE FROM merchant_dimension_evidence"))
        conn.execute(text("DELETE FROM merchant_dimension_calculations"))
        conn.execute(text("DELETE FROM merchant_complaints"))
        conn.execute(text("DELETE FROM market_trending_dishes"))

        if calc:
            conn.execute(text(
                "INSERT INTO merchant_dimension_calculations "
                "(merchant_id, dimension, basis, source_kind, scoring_version, calculated_at) "
                "VALUES (:merchant_id, :dimension, :basis, :source_kind, :scoring_version, :calculated_at)"
            ), calc)
        if evidence:
            conn.execute(text(
                "INSERT INTO merchant_dimension_evidence "
                "(evidence_id, merchant_id, dimension, evidence_type, "
                " value_numeric, value_text, value_boolean, source_kind) "
                "VALUES (:evidence_id, :merchant_id, :dimension, :evidence_type, "
                " :value_numeric, :value_text, :value_boolean, :source_kind)"
            ), evidence)
        if complaints:
            conn.execute(text(
                "INSERT INTO merchant_complaints "
                "(complaint_id, merchant_id, category, severity, text, occurred_on, source_kind) "
                "VALUES (:complaint_id, :merchant_id, :category, :severity, :text, "
                " CAST(:occurred_on AS DATE), :source_kind)"
            ), complaints)
        if trending:
            conn.execute(text(
                "INSERT INTO market_trending_dishes "
                "(city_slug, cuisine, dish_name, trend_score, rank) "
                "VALUES (:city_slug, :cuisine, :dish_name, :trend_score, :rank)"
            ), trending)

    print("backfill committed.")


if __name__ == "__main__":
    main()
