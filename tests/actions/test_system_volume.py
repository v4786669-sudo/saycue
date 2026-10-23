"""Testy `system.volume`: planowanie pactl/pycaw (dry-run) i sloty delta/direction."""

from __future__ import annotations

import shutil

from saycue.actions import ActionContext, SystemVolumeAction


def test_linux_up_and_down_plan():
    ctx = ActionContext(platform="linux", dry_run=True)
    action = SystemVolumeAction()
    r = action.execute({"direction": "up"}, ctx)
    assert r.ok and r.details["cmd"] == ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+10%"]
    r = action.execute({"direction": "down", "step": 20}, ctx)
    assert r.ok and r.details["cmd"] == ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-20%"]


def test_linux_mute_plan():
    ctx = ActionContext(platform="linux", dry_run=True)
    action = SystemVolumeAction()
    assert action.execute({"direction": "mute"}, ctx).details["cmd"] == [
        "pactl",
        "set-sink-mute",
        "@DEFAULT_SINK@",
        "1",
    ]
    assert action.execute({"direction": "unmute"}, ctx).details["cmd"] == [
        "pactl",
        "set-sink-mute",
        "@DEFAULT_SINK@",
        "0",
    ]
    assert action.execute({"direction": "toggle"}, ctx).details["cmd"] == [
        "pactl",
        "set-sink-mute",
        "@DEFAULT_SINK@",
        "toggle",
    ]


def test_delta_slot_w1_format():
    ctx = ActionContext(platform="linux", dry_run=True)
    action = SystemVolumeAction()
    r = action.execute({"delta": -20}, ctx)  # format W1 data/commands.yaml
    assert r.ok and r.details["cmd"] == ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-20%"]
    r = action.execute({"delta": 20}, ctx)
    assert r.ok and r.details["cmd"] == ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+20%"]


def test_win32_dry_run_plan():
    ctx = ActionContext(platform="win32", dry_run=True)
    r = SystemVolumeAction().execute({"direction": "up", "step": 5}, ctx)
    assert r.ok is True
    assert r.details == {"backend": "pycaw", "direction": "up", "step": 5}


def test_invalid_direction():
    ctx = ActionContext(platform="linux", dry_run=True)
    r = SystemVolumeAction().execute({"direction": "sideways"}, ctx)
    assert r.ok is False and r.error.startswith("invalid_slot:direction")


def test_available_reflects_pactl():
    action = SystemVolumeAction()
    ctx = ActionContext(platform="linux")
    assert action.available(ctx) is (shutil.which("pactl") is not None)
    if shutil.which("pactl") is None:
        assert "pactl" in action.availability_reason(ctx)
    assert action.available(ActionContext(platform="darwin")) is False
