"""Kontrakt akcji (architektura §3.3): Action, ActionContext, ActionResult."""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ActionResult:
    """Wynik wykonania akcji — zawsze deterministyczny, bez wyjątków w górę."""

    ok: bool
    message: str = ""
    error: str | None = None
    latency_ms: float | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionContext:
    """Kontekst wykonania (wstrzykiwany przez orchestratora, t9).

    ``apps`` — zunifikowana mapa aplikacji (parser.rules); ``obs`` — ObsClient;
    ``dry_run`` — planowanie bez dotykania systemu (używane w testach).
    """

    platform: str = field(default_factory=lambda: sys.platform)
    dry_run: bool = False
    apps: Mapping[str, Any] | None = None
    obs: Any = None
    data_dir: Path | None = None


class Action(ABC):
    """Kontrakt §3.3: id + execute(slots, ctx) + available()."""

    id: str = ""
    intent: str = ""
    description: str = ""

    @abstractmethod
    def execute(self, slots: Mapping[str, Any], ctx: ActionContext) -> ActionResult:
        """Wykonaj intencję. Nie rzuca — błędy w ActionResult."""

    def available(self, ctx: ActionContext | None = None) -> bool:
        """Czy akcja może zadziałać w tym środowisku (np. OBS tylko z klientem)."""
        return True

    def availability_reason(self, ctx: ActionContext | None = None) -> str:
        """Czytelny powód niedostępności (dla GUI/faq)."""
        return "" if self.available(ctx) else "akcja niedostępna"
