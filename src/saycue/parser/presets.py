"""Loader presetów YAML (architektura §2.5) — dane, nie kod.

Każdy preset to katalog ``presets/<id>/`` z plikiem ``preset.yaml``
walidowanym względem ``presets/schema.json`` (draft 2020-12, kontrakt
zdefiniowany w t8). Loader zwraca znormalizowane komendy gotowe dla
``parser/matcher.py``:

* ``input.keys`` + slot ``keybind`` → rozwiązywany na ``keys`` z mapy ``keys:`` presetu;
* ``obs.record`` slot ``action`` → ``state`` (kontrakt akcji);
* ``obs.replay`` slot ``buffer`` → ``action``;
* ``origin`` = id presetu (kolizje fraz rozstrzyga ``rules.py`` przy aktywacji).
"""

from __future__ import annotations

import json
import logging
import shlex
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)


class PresetError(ValueError):
    """Preset niezgodny ze schematem lub uszkodzony."""

    def __init__(self, preset_id: str, message: str):
        self.preset_id = preset_id
        super().__init__(f"preset {preset_id!r}: {message}")


def _repo_root() -> Path:
    try:
        from saycue.config.paths import repo_root

        return repo_root()
    except Exception:  # pragma: no cover
        return Path(__file__).resolve().parents[3]


@dataclass
class Preset:
    id: str
    version: str
    name: str
    kind: str
    platforms: list[str]
    author: str
    license: str
    requires: dict[str, Any]
    phrases: list[str]
    commands: list[dict[str, Any]]  # znormalizowane komendy (origin=preset id)
    apps: list[dict[str, Any]]  # surowe wpisy apps[]
    scenes: list[dict[str, str]]
    sources: list[dict[str, str]]
    keys: dict[str, list[str]]
    notes: str = ""
    path: Path = field(default_factory=Path)


def parse_win_launch(value: str) -> dict[str, Any]:
    """String `win` presetu → {"exe", "args", "app_id"}.

    Obsługuje: ``spotify.exe``, ``Update.exe --processStart Discord.exe``,
    ``shell:AppsFolder\\…`` (AUMID), URL (wtedy exe=None).
    """
    value = (value or "").strip()
    if not value:
        return {"exe": None, "args": [], "app_id": None}
    if value.lower().startswith("shell:"):
        return {"exe": None, "args": [], "app_id": value}
    if value.lower().startswith(("http://", "https://")):
        return {"exe": None, "args": [], "app_id": None}
    tokens = shlex.split(value)
    return {"exe": tokens[0] if tokens else None, "args": tokens[1:], "app_id": None}


def parse_linux_launch(value: str) -> dict[str, Any]:
    """String `linux` presetu → {"desktop_id", "cmd"}: .desktop albo komenda."""
    value = (value or "").strip()
    if not value:
        return {"desktop_id": None, "cmd": None}
    if value.endswith(".desktop"):
        return {"desktop_id": value, "cmd": None}
    return {"desktop_id": None, "cmd": shlex.split(value)}


class PresetLoader:
    """Ładowanie i walidacja presetów z katalogu ``presets/``."""

    def __init__(self, presets_dir: Path | None = None, *, validate: bool = True):
        self.presets_dir = Path(presets_dir) if presets_dir is not None else _repo_root() / "presets"
        self.validate = validate

    @property
    def schema_path(self) -> Path:
        return self.presets_dir / "schema.json"

    def list_available(self) -> list[str]:
        """Identyfikatory presetów (katalogi z preset.yaml), posortowane."""
        if not self.presets_dir.is_dir():
            return []
        out = []
        for child in sorted(self.presets_dir.iterdir()):
            if child.is_dir() and (child / "preset.yaml").is_file():
                out.append(child.name)
        return out

    def load(self, preset_id: str) -> Preset:
        preset_dir = self.presets_dir / preset_id
        path = preset_dir / "preset.yaml"
        if not path.is_file():
            raise PresetError(preset_id, f"brak pliku {path}")
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if self.validate:
            self._validate_doc(preset_id, doc, path)
        if doc.get("id") != preset_id:
            raise PresetError(preset_id, "pole `id` musi być równe nazwie katalogu")
        commands = self._normalize_commands(preset_id, doc, path)
        return Preset(
            id=str(doc["id"]),
            version=str(doc.get("version", "")),
            name=str(doc.get("name", preset_id)),
            kind=str(doc.get("kind", "")),
            platforms=list(doc.get("platforms") or []),
            author=str(doc.get("author", "")),
            license=str(doc.get("license", "MIT")),
            requires=dict(doc.get("requires") or {}),
            phrases=list(doc.get("phrases") or []),
            commands=commands,
            apps=list(doc.get("apps") or []),
            scenes=list(doc.get("scenes") or []),
            sources=list(doc.get("sources") or []),
            keys={k: list(v) for k, v in (doc.get("keys") or {}).items()},
            notes=str(doc.get("notes") or ""),
            path=path,
        )

    def load_many(self, preset_ids: list[str]) -> list[Preset]:
        return [self.load(pid) for pid in preset_ids]

    # ------------------------------------------------------------------ pomoc

    def _validate_doc(self, preset_id: str, doc: Mapping[str, Any], path: Path) -> None:
        try:
            import jsonschema
        except ImportError:  # pragma: no cover
            log.warning("jsonschema nie zainstalowany — walidacja presetu pominięta")
            return
        schema = json.loads(self.schema_path.read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(doc), key=lambda e: [str(p) for p in e.path])
        if errors:
            detail = "; ".join(
                f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors
            )
            raise PresetError(preset_id, f"niezgodny ze schematem — {detail}")

    def _normalize_commands(self, preset_id: str, doc: Mapping[str, Any], path: Path) -> list[dict[str, Any]]:
        keys_map: dict[str, list[str]] = {k: list(v) for k, v in (doc.get("keys") or {}).items()}
        out: list[dict[str, Any]] = []
        for raw in doc.get("commands") or []:
            cmd: dict[str, Any] = {
                "id": str(raw["id"]),
                "intent": str(raw["intent"]),
                "phrases": [str(p) for p in raw.get("phrases") or []],
                "slots": dict(raw.get("slots") or {}),
                "origin": preset_id,
                "risk": raw.get("risk"),
            }
            intent = cmd["intent"]
            slots = cmd["slots"]
            if intent == "input.keys" and "keybind" in slots:
                keybind = str(slots.pop("keybind"))
                if keybind not in keys_map:
                    raise PresetError(preset_id, f"komenda {cmd['id']!r}: nieznany keybind {keybind!r}")
                slots["keys"] = list(keys_map[keybind])
            if intent == "obs.record" and "action" in slots:
                slots["state"] = slots.pop("action")
            if intent == "obs.replay" and "buffer" in slots:
                slots["action"] = slots.pop("buffer")
            out.append(cmd)
        return out
