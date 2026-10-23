"""Testy jednostkowe Matcher: konflikty, progi, szablony, determinizm, ASK."""

from __future__ import annotations

import pytest

from saycue.parser.matcher import Matcher


@pytest.fixture(scope="module")
def matcher(intent_parser) -> Matcher:
    cfg = intent_parser.config
    return Matcher(cfg.commands, cfg.apps)


def test_exact_match_meta(matcher):
    r = matcher.parse("cisza")
    assert r is not None
    assert r.source == "exact"
    assert r.score == 1.0
    assert r.matched == ("cisza",)
    assert r.origin == "core"
    assert r.command_id == "mute_mic"


def test_longer_phrase_wins(matcher):
    r = matcher.parse("scena pvp")
    assert r is not None and r.intent == "obs.scene"
    assert r.matched == ("scena pvp",)  # nie gołe "pvp"
    assert r.command_id == "obs_scene_pvp"


def test_longer_phrase_wins_volume_over_mic(matcher):
    r = matcher.parse("wycisz dźwięk pulpitu")
    assert r is not None and r.intent == "obs.mute"
    assert dict(r.slots) == {"source": "Desktop Audio", "state": "on"}


def test_substring_conflict_prefers_longest(matcher):
    # "unmute mic" zawiera "mute" — pełna fraza wygrywa
    r = matcher.parse("unmute mic")
    assert r is not None and r.intent == "obs.mute"
    assert dict(r.slots) == {"source": "Mic/Aux", "state": "off"}


def test_template_word_boundary(matcher):
    # "otworzspotify" bez spacji: szablon się NIE wcina (granica słowa)
    r = matcher.parse("otworzspotify")
    assert r is None or r.source != "template"


def test_template_resolves_vocab(matcher):
    r = matcher.parse("scena brb")
    assert r is not None and r.intent == "obs.scene"
    assert r.source == "template"
    assert dict(r.slots) == {"scene": "BRB"}
    assert r.score == 1.0


def test_template_unresolved_keeps_raw(matcher):
    r = matcher.parse("scena stream")
    assert r is not None and r.intent == "obs.scene"
    assert dict(r.slots) == {"scene": "stream"}
    assert r.score == 0.9


def test_fuzzy_below_threshold_returns_none(matcher):
    assert matcher.parse("dusz") is None
    assert matcher.parse("zupełny bełkot") is None


def test_fuzzy_above_threshold(matcher):
    # "pogdlosnij" (przestawione litery) nie zawiera żadnej frazy → czyste fuzzy
    r = matcher.parse("pogdlosnij")
    assert r is not None and r.intent == "system.volume"
    assert r.source == "fuzzy"
    assert 0.78 <= r.score < 1.0


def test_substring_exact_beats_fuzzy(matcher):
    # "wlancz discord" zawiera dokładną frazę "discord" → exact (determinizm)
    r = matcher.parse("wlancz discord")
    assert r is not None and r.intent == "app.open"
    assert r.source == "exact"
    assert r.matched == ("discord",)


def test_parse_empty_and_none(matcher):
    assert matcher.parse("") is None
    assert matcher.parse(None) is None
    assert matcher.parse("   ") is None


def test_parse_is_deterministic(matcher):
    for text in ["scena pvp", "otworz spotifaj", "cisza w kompie", "bełkot"]:
        assert matcher.parse(text) == matcher.parse(text)


def test_candidates_for_ask(matcher):
    cands = matcher.candidates("otworz spotifaj", k=3)
    assert cands and cands[0].intent == "app.open"
    assert cands[0].score >= 0.78
    below = matcher.candidates("dusz", k=3)
    assert below and below[0].command_id == "press_dash"
    assert below[0].score < 0.78  # ASK pokazuje kandydatów poniżej progu
    assert len(below) <= 3


def test_no_templates_in_presets(matcher):
    # presety nie używają szablonów — tylko rdzeń; API pozostaje spójne
    r = matcher.parse("włącz")
    assert r is None
