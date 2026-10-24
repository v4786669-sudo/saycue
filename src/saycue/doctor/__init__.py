"""`saycue doctor` — self-diagnostyka.

Sprawdza: mikrofon (RMS), OBS (WebSocket v5 + wersja), modele (SHA-256 vs
manifest + wolne dysk/RAM), fałszywe wybudzenia (FP/h z 24 h events.jsonl),
uprawnienia (hotkey PTT, autostart), offline (modele lokalne → zero sieci).
Kody wyjścia: 0 = OK, 1 = ostrzeżenia, 2 = błąd. Każdy problem ma
jednozdaniową naprawę. `--faq` generuje docs/faq.md (szablony + top-5
problemów z events.jsonl).
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from ..asr.manifest import load_manifest, verify_all
from ..config.paths import models_dir

MIC_CAPTURE_S = 2.0
FP_PER_H_WARN = 3.0  # G4f: ≤3/h „dalej", >5/h pivot
OBS_TIMEOUT_S = 3.0


@dataclass
class CheckResult:
    name: str
    status: str  # ok | warn | error
    message: str
    fix: str = ""


def _free_ram_gb() -> float:
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemAvailable"):
                    return int(line.split()[1]) / 1e6  # kB → GB
    except OSError:
        pass
    return -1.0


def check_mic(capture_s: float = MIC_CAPTURE_S) -> CheckResult:
    """Otwiera mikrofon na `capture_s` s i mierzy RMS w dBFS."""
    import numpy as np

    from ..audio.capture import AudioCapture

    capture = AudioCapture()
    try:
        capture.start()
        frames = []
        deadline = time.monotonic() + capture_s
        while time.monotonic() < deadline:
            try:
                chunk, _ts = capture.read(timeout=0.4)
            except Exception:
                break
            frames.append(chunk)
    except Exception as exc:
        return CheckResult(
            "mikrofon",
            "error",
            f"nie można otworzyć wejścia audio: {exc}",
            "Podłącz mikrofon, sprawdź uprawnienia systemowe i uruchom ponownie.",
        )
    finally:
        capture.stop()

    if not frames:
        return CheckResult(
            "mikrofon",
            "error",
            "urządzenie otwarte, ale zero ramek audio",
            "Wybierz inne urządzenie wejściowe (GUI → Mikrofon → Test).",
        )
    audio = np.concatenate(frames)
    rms = float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))
    db = 20 * np.log10(rms + 1e-9)
    if db > -50:
        return CheckResult("mikrofon", "ok", f"poziom wejścia {db:.1f} dBFS (RMS {rms:.4f})")
    return CheckResult(
        "mikrofon",
        "warn",
        f"poziom wejścia bardzo niski: {db:.1f} dBFS",
        "Mów blisko mikrofonu lub podnieś wzmocnienie wejścia w systemie.",
    )


def check_obs(obs_url: str = "") -> CheckResult:
    """TCP + handshake obs-websocket v5 (wersja z Hello)."""
    from ..actions.obs import ObsClient, ObsError

    host, port, password = "127.0.0.1", 4455, ""
    if obs_url:
        parts = obs_url.split(":")
        host = parts[0]
        if len(parts) > 1:
            port = int(parts[1])
        if len(parts) > 2:
            password = parts[2]
    client = ObsClient(host=host, port=port, password=password, timeout=OBS_TIMEOUT_S)
    try:
        client.connect()
        version = getattr(client, "server_version", "?") or "?"
        client.close()
        return CheckResult(
            "obs",
            "ok",
            f"połączono z OBS WebSocket v5 ({host}:{port}), wersja {version}",
        )
    except (ObsError, OSError) as exc:
        return CheckResult(
            "obs",
            "error",
            f"brak połączenia z OBS ({host}:{port}): {exc}",
            "Uruchom OBS ≥ 28 → Narzędzia → WebSocket Server → włącz i podaj hasło w Integracjach.",
        )


def check_models() -> list[CheckResult]:
    """Obecność + SHA-256 vs manifest + wolne dysk/RAM."""
    results: list[CheckResult] = []
    try:
        specs = load_manifest()
    except Exception as exc:
        return [
            CheckResult(
                "modele",
                "error",
                f"manifest niedostępny: {exc}",
                "Przywróć models/manifest.json z repozytorium.",
            )
        ]
    for sid, _spec in specs.items():
        ok, msg = verify_all(specs)[sid]
        if ok:
            results.append(CheckResult("modele", "ok", f"{sid}: kompletny, SHA-256 zgodny"))
        else:
            results.append(
                CheckResult(
                    "modele",
                    "error",
                    f"{sid}: {msg}",
                    "Uruchom: python scripts/download_models.py",
                )
            )
    disk = shutil.disk_usage(models_dir() if models_dir().exists() else Path.home())
    if disk.free < 1e9:
        results.append(
            CheckResult(
                "dysk",
                "warn",
                f"mało miejsca: {disk.free / 1e9:.1f} GB wolne",
                "Zwolnij miejsce na dysku (modele potrzebują ~1 GB).",
            )
        )
    ram = _free_ram_gb()
    if ram != -1.0 and ram < 1.2:
        results.append(
            CheckResult(
                "ram",
                "warn",
                f"mało wolnego RAM: {ram:.1f} GB (model small ≈ 0,5 GB)",
                "Zamknij aplikacje w tle lub użyj modelu tiny (tryb low-power).",
            )
        )
    return results


def check_wakeword_fp() -> CheckResult:
    """FP/h z ostatnich 24 h events.jsonl (G4f)."""
    from ..config.settings import Settings
    from ..telemetry import Telemetry

    tel = Telemetry(Settings())
    fph = tel.fp_per_hour(24)
    if fph == 0.0:
        return CheckResult(
            "wake-word FP", "ok", "0 fałszywych wybudzeń w ostatnich 24 h (lub brak danych)"
        )
    if fph <= FP_PER_H_WARN:
        return CheckResult("wake-word FP", "ok", f"{fph:.2f} FP/h (próg G4f: ≤3/h)")
    return CheckResult(
        "wake-word FP",
        "warn",
        f"{fph:.2f} fałszywych wybudzeń/h",
        "Obniż czułość mikrofonu lub przejdź na push-to-talk (R6).",
    )


def check_permissions() -> list[CheckResult]:
    """Hotkey PTT + autostart."""
    results: list[CheckResult] = []
    try:
        from ..wakeword.ptt import PushToTalk

        ptt = PushToTalk()
        ptt.start()
        ok = ptt.running
        ptt.stop()
        if ok:
            results.append(CheckResult("hotkey PTT", "ok", "globalny hotkey Ctrl+Alt+Space działa"))
        else:
            results.append(
                CheckResult(
                    "hotkey PTT",
                    "warn",
                    "hotkey PTT niedostępny (Wayland/brak uprawnień) — zostaje wake-word",
                    "Na Wayland użyj wake-worda lub włącz uprawnienia globalnych skrótów.",
                )
            )
    except Exception as exc:
        results.append(
            CheckResult(
                "hotkey PTT",
                "error",
                f"test hotkeya rzucił wyjątek: {exc}",
                "Zgłoś błąd — hotkey powinien po prostu nie działać, nie wywalać.",
            )
        )
    autostart = Path.home() / ".config" / "autostart" / "saycue.desktop"
    if autostart.is_file():
        results.append(CheckResult("autostart", "ok", "autostart włączony (Linux .desktop)"))
    else:
        results.append(
            CheckResult(
                "autostart",
                "warn",
                "autostart nieaktywny",
                "GUI → Ustawienia → uruchamiaj przy logowaniu (Windows: rejestr).",
            )
        )
    return results


def check_offline() -> CheckResult:
    """Wszystkie modele lokalne → ścieżka sterowania w 100% offline."""
    try:
        specs = load_manifest()
        all_ok = all(ok for ok, _msg in verify_all(specs).values())
    except Exception:
        all_ok = False
    if all_ok:
        return CheckResult("offline", "ok", "wszystkie modele lokalne — praca w 100% offline")
    return CheckResult(
        "offline",
        "warn",
        "brak modeli w cache — pierwsze uruchomienie pobierze je z sieci (jawnie)",
        "Uruchom: python scripts/download_models.py",
    )


def run_checks(obs_url: str = "", mic_s: float = MIC_CAPTURE_S) -> tuple[list[CheckResult], float]:
    t0 = time.perf_counter()
    checks: list[CheckResult] = []
    checks.append(check_mic(mic_s))
    checks.append(check_obs(obs_url))
    checks.extend(check_models())
    checks.append(check_wakeword_fp())
    checks.extend(check_permissions())
    checks.append(check_offline())
    return checks, time.perf_counter() - t0


def verdict(checks: list[CheckResult]) -> tuple[int, str]:
    """Exit code 0/1/2 (OK / ostrzeżenie / błąd) + zdanie podsumowania."""
    errors = [c for c in checks if c.status == "error"]
    warns = [c for c in checks if c.status == "warn"]
    if errors:
        return 2, f"{len(errors)} błędów, {len(warns)} ostrzeżeń"
    if warns:
        return 1, f"OK z {len(warns)} ostrzeżeniami"
    return 0, "wszystko OK"


def format_checks(checks: list[CheckResult]) -> str:
    lines = []
    for c in checks:
        icon = {"ok": "✓", "warn": "⚠", "error": "✗"}[c.status]
        lines.append(f"  {icon} {c.name:<14} {c.message}")
        if c.fix:
            lines.append(f"          ↳ naprawa: {c.fix}")
    return "\n".join(lines)


def generate_faq(events_path: Path | None = None) -> str:
    """Renderuje docs/faq.md: szablony + top-5 problemów z events.jsonl."""
    from ..config.settings import Settings
    from ..telemetry import Telemetry

    tel = Telemetry(Settings(), events_path=events_path)
    support = tel.support_hours(days=90)
    misses = [e for e in tel.events.read_recent(hours=24 * 90) if e.get("ev") == "command_miss"]
    by_kind = sorted(support["by_kind"].items(), key=lambda kv: -kv[1])
    top_categories = ", ".join(f"{k} ({h:.1f} h)" for k, h in by_kind[:5]) or "brak danych"
    n_misses = len(misses)

    return f"""# FAQ — SayCue (generowane przez `saycue doctor --faq`)

