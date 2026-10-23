"""Telemetria SayCue: dwa rozdzielone strumienie (architektura §2.4, twardy wymóg).

`events.jsonl` — płatnościowe/aktywacyjne, włączony w rdzeniu OSS z jawnym
opt-out, **NIGDY treści wypowiedzi**. 9 typów zdarzeń (G4a–G4h):

    first_command, command_miss, preset_missing, paywall_view,
    checkout_start, checkout_abandon, purchase, support_ticket, wakeword_fp

`metrics.jsonl` — techniczny (jakość rozpoznawania, budżet latencji),
**opt-in**; `asr_text` wyłącznie w tym strumieniu i tylko po świadomej zgodzie.

Zasady twarde:
- zakazane pola w events.jsonl: `asr_text`, `text`, `phrase`, `transcript`
  (writer odmawia zapisu; test `tests/telemetry/test_privacy.py` skanuje plik),
- `intent_guess` w `command_miss` to fraza z commands.yaml (string z listy),
  nigdy transkrypcja; brak trafienia → null,
- rotacja 30 dni / 2 MB, lokalnie; zero wysyłki w rdzeniu OSS.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ..config.paths import config_dir

log = logging.getLogger(__name__)

# Zakazane pola w events.jsonl (§2.4) — obecność = naruszenie prywatności.
FORBIDDEN_FIELDS = ("asr_text", "text", "phrase", "transcript")

EVENT_TYPES = {
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

MAX_BYTES = 2 * 1024 * 1024
RETENTION_DAYS = 30


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ts_from_line(line: str) -> datetime | None:
    try:
        return datetime.fromisoformat(json.loads(line)["ts"].replace("Z", "+00:00"))
    except Exception:
        return None


class JsonlStore:
    """Wspólna warstwa: append JSONL + rotacja (2 MB / 30 dni), lokalnie."""

    def __init__(self, path: Path, forbidden: tuple[str, ...] = ()):
        self.path = path
        self.forbidden = forbidden
        self._lock = threading.Lock()
        self._session_id = uuid.uuid4().hex[:16]

    def _rotate(self) -> None:
        if not self.path.is_file():
            return
        if self.path.stat().st_size > MAX_BYTES:
            backup = self.path.with_suffix(self.path.suffix + ".1")
            backup.write_bytes(self.path.read_bytes())
            self.path.unlink()

    def _drop_old(self) -> None:
        cutoff = datetime.now(UTC) - timedelta(days=RETENTION_DAYS)
        if not self.path.is_file():
            return
        kept = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            ts = _ts_from_line(line)
            if ts is None or ts >= cutoff:
                kept.append(line)
        self.path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")

    def append(self, entry: dict[str, Any]) -> None:
        if self.forbidden:
            bad = [f for f in self.forbidden if f in entry]
            if bad:
                raise ValueError(f"odmowa zapisu: zakazane pola w {self.path.name}: {bad} (§2.4)")
        entry.setdefault("ts", _now_iso())
        with self._lock:
            self._rotate()
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")

    def read_recent(self, hours: int = 24) -> list[dict[str, Any]]:
        """Wpisy z ostatnich N godzin (do doctor: FP/h)."""
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        if not self.path.is_file():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = _ts_from_line(line)
            if ts is not None and ts >= cutoff:
                out.append(entry)
        return out


class Telemetry:
    """Dwa strumienie + przełączniki (Settings). Brak jakiejkolwiek wysyłki."""

    def __init__(self, settings, events_path: Path | None = None, metrics_path: Path | None = None):
        self.settings = settings
        data_dir = config_dir() / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        self.events = JsonlStore(events_path or data_dir / "events.jsonl", FORBIDDEN_FIELDS)
        self.metrics = JsonlStore(metrics_path or data_dir / "metrics.jsonl")
        self._wakeword_fp_count = 0
        self._wakeword_fp_window_start = time.monotonic()

    # ------------------------------------------------------------- events.jsonl

    def log_event(self, ev: str, **fields: Any) -> None:
        if not self.settings.events_enabled:
            return
        if ev not in EVENT_TYPES:
            raise ValueError(f"nieznany typ zdarzenia: {ev!r}")
        self.events.append({"ev": ev, **fields})

    def first_command(self, success: bool) -> None:
        if not success or self.settings.first_command_done:
            return  # G4a: liczy się PIERWSZA udana komenda (raz na instalację)
        self.log_event("first_command", success=True)
        self.settings.first_command_done = True
        self.settings.save()

    def command_miss(self, intent_guess: str | None, added_phrase: bool = False) -> None:
        # intent_guess = fraza z commands.yaml lub null — NIGDY transkrypcja (§2.4)
        self.log_event("command_miss", intent_guess=intent_guess, added_phrase=added_phrase)

    def preset_missing(self, game: str | None) -> None:
        self.log_event("preset_missing", game=game)

    def paywall_view(self, surface: str) -> None:
        self.log_event("paywall_view", surface=surface)

    def checkout_start(self, product: str, price_pln: int, geo: str) -> None:
        self.log_event("checkout_start", product=product, price_pln=price_pln, geo=geo)

    def checkout_abandon(self, step: str) -> None:
        self.log_event("checkout_abandon", step=step)

    def purchase(self, product: str, price_pln: int, geo: str) -> None:
        self.log_event("purchase", product=product, price_pln=price_pln, geo=geo)

    def support_ticket(self, kind: str, hours: float) -> None:
        self.log_event("support_ticket", kind=kind, hours=hours)

    def wakeword_fp(self, count: int = 1) -> None:
        """Agregacja FP: flush co okno godzinowe lub na close()."""
        self._wakeword_fp_count += count
        if time.monotonic() - self._wakeword_fp_window_start >= 3600:
            self._flush_wakeword_fp()

    def _flush_wakeword_fp(self) -> None:
        if self._wakeword_fp_count > 0:
            self.log_event("wakeword_fp", count=self._wakeword_fp_count, window_h=1)
            self._wakeword_fp_count = 0
        self._wakeword_fp_window_start = time.monotonic()

    def close(self) -> None:
        self._flush_wakeword_fp()

    # ------------------------------------------------------------ metrics.jsonl

    def log_metric(
        self, intent: str | None, ok: bool, latency_ms: float, asr_text: str = ""
    ) -> None:
        """Tylko po świadomej zgodzie (metrics_enabled=True); asr_text = opcja."""
        if not self.settings.metrics_enabled:
            return
        entry: dict[str, Any] = {"intent": intent, "ok": ok, "latency_ms": round(latency_ms, 1)}
        if self.settings.metrics_enabled:
            entry["asr_text"] = asr_text
        self.metrics.append(entry)

    # ---------------------------------------------------------------- odczyt (GUI)

    def fp_per_hour(self, hours: int = 24) -> float:
        total = sum(
            e.get("count", 0)
            for e in self.events.read_recent(hours)
            if e.get("ev") == "wakeword_fp"
        )
        return total / hours

    def support_hours(self, days: int = 30) -> dict[str, Any]:
        """Godziny wsparcia per kategoria (panel „Wsparcie", G4g)."""
        tickets = [e for e in self.events.read_recent(days * 24) if e.get("ev") == "support_ticket"]
        by_kind: dict[str, float] = {}
        for t in tickets:
            kind = str(t.get("kind") or "inne")
            by_kind[kind] = by_kind.get(kind, 0.0) + float(t.get("hours") or 0)
        return {
            "total_hours": round(sum(by_kind.values()), 2),
            "by_kind": by_kind,
            "n": len(tickets),
        }

    def metrics_summary(self) -> dict[str, Any]:
        """Liczba komend, % sukcesu, p50/p95 latencji z metrics.jsonl (GUI Statystyki)."""
        rows = [
            e
            for e in self.metrics.read_recent(hours=24 * 30)
            if isinstance(e.get("latency_ms"), (int, float))
        ]
        if not rows:
            return {"n": 0, "ok": 0, "p50_ms": None, "p95_ms": None}
        lat = sorted(e["latency_ms"] for e in rows)
        ok = sum(1 for e in rows if e.get("ok"))
        return {
            "n": len(rows),
            "ok": ok,
            "p50_ms": round(lat[len(lat) // 2], 1),
            "p95_ms": round(lat[int(len(lat) * 0.95)], 1),
        }
