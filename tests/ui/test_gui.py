"""Smoke test GUI (offscreen): 5 widoków, panel wsparcia, integracje."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from saycue.config.settings import Settings  # noqa: E402
from saycue.telemetry import Telemetry  # noqa: E402
from saycue.ui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    yield application


def test_main_window_five_views_and_support_panel(app, tmp_path):
    settings = Settings(first_run_done=True)
    telemetry = Telemetry(
        settings,
        events_path=tmp_path / "e.jsonl",
        metrics_path=tmp_path / "m.jsonl",
    )
    telemetry.support_ticket(kind="obs", hours=0.4)
    telemetry.support_ticket(kind="mic", hours=0.2)
    telemetry.support_ticket(kind="obs", hours=0.2)

    window = MainWindow(settings, telemetry)
    window.show()
    assert window.tabs.count() == 5
    assert window.tabs.tabText(0) == "Status"
    assert window.tabs.tabText(4) == "Statystyki"

    window._refresh_stats()
    assert "0.8 h" in window.support_label.text()
    assert "UWAGA (>0,7 h)" in window.support_label.text()  # 0.8 > próg G4g

    # dodanie zgłoszenia przez panel
    window.ticket_kind.setCurrentText("mic")
    window.ticket_hours.setValue(0.5)
    window._add_ticket()
    support = telemetry.support_hours()
    assert support["total_hours"] == pytest.approx(1.3)
    assert support["by_kind"]["mic"] == pytest.approx(0.7)

    # eksport CSV (jawna ścieżka — bez modalnego dialogu w testach)
    csv_path = tmp_path / "support.csv"
    window._export_csv(str(csv_path))
    assert csv_path.is_file()
    window.close()


def test_settings_integrations_checkboxes(app, tmp_path):
    settings = Settings(first_run_done=True, events_enabled=True, metrics_enabled=False)
    telemetry = Telemetry(
        settings, events_path=tmp_path / "e.jsonl", metrics_path=tmp_path / "m.jsonl"
    )
    window = MainWindow(settings, telemetry)
    assert window.events_check.isChecked() is True
    assert window.metrics_check.isChecked() is False
    window.metrics_check.setChecked(True)
    window._save_integrations()
    assert settings.metrics_enabled is True
    window.close()


def test_onboarding_skipped_when_first_run_done(app, tmp_path):
    # first_run_done=True → onboarding nie blokuje tworzenia okna
    settings = Settings(first_run_done=True)
    telemetry = Telemetry(
        settings, events_path=tmp_path / "e.jsonl", metrics_path=tmp_path / "m.jsonl"
    )
    window = MainWindow(settings, telemetry)
    window.show()
    assert window.window.isVisible()
    window.close()
