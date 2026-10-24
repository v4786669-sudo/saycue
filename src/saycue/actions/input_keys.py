"""Akcja `input.keys` — klawisze/hotkeye: pydirectinput (Windows) / xdotool (Linux X11).

Architektura §3.3: gry często blokują SendInput — na Linuksie Wayland brak
wsparcia XTest (dokumentujemy w faq). Combo = przytrzymanie wszystkich klawiszy
i zwolnienie w odwrotnej kolejności.
"""

from __future__ import annotations

import importlib.util
import logging
import shutil
import subprocess
import time
from collections.abc import Mapping, Sequence
from typing import Any

from .base import Action, ActionContext, ActionResult

log = logging.getLogger(__name__)

_KEY_ALIASES = {"spacja": "space", "control": "ctrl", "myslnik": "minus"}


def normalize_keys(keys: str | Sequence[str] | None) -> list[str]:
    """slot keys → lista nazw klawiszy (akceptuje listę i "shift+space")."""
    if isinstance(keys, str):
        raw: list[str] = [keys]
    else:
        raw = [str(k) for k in (keys or [])]
    out: list[str] = []
    for part in raw:
        for token in part.split("+"):
            token = token.strip().lower()
            if token:
                out.append(_KEY_ALIASES.get(token, token))
    return out


class InputKeysAction(Action):
    id = "input_keys"
    intent = "input.keys"
    description = "Wciśnij klawisze/hotkey (gry: pydirectinput; Linux X11: xdotool)."

    def execute(self, slots: Mapping[str, Any], ctx: ActionContext) -> ActionResult:
        t0 = time.monotonic()
        keys = normalize_keys((slots or {}).get("keys"))
        if not keys:
            return ActionResult(False, error="missing_slot:keys", message="brak slotu keys")
        if ctx.platform != "win32" and not ctx.platform.startswith("linux"):
            return ActionResult(
                False,
                error=f"unsupported_platform:{ctx.platform}",
                message="input.keys działa na Windows i Linux X11",
            )
        latency = (time.monotonic() - t0) * 1000
        if ctx.dry_run:
            plan: dict[str, Any] = {"keys": keys}
            if ctx.platform == "win32":
                plan["backend"] = "pydirectinput"
            else:
                plan["backend"] = "xdotool"
                plan["cmd"] = ["xdotool", "key", "--clearmodifiers", "+".join(keys)]
            return ActionResult(
                True,
                message=f"[dry-run] klawisze {'+'.join(keys)}",
                details=plan,
                latency_ms=latency,
            )
        if ctx.platform == "win32":
            return self._execute_win(keys)
        if ctx.platform.startswith("linux"):
            return self._execute_linux(keys)
        return ActionResult(
            False,
            error=f"unsupported_platform:{ctx.platform}",
            message="input.keys działa na Windows i Linux X11",
        )

    def _execute_win(self, keys: list[str]) -> ActionResult:
        try:
            import pydirectinput
        except ImportError:
            return ActionResult(
                False,
                error="missing_dependency:pydirectinput",
                message="brak pydirectinput (pip install pydirectinput)",
            )
        try:
            if len(keys) == 1:
                pydirectinput.press(keys[0])
            else:
                for key in keys:
                    pydirectinput.keyDown(key)
                for key in reversed(keys):
                    pydirectinput.keyUp(key)
            return ActionResult(True, message=f"wciśnięto {'+'.join(keys)}")
        except Exception as exc:  # gry potrafią blokować SendInput
            return ActionResult(
                False,
                error=f"keys_failed:{type(exc).__name__}:{exc}",
                message=f"wciśnięcie {'+'.join(keys)} nie powiodło się: {exc}",
            )

    def _execute_linux(self, keys: list[str]) -> ActionResult:
        cmd = ["xdotool", "key", "--clearmodifiers", "+".join(keys)]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=5)
        except FileNotFoundError:
            return ActionResult(False, error="missing_dependency:xdotool", message="brak xdotool")
        except subprocess.TimeoutExpired:
            return ActionResult(False, error="xdotool_timeout", message="xdotool zawiesił się")
        if proc.returncode != 0:
            return ActionResult(
                False,
                error=f"xdotool_exit:{proc.returncode}",
                message=proc.stderr.decode(errors="replace")[:200] or "xdotool zwrócił błąd",
            )
        return ActionResult(True, message=f"wciśnięto {'+'.join(keys)}")

    def available(self, ctx: ActionContext | None = None) -> bool:
        if ctx is None:
            return False
        if ctx.platform == "win32":
            return importlib.util.find_spec("pydirectinput") is not None
        if ctx.platform.startswith("linux"):
            return shutil.which("xdotool") is not None
        return False

    def availability_reason(self, ctx: ActionContext | None = None) -> str:
        if self.available(ctx):
            return ""
        if ctx and ctx.platform == "win32":
            return "brak pydirectinput (pip install pydirectinput)"
        if ctx and ctx.platform.startswith("linux"):
            return "brak xdotool (Wayland bez XTest)"
        return "input.keys wspierany na Windows i Linux X11"
