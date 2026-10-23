"""Onboarding „pierwsze 5 minut" (architektura §3.5): mikrofon → 3 komendy →
test → FAQ. Pokazywany raz (settings.first_run_done)."""

from __future__ import annotations

import logging
import threading

import numpy as np

log = logging.getLogger(__name__)


def show_onboarding(main_window, QtCore, QtWidgets) -> None:
    from PySide6.QtWidgets import (
        QDialog,
        QLabel,
        QPushButton,
        QVBoxLayout,
    )

    dlg = QDialog(main_window.window)
    dlg.setWindowTitle("SayCue — pierwsze 5 minut")
    dlg.resize(520, 360)
    lay = QVBoxLayout(dlg)
    lay.addWidget(QLabel("Witaj w SayCue! Mówisz — stream się nie psuje. Offline, bez chmury."))
    mic_label = QLabel("1. Mikrofon: używamy wejścia domyślnego (zmienisz w zakładce Mikrofon).")
    lay.addWidget(mic_label)
    lay.addWidget(
        QLabel(
            "2. Trzy komendy na start:\n"
            '   • „otwórz spotify" / „otwórz notatnik" — uruchomi aplikację\n'
            '   • „scena pvp" — przełączy scenę w OBS (po podpięciu OBS w Integracjach)\n'
            '   • „wycisz mikrofon" — wyciszy mikrofon w OBS'
        )
    )
    test_label = QLabel('3. Test: naciśnij „Testuj" i powiedz „otwórz kalkulator".')
    lay.addWidget(test_label)
    test_btn = QPushButton("Testuj (4 s nasłuchu)")
    lay.addWidget(test_btn)
    faq_label = QLabel("Problemy? FAQ: docs/faq.md (saycue doctor --faq) i GitHub Issues.")
    faq_label.setOpenExternalLinks(True)
    lay.addWidget(faq_label)
    done_btn = QPushButton("Rozumiem — do dzieła")
    dlg.setLayout(lay)

    def _test() -> None:
        test_label.setText('nasłuchuję 4 s — powiedz „otwórz kalkulator"…')
        threading.Thread(target=_test_bg, args=(main_window, test_label), daemon=True).start()

    test_btn.clicked.connect(_test)

    def _done() -> None:
        main_window.settings.first_run_done = True
        main_window.settings.save()
        dlg.accept()

    done_btn.clicked.connect(_done)
    dlg.exec()


def _test_bg(main_window, label) -> None:
    import time

    try:
        from ..asr.whisper import ASREngine
        from ..audio.capture import AudioCapture

        capture = AudioCapture()
        capture.start()
        frames = []
        deadline_time = time.monotonic() + 4.0
        while time.monotonic() < deadline_time:
            try:
                chunk, _ts = capture.read(timeout=0.4)
            except Exception:
                break
            frames.append(chunk)
        capture.stop()
        if not frames:
            text = "cisza — sprawdź mikrofon (zakładka Mikrofon)"
        else:
            audio = np.concatenate(frames)
            engine = ASREngine(model_size="small", language="pl")
            result = engine.transcribe(audio)
            text = f"usłyszałem: „{result.text or '…'}”"
    except Exception as exc:
        text = f"test nieudany: {exc}"
    _set_label(label, text)


def _set_label(label, text: str) -> None:
    try:
        from PySide6.QtCore import QMetaObject, Qt

        QMetaObject.invokeMethod(label, "setText", Qt.QueuedConnection, text)
    except Exception:
        pass
