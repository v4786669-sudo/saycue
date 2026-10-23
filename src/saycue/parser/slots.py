"""Ekstrakcja i rozwiązywanie slotów (architektura §2.3 krok 6).

Sloty statyczne pochodzą z YAML. Sloty dynamiczne (frazy-szablony
``otwórz {app}``, ``scena {scene}``) są wycinane z tekstu i rozwiązywane
po słownikach: nazwy aplikacji (apps.yaml / presety `apps[]`) i nazwy scen
(wartości slotów `scene` w aktywnych komendach). Dopasowanie po normalizacji,
z fuzzy ≥ 0.78 jako uzupełnieniem.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .fuzzy import ratio as _ratio
from .normalize import normalize_text


class SlotResolver:
    """Rozwiązywanie wartości slotu po słowniku (exact → fuzzy ≥ próg)."""

    def __init__(self, vocabs: Mapping[str, Mapping[str, Any]], *, threshold: float = 0.78):
        self._vocabs = {k: dict(v) for k, v in (vocabs or {}).items()}
        self._threshold = float(threshold)

    def allowed(self, slot: str) -> list[str]:
        """Dozwolone wartości slotu (posortowane, unikalne) — lista dla widoku
        ASK, gdy wartość nie została rozpoznana (R-02: nigdy akcja z surowym
        tekstem, zamiast tego propozycje)."""
        vocab = self._vocabs.get(slot) or {}
        return sorted({str(v) for v in vocab.values()})

    def resolve(self, slot: str, raw: str) -> Any | None:
        vocab = self._vocabs.get(slot) or {}
        if not vocab:
            return None
        norm = normalize_text(raw)
        if not norm:
            return None
        if norm in vocab:
            return vocab[norm]
        best: Any | None = None
        best_score = -1.0
        for key, canonical in vocab.items():
            score = _ratio(norm, key)
            if score > best_score:
                best_score, best = score, canonical
        if best_score >= self._threshold:
            return best
        return None


def build_slot_vocabs(
    commands: list[Mapping[str, Any]], apps: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    """Buduje słowniki slotów z komend i mapy aplikacji.

    * slot ``app``/``target`` → klucze i aliasy aplikacji (apps.yaml + presety);
    * slot ``scene`` i każdy inny statyczny slot string → wartości z komend.
    """
    vocabs: dict[str, dict[str, Any]] = {}
    app_vocab: dict[str, Any] = {}
    for app_id, entry in (apps or {}).items():
        # słowniki slotów to definicje — bez usuwania wypełniaczy (R-01)
        app_vocab[normalize_text(str(app_id), remove_fillers=False)] = str(app_id)
        for alias in entry.get("aliases") or []:
            app_vocab[normalize_text(str(alias), remove_fillers=False)] = str(app_id)
    if app_vocab:
        vocabs["app"] = app_vocab
        vocabs["target"] = dict(app_vocab)
    for cmd in commands or []:
        slots = cmd.get("slots") or {}
        for name, value in slots.items():
            if isinstance(value, str):
                vocabs.setdefault(name, {})[normalize_text(value, remove_fillers=False)] = value
            elif isinstance(value, (int, float)):
                vocabs.setdefault(name, {})[normalize_text(str(value))] = value
    return vocabs
