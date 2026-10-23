"""Regresje R-01/R-02 (findingi przeglądu t11, fixy t10).

R-01: dopasowanie musi objąć CAŁĄ wypowiedź (nie fragment w środku);
     fillery „proszę/hej/asystent/ok" usuwane TYLKO z początku.
R-02: nierozpoznany slot i fuzzy w [0.78, 0.8) → ASK, nie akcja.
"""

from __future__ import annotations

import pytest

from saycue.parser.matcher import Matcher
from saycue.parser.normalize import normalize_text

R01_CASES = [
    # naturalne zdania — żaden fragment frazy nie może odpalić akcji
    "umówmy się na spotkanie o 8",
    "powiedz scena pvp",
    "daj mi ciszej muzykę w tle",
    "hej siri otwórz mi spotify",
    "to nie jest scena startowa tylko brb",
]


def test_r01_mid_sentence_fragments_do_not_fire(intent_parser):
    for text in R01_CASES:
        result = intent_parser.parse(text)
        assert result is None, f"{text!r} odpalił {result}"


def test_r01_fillers_only_at_start():
    assert normalize_text("hej, proszę otwórz spotify") == "otworz spotify"
    assert normalize_text("ok asystent, nagrywaj") == "nagrywaj"
    # na końcu/w środku zostają — inaczej „…o 8" traci „o" i trafia we fragmenty
    assert normalize_text("spotify ok") == "spotify ok"
    assert normalize_text("ciszej proszę") == "ciszej prosze"


def test_r01_leading_fillers_chain():
    assert normalize_text("proszę hej ok asystent otwórz obs") == "otworz obs"


def test_r02_unresolved_slot_never_executes(intent_parser):
    # „scena 3" — wartość slotu spoza słownika scen: ASK, nie obs.scene „3"
    assert intent_parser.parse("scena 3") is None
    assert intent_parser.parse("otworz spoty fi") is None
    cands = intent_parser.candidates("otworz spoty fi", k=3)
    assert any(c.intent == "app.open" and c.source == "template" for c in cands)


def test_r02_fuzzy_in_threshold_window_is_ask():
    """fuzzy w [fuzzy_threshold, min_action_score) → None (ASK); ≥ min → akcja.

    Sprawdzamy mechanizm bramki (nie konkretną parę 0.78–0.8, którą ciężko
    zbudzić rapidfuzzem): z min_action_score=0.85 tekst o ratio 0.824 odpada,
    o ratio 0.889 przechodzi."""
    commands = [
        {
            "id": "t",
            "phrases": ["abcdefghij"],
            "intent": "obs.record",
            "slots": {"state": "stop"},
            "origin": "core",
        },
    ]
    matcher = Matcher(commands, {}, fuzzy_threshold=0.78, min_action_score=0.85)
    assert matcher.parse("abcdefg") is None  # ratio 2*7/17 ≈ 0.824 → ASK
    assert matcher.parse("abcdefgh") is not None  # ratio 2*8/18 ≈ 0.889 → akcja
    # domyślna bramka wykonania = 0.8
    matcher_default = Matcher(commands, {})
    assert matcher_default.min_action_score == 0.8


def test_r02_exact_and_resolved_template_still_score_1(intent_parser):
    r = intent_parser.parse("scena brb")  # szablon + rozwiązany slot
    assert r is not None and r.score == 1.0
    r2 = intent_parser.parse("przełącz na pvp")  # dokładna fraza
    assert r2 is not None and r2.score == 1.0


@pytest.mark.parametrize(
    "text",
    ["scena stream", "scena pvn", "scena 3", "otworz spoty fi"],
)
def test_r02_ask_still_shows_candidate_with_raw_value(intent_parser, text):
    cands = intent_parser.candidates(text, k=8)
    assert cands, f"brak kandydatów dla {text!r}"
