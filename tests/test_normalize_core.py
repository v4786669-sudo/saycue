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


# --- prompt ASR (N-01, t15): rdzeń + krótkie frazy presetów, cap 60 ---
from saycue.asr.whisper import filter_short_phrases, load_initial_prompt  # noqa: E402


def test_filter_short_phrases_drops_templates_and_long():
    phrases = ["mute", "cisza", "scena pvp", "otwórz {target}", "przełącz na startową"]
    assert filter_short_phrases(phrases) == ["mute", "cisza", "scena pvp"]


def test_initial_prompt_caps_and_dedups():
    extras = [f"fraza {i}" for i in range(200)] + ["cisza"]
    prompt = load_initial_prompt(extra_phrases=extras, max_phrases=60)
    words = prompt.split(", ")
    assert len(words) <= 60
    assert words.count("cisza") <= 1  # dedup z rdzeniem


def test_initial_prompt_starts_with_core():
    core = load_initial_prompt()
    prompt = load_initial_prompt(extra_phrases=["arcade mute", "dasz"], max_phrases=60)
    assert prompt.startswith(core.split(", ")[0]) or core.split(", ")[0] in prompt
    assert "dasz" in prompt.split(", ")  # krótka fraza presetu dodana
