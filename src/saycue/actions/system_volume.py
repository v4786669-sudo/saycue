"""Akcja `system.volume` — głośność: pycaw (Windows) / pactl (Linux).

Sloty (rdzeń i presety): ``direction: up|down|mute|unmute|toggle`` +
``step`` (procent) albo ``delta`` (ze znakiem; format W1 data/commands.yaml).
"""

from __future__ import annotations

import importlib.util
import logging
import shutil
import subprocess
import time
from collections.abc import Mapping
from typing import Any

from .base import Action, ActionContext, ActionResult

log = logging.getLogger(__name__)

_DIRECTIONS = {"up", "down", "mute", "unmute", "toggle"}
DEFAULT_STEP = 10


class SystemVolumeAction(Action):
    id = "system_volume"
    intent = "system.volume"
    description = "Głośność systemowa (ciszej/głośniej/wycisz): pycaw / pactl."

    def execute(self, slots: Mapping[str, Any], ctx: ActionContext) -> ActionResult:
        t0 = time.monotonic()
        slots = dict(slots or {})
        direction, step = self._resolve_args(slots)
        if direction is None:
            return ActionResult(
                False,
                error=f"invalid_slot:direction:{slots.get('direction')!r}",
                message=f"kierunek {slots.get('direction')!r} nieobsługiwany (up/down/mute/unmute/toggle)",
            )
        latency = (time.monotonic() - t0) * 1000
        if ctx.dry_run:
            plan: dict[str, Any]
            if ctx.platform == "win32":
                plan = {"backend": "pycaw", "direction": direction, "step": step}
            else:
                plan = {"backend": "pactl", "cmd": self._pactl_cmd(direction, step)}
            return ActionResult(
                True,
                message=f"[dry-run] volume {direction} ({step}%)",
                details=plan,
                latency_ms=latency,
            )
        if ctx.platform == "win32":
            return self._execute_win(direction, step)
        if ctx.platform.startswith("linux"):
            return self._execute_linux(direction, step)
        return ActionResult(
            False,
            error=f"unsupported_platform:{ctx.platform}",
            message="system.volume działa na Windows i Linux (pactl)",
        )

    def _resolve_args(self, slots: Mapping[str, Any]) -> tuple[str | None, int]:
        direction = str(slots.get("direction") or "").strip().lower()
        try:
            step = int(float(slots.get("step", slots.get("delta", DEFAULT_STEP))))
        except (TypeError, ValueError):
            step = DEFAULT_STEP
        if not direction:
            if "delta" in slots:
                direction = "up" if step >= 0 else "down"
                step = abs(step)
            else:
                direction = "up"
        if direction not in _DIRECTIONS:
            return None, step
        return direction, max(1, step)

    def _pactl_cmd(self, direction: str, step: int) -> list[str]:
        if direction == "up":
            return ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"+{step}%"]
        if direction == "down":
            return ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"-{step}%"]
        if direction == "mute":
            return ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1"]
        if direction == "unmute":
            return ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"]
        return ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"]

    def _execute_linux(self, direction: str, step: int) -> ActionResult:
        cmd = self._pactl_cmd(direction, step)
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=5)
        except FileNotFoundError:
            return ActionResult(
                False, error="missing_dependency:pactl", message="brak pactl (pulseaudio/pipewire)"
            )
        except subprocess.TimeoutExpired:
            return ActionResult(False, error="pactl_timeout", message="pactl zawiesił się")
        if proc.returncode != 0:
            return ActionResult(
                False,
                error=f"pactl_exit:{proc.returncode}",
                message=proc.stderr.decode(errors="replace")[:200] or "pactl zwrócił błąd",
            )
        return ActionResult(True, message=f"głośność: {direction} ({step}%)")

    def _execute_win(self, direction: str, step: int) -> ActionResult:
        try:
            from ctypes import POINTER, cast

            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        except ImportError as exc:
            return ActionResult(
                False,
                error=f"missing_dependency:{exc.name if hasattr(exc, 'name') else 'pycaw'}",
                message="brak pycaw/comtypes (pip install pycaw)",
            )
        try:
            device = AudioUtilities.GetSpeakers()
            interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            if direction == "up":
                current = volume.GetMasterVolumeLevelScalar()
                volume.SetMasterVolumeLevelScalar(min(1.0, current + step / 100.0), None)
            elif direction == "down":
                current = volume.GetMasterVolumeLevelScalar()
                volume.SetMasterVolumeLevelScalar(max(0.0, current - step / 100.0), None)
            elif direction == "mute":
                volume.SetMute(True, None)
            elif direction == "unmute":
                volume.SetMute(False, None)
            else:
                volume.SetMute(not bool(volume.GetMute()), None)
            return ActionResult(True, message=f"głośność: {direction} ({step}%)")
        except Exception as exc:
            return ActionResult(
                False,
                error=f"pycaw_failed:{type(exc).__name__}:{exc}",
                message=f"nie udało się ustawić głośności: {exc}",
            )

    def available(self, ctx: ActionContext | None = None) -> bool:
        if ctx is None:
            return False
        if ctx.platform == "win32":
            return importlib.util.find_spec("pycaw") is not None
        if ctx.platform.startswith("linux"):
            return shutil.which("pactl") is not None
        return False

    def availability_reason(self, ctx: ActionContext | None = None) -> str:
        if self.available(ctx):
            return ""
        if ctx and ctx.platform == "win32":
            return "brak pycaw (pip install pycaw)"
        if ctx and ctx.platform.startswith("linux"):
            return "brak pactl (pulseaudio/pipewire-pulse)"
        return "system.volume wspierany na Windows i Linux"
