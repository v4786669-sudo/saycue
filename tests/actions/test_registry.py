"""Testy rejestru akcji (kontrakt §3.3)."""

from __future__ import annotations

import pytest

from saycue.actions import (
    ActionContext,
    build_default_registry,
)

ALL_INTENTS = {
    "app.open",
    "app.close",
    "input.keys",
    "system.volume",
    "window.focus",
    "obs.scene",
    "obs.mute",
    "obs.record",
    "obs.replay",
    "obs.filter",
    "obs.source_toggle",
}


def test_builtin_intents():
    registry = build_default_registry()
    assert {a.intent for a in registry.all()} == ALL_INTENTS


def test_get_and_unknown_intent():
    registry = build_default_registry()
    assert registry.get("app.open") is not None
    assert registry.get("nie.istnieje") is None
    result = registry.execute("nie.istnieje", {}, ActionContext(dry_run=True))
    assert result.ok is False
    assert result.error.startswith("unknown_intent:")


def test_duplicate_intent_rejected():
    registry = build_default_registry()
    from saycue.actions import AppOpenAction

    with pytest.raises(ValueError):
        registry.register(AppOpenAction())


def test_available_intents_without_obs():
    registry = build_default_registry()
    ctx = ActionContext()
    intents = registry.available_intents(ctx)
    assert "obs.scene" not in intents
    assert "app.open" in intents


def test_obs_intents_available_with_connected_client(intent_parser):
    from saycue.actions import ObsClient

    registry = build_default_registry()
    client = ObsClient.__new__(ObsClient)  # nie łączymy — tylko atrapa stanu
    client._connected = True
    ctx = ActionContext(obs=client)
    intents = registry.available_intents(ctx)
    for obs_intent in ("obs.scene", "obs.mute", "obs.record", "obs.replay", "obs.source_toggle"):
        assert obs_intent in intents


def test_action_crash_is_caught():
    registry = build_default_registry()

    class _Boom:
        intent = "app.open"

        @staticmethod
        def execute(slots, ctx):
            raise RuntimeError("boom")

    registry._by_intent["app.open"] = _Boom()
    result = registry.execute("app.open", {}, ActionContext(dry_run=True))
    assert result.ok is False
    assert result.error.startswith("action_crash:RuntimeError")
