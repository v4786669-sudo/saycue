"""Typy wynikowe parsera (architektura §2.3 krok 7)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ParseResult:
    """Wynik dopasowania: Intent(name, slots, score, matches, …)."""

    intent: str
    slots: dict[str, Any]
    score: float
    matched: tuple[str, ...]
    source: str  # "exact" | "template" | "fuzzy"
    command_id: str
    origin: str = "core"  # "core" lub id presetu, z którego pochodzi komenda


@dataclass(frozen=True)
class Candidate:
    """Jeden kandydat dla widoku ASK („czy chodziło ci o …?")."""

    command_id: str
    intent: str
    slots: Mapping[str, Any]
    phrase: str
    original: str
    score: float
    source: str
    origin: str = "core"
    order: int = 0
