"""Test prywatności (twardy wymóg §2.4): events.jsonl bez treści wypowiedzi.

Skanuje zapisany plik pod kątem zakazanych pól: asr_text/text/phrase/transcript
— obecność któregokolwiek = FAIL (ten test idzie do CI).
Dodatkowo: opt-out wyłącza zapis; writer odmawia wpisu z zakazanym polem.
"""

import json
import re
from pathlib import Path

import pytest

from saycue.config.settings import Settings
from saycue.telemetry import FORBIDDEN_FIELDS, JsonlStore, Telemetry


def write_all_events(tel: Telemetry) -> None:
    """Wszystkie 9 typów + wartości graniczne (w tym próby wstrzyknięcia treści)."""
    tel.first_command(success=True)
    tel.command_miss(intent_guess="otwórz spotify")
    tel.command_miss(intent_guess=None)
    tel.preset_missing(game="elite_dangerous")
    tel.paywall_view(surface="starter_pack")
    tel.checkout_start(product="starter_pack", price_pln=39, geo="PL")
    tel.checkout_abandon(step="payment_method")
    tel.purchase(product="pro_pack", price_pln=79, geo="PL")
    tel.support_ticket(kind="obs", hours=0.7)
    tel.wakeword_fp(count=2)
    tel.close()


def test_events_jsonl_has_no_forbidden_fields(tmp_path: Path):
    tel = Telemetry(Settings(events_enabled=True), events_path=tmp_path / "events.jsonl")
    write_all_events(tel)
    raw = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    for line in raw.splitlines():
        entry = json.loads(line)
        for field in FORBIDDEN_FIELDS:
            assert field not in entry, f"zakazane pole {field!r} w events.jsonl: {entry}"
    # również w kluczach zagnieżdżonych wartości (obrona w głąb):
    for field in FORBIDDEN_FIELDS:
        assert not re.search(rf"[\"']{field}[\"']\s*:", raw), (
            f"zakazane pole {field!r} w surowym pliku"
        )


def test_writer_rejects_forbidden_field(tmp_path: Path):
    store = JsonlStore(tmp_path / "events.jsonl", FORBIDDEN_FIELDS)
    with pytest.raises(ValueError, match="zakazane pola"):
        store.append({"ev": "command_miss", "transcript": "otwórz spotify"})


def test_opt_out_disables_both_streams(tmp_path: Path):
    settings = Settings(events_enabled=False, metrics_enabled=False)
    tel = Telemetry(settings, events_path=tmp_path / "e.jsonl", metrics_path=tmp_path / "m.jsonl")
    write_all_events(tel)
    tel.log_metric("app.open", True, 100.0, asr_text="otwórz spotify")
    assert not (tmp_path / "e.jsonl").exists()
    assert not (tmp_path / "m.jsonl").exists()


def test_intent_guess_never_raw_transcript(tmp_path: Path):
    """command_miss.intent_guess to fraza z listy lub null — nie transkrypcja."""
    tel = Telemetry(Settings(), events_path=tmp_path / "events.jsonl")
    tel.command_miss(intent_guess="replay")
    raw = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    row = json.loads(raw.splitlines()[0])
    assert row["intent_guess"] == "replay"
    assert len(row["intent_guess"]) < 64
