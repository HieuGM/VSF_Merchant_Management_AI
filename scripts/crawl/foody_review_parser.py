"""Parse reviews tu HTML trang Foody (server-rendered).
Foody nhung san ~12 review dau + rating tong quan trong HTML -> khong can API ky.
"""
import html as H
import re

_TAG = re.compile(r"<[^>]+>")


def _clean(s):
    return H.unescape(_TAG.sub("", s)).strip()


def parse_foody_html(raw):
    """Tra ve dict: rating tong quan + danh sach review text."""
    out = {"foody_rating": None, "foody_review_count": None, "reviews": []}

    # tat ca gia tri ratingValue: dau tien = rating tong quan, con lai = tung review
    rating_vals = re.findall(r'itemprop="ratingValue"[^>]*>\s*([0-9.]+)', raw)
    if rating_vals:
        out["foody_rating"] = float(rating_vals[0])  # thang 10
    m = re.search(r"(?:reviewCount|TotalReview)['\"]?\s*[:=]\s*['\"]?([0-9]+)", raw)
    if m:
        out["foody_review_count"] = int(m.group(1))

    # noi dung review: Foody dung itemprop="description" cho tung review
    texts = re.findall(r'itemprop="description"[^>]*>(.*?)</', raw, re.S)
    if not texts:
        texts = re.findall(r'class="[^"]*rd-des[^"]*"[^>]*>(.*?)</', raw, re.S)

    # diem tung review = cac ratingValue sau cai dau tien (thang 10)
    scores = rating_vals[1:]

    for i, t in enumerate(texts):
        txt = _clean(t)
        if len(txt) < 3:
            continue
        rv = {"text": txt}
        if i < len(scores):
            try:
                rv["score"] = float(scores[i])
            except ValueError:
                pass
        out["reviews"].append(rv)
    return out


if __name__ == "__main__":
    import sys
    data = open(sys.argv[1], encoding="utf-8", errors="ignore").read()
    res = parse_foody_html(data)
    print("rating:", res["foody_rating"], "| count:", res["foody_review_count"],
          "| reviews:", len(res["reviews"]))
    for r in res["reviews"][:3]:
        print("-", r.get("score"), r["text"][:120])
