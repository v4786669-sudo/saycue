"""Testy normalizacji PL (parser/normalize.py — architektura §2.3)."""

from saycue.parser.normalize import fold_diacritics, fuzzy_similarity, normalize


def test_lowercase_and_punctuation():
    assert normalize("Otwórz Spotify!") == "otworz spotify"


def test_pl_diacritics_fold():
    assert fold_diacritics("ąćęłńóśźż") == "acelnoszz"
    assert normalize("GŁOŚNIEJ") == "glosniej"
    assert normalize("ścisz") == "scisz"


def test_whitespace_collapse():
    assert normalize("  scena   pvp  ") == "scena pvp"


def test_unicode_nfkc():
    assert normalize("ｓｃｅｎａ") == "scena"


def test_fuzzy_similarity():
    assert fuzzy_similarity("otworz spotify", "otwórz spotify") == 1.0
    assert fuzzy_similarity("scena pvp", "sceny pvp") > 0.85
    assert fuzzy_similarity("dasz", "głośniej") < 0.5


def test_mute_variants_normalize_to_same_intent_phrases():
    assert normalize("Wycisz!") == normalize("wycisz")
    assert normalize("MUte") == "mute"
