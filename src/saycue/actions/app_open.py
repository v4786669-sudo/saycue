"""Akcja `app.open` — uruchamianie aplikacji (Windows Popen / Linux gio launch).

Mapowanie nazw: zunifikowane wpisy aplikacji z ``parser/rules.py``
(rdzeń data/apps.yaml + presety apps[]). URL otwierany w przeglądarce.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..parser.fuzzy import ratio as _fuzzy_ratio
from ..parser.normalize import normalize_text
from .base import Action, ActionContext, ActionResult

log = logging.getLogger(__name__)


def resolve_app(
    apps: Mapping[str, Any], target: str, *, threshold: float = 0.78
) -> tuple[str, Mapping[str, Any]] | None:
    """target (PL/EN, może z przekręceniem) → (id, wpis aplikacji)."""
    if not target:
        return None
    norm_target = normalize_text(target)
    best: tuple[str, Mapping[str, Any]] | None = None
    best_score = -1.0
    for app_id, entry in (apps or {}).items():
        keys = [normalize_text(str(app_id))]
        keys += [normalize_text(str(a)) for a in (entry.get("aliases") or [])]
        for key in keys:
            if key == norm_target:
                return (str(app_id), entry)
            score = _fuzzy_ratio(norm_target, key)
            if score > best_score:
                best_score, best = score, (str(app_id), entry)
    if best_score >= threshold:
        return best
    return None


def _apps_from_ctx(ctx: ActionContext) -> Mapping[str, Any]:
    apps: Mapping[str, Any] = dict(ctx.apps or {})
    if not apps and ctx.data_dir is not None:
        try:
            from ..parser.rules import load_apps

            path = Path(ctx.data_dir) / "apps.yaml"
            if path.is_file():
                apps = load_apps(path)
        except Exception:  # pragma: no cover
            log.exception("nie udało się załadować apps.yaml z data_dir")
    return apps


class AppOpenAction(Action):
    id = "app_open"
    intent = "app.open"
    description = "Uruchom aplikację: Windows Popen / Linux gio launch; URL w przeglądarce."

    def execute(self, slots: Mapping[str, Any], ctx: ActionContext) -> ActionResult:
        t0 = time.monotonic()
        target = str((slots or {}).get("target") or "").strip()
        if not target:
            return ActionResult(False, error="missing_slot:target", message="brak slotu target")
        resolved = resolve_app(_apps_from_ctx(ctx), target)
        if resolved is None:
            return ActionResult(
                False,
                error=f"unknown_app:{target}",
                message=f"brak aplikacji {target!r} w apps.yaml/presetach",
            )
        app_id, entry = resolved
        latency = (time.monotonic() - t0) * 1000
        if entry.get("url"):
            url = str(entry["url"])
            if ctx.dry_run:
                return ActionResult(
                    True,
                    message=f"[dry-run] otwieram {app_id} (URL {url})",
                    details={"url": url, "app": app_id},
                    latency_ms=latency,
                )
            try:
                self._open_url(url, ctx.platform)
                return ActionResult(
                    True,
                    message=f"otwarto {app_id} (URL)",
                    details={"url": url},
                    latency_ms=(time.monotonic() - t0) * 1000,
                )
            except OSError as exc:
                return ActionResult(
                    False,
                    error=f"launch_failed:{exc}",
                    message=f"nie udało się otworzyć URL {url}: {exc}",
                )
        cmd = self._build_command(entry, ctx.platform)
        if cmd is None:
            return ActionResult(
                False,
                error=f"unsupported_platform:{ctx.platform}",
                message=f"brak sposobu uruchomienia {app_id!r} na {ctx.platform}",
            )
        if ctx.dry_run:
            return ActionResult(
                True,
                message=f"[dry-run] uruchamiam {app_id}: {' '.join(cmd)}",
                details={"cmd": cmd, "app": app_id},
                latency_ms=latency,
            )
        try:
            kwargs: dict[str, Any] = {}
            if ctx.platform == "win32" and hasattr(subprocess, "DETACHED_PROCESS"):
                kwargs["creationflags"] = subprocess.DETACHED_PROCESS
            else:
                kwargs["start_new_session"] = True
            subprocess.Popen(cmd, **kwargs)
            return ActionResult(
                True,
                message=f"uruchomiono {app_id}",
                details={"cmd": cmd, "app": app_id},
                latency_ms=(time.monotonic() - t0) * 1000,
            )
        except OSError as exc:
            return ActionResult(
                False,
                error=f"launch_failed:{exc}",
                message=f"nie udało się uruchomić {app_id}: {exc}",
            )

    def _build_command(self, entry: Mapping[str, Any], platform: str) -> list[str] | None:
        if platform == "win32":
            win = dict(entry.get("win") or {})
            if win.get("app_id"):
                return ["explorer", f"shell:AppsFolder\\{win['app_id']}"]
            if win.get("exe"):
                return [str(win["exe"]), *[str(a) for a in (win.get("args") or [])]]
            return None
        if platform.startswith("linux"):
            linux = dict(entry.get("linux") or {})
            desktop = linux.get("desktop_id")
            if desktop:
                desktop = str(desktop)
                if not desktop.endswith(".desktop"):
                    desktop += ".desktop"
                return ["gio", "launch", desktop]
            cmd = linux.get("cmd")
            if cmd:
                return [str(c) for c in cmd]
        return None

    @staticmethod
    def _open_url(url: str, platform: str) -> None:
        if platform == "win32":
            os.startfile(url)  # noqa: S606 - lokalna akcja użytkownika
        else:
            subprocess.Popen(["gio", "open", url], start_new_session=True)