> Ten plik jest GENEROWANY — nie edytuj ręcznie. Źródło: szablony w
> `src/saycue/doctor/` + statystyki lokalne z `events.jsonl`.
> Ostatnia generacja: {time.strftime("%Y-%m-%d %H:%M")}.

## Najczęstsze 5 problemów (z Twoich logów)

- Kategorie ticketów wsparcia: {top_categories}
- Nierozpoznane komendy (90 dni): {n_misses}

Jeśli powyżej jest „brak danych" — nie zgłaszałeś jeszcze problemów. Dobrze!

## OBS nie łączy się / „obs_not_connected"

1. Potrzebny **OBS 28 lub nowszy** (wbudowany WebSocket).
2. W OBS: **Narzędzia → WebSocket Server → Włącz** (+ opcjonalne hasło).
3. W SayCue: **Integracje** → podaj host/port/hasło → „Testuj połączenie".
4. Diagnostyka: `saycue doctor --obs 127.0.0.1:4455[:hasło]`.

## Wayland — hotkey/klawisze nie działają

Wayland blokuje globalne hotkeye i wstrzykiwanie klawiszy.
Działają: komendy OBS, otwieranie aplikacji, głośność (pactl). Wybudzanie:
wake-word („hej asystent") zamiast push-to-talk.

## Mikrofon za cichy / transkrypcje puste

1. `saycue doctor` → sprawdź „mikrofon" (RMS).
2. Mów 20–40 cm od mikrofonu; w GUI → Mikrofon → Test.
3. Zamknij inne aplikacje trzymające mikrofon (Discord/OBS mogą go blokować).

## Wolne rozpoznawanie / dużo CPU

1. Model `small` ≈ 0,5 GB RAM; zamknij zbędne aplikacje.
2. Tryb low-power: `--model tiny` (mniejsza dokładność, mniej CPU).
3. GPU (CUDA) jest wykrywane automatycznie (float16).

## Brak modeli / błąd SHA-256

`python scripts/download_models.py` — pobierze wagi z manifestu i zweryfikuje
sumy SHA-256 (ryzyko R10: modele nigdy nie są w repo).

## Czego NIE robimy (uczciwość)

- Makra omijające antycheat, dyktowanie do czatu gry, modele LLM w ścieżce
  sterowania, macOS. Pełna lista: README.
"""
