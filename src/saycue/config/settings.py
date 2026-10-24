"""Ustawienia SayCue : config.yaml użytkownika + domyślne wartości.

Telemetria, twardy wymóg):
- `events.jsonl` — włączony domyślnie (rdzeń OSS), jawny opt-out (`events: false`
  lub `--no-events`); NIGDY treści wypowiedzi.
- `metrics.jsonl` — opt-in (pyta przy pierwszym uruchomieniu); `asr_text`
  tylko w tym strumieniu i tylko po świadomej zgodzie.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .paths import config_dir


@dataclass
class Settings:
    language: str = "pl"
    model: str = "small"
    input: str = "auto"  # auto | wake | ptt | vad-gate
    end_silence_s: float = 0.6
    max_utterance_s: float = 8.0
    dry_run: bool = True
    presets: list[str] = field(
        default_factory=lambda: ["obs-core", "apps-open", "apps-streaming", "elite-dangerous"]
    )
    obs_url: str = ""  # host:port[:hasło]
    # telemetria (§2.4)
    events_enabled: bool = True  # events.jsonl: rdzeń OSS ON, jawny opt-out
    metrics_enabled: bool = False  # metrics.jsonl: opt-in (pyta przy 1. uruchomieniu)
    metrics_asked: bool = False  # czy pytanie o zgodę już zadane
    first_command_done: bool = False  # do first_command.success (G4a)
    first_run_done: bool = False  # onboarding „pierwsze 5 minut" pokazany

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        path = path or config_dir() / "config.yaml"
        if not path.is_file():
            return cls()
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            return cls()
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in raw.items() if k in known})

    def save(self, path: Path | None = None) -> Path:
        path = path or config_dir() / "config.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(asdict(self), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return path

    def update(self, **changes: Any) -> Settings:
        for key, value in changes.items():
            if hasattr(self, key):
                setattr(self, key, value)
        return self
