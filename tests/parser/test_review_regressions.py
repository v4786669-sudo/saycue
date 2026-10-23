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


# ---------------------------------------------------------------- v0.3 (t15)


def test_r02_ask_candidate_is_not_actionable_and_lists_allowed_values(intent_parser):
    """R-02: nierozpoznany slot → kandydat ASK z listą dozwolonych wartości."""
    cands = intent_parser.candidates("scena 3", k=8)
    tpl = [c for c in cands if c.source == "template"]
    assert tpl, "brak kandydata szablonowego dla 'scena 3'"
    assert tpl[0].actionable is False
    assert tpl[0].allowed_values, "brak listy dozwolonych wartości dla ASK"
    for value in tpl[0].allowed_values:
        assert isinstance(value, str)


def test_r02_resolved_template_candidate_is_actionable(intent_parser):
    cands = intent_parser.candidates("scena brb", k=8)
    tpl = [c for c in cands if c.source == "template"]
    assert tpl and tpl[0].actionable is True
    assert tpl[0].allowed_values == ()


def test_r01_min_phrase_coverage_parameter():
    """R-01 (v0.3 §2.3): dokładna fraza musi pokryć ≥ min_phrase_coverage
    tokenów wypowiedzi — fragment w środku zdania nie wyzwala akcji."""
    commands = [
        {
            "id": "vol",
            "phrases": ["wycisz mikrofon", "nagrywaj"],
            "intent": "obs.mute",
            "slots": {"source": "mic", "state": "toggle"},
            "origin": "core",
        },
    ]
    matcher = Matcher(commands, {})
    assert matcher.min_phrase_coverage == 0.7
    # pełne wypowiedzi — 100% pokrycia
    assert matcher.parse("wycisz mikrofon") is not None
    # 2 tokeny frazy na 3 tokeny zdania = 66.7% < 70% → ASK
    assert matcher.parse("powiedz wycisz mikrofon") is None
    # 3 tokeny frazy na 4 tokeny zdania = 75% ≥ 70% → akcja
    matcher4 = Matcher(
        [
            {
                "id": "x",
                "phrases": ["wycisz mikrofon prosze"],
                "intent": "obs.mute",
                "slots": {},
                "origin": "core",
            }
        ],
        {},
    )
    assert matcher4.parse("teraz wycisz mikrofon prosze") is not None
    # jawny próg 1.0 = wymóg pełnego pokrycia
    strict = Matcher(commands, {}, min_phrase_coverage=1.0)
    assert strict.parse("teraz nagrywaj") is None
    assert strict.parse("nagrywaj") is not None


def test_r01_allow_free_text_exception_for_templates():
    """R-01 (v0.3 §2.3): szablony z wolnym slotem są wyjątkiem od reguły
    pokrycia (allow_free_text=True) — slot konsumuje wolne tokeny."""
    commands = [
        {
            "id": "app_tpl",
            "phrases": ["otwórz {target}"],
            "intent": "app.open",
            "origin": "core",
        },
    ]
    apps = {"blender": {"label": "Blender", "aliases": []}}
    free = Matcher(commands, apps)  # allow_free_text=True (domyślnie)
    assert free.parse("otwórz blender") is not None
    # wielowyrazowa wartość slotu — nadal działa
    assert free.parse("otwórz blender studio") is None  # nieznana wartość → ASK
    strict = Matcher(commands, apps, allow_free_text=False)
    assert strict.parse("otwórz blender") is None  # pokrycie 1/2 < 0.7


def test_rewritten_fillers_diagnostics_are_tokens_only(intent_parser):
    """v0.3 §2.3: rewritten_fillers = licznik/tokeny stałego słownika,
    nigdy treść mowy."""
    from saycue.parser.normalize import FILLER_TOKENS

    r = intent_parser.parse("hej, proszę cisza")
    assert r is not None and r.intent == "obs.mute"
    assert r.rewritten_fillers == ("hej", "prosze")
    for token in r.rewritten_fillers:
        assert token in FILLER_TOKENS  # tylko stały słownik, bez treści mowy
    r2 = intent_parser.parse("cisza")
    assert r2 is not None and r2.rewritten_fillers == ()


def test_rewritten_fillers_count_via_normalize_verbose():
    from saycue.parser.normalize import normalize_verbose

    norm, removed = normalize_verbose("ok asystent hej nagrywaj")
    assert norm == "nagrywaj"
    assert removed == ("ok", "asystent", "hej")
    norm2, removed2 = normalize_verbose("nagrywaj proszę")
    assert norm2 == "nagrywaj prosze"  # w środku/na końcu zostają (R-01)
    assert removed2 == ()


def test_trailing_filler_utterance_is_ask(intent_parser):
    """Zachowanie przypięte (konserwatywne): „otworz spotify proszę" — filler
    na końcu zostaje (R-01), dokładne pokrycie odpada (2/3 < 0.7), a szablon
    z nierozpoznaną wartością „spotify prosze" NIE przepada na fuzzy —
    użytkownik dostaje ASK z kandydatami (determinizm, R-02)."""
    assert intent_parser.parse("otworz spotify proszę") is None
    cands = intent_parser.candidates("otworz spotify proszę", k=8)
    tpl = [c for c in cands if c.source == "template"]
    assert tpl and tpl[0].actionable is False
    assert tpl[0].slots["target"] == "spotify prosze"  # surowa wartość w ASK
