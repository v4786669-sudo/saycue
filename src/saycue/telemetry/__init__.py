"""Telemetria — SZKIELET (tydzień 3, twardy wymóg §2.4).

Kontrakt na W3:
- `metrics.jsonl` (opt-in): {ts, intent, ok, latency_ms, asr_text?} — asr_text
  tylko przy świadomej zgodzie;
- `events.jsonl` (włączony, jawny opt-out): 9 typów zdarzeń G4a–G4h,
  NIGDY treści wypowiedzi — zakazane pola: asr_text/text/phrase/transcript
  (test CI tests/telemetry/test_privacy.py);
- rotacja 30 dni / 2 MB, eksport do schowka w GUI.
W1: moduł istnieje, ale nic nie zapisuje (metryki startują w tyg. 3).
"""
