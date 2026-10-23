"""MainWindow — 5 widoków wg architektury §3.5 + panel „Wsparcie" (v0.2).

Status / Mikrofon / Komendy / Integracje / Statystyki.
Statystyki zawierają panel wsparcia: `support_ticket.hours` vs próg G4g
(≤0,7 h/pakiet/mies.), kategorie i eksport CSV — widok wyłącznie lokalny.
"""

from __future__ import annotations

import csv
import logging
import threading

from ..config.settings import Settings
from ..orchestrator import State
from ..telemetry import Telemetry

log = logging.getLogger(__name__)

G4G_THRESHOLD_HOURS = 0.7  # ≤0,7 h/pakiet/mies. „dalej"; >1,5 h „stop"
SUPPORT_KINDS = ["obs", "mic", "preset", "instalacja", "inne"]


def _qt():
    from PySide6 import QtCore, QtWidgets

    return QtCore, QtWidgets


class _OrchestratorBridge:
    """Wątek roboczy orchestratora → sygnały Qt (bez Qt w wątku audio)."""

    def __init__(self, build_orchestrator, on_status, on_outcome):
        self._build = build_orchestrator
        self._on_status = on_status
        self._on_outcome = on_outcome
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._orch = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        orch = self._build(
            on_state=lambda s: self._emit_status(s),
            on_outcome=lambda o: self._emit_outcome(o),
        )
        self._orch = orch
        try:
            orch.run_forever()
        except Exception:
            log.exception("orchestrator w GUI padł")
            self._emit_status(State.IDLE)

    def stop(self) -> None:
        self._stop.set()
        if self._orch is not None:
            self._orch._stop = True
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _emit_status(self, state: State) -> None:
        try:
            from PySide6.QtCore import QMetaObject, Qt

            QMetaObject.invokeMethod(self._on_status, "emit", Qt.QueuedConnection, str(state))
        except Exception:
            pass

    def _emit_outcome(self, outcome) -> None:
        try:
            from PySide6.QtCore import QMetaObject, Qt

            QMetaObject.invokeMethod(self._on_outcome, "emit", Qt.QueuedConnection, outcome)
        except Exception:
            pass


