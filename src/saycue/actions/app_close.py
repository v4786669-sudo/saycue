"""Akcja `app.close` — grzeczne zamknięcie aplikacji (decyzja t13/kapitan).

Windows: WM_CLOSE przez ctypes (aplikacja może zapytać o zapis — bez taskkill).
Linux X11: xdotool search --class → wmctrl -ic (polite _NET_CLOSE_WINDOW).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from collections.abc import Mapping
from typing import Any

from .app_open import _apps_from_ctx, resolve_app
from .base import Action, ActionContext, ActionResult
from .win32 import post_close_to_processes, process_names_of

log = logging.getLogger(__name__)


class AppCloseAction(Action):
    id = "app_close"
    intent = "app.close"
    description = "Grzeczne zamknięcie aplikacji: WM_CLOSE (Windows) / wmctrl -ic (Linux)."

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
        if ctx.platform == "win32":
            names = process_names_of(
                (entry.get("win") or {}).get("exe"),
                list((entry.get("win") or {}).get("args") or []),
            )
            if not names:
                return ActionResult(
                    False,
                    error=f"unsupported_platform:{ctx.platform}",
                    message=f"brak definicji procesu dla {app_id!r}",
                )
            if ctx.dry_run:
                return ActionResult(
                    True,
                    message=f"[dry-run] WM_CLOSE → {names}",
                    details={"backend": "win32_wm_close", "processes": names, "app": app_id},
                    latency_ms=latency,
                )
            count = post_close_to_processes(names)
            if count == 0:
                return ActionResult(
                    False,
                    error="window_not_found",
                    message=f"nie znaleziono okna procesu {names} (aplikacja może nie działać)",
                )
            return ActionResult(
                True,
                message=f"wysłano WM_CLOSE ({count} okien)",
                details={"processes": names, "windows": count},
                latency_ms=(time.monotonic() - t0) * 1000,
            )
        if ctx.platform.startswith("linux"):
            pattern = app_id
            if ctx.dry_run:
                return ActionResult(
                    True,
                    message=f"[dry-run] zamykam {app_id} (class={pattern})",
                    details={"backend": "xdotool+wmctrl", "class": pattern, "app": app_id},
                    latency_ms=latency,
                )
            return self._close_linux(pattern, app_id, t0)
        return ActionResult(
            False,
            error=f"unsupported_platform:{ctx.platform}",
            message="app.close działa na Windows i Linux X11",
        )

    def _close_linux(self, pattern: str, app_id: str, t0: float) -> ActionResult:
        try:
            proc = subprocess.run(
                ["xdotool", "search", "--class", pattern],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except FileNotFoundError:
            return ActionResult(False, error="missing_dependency:xdotool", message="brak xdotool")
        except subprocess.TimeoutExpired:
            return ActionResult(False, error="xdotool_timeout", message="xdotool search zawiesił się")
        window_ids = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        if proc.returncode != 0 or not window_ids:
            return ActionResult(
                False,
                error="window_not_found",
                message=f"nie znaleziono okna klasy {pattern!r} (aplikacja może nie działać)",
            )
        for wid in window_ids:
            try:
                subprocess.run(["wmctrl", "-ic", wid], capture_output=True, timeout=5)
            except FileNotFoundError:
                return ActionResult(False, error="missing_dependency:wmctrl", message="brak wmctrl")
            except subprocess.TimeoutExpired:  # pragma: no cover
                continue
        return ActionResult(
            True,
            message=f"wysłano _NET_CLOSE_WINDOW do {len(window_ids)} okien {pattern!r}",
            details={"class": pattern, "windows": len(window_ids)},
            latency_ms=(time.monotonic() - t0) * 1000,
        )

    def available(self, ctx: ActionContext | None = None) -> bool:
        if ctx is None:
            return False
        if ctx.platform == "win32":
            return True  # ctypes ze stdlib
        if ctx.platform.startswith("linux"):
            return shutil.which("xdotool") is not None and shutil.which("wmctrl") is not None
        return False

    def availability_reason(self, ctx: ActionContext | None = None) -> str:
        if self.available(ctx):
            return ""
        if ctx and ctx.platform.startswith("linux"):
            return "brak xdotool lub wmctrl (Linux X11)"
        return "app.close wspierany na Windows i Linux X11"
