"""Testy normalizacji PL (architektura §2.3 kroki 1–3)."""

from __future__ import annotations

import pytest

from saycue.parser.normalize import FILLER_TOKENS, fold_diacritics, normalize, normalize_text


def test_w1_normalize_unchanged():
    """Wersja W1 (eval G1) działa jak dotychczas."""
    assert normalize("Otwórz Spotify!") == "otworz spotify"
    assert normalize("  Cisza   na   planie ") == "cisza na planie"


def test_pl_fold():
    assert fold_diacritics("ąćęłńóśźż") == "acelnoszz"
    # tabela W1 mapuje małe litery — fold działa PO lower() (kontrakt eval G1)
    assert fold_diacritics("ŻÓŁĆ") == "ŻÓŁĆ"
    assert fold_diacritics("żółć") == "zolc"
    assert normalize_text("żółw ąę") == "zolw ae"


def test_nfkc_fullwidth():
    # pełnoszerokowe litery → ASCII po NFKC, potem fold
    assert normalize_text("ＯＴＷÓＲＺ ＳＰＯＴＩＦＹ") == "otworz spotify"
    assert normalize_text("ｃｉｓｚａ") == "cisza"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Otwórz Spotify!", "otworz spotify"),
        ("otworz spotify", "otworz spotify"),
        ("Włącz Discord", "wlacz discord"),
        ("Hej, proszę otwórz notatnik", "otworz notatnik"),
        ("ok asystent, nagrywaj", "nagrywaj"),
        ("proszę głośniej", "glosniej"),
        ("cisza!!!", "cisza"),
        ("skok", "skok"),  # "ok" wewnątrz słowa NIE jest wypełniaczem
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_text(text, expected):
    assert normalize_text(text) == expected


def test_filler_tokens_only_as_whole_words():
    assert normalize_text("ok") == ""
    assert normalize_text("ok ok") == ""
    assert normalize_text("spotify ok") == "spotify"


def test_normalize_text_idempotent():
    for text in ["Hej proszę Otwórz Spotify!", "nagrywaj", "ścisz", ""]:
        once = normalize_text(text)
        assert normalize_text(once) == once


def test_filler_tokens_set():
    assert FILLER_TOKENS == frozenset({"prosze", "hej", "asystent", "ok"})
