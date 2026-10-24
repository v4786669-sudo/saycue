"""UI — PySide6: MainWindow (5 widoków §3.5), tray, onboarding, autostart .

Wątki: Qt w głównym wątku; orchestrator w wątku roboczym; komunikacja przez
sygnały — żadnego Qt w wątkach audio)."""

from __future__ import annotations

import logging
import signal
import sys
from pathlib import Path

from ..config.paths import config_dir
from ..config.settings import Settings

log = logging.getLogger(__name__)


def run_gui(
    settings: Settings | None = None,
    *,
    no_tray: bool = False,
    offscreen: bool = False,
) -> int:
    """Uruchamia aplikację Qt. Zwraca kod wyjścia."""
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("PySide6 nie zainstalowany (uv pip install -e '.[ui]').", file=sys.stderr)
        return 2

    if offscreen:
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    app = QApplication(sys.argv)
    app.setApplicationName("SayCue")

    settings = settings or Settings.load()

    from ..telemetry import Telemetry

    telemetry = Telemetry(settings)

    from .main_window import MainWindow

    window = MainWindow(settings, telemetry)
    window.show()

    tray_icon = None
    if not no_tray:
        from .tray import create_tray

        tray_icon = create_tray(window, settings)

    # Ctrl+C w konsoli → czyste zamknięcie (też pod offscreen w testach)
    signal.signal(signal.SIGINT, lambda *_: app.quit())

    code = app.exec()
    if tray_icon is not None:
        try:
            tray_icon.stop()
        except Exception:
            pass
    telemetry.close()
    settings.save(Path(config_dir() / "config.yaml"))
    return code


def autostart_install() -> Path:
    """Autostart Linux: ~/.config/autostart/saycue.desktop (Windows: rejestr — installer)."""
    import sys as _sys

    content = f"""[Desktop Entry]
Type=Application
Name=SayCue
Comment=Offline'owy asystent głosowy dla streamerów
Exec={_sys.executable} -m saycue gui --no-tray
X-GNOME-Autostart-enabled=true
"""
    path = Path.home() / ".config" / "autostart" / "saycue.desktop"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def autostart_remove() -> None:
    Path.home().joinpath(".config", "autostart", "saycue.desktop").unlink(missing_ok=True)


def autostart_enabled() -> bool:
    return (Path.home() / ".config" / "autostart" / "saycue.desktop").is_file()
