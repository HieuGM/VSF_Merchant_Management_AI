"""Unit tests for core/vi_numbers.py — Vietnamese price-word → digit normalizer (TC-34)."""
from __future__ import annotations

from core.vi_numbers import normalize_price_words, parse_vi_int


# --- parse_vi_int: the number grammar (1-999,999) ---
def test_parse_single_digits_and_ten():
    assert parse_vi_int("năm") == 5
    assert parse_vi_int("mười") == 10
    assert parse_vi_int("chín") == 9


def test_parse_teens():
    assert parse_vi_int("mười lăm") == 15          # 10 + 5
    assert parse_vi_int("mười chín") == 19


def test_parse_tens():
    assert parse_vi_int("hai mươi") == 20
    assert parse_vi_int("hai mươi lăm") == 25     # 20 + 5
    assert parse_vi_int("hai mươi mốt") == 21     # 20 + 1 (mốt folds to mot)
    assert parse_vi_int("năm chục") == 50          # chục = ×10


def test_parse_thousands():
    assert parse_vi_int("năm chục nghìn") == 50000   # TC-34: 5×10×1000
    assert parse_vi_int("hai mươi nghìn") == 20000
    assert parse_vi_int("hai trăm nghìn") == 200000
    assert parse_vi_int("mười lăm nghìn") == 15000
    assert parse_vi_int("hai mươi mốt nghìn") == 21000
    assert parse_vi_int("năm nghìn") == 5000


def test_parse_millions():
    assert parse_vi_int("năm triệu") == 5_000_000


def test_parse_diacritics_agnostic():
    assert parse_vi_int("năm mươi nghìn") == parse_vi_int("nam muoi nghin") == 50000


def test_parse_refuses_unknown():
    assert parse_vi_int("năm người") is None        # 'người' is not a number token
    assert parse_vi_int("") is None
    assert parse_vi_int(None) is None


# --- normalize_price_words: the query rewriter ---
def test_normalize_tc34_phrase():
    assert normalize_price_words("giá khoảng năm chục nghìn đổ lại") == "giá khoảng 50000 đổ lại"


def test_normalize_various_price_forms():
    assert normalize_price_words("dưới hai mươi nghìn") == "dưới 20000"
    assert normalize_price_words("khoảng hai trăm nghìn") == "khoảng 200000"
    assert normalize_price_words("mười lăm nghìn thôi") == "15000 thôi"


def test_normalize_keeps_non_price_words_untouched():
    # 'năm' without a price unit → NOT a price; left unchanged.
    assert normalize_price_words("quán cho nhóm năm người") == "quán cho nhóm năm người"
    assert normalize_price_words("chỉ lấy quán năm sao") == "chỉ lấy quán năm sao"
    assert normalize_price_words("ăn gì trưa nay") == "ăn gì trưa nay"


def test_normalize_preserves_diacritics_outside_run():
    # The non-matched tokens keep their Vietnamese diacritics.
    out = normalize_price_words("Tìm quán ở Hà Đông giá năm chục nghìn đổ lại")
    assert "Hà Đông" in out
    assert "50000" in out
    assert "năm chục nghìn" not in out


def test_normalize_none_empty():
    assert normalize_price_words(None) is None
    assert normalize_price_words("") == ""
