"""Testy `app.open`: planowanie (dry-run) — bez uruchamiania aplikacji."""

from __future__ import annotations

import pytest

from saycue.actions import ActionContext, AppOpenAction, resolve_app


@pytest.fixture(scope="module")
def action() -> AppOpenAction:
    return AppOpenAction()


def _run(action, target, merged_apps, platform="linux"):
    ctx = ActionContext(platform=platform, dry_run=True, apps=merged_apps)
    return action.execute({"target": target}, ctx)


def test_linux_desktop_id(action, merged_apps):
    r = _run(action, "blender", merged_apps)
    assert r.ok and r.details["cmd"] == ["gio", "launch", "blender.desktop"]
    r = _run(action, "spotify", merged_apps)  # preset apps-open
    assert r.ok and r.details["cmd"] == ["gio", "launch", "spotify.desktop"]
    r = _run(action, "notepad", merged_apps)
    assert r.ok and r.details["cmd"] == ["gio", "launch", "org.gnome.TextEditor.desktop"]


def test_linux_desktop_id_without_suffix(action, merged_apps):
    apps = dict(merged_apps)
    apps["xyz"] = {
        "label": "Xyz",
        "aliases": [],
        "win": {"exe": None, "args": [], "app_id": None},
        "linux": {"desktop_id": "xyz", "cmd": None},
        "url": None,
    }
    r = _run(action, "xyz", apps)
    assert r.ok and r.details["cmd"] == ["gio", "launch", "xyz.desktop"]


def test_win32_exe_and_args(action, merged_apps):
    r = _run(action, "spotify", merged_apps, platform="win32")
    assert r.ok and r.details["cmd"] == ["Spotify.exe"]
    # preset discord: "Update.exe --processStart Discord.exe"
    r = _run(action, "discord", merged_apps, platform="win32")
    assert r.ok and r.details["cmd"] == ["Update.exe", "--processStart", "Discord.exe"]


def test_win32_app_id_shell(action, merged_apps):
    apps = dict(merged_apps)
    apps["mail"] = {
        "label": "Poczta",
        "aliases": [],
        "win": {"exe": None, "args": [], "app_id": "Microsoft.Outlook_8wekyb3d8bbwe"},
        "linux": {"desktop_id": None, "cmd": None},
        "url": None,
    }
    r = _run(action, "mail", apps, platform="win32")
    assert r.ok
    assert r.details["cmd"] == ["explorer", "shell:AppsFolder\\Microsoft.Outlook_8wekyb3d8bbwe"]


def test_url_entry(action, merged_apps):
    r = _run(action, "chatgpt", merged_apps)
    assert r.ok and r.details["url"] == "https://chat.openai.com"


def test_alias_and_fuzzy_resolution(action, merged_apps):
    assert resolve_app(merged_apps, "spoti")[0] == "spotify"
    assert resolve_app(merged_apps, "obs studio")[0] == "obs"
    assert resolve_app(merged_apps, "przeglądarka")[0] == "browser"
    assert resolve_app(merged_apps, "spotifaj")[0] == "spotify"  # fuzzy ≥ 0.78
    assert resolve_app(merged_apps, "dc")[0] == "discord"  # alias z rdzenia


def test_unknown_and_missing_target(action, merged_apps):
    r = _run(action, "nieistniejaca aplikacja", merged_apps)
    assert r.ok is False and r.error.startswith("unknown_app:")
    ctx = ActionContext(platform="linux", dry_run=True, apps=merged_apps)
    r = action.execute({}, ctx)
    assert r.ok is False and r.error == "missing_slot:target"


def test_data_dir_fallback(data_dir):
    ctx = ActionContext(platform="linux", dry_run=True, apps=None, data_dir=data_dir)
    r = AppOpenAction().execute({"target": "kalkulator"}, ctx)
    assert r.ok and r.details["cmd"] == ["gio", "launch", "org.gnome.Calculator.desktop"]
