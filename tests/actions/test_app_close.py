"""Testy `app.close` (decyzja t13/kapitan: grzeczne WM_CLOSE, nie kill)."""

from __future__ import annotations

import shutil

import pytest

from saycue.actions import ActionContext, AppCloseAction


@pytest.fixture(scope="module")
def action() -> AppCloseAction:
    return AppCloseAction()


def test_win32_wm_close_plan(action, merged_apps):
    ctx = ActionContext(platform="win32", dry_run=True, apps=merged_apps)
    r = action.execute({"target": "discord"}, ctx)
    assert r.ok is True
    assert r.details["backend"] == "win32_wm_close"
    # "Update.exe --processStart Discord.exe" → oba procesy kandydatami
    assert r.details["processes"] == ["update.exe", "discord.exe"]


def test_win32_simple_exe(action, merged_apps):
    ctx = ActionContext(platform="win32", dry_run=True, apps=merged_apps)
    r = action.execute({"target": "spotify"}, ctx)
    assert r.ok is True
    assert r.details["processes"] == ["spotify.exe"]


def test_linux_plan_uses_class_and_wmctrl(action, merged_apps):
    ctx = ActionContext(platform="linux", dry_run=True, apps=merged_apps)
    r = action.execute({"target": "obs"}, ctx)
    assert r.ok is True
    assert r.details["backend"] == "xdotool+wmctrl"
    assert r.details["class"] == "obs"


def test_missing_and_unknown_target(action, merged_apps):
    ctx = ActionContext(platform="linux", dry_run=True, apps=merged_apps)
    r = action.execute({}, ctx)
    assert r.ok is False and r.error == "missing_slot:target"
    r = action.execute({"target": "nie-ma-takiej"}, ctx)
    assert r.ok is False and r.error.startswith("unknown_app:")


def test_available_reflects_tools(action):
    linux_ctx = ActionContext(platform="linux")
    expected = shutil.which("xdotool") is not None and shutil.which("wmctrl") is not None
    assert action.available(linux_ctx) is expected
    if not expected:
        assert action.availability_reason(linux_ctx)
    assert action.available(ActionContext(platform="win32")) is True
    assert action.available(ActionContext(platform="darwin")) is False
