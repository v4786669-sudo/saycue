"""Telemetria: metrics.jsonl + events.jsonl.

- `events.jsonl` — 9 zdarzeń G4a–G4h, rdzeń OSS ON z jawnym opt-out,
  NIGDY treści wypowiedzi (zakazane pola: asr_text/text/phrase/transcript);
- `metrics.jsonl` — opt-in, jedyne miejsce na `asr_text` (po zgodzie).
Rotacja 30 dni / 2 MB, lokalnie, zero wysyłki. Test prywatności w CI:
`tests/telemetry/test_privacy.py`.
"""

from .telemetry import FORBIDDEN_FIELDS, JsonlStore, Telemetry

__all__ = ["Telemetry", "JsonlStore", "FORBIDDEN_FIELDS"]
