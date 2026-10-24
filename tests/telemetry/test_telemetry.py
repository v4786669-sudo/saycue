"""Testy telemetrii: dwa strumienie, przełączniki, rotacja."""

import json
from pathlib import Path

from saycue.config.settings import Settings
from saycue.telemetry import Telemetry


def make_telemetry(tmp_path: Path, events=True, metrics=False):
    settings = Settings(events_enabled=events, metrics_enabled=metrics)
    return Telemetry(
        settings, events_path=tmp_path / "events.jsonl", metrics_path=tmp_path / "metrics.jsonl"
    )


def read_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_all_nine_event_types_serialize(tmp_path):
    tel = make_telemetry(tmp_path)
    tel.first_command(success=True)
    tel.command_miss(intent_guess="otwórz spotify")
    tel.command_miss(intent_guess=None)
    tel.preset_missing(game="elite_dangerous")
    tel.paywall_view(surface="starter_pack")
    tel.checkout_start(product="starter_pack", price_pln=39, geo="PL")
    tel.checkout_abandon(step="payment_method")
    tel.purchase(product="streamer_annual", price_pln=149, geo="PL")
    tel.support_ticket(kind="obs", hours=0.3)
    tel.wakeword_fp(count=3)
    tel.close()
    evs = [e["ev"] for e in read_lines(tmp_path / "events.jsonl")]
    assert set(evs) == {
        "first_command",
        "command_miss",
        "preset_missing",
        "paywall_view",
        "checkout_start",
        "checkout_abandon",
        "purchase",
        "support_ticket",
        "wakeword_fp",
    }


def test_first_command_logged_only_once(tmp_path):
    tel = make_telemetry(tmp_path)
    tel.first_command(success=True)
    tel.first_command(success=True)
    tel.first_command(success=False)
    firsts = [e for e in read_lines(tmp_path / "events.jsonl") if e["ev"] == "first_command"]
    assert len(firsts) == 1 and firsts[0]["success"] is True
    assert tel.settings.first_command_done


def test_events_opt_out_disables_writes(tmp_path):
    tel = make_telemetry(tmp_path, events=False)
    tel.support_ticket(kind="obs", hours=1.0)
    assert not (tmp_path / "events.jsonl").exists()


def test_metrics_opt_in_gate(tmp_path):
    tel = make_telemetry(tmp_path, metrics=False)
    tel.log_metric("app.open", True, 123.4, asr_text="otwórz spotify")
    assert not (tmp_path / "metrics.jsonl").exists()
    tel.settings.metrics_enabled = True
    tel.log_metric("app.open", True, 123.4, asr_text="otwórz spotify")
    row = read_lines(tmp_path / "metrics.jsonl")[0]
    assert row["intent"] == "app.open" and row["latency_ms"] == 123.4
    assert row["asr_text"] == "otwórz spotify"  # asr_text dozwolony TYLKO w metrics


def test_command_miss_intent_guess_is_phrase_not_transcript(tmp_path):
    tel = make_telemetry(tmp_path)
    tel.command_miss(intent_guess="replay", added_phrase=False)
    row = read_lines(tmp_path / "events.jsonl")[0]
    assert row["intent_guess"] == "replay"  # fraza z commands.yaml, nie transkrypcja


def test_metrics_summary_and_support_hours(tmp_path):
    tel = make_telemetry(tmp_path, metrics=True)
    tel.support_ticket(kind="obs", hours=0.4)
    tel.support_ticket(kind="mic", hours=0.3)
    tel.support_ticket(kind="obs", hours=0.5)
    for _i, ms in enumerate([100, 200, 300, 400, 500]):
        tel.log_metric("app.open", True, ms, asr_text="x")
    support = tel.support_hours()
    assert support["total_hours"] == 1.2
    assert support["by_kind"] == {"obs": 0.9, "mic": 0.3}
    summary = tel.metrics_summary()
    assert summary["n"] == 5 and summary["p50_ms"] == 300.0


def test_fp_per_hour(tmp_path):
    tel = make_telemetry(tmp_path)
    tel.wakeword_fp(count=6)
    tel.close()
    assert tel.fp_per_hour(hours=24) == 6 / 24