class MainWindow:
    def __init__(self, settings: Settings, telemetry: Telemetry):
        QtCore, QtWidgets = _qt()
        self.settings = settings
        self.telemetry = telemetry
        self.window = QtWidgets.QMainWindow()
        self.window.setWindowTitle("SayCue — mówisz, stream się nie psuje")
        self.window.resize(860, 560)
        self.tabs = QtWidgets.QTabWidget()
        self.window.setCentralWidget(self.tabs)

        self._build_status_tab(QtCore, QtWidgets)
        self._build_mic_tab(QtCore, QtWidgets)
        self._build_commands_tab(QtCore, QtWidgets)
        self._build_integrations_tab(QtCore, QtWidgets)
        self._build_stats_tab(QtCore, QtWidgets)

        self.bridge: _OrchestratorBridge | None = None

        if not settings.first_run_done:
            from .onboarding import show_onboarding

            show_onboarding(self, QtCore, QtWidgets)

    # ---------------------------------------------------------------- Status

    def _build_status_tab(self, QtCore, QtWidgets) -> None:
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        self.state_label = QtWidgets.QLabel("IDLE")
        font = self.state_label.font()
        font.setPointSize(22)
        self.state_label.setFont(font)
        self.state_label.setAlignment(QtCore.Qt.AlignCenter)
        lay.addWidget(self.state_label)
        self.transcript_label = QtWidgets.QLabel("ostatnia transkrypcja: —")
        lay.addWidget(self.transcript_label)
        self.action_label = QtWidgets.QLabel("ostatnia akcja: —")
        lay.addWidget(self.action_label)
        row = QtWidgets.QHBoxLayout()
        self.start_btn = QtWidgets.QPushButton("▶ Start (dry-run)")
        self.start_btn.clicked.connect(self._toggle_orchestrator)
        row.addWidget(self.start_btn)
        self.ptt_hint = QtWidgets.QLabel(
            'Wybudzanie: „hej asystent" (wake-word) lub przytrzymaj Ctrl+Alt+Space (PTT).'
        )
        row.addWidget(self.ptt_hint, 1)
        lay.addLayout(row)
        lay.addStretch(1)
        self.tabs.addTab(w, "Status")

    def _toggle_orchestrator(self) -> None:
        if self.bridge is None:
            self._start_orchestrator()
        else:
            self._stop_orchestrator()

    def _start_orchestrator(self) -> None:
        from ..actions import ActionContext, build_default_registry
        from ..asr.whisper import ASREngine
        from ..audio.capture import AudioCapture
        from ..orchestrator import Orchestrator
        from ..parser import IntentParser
        from ..vad.silero import SileroVAD
        from ..wakeword.openwakeword import WakeWordDetector
        from ..wakeword.ptt import PushToTalk

        def build(on_state, on_outcome):
            parser = IntentParser(active_presets=self.settings.presets)
            registry = build_default_registry()
            ctx = ActionContext(apps=parser.config.apps, obs=None, dry_run=self.settings.dry_run)
            return Orchestrator(
                asr=ASREngine(model_size=self.settings.model, language=self.settings.language),
                capture=AudioCapture(),
                vad=SileroVAD(),
                wake=WakeWordDetector() if self.settings.input in ("auto", "wake") else None,
                ptt=PushToTalk() if self.settings.input in ("auto", "ptt") else None,
                parser=parser,
                registry=registry,
                ctx=ctx,
                telemetry=self.telemetry,
                on_state=on_state,
                on_outcome=on_outcome,
            )

        QtCore, _ = _qt()
        from PySide6.QtCore import Signal

        class Signals(QtCore.QObject):
            status = Signal(str)
            outcome = Signal(object)

        self._signals = Signals()
        self._signals.status.connect(lambda s: self._on_state_text(s))
        self._signals.outcome.connect(self._on_outcome)
        self.bridge = _OrchestratorBridge(build, self._signals.status, self._signals.outcome)
        self.bridge.start()
        self.start_btn.setText("■ Stop")

    def _stop_orchestrator(self) -> None:
        if self.bridge is not None:
            self.bridge.stop()
            self.bridge = None
        self.start_btn.setText("▶ Start (dry-run)")

    def _on_state_text(self, state: str) -> None:
        self.state_label.setText(state)

    def _on_outcome(self, outcome) -> None:
        self.transcript_label.setText(f"ostatnia transkrypcja: {outcome.text or '(cisza)'}")
        if outcome.intent:
            self.action_label.setText(
                f"ostatnia akcja: {outcome.intent} {outcome.slots or ''} — "
                f"{'✓' if outcome.action_ok else '✗'} {outcome.action_message}"
            )
        else:
            cand = ", ".join(c.phrase for c in outcome.candidates[:3]) or "—"
            self.action_label.setText(f"nie zrozumiałem (czy chodziło ci o: {cand})")

    # ------------------------------------------------------------- Mikrofon

    def _build_mic_tab(self, QtCore, QtWidgets) -> None:
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        self.mic_combo = QtWidgets.QComboBox()
        for name in self._list_inputs():
            self.mic_combo.addItem(name)
        lay.addWidget(QtWidgets.QLabel("Urządzenie wejściowe:"))
        lay.addWidget(self.mic_combo)
        self.mic_level = QtWidgets.QLabel("poziom: —")
        test_btn = QtWidgets.QPushButton("Testuj (2 s)")
        test_btn.clicked.connect(self._test_mic)
        lay.addWidget(test_btn)
        lay.addWidget(self.mic_level)
        lay.addStretch(1)
        self.tabs.addTab(w, "Mikrofon")

    @staticmethod
    def _list_inputs() -> list[str]:
        try:
            import sounddevice as sd

            return [str(sd.query_devices(kind="input").get("name", "domyślne"))]
        except OSError:
            from ..audio._alsa_backend import list_devices

            return [f"{d['alsa_name']} — {d['description']}" for d in list_devices()]

    def _test_mic(self) -> None:
        from ..doctor import check_mic

        self.mic_level.setText("pomiar…")
        result = check_mic(2.0)
        self.mic_level.setText(f"{'✓' if result.status != 'error' else '✗'} {result.message}")

    # -------------------------------------------------------------- Komendy

    def _build_commands_tab(self, QtCore, QtWidgets) -> None:
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        self.commands_table = QtWidgets.QTableWidget(0, 4)
        self.commands_table.setHorizontalHeaderLabels(["intent", "frazy", "źródło", "id"])
        self.commands_table.horizontalHeader().setStretchLastSection(True)
        self._reload_commands()
        lay.addWidget(
            QtWidgets.QLabel(
                "Komendy = data/commands.yaml (rdzeń) + aktywne presety (§2.5). "
                "Edycja: pliki YAML — bez restartu (hot-reload)."
            )
        )
        lay.addWidget(self.commands_table)
        reload_btn = QtWidgets.QPushButton("Odśwież")
        reload_btn.clicked.connect(self._reload_commands)
        lay.addWidget(reload_btn)
        self.tabs.addTab(w, "Komendy")

    def _reload_commands(self) -> None:
        try:
            from ..parser import IntentParser

            parser = IntentParser(active_presets=self.settings.presets)
            cfg = parser.config
            rows = []
            for cmd in cfg.commands:
                rows.append(
                    [
                        cmd.get("intent", ""),
                        ", ".join(cmd.get("phrases", [])),
                        cmd.get("origin", "core"),
                        cmd.get("id", ""),
                    ]
                )
            self.commands_table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                for j, value in enumerate(row):
                    from PySide6.QtWidgets import QTableWidgetItem

                    self.commands_table.setItem(i, j, QTableWidgetItem(str(value)))
        except Exception as exc:
            log.warning("ładowanie komend: %s", exc)

    # ---------------------------------------------------------- Integracje

    def _build_integrations_tab(self, QtCore, QtWidgets) -> None:
        w = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(w)
        self.obs_host = QtWidgets.QLineEdit("127.0.0.1")
        self.obs_port = QtWidgets.QLineEdit("4455")
        self.obs_pass = QtWidgets.QLineEdit("")
        self.obs_pass.setEchoMode(QtWidgets.QLineEdit.Password)
        form.addRow("OBS host:", self.obs_host)
        form.addRow("OBS port:", self.obs_port)
        form.addRow("OBS hasło:", self.obs_pass)
        self.obs_status = QtWidgets.QLabel("nie testowano")
        obs_btn = QtWidgets.QPushButton("Testuj połączenie")
        obs_btn.clicked.connect(self._test_obs)
        form.addRow(obs_btn, self.obs_status)

        self.live_check = QtWidgets.QCheckBox(
            "Wykonuj akcje naprawdę (live) — odznaczone = dry-run (plan akcji)"
        )
        self.live_check.setChecked(not self.settings.dry_run)
        form.addRow(self.live_check)
        form.addRow(
            QtWidgets.QLabel(
                "UWAGA: live = realne klawisze/aplikacje/OBS w systemie. "
                "Dla testera G3: zaznacz, jeśli chcesz widzieć efekty."
            )
        )

        self.events_check = QtWidgets.QCheckBox(
            "events.jsonl (zdarzenia G4 — bez treści wypowiedzi)"
        )
        self.events_check.setChecked(self.settings.events_enabled)
        self.metrics_check = QtWidgets.QCheckBox(
            "metrics.jsonl (jakość rozpoznawania — WYŁĄCZNIE za świadomą zgodą; zawiera asr_text)"
        )
        self.metrics_check.setChecked(self.settings.metrics_enabled)
        form.addRow(self.events_check)
        form.addRow(self.metrics_check)
        save_btn = QtWidgets.QPushButton("Zapisz ustawienia")
        save_btn.clicked.connect(self._save_integrations)
        form.addRow(save_btn)
        self.tabs.addTab(w, "Integracje")

    def _test_obs(self) -> None:
        from ..doctor import check_obs

        url = f"{self.obs_host.text()}:{self.obs_port.text()}"
        if self.obs_pass.text():
            url += f":{self.obs_pass.text()}"
        self.obs_status.setText("testowanie…")
        result = check_obs(url)
        self.obs_status.setText(f"{'✓' if result.status == 'ok' else '✗'} {result.message}")

    def _save_integrations(self) -> None:
        self.settings.events_enabled = self.events_check.isChecked()
        self.settings.metrics_enabled = self.metrics_check.isChecked()
        # N-02 (t17): domyślnie dry-run; live = świadoma decyzja użytkownika/testera
        self.settings.dry_run = not self.live_check.isChecked()
        self.settings.save()
        self.obs_status.setText("zapisano — restart orchestrationa (Stop→Start) wczyta tryb live")

    # ---------------------------------------------------------- Statystyki

    def _build_stats_tab(self, QtCore, QtWidgets) -> None:
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        self.stats_label = QtWidgets.QLabel("—")
        refresh_btn = QtWidgets.QPushButton("Odśwież statystyki")
        refresh_btn.clicked.connect(self._refresh_stats)
        lay.addWidget(refresh_btn)
        lay.addWidget(self.stats_label)

        lay.addWidget(QtWidgets.QLabel('Panel „Wsparcie" (koszt, G4g):'))
        self.support_label = QtWidgets.QLabel("—")
        lay.addWidget(self.support_label)
        row = QtWidgets.QHBoxLayout()
        self.ticket_kind = QtWidgets.QComboBox()
        self.ticket_kind.addItems(SUPPORT_KINDS)
        self.ticket_hours = QtWidgets.QDoubleSpinBox()
        self.ticket_hours.setRange(0.0, 100.0)
        self.ticket_hours.setSingleStep(0.1)
        self.ticket_hours.setValue(0.3)
        add_ticket_btn = QtWidgets.QPushButton("Dodaj zgłoszenie (godziny)")
        add_ticket_btn.clicked.connect(self._add_ticket)
        row.addWidget(QtWidgets.QLabel("kategoria:"))
        row.addWidget(self.ticket_kind)
        row.addWidget(QtWidgets.QLabel("godziny:"))
        row.addWidget(self.ticket_hours)
        row.addWidget(add_ticket_btn)
        lay.addLayout(row)
        export_btn = QtWidgets.QPushButton("Eksport CSV")
        export_btn.clicked.connect(self._export_csv)
        lay.addWidget(export_btn)
        lay.addStretch(1)
        self.tabs.addTab(w, "Statystyki")
        self._refresh_stats()

    def _refresh_stats(self) -> None:
        summary = self.telemetry.metrics_summary()
        if summary["n"]:
            self.stats_label.setText(
                f"Komendy (metrics, opt-in): {summary['n']} | sukces {summary['ok']} | "
                f"p50 {summary['p50_ms']} ms | p95 {summary['p95_ms']} ms"
            )
        else:
            self.stats_label.setText(
                "Komendy (metrics): brak danych — metrics.jsonl jest opt-in (włącz w Integracjach)."
            )
        support = self.telemetry.support_hours()
        verdict = (
            "OK (≤0,7 h/pakiet)"
            if support["total_hours"] <= G4G_THRESHOLD_HOURS
            else ("STOP (>1,5 h)" if support["total_hours"] > 1.5 else "UWAGA (>0,7 h)")
        )
        kinds = "; ".join(f"{k}: {h:.1f} h" for k, h in sorted(support["by_kind"].items()))
        self.support_label.setText(
            f"support_ticket.hours (30 dni): {support['total_hours']:.1f} h "
            f"({support['n']} zgłoszeń) → {verdict}\nkategorie: {kinds or '—'}"
        )

    def _add_ticket(self) -> None:
        self.telemetry.support_ticket(self.ticket_kind.currentText(), self.ticket_hours.value())
        self._refresh_stats()

    def _export_csv(self, path: str | None = None) -> None:
        """Eksport godzin wsparcia do CSV; bez ścieżki → dialog (tryb interaktywny)."""
        if path is None:
            QtCore, QtWidgets = _qt()
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self.window, "Eksport godzin wsparcia", "support.csv", "CSV (*.csv)"
            )
        if not path:
            return
        support = self.telemetry.support_hours(days=365)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["kind", "hours"])
            for kind, hours in sorted(support["by_kind"].items()):
                writer.writerow([kind, hours])
        self.support_label.setText(self.support_label.text() + f"\nwyeksportowano: {path}")

    def show(self) -> None:
        self.window.show()

    def close(self) -> None:
        self._stop_orchestrator()
        self.window.close()
