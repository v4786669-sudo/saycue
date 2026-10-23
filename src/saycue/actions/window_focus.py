"""Akcja `window.focus` — przełączenie na okno aplikacji (best effort, §3.3).

Windows: SetForegroundWindow przez ctypes (współdzielone z app.close).
Linux X11: xdotool search --class → windowactivate.
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
from .win32 import focus_process_window, process_names_of

log = logging.getLogger(__name__)


class WindowFocusAction(Action):
    id = "window_focus"
    intent = "window.focus"
    description = "Przełącz na okno aplikacji: SetForegroundWindow / xdotool windowactivate."

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
            if ctx.dry_run:
                return ActionResult(
                    True,
                    message=f"[dry-run] focus → {names}",
                    details={"backend": "win32_set_foreground", "processes": names},
                    latency_ms=latency,
                )
            count = focus_process_window(names) if names else 0
            if count == 0:
                return ActionResult(False, error="window_not_found", message=f"brak okna procesu {names}")
            return ActionResult(
                True,
                message=f"fokus na {app_id}",
                details={"windows": count},
                latency_ms=(time.monotonic() - t0) * 1000,
            )
        if ctx.platform.startswith("linux"):
            if ctx.dry_run:
                return ActionResult(
                    True,
                    message=f"[dry-run] focus {app_id} (class={app_id})",
                    details={"backend": "xdotool", "class": app_id},
                    latency_ms=latency,
                )
            try:
                proc = subprocess.run(
                    ["xdotool", "search", "--class", app_id],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            except FileNotFoundError:
                return ActionResult(False, error="missing_dependency:xdotool", message="brak xdotool")
            except subprocess.TimeoutExpired:
                return ActionResult(False, error="xdotool_timeout", message="xdotool zawiesił się")
            window_ids = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            if not window_ids:
                return ActionResult(False, error="window_not_found", message=f"brak okna klasy {app_id!r}")
            subprocess.run(
                ["xdotool", "windowactivate", "--sync", window_ids[0]],
                capture_output=True,
                timeout=5,
            )
            return ActionResult(
                True,
                message=f"fokus na {app_id}",
                details={"windows": len(window_ids)},
                latency_ms=(time.monotonic() - t0) * 1000,
            )
        return ActionResult(
            False,
            error=f"unsupported_platform:{ctx.platform}",
            message="window.focus działa na Windows i Linux X11",
        )

    def available(self, ctx: ActionContext | None = None) -> bool:
        if ctx is None:
            return False
        if ctx.platform == "win32":
            return True
        if ctx.platform.startswith("linux"):
            return shutil.which("xdotool") is not None
        return False

    def availability_reason(self, ctx: ActionContext | None = None) -> str:
        if self.available(ctx):
            return ""
        if ctx and ctx.platform.startswith("linux"):
            return "brak xdotool (Wayland bez XTest — architektura §3.3)"
        return "window.focus wspierany na Windows i Linux X11"
