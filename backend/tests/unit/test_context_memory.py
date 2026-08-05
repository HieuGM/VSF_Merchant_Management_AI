"""Unit tests for context_memory extraction (phase-03) — pure, no DB.

The append/repo round-trip is covered by an integration test in
tests/integration/test_customer_memory_wireup.py (phase-03)."""
from __future__ import annotations

from services.context_memory_service import _MAX_NOTE_LEN, extract_notes


def test_no_trigger_returns_empty():
    assert extract_notes("Hôm nay muốn ăn phở bò gần Cầu Giấy") == []
    assert extract_notes("") == []
    assert extract_notes(None) == []


def test_allergy_trigger_extracted_in_original_diacritics():
    notes = extract_notes("Mình dị ứng đậu phộng đấy. Cho mình gợi ý quán ăn.")
    assert len(notes) == 1
    assert "dị ứng đậu phộng" in notes[0]  # original Vietnamese preserved (crew reads natural text)


def test_kieng_and_chay_truong_triggers():
    notes = extract_notes("Tôi kiêng đồ cay. Ăn chay trường nhé.")
    assert len(notes) == 2
    assert any("kiêng" in n for n in notes)
    assert any("chay trường" in n for n in notes)


def test_declared_persistent_chay():
    notes = extract_notes("Từ giờ ăn chay nha, nhớ giúp mình.")
    assert len(notes) == 1 and "ăn chay" in notes[0]


def test_medical_specific_triggers():
    assert any("tiểu đường" in n for n in extract_notes("Mình bị tiểu đường nên ăn nhạt"))
    assert any("dạ dày" in n for n in extract_notes("Hôm nay đau dạ dày, gợi ý món mềm"))


def test_da_day_full_collision_excluded():
    # "đã đầy" (I'm full) folds to "da day" — must NOT trigger a stomach note. The bare
    # "da day" trigger is excluded (only qualified đau/viêm dạ dày fire) to avoid this.
    assert extract_notes("Mình đã đầy rồi, không ăn nữa") == []


def test_benh_location_false_positive_excluded():
    # "gần bệnh viện" must NOT be captured (location cue, not a durable medical fact).
    notes = extract_notes("Cho mình quán ăn gần bệnh viện nhé")
    assert notes == [], "'benh' trigger must be excluded to avoid location false positives"


def test_multiple_sentences_only_triggered_kept():
    text = "Trời hôm nay đẹp quá. Mình dị ứng hải sản. Ăn phở được không."
    notes = extract_notes(text)
    assert len(notes) == 1
    assert "dị ứng hải sản" in notes[0]


def test_pii_redacted_in_note():
    # Phone number inside an allergy sentence is redacted before storing.
    notes = extract_notes("Dị ứng tôm nhé, gọi mình 0912345678")
    assert len(notes) == 1
    assert "0912345678" not in notes[0]
    assert "[PHONE]" in notes[0]


def test_long_note_capped():
    tail = "xyz " * 100  # very long allergy sentence
    notes = extract_notes(f"Mình dị ứng tôm {tail}")
    assert len(notes) == 1
    assert len(notes[0]) <= _MAX_NOTE_LEN
    assert notes[0].endswith("...")
