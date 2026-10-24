"""Testy loadera rdzenia: JSON Schema, hot-reload (polling), odporność na błędy."""

from __future__ import annotations

import shutil

import pytest
import yaml

from saycue.parser import (
    ConfigStore,
    PollingWatcher,
    RulesLoader,
    ValidationError,
)


@pytest.fixture()
def tmp_data(tmp_path, data_dir):
    dst = tmp_path / "data"
    dst.mkdir()
    shutil.copy(data_dir / "commands.yaml", dst / "commands.yaml")
    shutil.copy(data_dir / "apps.yaml", dst / "apps.yaml")
    return dst


def test_load_default_grammar(data_dir):
    cfg = RulesLoader(data_dir).load()
    assert cfg.version == 1
    assert cfg.language == "pl"
    assert len(cfg.commands) >= 14
    assert {"discord", "blender", "kalkulator"} <= set(cfg.apps)


def test_commands_schema_rejects_broken(tmp_data):
    doc = yaml.safe_load((tmp_data / "commands.yaml").read_text(encoding="utf-8"))
    doc["commands"][0]["id"] = "BAD ID!"
    (tmp_data / "commands.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(ValidationError):
        RulesLoader(tmp_data).load()


def test_commands_schema_rejects_missing_intent(tmp_data):
    doc = yaml.safe_load((tmp_data / "commands.yaml").read_text(encoding="utf-8"))
    del doc["commands"][0]["intent"]
    (tmp_data / "commands.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(ValidationError):
        RulesLoader(tmp_data).load()


def test_apps_schema_rejects_broken(tmp_data):
    doc = yaml.safe_load((tmp_data / "apps.yaml").read_text(encoding="utf-8"))
    doc["apps"]["blender"]["label"] = ""
    (tmp_data / "apps.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(ValidationError):
        RulesLoader(tmp_data).load()


def test_missing_commands_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        RulesLoader(tmp_path / "empty").load()


def test_missing_apps_yaml_is_tolerated(tmp_data):
    (tmp_data / "apps.yaml").unlink()
    cfg = RulesLoader(tmp_data).load()
    assert cfg.apps == {}
    assert len(cfg.commands) >= 14


def test_config_store_reload(tmp_data):
    changes = []
    store = ConfigStore(
        RulesLoader(tmp_data),
        watcher_cls=PollingWatcher,
        autostart=False,
        on_change=lambda cfg: changes.append(cfg),
    )
    n0 = len(store.config.commands)
    doc = yaml.safe_load((tmp_data / "commands.yaml").read_text(encoding="utf-8"))
    doc["commands"].append(
        {
            "id": "test_extra",
            "phrases": ["testowa fraza"],
            "intent": "app.open",
            "slots": {"target": "spotify"},
        }
    )
    (tmp_data / "commands.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    assert store.poll_once() is True
    assert len(changes) == 1
    assert len(store.config.commands) == n0 + 1
    assert store.last_error is None
    store.stop()


def test_config_store_broken_keeps_old(tmp_data):
    store = ConfigStore(RulesLoader(tmp_data), watcher_cls=PollingWatcher, autostart=False)
    n0 = len(store.config.commands)
    (tmp_data / "commands.yaml").write_text("commands: [niezamknięte", encoding="utf-8")
    assert store.poll_once() is False
    assert store.last_error is not None
    assert len(store.config.commands) == n0  # działa dalej na poprzedniej
    store.stop()


def test_reload_picks_up_removed_command(tmp_data):
    store = ConfigStore(RulesLoader(tmp_data), watcher_cls=PollingWatcher, autostart=False)
    doc = yaml.safe_load((tmp_data / "commands.yaml").read_text(encoding="utf-8"))
    doc["commands"] = doc["commands"][1:]
    (tmp_data / "commands.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    assert store.poll_once() is True
    assert len(store.config.commands) == len(doc["commands"])
    store.stop()
