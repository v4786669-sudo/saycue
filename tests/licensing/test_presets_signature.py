"""Testy podpisu manifestu presetów (łańcuch dostaw): loader ładuje tylko
podpisane manifesty; zmiana index.json = odmowa."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import nacl.signing
import pytest

from saycue.licensing.manifest import verify_index_signature
from saycue.parser.presets import PresetError, PresetLoader


@pytest.fixture
def keypair():
    key = nacl.signing.SigningKey.generate()
    return key, key.verify_key


def make_index(index_path: Path, entries: dict | None = None) -> None:
    index_path.write_text(
        json.dumps(
            entries or {"obs-core": {"name": "OBS", "version": "1.0.0"}},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def sign_index(index_path: Path, key) -> Path:
    sig_path = index_path.with_suffix(index_path.suffix + ".sig")
    sig_path.write_text(
        base64.b64encode(key.sign(index_path.read_bytes()).signature).decode("ascii") + "\n",
        encoding="ascii",
    )
    return sig_path


def test_signed_manifest_verifies(tmp_path, keypair):
    key, verify = keypair
    index = tmp_path / "index.json"
    make_index(index)
    sign_index(index, key)
    assert verify_index_signature(index, verify_key=verify)


def test_modified_manifest_rejected(tmp_path, keypair):
    key, verify = keypair
    index = tmp_path / "index.json"
    make_index(index)
    sign_index(index, key)
    index.write_text(index.read_text().replace("1.0.0", "9.9.9"), encoding="utf-8")
    assert not verify_index_signature(index, verify_key=verify)


def test_missing_signature_rejected(tmp_path, keypair):
    _key, verify = keypair
    index = tmp_path / "index.json"
    make_index(index)
    assert not verify_index_signature(index, verify_key=verify)


def test_loader_loads_signed_manifest(tmp_path, keypair):
    key, verify = keypair
    presets = tmp_path / "presets"
    (presets / "obs-core").mkdir(parents=True)
    (presets / "obs-core" / "preset.yaml").write_text(
        "id: obs-core\nversion: '1.0.0'\nname: OBS\n"
        "platforms: [win, linux-x11]\nphrases: [scena testowa]\n"
        "commands: []\nlicense: MIT\n",
        encoding="utf-8",
    )
    make_index(presets / "index.json")
    sign_index(presets / "index.json", key)

    loader = PresetLoader(presets, validate=False, verify_key=verify)
    assert "obs-core" in loader.list_available()


def test_loader_rejects_modified_manifest(tmp_path, keypair, monkeypatch):
    key, verify = keypair
    presets = tmp_path / "presets"
    (presets / "obs-core").mkdir(parents=True)
    (presets / "obs-core" / "preset.yaml").write_text(
        "id: obs-core\nversion: '1.0.0'\nname: OBS\n"
        "platforms: [win, linux-x11]\nphrases: [scena testowa]\n"
        "commands: []\nlicense: MIT\n",
        encoding="utf-8",
    )
    make_index(presets / "index.json")
    sign_index(presets / "index.json", key)
    # wstrzyknięcie: podmiana manifestu bez ponownego podpisu
    index = presets / "index.json"
    make_index(index, {"malware": {"name": "złośliwy preset", "version": "0.0.1"}})

    with pytest.raises(PresetError, match="podpis"):
        PresetLoader(presets, validate=False, verify_key=verify)


def test_loader_without_index_json_is_noop(tmp_path):
    # katalogi bez manifestu (testy/dev) — hook nie przeszkadza
    presets = tmp_path / "presets"
    (presets / "graz").mkdir(parents=True)
    (presets / "graz" / "preset.yaml").write_text(
        "id: graz\nversion: '1.0.0'\nname: Gra\n"
        "platforms: [win]\nphrases: [komenda testowa]\n"
        "commands: []\nlicense: MIT\n",
        encoding="utf-8",
    )
    loader = PresetLoader(presets, validate=False)
    assert "graz" in loader.list_available()
