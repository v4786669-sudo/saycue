"""Typy wynikowe parsera (architektura §2.3 krok 7)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ParseResult:
    """Wynik dopasowania: Intent(name, slots, score, matches, …).

    ``rewritten_fillers`` — DIAGNOSTYKA R-01 (architektura v0.3 §2.3):
    wyłącznie licznik/tokeny usuniętych wypełniaczy ze stałego słownika
    (prosze/hej/asystent/ok), NIGDY treść mowy — bezpieczne dla events.jsonl.
    """

    intent: str
    slots: dict[str, Any]
    score: float
    matched: tuple[str, ...]
    source: str  # "exact" | "template" | "fuzzy"
    command_id: str
    origin: str = "core"  # "core" lub id presetu, z którego pochodzi komenda
    rewritten_fillers: tuple[str, ...] = ()


@dataclass(frozen=True)
class Candidate:
    """Jeden kandydat dla widoku ASK („czy chodziło ci o …?").

    ``actionable`` — czy kandydat przekroczył progi wykonania (score ≥
    min_action_score, pokrycie tokenów ≥ min_phrase_coverage). Kandydat
    z ``actionable=False`` to propozycja ASK, nigdy akcja (R-02).
    ``allowed_values`` — dozwolone wartości slotu (dla szablonów z
    nierozpoznaną wartością — lista dla widoku ASK, R-02).
    """

    command_id: str
    intent: str
    slots: Mapping[str, Any]
    phrase: str
    original: str
    score: float
    source: str
    origin: str = "core"
    order: int = 0
    actionable: bool = True
    allowed_values: tuple[str, ...] = ()
