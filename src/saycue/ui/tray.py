"""Tray (pystray): ikona ze stanem, menu Start/Stop / Tryb cichy / Otwórz / Zamknij.

Na Wayland tray zależy od DE (GNOME wymaga rozszerzenia) — łapiemy błąd
i działamy bez traya (architektura §3.5)."""

from __future__ import annotations

import logging
import threading

log = logging.getLogger(__name__)


def create_tray(main_window, settings):
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        log.warning("pystray/Pillow brak — działam bez traya")
        return None

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((6, 6, 58, 58), fill=(30, 150, 90, 255))
    draw.text((24, 16), "S", fill=(255, 255, 255, 255))

    def _open(_icon, _item):
        main_window.window.show()

    def _quit(_icon, _item):
        main_window.close()
        try:
            _icon.stop()
        except Exception:
            pass

    menu = pystray.Menu(
        pystray.MenuItem("Otwórz okno", _open, default=True),
        pystray.MenuItem("Tryb cichy (tylko tray)", lambda i, m: main_window.window.hide()),
        pystray.MenuItem("Zamknij", _quit),
    )
    icon = pystray.Icon("saycue", img, "SayCue — asystent głosowy", menu)
    threading.Thread(target=icon.run, daemon=True).start()
    return icon
