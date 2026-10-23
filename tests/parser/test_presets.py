"""Testy loadera presetów (presets/<id>/preset.yaml, schema t8) i aktywacji."""

from __future__ import annotations

import pytest
import yaml

from saycue.parser import IntentParser, PresetError, PresetLoader, ValidationError
from saycue.parser.presets import parse_linux_launch, parse_win_launch


def test_list_available(presets_dir):
    loader = PresetLoader(presets_dir)
    ids = loader.list_available()
    assert set(ids) == {
        "apps-open",
        "apps-streaming",
        "dcs",
        "elite-dangerous",
        "minecraft",
        "msfs",
        "obs-core",
        "star-citizen",
    }


def test_all_presets_pass_schema(presets_dir):
    loader = PresetLoader(presets_dir)
    for preset_id in loader.list_available():
        preset = loader.load(preset_id)
        assert preset.id == preset_id
        assert preset.commands


def test_obs_core_normalization(presets_dir):
    preset = PresetLoader(presets_dir).load("obs-core")
    by_id = {c["id"]: c for c in preset.commands}
    assert by_id["obs_next_scene"]["slots"] == {"scene": "__next__"}
    assert by_id["obs_prev_scene"]["slots"] == {"scene": "__prev__"}
    assert by_id["obs_record_start"]["slots"] == {"state": "start"}  # action→state
    assert by_id["obs_replay_save"]["slots"] == {"action": "save"}  # buffer→action
    for cmd in preset.commands:
        assert cmd["origin"] == "obs-core"


def test_game_keybind_resolution(presets_dir):
    preset = PresetLoader(presets_dir).load("elite-dangerous")
    by_id = {c["id"]: c for c in preset.commands}
    assert by_id["ed_landing_gear"]["slots"] == {"keys": ["g"]}
    # preset zapisuje combo jako pojedynczy token "shift+x" — dzieli je akcja
    assert by_id["ed_boost"]["slots"] == {"keys": ["shift+x"]}


def test_parse_launch_strings():
    assert parse_win_launch("Spotify.exe") == {"exe": "Spotify.exe", "args": [], "app_id": None}
    assert parse_win_launch("Update.exe --processStart Discord.exe") == {
        "exe": "Update.exe",
        "args": ["--processStart", "Discord.exe"],
        "app_id": None,
    }
    assert (
        parse_win_launch("shell:AppsFolder\\Foo.Bar_123")["app_id"]
        == "shell:AppsFolder\\Foo.Bar_123"
    )
    assert parse_linux_launch("firefox.desktop") == {"desktop_id": "firefox.desktop", "cmd": None}
    assert parse_linux_launch("obs --studio-mode") == {
        "desktop_id": None,
        "cmd": ["obs", "--studio-mode"],
    }


def test_game_preset_active_switches_grammar(presets_dir):
    parser = IntentParser(
        active_presets=["obs-core", "apps-open", "apps-streaming", "elite-dangerous"]
    )
    r = parser.parse("elite podwozie")
    assert r is not None and r.intent == "input.keys"
    assert dict(r.slots) == {"keys": ["g"]}
    assert r.origin == "elite-dangerous"
    assert parser.parse("mine ekwipunek") is None
    # podmiana gry na inną — deterministyczna przebudowa
    parser.set_active_presets(["obs-core", "apps-open", "apps-streaming", "minecraft"])
    r = parser.parse("mine ekwipunek")
    assert r is not None and r.intent == "input.keys"
    assert dict(r.slots) == {"keys": ["e"]}
    assert parser.parse("elite podwozie") is None


def test_game_prefixes_share_vocabulary(presets_dir):
    """Gry dzielą słownictwo — prefiks gry rozstrzyga (decyzja t13/kapitan)."""
    parser = IntentParser(
        active_presets=["obs-core", "apps-open", "apps-streaming", "elite-dangerous"]
    )
    assert parser.parse("elite podwozie") is not None
    # "podwozie" bez prefiksu nie uruchamia akcji gry
    assert parser.parse("podwozie") is None


def test_broken_preset_raises(tmp_path, presets_dir):
    bad_dir = tmp_path / "presets"
    bad_dir.mkdir()
    (bad_dir / "schema.json").write_text(
        (presets_dir / "schema.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    doc = yaml.safe_load((presets_dir / "obs-core" / "preset.yaml").read_text(encoding="utf-8"))
    doc["id"] = "inny-id"  # niezgodne z nazwą katalogu
    target = bad_dir / "broken"
    target.mkdir()
    (target / "preset.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    with pytest.raises(PresetError):
        PresetLoader(bad_dir).load("broken")


def test_unknown_keybind_raises(tmp_path, presets_dir):
    bad_dir = tmp_path / "presets"
    bad_dir.mkdir()
    (bad_dir / "schema.json").write_text(
        (presets_dir / "schema.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    doc = yaml.safe_load((presets_dir / "minecraft" / "preset.yaml").read_text(encoding="utf-8"))
    doc["id"] = "badbind"
    doc["commands"][0]["slots"] = {"keybind": "nieistniejacy"}
    target = bad_dir / "badbind"
    target.mkdir()
    (target / "preset.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    with pytest.raises(PresetError, match="keybind"):
        PresetLoader(bad_dir).load("badbind")


def test_cross_intent_phrase_collision_fails(tmp_path, presets_dir, data_dir):
    """Ta sama fraza z różnymi intentami w aktywacji = ValidationError (determinizm)."""
    import shutil

    bad_dir = tmp_path / "presets"
    bad_dir.mkdir()
    (bad_dir / "schema.json").write_text(
        (presets_dir / "schema.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    schema_ok_doc = yaml.safe_load(
        (presets_dir / "apps-open" / "preset.yaml").read_text(encoding="utf-8")
    )

    def write_preset(pid: str, phrases: list[str], intent: str) -> None:
        doc = dict(schema_ok_doc)
        doc["id"] = pid
        doc["commands"] = [
            {"id": f"cmd{len(doc['commands'])}", "intent": intent, "phrases": phrases, "slots": {}}
        ]
        d = bad_dir / pid
        d.mkdir()
        (d / "preset.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")

    write_preset("aaa-first", ["dziwna fraza", "dziwna fraza dwa", "dziwna fraza trzy"], "app.open")
    write_preset(
        "bbb-second", ["dziwna fraza", "inna fraza druga", "inna fraza trzecia"], "input.keys"
    )
    from saycue.parser.rules import RulesLoader

    data = tmp_path / "data"
    data.mkdir()
    shutil.copy(data_dir / "commands.yaml", data / "commands.yaml")
    loader = RulesLoader(data)
    with pytest.raises(ValidationError, match="kolizja frazy"):
        loader.load(["aaa-first", "bbb-second"], PresetLoader(bad_dir))
