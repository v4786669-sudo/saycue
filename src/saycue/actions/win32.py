"""Pomocnicze funkcje Win32 przez ctypes (bez pywin32): WM_CLOSE, focus okna.

Używane przez ``app.close`` (grzeczne zamknięcie — WM_CLOSE, aplikacja może
zapytać o zapis stanu; NIE taskkill/kill) i ``window.focus``. Importowalne na
każdej platformie; na nie-Windows funkcje zwracają 0 (testy planują w dry-run).
"""

from __future__ import annotations

import ctypes
from collections.abc import Callable
from ctypes import wintypes

WM_CLOSE = 0x0010
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SW_RESTORE = 9


def is_windows() -> bool:
    return hasattr(ctypes, "windll")


def process_names_of(exe: str | None, args: list[str]) -> list[str]:
    """Nazwy procesów (małymi literami) do dopasowania okien.

    Obsługuje ``Spotify.exe`` oraz ``Update.exe --processStart Discord.exe`` —
    brane są basename exe i wszystkie tokeny args z rozszerzeniem .exe.
    """
    names: list[str] = []
    for token in [exe or "", *(args or [])]:
        base = str(token).replace("\\", "/").rsplit("/", 1)[-1].lower()
        if base.endswith(".exe") and base not in names:
            names.append(base)
    return names


def _process_name(pid: int) -> str | None:
    if not is_windows():
        return None
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(4096)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value.replace("\\", "/").rsplit("/", 1)[-1].lower()
        return None
    finally:
        kernel32.CloseHandle(handle)


def _enum_windows(exe_names: list[str], action: Callable[[int], None]) -> int:
    """Wywołuje ``action(hwnd)`` dla widocznych okien procesów z listy; zwraca liczbę."""
    if not is_windows():
        return 0
    user32 = ctypes.windll.user32
    wanted = set(exe_names)
    found: list[int] = []
    enumproc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _cb(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if _process_name(pid.value) in wanted:
            found.append(hwnd)
        return True

    user32.EnumWindows(enumproc(_cb), 0)
    for hwnd in found:
        try:
            action(hwnd)
        except Exception:  # pragma: no cover
            continue
    return len(found)


def post_close_to_processes(exe_names: list[str]) -> int:
    """Grzeczne WM_CLOSE do okien procesów; zwraca liczbę trafionych okien."""
    if not is_windows():
        return 0
    user32 = ctypes.windll.user32
    return _enum_windows(exe_names, lambda hwnd: user32.PostMessageW(hwnd, WM_CLOSE, 0, 0))


def focus_process_window(exe_names: list[str]) -> int:
    """Przywraca i fokusuje okna procesów; zwraca liczbę trafionych okien."""
    if not is_windows():
        return 0
    user32 = ctypes.windll.user32

    def _focus(hwnd: int) -> None:
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)

    return _enum_windows(exe_names, _focus)
