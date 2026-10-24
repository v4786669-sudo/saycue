"""Akcje OS/OBS — wspólny kontrakt `Action` i implementacje MVP.

    class Action(Protocol):
        id: str
        def execute(self, slots: dict, ctx: ActionContext) -> ActionResult: ...
        def available(self, ctx=None) -> bool: ...

Intencje: app.open, app.close, input.keys, system.volume, window.focus,
obs.scene (w tym __next__/__prev__), obs.mute, obs.record, obs.replay,
obs.filter, obs.source_toggle. Wszystkie akcje wspierają ``dry_run``
(planowanie bez dotykania systemu — testy bez sprzętu).
"""

from __future__ import annotations

from .app_close import AppCloseAction
from .app_open import AppOpenAction, resolve_app
from .base import Action, ActionContext, ActionResult
from .input_keys import InputKeysAction, normalize_keys
from .obs import (
    OBS_REQUIREMENTS,
    ObsClient,
    ObsError,
    ObsFilterAction,
    ObsMuteAction,
    ObsRecordAction,
    ObsReplayAction,
    ObsSceneAction,
    ObsSourceToggleAction,
)
from .registry import Registry, build_default_registry
from .system_volume import SystemVolumeAction
from .window_focus import WindowFocusAction

__all__ = [
    "Action",
    "ActionContext",
    "ActionResult",
    "AppCloseAction",
    "AppOpenAction",
    "InputKeysAction",
    "OBS_REQUIREMENTS",
    "ObsClient",
    "ObsError",
    "ObsFilterAction",
    "ObsMuteAction",
    "ObsRecordAction",
    "ObsReplayAction",
    "ObsSceneAction",
    "ObsSourceToggleAction",
    "Registry",
    "SystemVolumeAction",
    "WindowFocusAction",
    "build_default_registry",
    "normalize_keys",
    "resolve_app",
]
