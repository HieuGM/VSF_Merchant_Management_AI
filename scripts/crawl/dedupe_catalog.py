"""Dedupe catalog: 3277 records -> quan unique theo source_url.
Uu tien ban co merchant_id dang so (goi API duoc), gop bo sung field tu ban con lai,
loai ban DOM co ten loi (vd 'Toi thieu 20k Gia 0').
Output: data/merchants_unique.jsonl (giu nguyen file goc).
"""
import json
import re
from pathlib import Path

SRC = Path("data/shopeefood_catalog.jsonl")
OUT = Path("data/merchants_unique.jsonl")

# ten loi tu ban DOM: bat dau bang cac cum quang cao/thong tin gia thay vi ten quan
BROKEN_NAME = re.compile(r"^(Tối thiểu|Giá|Freeship|Giảm|Ưu đãi|Món|Đang)", re.IGNORECASE)


def name_ok(name):
    return bool(name) and not BROKEN_NAME.match(name.strip())


def merge(primary, other):
    """Bo sung field null cua primary bang other."""
    for k, v in other.items():
        if primary.get(k) in (None, "", [], {}) and v not in (None, "", [], {}):
            primary[k] = v
    return primary


def main():
    by_url = {}
    total = 0
    with SRC.open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            total += 1
            url = r.get("source_url")
            if not url:
                continue
            numeric = r.get("merchant_id", "").isdigit()
            r["_numeric_id"] = numeric
            if url not in by_url:
                by_url[url] = r
                continue
            cur = by_url[url]
            # chon ban tot hon lam primary: uu tien numeric id + ten hop le
            cur_score = (cur["_numeric_id"], name_ok(cur.get("merchant_name", "")))
            new_score = (numeric, name_ok(r.get("merchant_name", "")))
            if new_score > cur_score:
                by_url[url] = merge(r, cur)
            else:
                by_url[url] = merge(cur, r)

    merchants = list(by_url.values())
    for m in merchants:
        m.pop("_numeric_id", None)

    with OUT.open("w", encoding="utf-8") as f:
        for m in merchants:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")

    numeric = sum(1 for m in merchants if m.get("merchant_id", "").isdigit())
    print(f"input records: {total}")
    print(f"unique merchants: {len(merchants)}")
    print(f"  with numeric merchant_id (API-able): {numeric}")
    print(f"  slug-only id: {len(merchants) - numeric}")
    print(f"written -> {OUT}")


if __name__ == "__main__":
    main()
