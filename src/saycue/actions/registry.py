"""Rejestr akcji: intent (np. ``app.open``) → Action."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from .app_close import AppCloseAction
from .app_open import AppOpenAction
from .base import Action, ActionContext, ActionResult
from .input_keys import InputKeysAction
from .obs import (
    ObsFilterAction,
    ObsMuteAction,
    ObsRecordAction,
    ObsReplayAction,
    ObsSceneAction,
    ObsSourceToggleAction,
)
from .system_volume import SystemVolumeAction
from .window_focus import WindowFocusAction

log = logging.getLogger(__name__)


class Registry:
    """Mapa intent → akcja. Nieznany intent = czytelny błąd, nie wyjątek."""

    def __init__(self) -> None:
        self._by_intent: dict[str, Action] = {}
        self._order: list[Action] = []

    def register(self, action: Action) -> None:
        if action.intent in self._by_intent:
            raise ValueError(f"duplikat intentu {action.intent!r}")
        self._by_intent[action.intent] = action
        self._order.append(action)

    def get(self, intent: str) -> Action | None:
        return self._by_intent.get(intent)

    def all(self) -> list[Action]:
        return list(self._order)

    def available_intents(self, ctx: ActionContext | None = None) -> list[str]:
        return [a.intent for a in self._order if a.available(ctx)]

    def execute(self, intent: str, slots: Mapping[str, Any], ctx: ActionContext) -> ActionResult:
        action = self.get(intent)
        if action is None:
            return ActionResult(
                False,
                error=f"unknown_intent:{intent}",
                message=f"brak akcji dla intentu {intent!r}",
            )
        try:
            return action.execute(slots or {}, ctx)
        except Exception as exc:  # akcje nie mogą zabić pętli
            log.exception("akcja %s rzuciła wyjątek", intent)
            return ActionResult(
                False,
                error=f"action_crash:{type(exc).__name__}:{exc}",
                message="akcja zakończona nieoczekiwanym wyjątkiem",
            )


def build_default_registry() -> Registry:
    """Wbudowane akcje MVP."""
    registry = Registry()
    for action in (
        AppOpenAction(),
        AppCloseAction(),
        InputKeysAction(),
        SystemVolumeAction(),
        ObsSceneAction(),
        ObsMuteAction(),
        ObsRecordAction(),
        ObsReplayAction(),
        ObsFilterAction(),
        ObsSourceToggleAction(),
        WindowFocusAction(),
    ):
        registry.register(action)
    return registry
