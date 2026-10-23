"""Testy `input.keys`: planowanie (dry-run) i normalizacja klawiszy."""

from __future__ import annotations

import shutil

from saycue.actions import ActionContext, InputKeysAction, normalize_keys


def test_normalize_keys():
    assert normalize_keys(["shift", "space"]) == ["shift", "space"]
    assert normalize_keys("shift+space") == ["shift", "space"]
    assert normalize_keys("ctrl+c") == ["ctrl", "c"]
    assert normalize_keys(["spacja"]) == ["space"]
    assert normalize_keys(None) == []
    assert normalize_keys("Shift+SPACE") == ["shift", "space"]


def test_linux_dry_run_plan():
    ctx = ActionContext(platform="linux", dry_run=True)
    r = InputKeysAction().execute({"keys": ["shift", "space"]}, ctx)
    assert r.ok is True
    assert r.details["backend"] == "xdotool"
    assert r.details["cmd"] == ["xdotool", "key", "--clearmodifiers", "shift+space"]


def test_win32_dry_run_plan():
    ctx = ActionContext(platform="win32", dry_run=True)
    r = InputKeysAction().execute({"keys": ["shift", "space"]}, ctx)
    assert r.ok is True
    assert r.details["backend"] == "pydirectinput"
    assert r.details["keys"] == ["shift", "space"]


def test_missing_keys_slot():
    ctx = ActionContext(platform="linux", dry_run=True)
    r = InputKeysAction().execute({}, ctx)
    assert r.ok is False and r.error == "missing_slot:keys"


def test_unsupported_platform():
    ctx = ActionContext(platform="darwin", dry_run=True)
    r = InputKeysAction().execute({"keys": ["a"]}, ctx)
    assert r.ok is False and r.error.startswith("unsupported_platform:")


def test_available_reflects_xdotool():
    action = InputKeysAction()
    ctx = ActionContext(platform="linux")
    assert action.available(ctx) is (shutil.which("xdotool") is not None)
    if shutil.which("xdotool") is None:
        assert "xdotool" in action.availability_reason(ctx)
    assert action.available(ActionContext(platform="darwin")) is False
