"""Regresja B-02/B-03 (notes/build-defects-g3.md): ścieżki danych w bundle PyInstaller.

W spakowanej aplikacji `__file__` wskazuje `_internal/saycue/config/paths.py`,
więc `parents[3]` ≠ katalog instalacji — `data_dir()` musi iść po
`sys._MEIPASS`. Ten test symuluje oba warianty (onedir `_internal`, onefile
katalog tymczasowy) i sprawdza, że loader znajduje gramatykę.
"""

from __future__ import annotations

import sys

import pytest

from saycue.config import paths


@pytest.fixture
def fake_install(tmp_path):
    """Struktura katalogów jak w onedir PyInstallera: <inst>/_internal/{data,saycue}."""
    internal = tmp_path / "saycue-install" / "_internal"
    (internal / "data").mkdir(parents=True)
    (internal / "saycue").mkdir(parents=True)
    for name, content in [
        (
            "commands.yaml",
            "version: 1\ncommands:\n  - id: t\n    phrases: [cisza]\n    intent: obs.mute\n",
        ),
        ("apps.yaml", "version: 1\napps: {}\n"),
        ("manifest.json", '{"format": 1, "models": []}\n'),
    ]:
        (internal / "data" / name).write_text(content, encoding="utf-8")
    return tmp_path / "saycue-install"


def test_data_dir_onedir_bundle(fake_install, monkeypatch):
    monkeypatch.setattr(sys, "_MEIPASS", str(fake_install / "_internal"), raising=False)
    data = paths.data_dir()
    assert data.is_dir()
    assert (data / "commands.yaml").is_file()
    assert (data / "apps.yaml").is_file()
    assert (data / "manifest.json").is_file()


def test_data_dir_onefile_bundle(fake_install, monkeypatch):
    # onefile: _MEIPASS = katalog tymczasowy zawierający data/ bezpośrednio
    tmp = fake_install / "_internal"  # używamy _internal jako „tmpdir" onefile
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp), raising=False)
    data = paths.data_dir()
    assert data.is_dir() and (data / "commands.yaml").is_file()


def test_presets_dir_bundle(fake_install, monkeypatch):
    (fake_install / "_internal" / "presets").mkdir()
    monkeypatch.setattr(sys, "_MEIPASS", str(fake_install / "_internal"), raising=False)
    assert paths.presets_dir().is_dir()


def test_data_dir_dev_mode(monkeypatch):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    data = paths.data_dir()
    assert data.is_dir() and (data / "commands.yaml").is_file()


def test_rules_loader_uses_bundled_data(fake_install, monkeypatch):
    """End-to-end: RulesLoader z paths.py działa na symulowanym bundle."""
    monkeypatch.setattr(sys, "_MEIPASS", str(fake_install / "_internal"), raising=False)
    # paths.data_dir() deleguje przez sys._MEIPASS — bez dodatkowych patchy
    from saycue.parser.rules import RulesLoader

    loader = RulesLoader()
    cfg = loader.load([], None)  # sam rdzeń, bez presetów
    assert len(cfg.commands) == 1
    assert cfg.commands[0]["id"] == "t"
