"""Testy IntentParser — punkt integracji dla orchestratora (t9)."""

from __future__ import annotations

import shutil

import yaml

from saycue.parser import IntentParser, PollingWatcher


def test_default_core_only(data_dir):
    parser = IntentParser(data_dir=data_dir)
    assert parser.parse("cisza") is not None
    assert parser.parse("następna scena") is None  # obs-core nieaktywny
    parser.close()


def test_parse_and_candidates(data_dir):
    parser = IntentParser(data_dir=data_dir, active_presets=["obs-core"])
    result = parser.parse("wycisz mikrofon")
    assert result is not None and result.intent == "obs.mute"
    assert dict(result.slots) == {"source": "Mic/Aux", "state": "on"}
    cands = parser.candidates("wycisz mikrofn", k=3)
    assert cands and cands[0].intent == "obs.mute"
    parser.close()


def test_set_active_presets_rebuilds(data_dir, presets_dir):
    parser = IntentParser(data_dir=data_dir, presets_dir=presets_dir, active_presets=["obs-core"])
    assert parser.parse("elite podwozie") is None
    parser.set_active_presets(["obs-core", "elite-dangerous"])
    result = parser.parse("elite podwozie")
    assert result is not None and dict(result.slots) == {"keys": ["g"]}
    parser.close()


def test_hot_reload_via_store(tmp_path, data_dir, presets_dir):
    dst = tmp_path / "data"
    dst.mkdir()
    shutil.copy(data_dir / "commands.yaml", dst / "commands.yaml")
    shutil.copy(data_dir / "apps.yaml", dst / "apps.yaml")
    parser = IntentParser(
        data_dir=dst,
        presets_dir=presets_dir,
        active_presets=["obs-core"],
        watch=True,
        watcher_cls=PollingWatcher,
    )
    try:
        assert parser.parse("testowa fraza hot") is None
        doc = yaml.safe_load((dst / "commands.yaml").read_text(encoding="utf-8"))
        doc["commands"].append(
            {"id": "test_hot", "phrases": ["testowa fraza hot"], "intent": "app.open",
             "slots": {"target": "spotify"}}
        )
        (dst / "commands.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
        assert parser.store.poll_once() is True
        result = parser.parse("testowa fraza hot")
        assert result is not None and result.intent == "app.open"
    finally:
        parser.close()
