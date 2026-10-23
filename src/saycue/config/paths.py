"""Ścieżki katalogów SayCue (cache modeli, konfiguracja użytkownika, dane).

Uwaga na PyInstaller (defekty B-02/B-03, notes/build-defects-g3.md):
w spakowanej aplikacji `__file__` wskazuje `_internal/saycue/config/paths.py`,
więc `parents[3]` NIE jest katalogiem instalacji. `sys._MEIPASS` (onedir:
`_internal`; onefile: katalog tymczasowy) jednoznacznie wskazuje zasoby —
`repo_root()` najpierw sprawdza bundle, dopiero potem strukturę dev.
"""

from __future__ import annotations

import sys
from pathlib import Path

from platformdirs import user_cache_dir, user_config_dir

APP_NAME = "saycue"


def _bundle_root() -> Path | None:
    """Katalog zasobów PyInstallera: None poza bundle'em."""
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) if base else None


def cache_dir() -> Path:
    """Katalog cache: modele (wg manifestu), logi lokalne."""
    return Path(user_cache_dir(APP_NAME))


def models_dir() -> Path:
    return cache_dir() / "models"


def config_dir() -> Path:
    return Path(user_config_dir(APP_NAME))


def repo_root() -> Path:
    """Katalog główny repozytorium/instalacji (dla `data/`, `presets/`).

    Bundle PyInstaller onedir: `sys._MEIPASS` = `<instalacja>/_internal`,
    więc zasoby leżą w jego RODZICU (katalog instalacji) lub w samym `_internal`
    — rozstrzyga `data_dir()`. Onefile: zasoby w katalogu tymczasowym."""
    frozen = _bundle_root()
    if frozen is not None:
        # onedir: _internal/ → katalog instalacji; onefile: katalog tymczasowy
        return frozen.parent if frozen.name == "_internal" else frozen
    return Path(__file__).resolve().parents[3]


def data_dir() -> Path:
    """Katalog z commands.yaml/apps.yaml (repo lub bundle)."""
    root = repo_root()
    for candidate in (root / "data", root / "_internal" / "data"):
        if candidate.is_dir():
            return candidate
    return root / "data"


def presets_dir() -> Path:
    """Katalog presetów YAML (repo lub bundle)."""
    root = repo_root()
    for candidate in (root / "presets", root / "_internal" / "presets"):
        if candidate.is_dir():
            return candidate
    return root / "presets"
