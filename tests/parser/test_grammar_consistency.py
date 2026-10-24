"""Spójność gramatyki: deduplikacja fraz core↔presety + pokrycie G1/G2.

(c) rdzeń (data/commands.yaml) NIE może duplikować fraz z presetów — przy
identycznej frazie wygrywa preset (parser/rules.py), a duplikat w rdzeniu
tylko mąci obraz i zaśmieca logi. Test sprawdza też unikalność fraz w obrębie
rdzenia oraz pokrycie zestawów bramek G1 (eval/commands.yaml) i G2
(eval/g2_commands.yaml) przez scaloną gramatykę (bez ASR i modeli —
deterministyczna symulacja warstwy parsera).
"""

from __future__ import annotations

import yaml

from saycue.parser import IntentParser, PresetLoader, RulesLoader
from saycue.parser.normalize import normalize_text

ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]
CORE_PATH = ROOT / "data" / "commands.yaml"
PRESETS_DIR = ROOT / "presets"
G1_YAML = ROOT / "eval" / "commands.yaml"
G2_YAML = ROOT / "eval" / "g2_commands.yaml"
# arcade-dash: frazy dash przeniesione z rdzenia
G2_ACTIVATION = ["obs-core", "apps-open", "apps-streaming", "elite-dangerous", "arcade-dash"]

TARGET_PRESETS = None  # None = WSZYSTKIE presety z katalogu (silniejszy test)


def _core_phrases() -> dict[str, str]:
    doc = yaml.safe_load(CORE_PATH.read_text(encoding="utf-8"))
    phrases: dict[str, str] = {}
    for cmd in doc.get("commands") or []:
        for phrase in cmd.get("phrases") or []:
            norm = normalize_text(str(phrase))
            if not norm:
                continue
            if norm in phrases:
                raise AssertionError(f"duplikat frazy {phrase!r} W RZENIU")
            phrases[norm] = cmd["id"]
    return phrases


def _preset_phrases(presets_dir=PRESETS_DIR) -> dict[str, str]:
    loader = PresetLoader(presets_dir)
    phrases: dict[str, str] = {}
    target = TARGET_PRESETS or loader.list_available()
    for preset_id in target:
        preset = loader.load(preset_id)
        for cmd in preset.commands:
            for phrase in cmd.get("phrases") or []:
                norm = normalize_text(str(phrase))
                if norm:
                    phrases[norm] = f"{preset_id}.{cmd['id']}"
    return phrases


def test_no_phrase_duplicates_between_core_and_presets():
    """(c) brak duplikatów fraz w gramatyce: rdzeń vs obs-core/apps-open/
    apps-streaming (dedup)."""
    core = _core_phrases()
    presets = _preset_phrases()
    dups = sorted(set(core) & set(presets))
    assert not dups, f"{len(dups)} fraz zduplikowanych między rdzeniem a presetami: {dups}"


def test_core_phrases_unique_across_commands():
    _core_phrases()  # rzuca AssertionError przy duplikacie wewnątrz rdzenia


def _g2_expected():
    doc = yaml.safe_load(G2_YAML.read_text(encoding="utf-8"))
    return [(str(p["phrase"]), str(p["intent"]), p.get("slots")) for p in doc["phrases"]]


def test_grammar_covers_g1_set():
    doc = yaml.safe_load(G1_YAML.read_text(encoding="utf-8"))
    parser = IntentParser(active_presets=G2_ACTIVATION)
    try:
        failures = []
        for entry in doc["phrases"]:
            result = parser.parse(str(entry["phrase"]))
            if result is None or result.intent != str(entry["intent"]):
                failures.append(f"{entry['id']}: {entry['phrase']!r} → {result}")
        assert not failures, "G1 bez pokrycia:\n" + "\n".join(failures)
    finally:
        parser.close()


def test_grammar_covers_g2_set():
    parser = IntentParser(active_presets=G2_ACTIVATION)
    try:
        failures = []
        for phrase, intent, slots in _g2_expected():
            result = parser.parse(phrase)
            if result is None:
                failures.append(f"{phrase!r} → brak intencji (oczekiwano {intent})")
                continue
            if result.intent != intent:
                failures.append(f"{phrase!r} → {result.intent} (oczekiwano {intent})")
                continue
            if slots:
                for key, value in slots.items():
                    if result.slots.get(key) != value:
                        failures.append(
                            f"{phrase!r} slot {key}={result.slots.get(key)!r} "
                            f"(oczekiwano {value!r})"
                        )
        assert not failures, "G2 bez pokrycia:\n" + "\n".join(failures)
    finally:
        parser.close()


def test_merged_grammar_has_no_cross_source_collision_errors():
    """Scalenie rdzeń+presety nie rzuca ValidationError (kolizje intentów)."""
    loader = RulesLoader(ROOT / "data")
    cfg = loader.load(G2_ACTIVATION, PresetLoader(PRESETS_DIR))
    assert cfg.commands
    assert cfg.active_presets == G2_ACTIVATION
