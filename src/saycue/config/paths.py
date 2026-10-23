"""Ścieżki katalogów SayCue (cache modeli, konfiguracja użytkownika)."""

from __future__ import annotations

from pathlib import Path

from platformdirs import user_cache_dir, user_config_dir

APP_NAME = "saycue"


def cache_dir() -> Path:
    """Katalog cache: modele (wg manifestu), logi lokalne."""
    return Path(user_cache_dir(APP_NAME))


def models_dir() -> Path:
    return cache_dir() / "models"


def config_dir() -> Path:
    return Path(user_config_dir(APP_NAME))


def repo_root() -> Path:
    """Katalog główny repozytorium (dla `data/`, `models/` w trybie dev)."""
    return Path(__file__).resolve().parents[3]


def data_dir() -> Path:
    return repo_root() / "data"
