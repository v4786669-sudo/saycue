"""Push-to-talk (PTT): hotkey jako fallback dla wake-worda (ryzyko R6).

Domyślny hotkey: Ctrl+Alt+Space. Przytrzymanie hotkeya =
nagrywanie; puszczenie = koniec wypowiedzi. Działa przez `pynput`
(Windows/Linux X11; na Wayland wymaga uprawnień — łapiemy błąd i logujemy).
"""

from __future__ import annotations

import logging
import threading
import time

log = logging.getLogger(__name__)

# Ctrl+Alt+Space — wszystkie trzy muszą być wciśnięte jednocześnie
_HOTKEY_KEYS = {"<ctrl>", "<alt>", "<space>"}


class PushToTalk:
    def __init__(self, hotkey: str | None = None):
        # obsługiwany jest wyłącznie domyślny układ; parametr zachowany dla W3/GUI
        self.hotkey = hotkey or "ctrl+alt+space"
        self._pressed_since: float | None = None
        self._held: set[str] = set()
        self._listener = None
        self._lock = threading.Lock()
        self.running = False

    def start(self) -> None:
        if self.running:
            return
        try:
            from pynput import keyboard
        except ImportError:
            log.warning("pynput niedostępny — PTT wyłączony.")
            return
        try:
            self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
            self._listener.start()
            self.running = True
            log.info("push-to-talk: przytrzymaj %s", self.hotkey)
        except Exception as exc:  # Wayland/brak X: PTT niedostępny
            log.warning("PTT hotkey niedostępny (%s) — zostaje tylko wake-word.", exc)

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
        self.running = False

    def _key_name(self, key) -> str:
        try:
            return f"<{key.name}>"
        except AttributeError:
            return f"<{key.char}>"

    def _on_press(self, key) -> None:
        self._held.add(self._key_name(key))
        if _HOTKEY_KEYS <= self._held:
            with self._lock:
                if self._pressed_since is None:
                    self._pressed_since = time.monotonic()

    def _on_release(self, key) -> None:
        self._held.discard(self._key_name(key))
        with self._lock:
            self._pressed_since = None

    @property
    def is_pressed(self) -> bool:
        with self._lock:
            return self._pressed_since is not None

    @property
    def press_duration(self) -> float:
        with self._lock:
            if self._pressed_since is None:
                return 0.0
            return time.monotonic() - self._pressed_since
