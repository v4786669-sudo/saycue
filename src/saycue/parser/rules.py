"""Loader gramatyki: commands.yaml + apps.yaml + presety + JSON Schema + hot-reload.

* ``RulesLoader`` — ładuje ``data/commands.yaml`` (rdzeń gramatyki)
  i ``data/apps.yaml`` (mapowanie aplikacji) z walidacją JSON Schema.
* Aktywacja presetów: ``load(active_presets=[...])``
  skleja rdzeń z komendami aktywnych presetów (kolejność aktywacji = priorytet;
  przy identycznej frazie wygrywa później aktywowany preset — jedna gra +
  obs-core + apps-* naraz, kolizje rozstrzygane w obrębie aktywacji).
* ``ConfigStore`` — hot-reload (watchdog, fallback: polling mtime).
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .normalize import normalize_text
from .presets import Preset, PresetLoader

log = logging.getLogger(__name__)

SCHEMAS_DIR = Path(__file__).resolve().parent / "schemas"


class ValidationError(ValueError):
    """Dokument YAML nie spełnia JSON Schema."""

    def __init__(self, path: Path, errors: list[str]):
        self.path = path
        self.errors = errors
        super().__init__(f"walidacja {path.name} nieudana: {'; '.join(errors)}")


def validate_doc(doc: Any, schema_name: str, path: Path) -> None:
    try:
        import jsonschema
    except ImportError:  # pragma: no cover
        log.warning("jsonschema nie zainstalowany — walidacja %s pominięta", path.name)
        return
    schema = json.loads((SCHEMAS_DIR / schema_name).read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(doc), key=lambda e: [str(p) for p in e.path])
    if errors:
        raise ValidationError(
            path,
            [f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors],
        )


def load_yaml(path: Path) -> Any:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_commands(path: Path, *, validate: bool = True) -> list[dict[str, Any]]:
    doc = load_yaml(path)
    if validate:
        validate_doc(doc, "commands.schema.json", path)
    return list(doc.get("commands") or [])


def load_apps(path: Path, *, validate: bool = True) -> dict[str, Any]:
    doc = load_yaml(path)
    if validate:
        validate_doc(doc, "apps.schema.json", path)
    return dict(doc.get("apps") or {})


# ------------------------------------------------------------------ modele


@dataclass
class RulesConfig:
    version: int
    language: str
    commands: list[dict[str, Any]]  # znormalizowane + origin ("core" | id presetu)
    apps: dict[str, Any]  # zunifikowane wpisy aplikacji (patrz _normalize_app)
    commands_path: Path
    apps_path: Path
    active_presets: list[str] = field(default_factory=list)
    presets: list[Preset] = field(default_factory=list)


def _normalize_core_app(app_id: str, entry: Mapping[str, Any]) -> dict[str, Any]:
    """Wpis apps.yaml → zunifikowana postać {label, aliases, win, linux, url}."""
    win = dict(entry.get("windows") or {})
    linux = dict(entry.get("linux") or {})
    return {
        "label": str(entry.get("label") or app_id),
        "aliases": [str(a) for a in (entry.get("aliases") or [])],
        "win": {
            "exe": win.get("exe"),
            "args": [str(a) for a in (win.get("args") or [])],
            "app_id": win.get("app_id"),
        },
        "linux": {
            "desktop_id": linux.get("desktop_id"),
            "cmd": [str(c) for c in (linux.get("cmd") or [])] if linux.get("cmd") else None,
        },
        "url": entry.get("url"),
    }


def _merge_preset_app(app_id: str, raw: Mapping[str, Any]) -> dict[str, Any]:
    from .presets import parse_linux_launch, parse_win_launch

    win = parse_win_launch(str(raw.get("win") or ""))
    linux = parse_linux_launch(str(raw.get("linux") or ""))
    return {
        "label": str(raw.get("name") or app_id),
        "aliases": [str(a) for a in (raw.get("aliases") or [])],
        "win": win,
        "linux": linux,
        "url": raw.get("url"),
    }


def _merge_apps(core_apps: Mapping[str, Any], presets: list[Preset]) -> dict[str, Any]:
    """Rdzeń + apps[] presetów (kolejność aktywacji = priorytet; aliasy się sumują)."""
    merged: dict[str, Any] = {}
    for app_id, entry in core_apps.items():
        merged[str(app_id)] = _normalize_core_app(str(app_id), entry)
    for preset in presets:
        for raw in preset.apps:
            app_id = str(raw.get("id") or "")
            if not app_id:
                continue
            incoming = _merge_preset_app(app_id, raw)
            if app_id in merged:
                merged[app_id]["label"] = incoming["label"]
                merged[app_id]["win"] = incoming["win"]
                merged[app_id]["linux"] = incoming["linux"]
                if incoming["url"]:
                    merged[app_id]["url"] = incoming["url"]
                merged[app_id]["aliases"] = list(
                    dict.fromkeys(merged[app_id]["aliases"] + incoming["aliases"])
                )
            else:
                merged[app_id] = incoming
    return merged


def _merge_commands(
    core_commands: list[Mapping[str, Any]],
    presets: list[Preset],
) -> list[dict[str, Any]]:
    """Skleja rdzeń z komendami presetów; rozstrzyga kolizje fraz.

    * identyczna fraza + ten sam intent → frazę przejmuje później aktywowany
      preset (komenda wcześniejsza traci tylko TĘ frazę; znika, gdy straci
      wszystkie — determinizm, log);
    * identyczna fraza + inny intent → ValidationError.
    """
    merged: list[dict[str, Any]] = []
    for cmd in core_commands:
        merged.append(
            {
                "id": str(cmd["id"]),
                "intent": str(cmd["intent"]),
                "phrases": [str(p) for p in (cmd.get("phrases") or [])],
                "slots": dict(cmd.get("slots") or {}),
                "origin": "core",
            }
        )
    for preset in presets:
        merged.extend(preset.commands)

    # Faza 1: indeks fraz → komenda-właściciel (późniejsza aktywacja wygrywa).
    phrase_index: dict[str, dict[str, Any]] = {}
    for cmd in merged:
        for phrase in cmd.get("phrases") or []:
            norm = normalize_text(str(phrase))
            if not norm:
                continue
            existing = phrase_index.get(norm)
            if existing is not None:
                if existing["intent"] != cmd["intent"]:
                    raise ValidationError(
                        Path("commands/presets"),
                        [
                            f"kolizja frazy {phrase!r}: {existing['id']} "
                            f"(intent {existing['intent']}, {existing['origin']}) vs "
                            f"{cmd['id']} (intent {cmd['intent']}, {cmd['origin']})"
                        ],
                    )
                log.info(
                    "fraza %r zduplikowana (%s.%s vs %s.%s) — wygrywa %s.%s",
                    phrase,
                    existing["origin"],
                    existing["id"],
                    cmd["origin"],
                    cmd["id"],
                    cmd["origin"],
                    cmd["id"],
                )
            phrase_index[norm] = cmd

    # Faza 2: komenda zostaje, jeśli ma jeszcze własne frazy (bez mutacji).
    out: list[dict[str, Any]] = []
    for cmd in merged:
        owned = [
            str(p)
            for p in (cmd.get("phrases") or [])
            if phrase_index.get(normalize_text(str(p))) is cmd
        ]
        if not owned:
            continue
        final = dict(cmd)
        final["phrases"] = owned
        out.append(final)
    return out


# ------------------------------------------------------------------ loader


def default_data_dir() -> Path:
    try:
        from saycue.config.paths import data_dir

        return data_dir()
    except Exception:  # pragma: no cover
        return Path(__file__).resolve().parents[3] / "data"


class RulesLoader:
    def __init__(self, data_dir: Path | None = None, *, validate: bool = True):
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        self.validate = validate

    @property
    def commands_path(self) -> Path:
        return self.data_dir / "commands.yaml"

    @property
    def apps_path(self) -> Path:
        return self.data_dir / "apps.yaml"

    def load(
        self,
        active_presets: list[str] | None = None,
        preset_loader: PresetLoader | None = None,
    ) -> RulesConfig:
        commands = load_commands(self.commands_path, validate=self.validate)
        apps: dict[str, Any] = {}
        if self.apps_path.is_file():
            apps = load_apps(self.apps_path, validate=self.validate)
        else:
            log.info("brak apps.yaml (%s) — rdzeń bez mapowania aplikacji", self.apps_path)
        doc = load_yaml(self.commands_path)
        presets: list[Preset] = []
        if active_presets:
            loader = preset_loader or PresetLoader()
            presets = loader.load_many(list(active_presets))
        merged_commands = _merge_commands(commands, presets)
        merged_apps = _merge_apps(apps, presets)
        return RulesConfig(
            version=int(doc.get("version") or 0),
            language=str(doc.get("language") or "pl"),
            commands=merged_commands,
            apps=merged_apps,
            commands_path=self.commands_path,
            apps_path=self.apps_path,
            active_presets=list(active_presets or []),
            presets=presets,
        )


# ------------------------------------------------------- hot-reload (watchdog)


class PollingWatcher(threading.Thread):
    """Deterministyczny fallback: co interwał sprawdza mtime/size plików."""

    def __init__(
        self,
        paths: list[Path],
        callback: Callable[[], bool],
        interval: float = 0.5,
    ):
        super().__init__(name="saycue-config-poll", daemon=True)
        self._paths = [Path(p) for p in paths]
        self._callback = callback
        self._interval = interval
        self._stop_event = threading.Event()
        self._mtimes = {p: self._stat(p) for p in self._paths}

    @staticmethod
    def _stat(path: Path):
        try:
            st = path.stat()
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def poll_once(self) -> bool:
        if not any(self._stat(p) != self._mtimes[p] for p in self._paths):
            return False
        result = False
        try:
            result = bool(self._callback())
        except Exception:
            log.exception("callback przeładowania konfiguracji rzucił wyjątek")
        for p in self._paths:
            self._mtimes[p] = self._stat(p)
        return result

    def run(self) -> None:
        while not self._stop_event.wait(self._interval):
            self.poll_once()

    def start(self) -> None:
        if not self.is_alive():
            super().start()

    def stop(self) -> None:
        self._stop_event.set()
        if self.is_alive():
            self.join(timeout=2.0)


class WatchdogWatcher:
    """Obserwator plików na bazie `watchdog` (gdy biblioteka dostępna)."""

    def __init__(self, paths: list[Path], callback: Callable[[], bool], interval: float = 0.5):
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer

        self._callback = callback
        names = {Path(p).name for p in paths}
        dirs = {Path(p).parent for p in paths}
        self._observer = Observer()
        self._observer.daemon = True

        class _Handler(FileSystemEventHandler):
            def on_any_event(self, event) -> None:  # noqa: ANN001
                if event.is_directory:
                    return
                if Path(event.src_path).name in names:
                    try:
                        callback()
                    except Exception:
                        log.exception("callback przeładowania konfiguracji rzucił wyjątek")

        for d in dirs:
            if d.is_dir():
                self._observer.schedule(_Handler(), str(d), recursive=False)

    def poll_once(self) -> bool:
        return False

    def start(self) -> None:
        self._observer.start()

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join(timeout=2.0)


def _prefer_watcher() -> type:
    try:
        import watchdog  # noqa: F401

        return WatchdogWatcher
    except ImportError:  # pragma: no cover
        return PollingWatcher


class ConfigStore:
    """Trzyma aktualny RulesConfig i przeładowuje go przy zmianie plików.

    Błędna konfiguracja NIE podmienia działającej — zostaje poprzednia,
    a błąd ląduje w ``last_error`` (hot-reload odporny na literówki).
    """

    def __init__(
        self,
        loader: RulesLoader,
        *,
        watcher_cls: type | None = None,
        interval: float = 0.5,
        on_change: Callable[[RulesConfig], None] | None = None,
        autostart: bool = True,
    ):
        self.loader = loader
        self._on_change = on_change
        self._lock = threading.Lock()
        self.last_error: Exception | None = None
        self.config: RulesConfig = loader.load()
        cls = watcher_cls or _prefer_watcher()
        self.watcher = cls(
            paths=[loader.commands_path, loader.apps_path],
            callback=self._handle_change,
            interval=interval,
        )
        if autostart:
            self.start()

    def _handle_change(self) -> bool:
        try:
            cfg = self.loader.load(self.config.active_presets)
        except Exception as exc:
            self.last_error = exc
            log.warning("błędna konfiguracja — zostaje poprzednia: %s", exc)
            return False
        with self._lock:
            self.config = cfg
            self.last_error = None
        if self._on_change is not None:
            try:
                self._on_change(cfg)
            except Exception:
                log.exception("on_change rzucił wyjątek")
        return True

    def reload_now(self) -> bool:
        return self._handle_change()

    def poll_once(self) -> bool:
        return bool(self.watcher.poll_once())

    def start(self) -> None:
        self.watcher.start()

    def stop(self) -> None:
        self.watcher.stop()
