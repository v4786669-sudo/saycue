# SayCue — mówisz, stream się nie psuje

**Offline'owy asystent głosowy dla streamerów i graczy.** Wypowiadasz krótką komendę bez klikania → asystent w ≤1,2 s (p95) wykonuje akcję (scena OBS, mute, nagrywanie, replay, klawisze, aplikacje) → w trayu widzisz, co się stało. Zero chmury w ścieżce sterowania, zero treści wypowiedzi w telemetrii.

> **Status: tydzień 2 / 4 MVP** — „rozpoznaj i zrób": mikrofon → wake-word/PTT → VAD → ASR → parser → akcje OS/OBS (dry-run domyślnie).
> Wyniki bramek: [G1](notes/g1-report.md) (dokładność ASR) · [G2](notes/g2-report.md) (pętla end-to-end).

## Trzy filary

1. **Działa od razu** — 20 presetów w darmowym rdzeniu (OBS, popularne gry), 200+ w płatnych paczkach. Bez „hours of setup".
2. **Nie zepsuje streamu** — ochrona przed fałszywymi wybudzeniami, monitor FP/h, bramka energii przed VAD.
3. **Offline i audytowalne** — 100% lokalnie, MIT = możesz sprawdzić, a nie „zaufać". Modele pobierane jawnie z manifestu + SHA-256.

## Czego NIGDY nie obiecujemy

Makr omijających antycheat · dyktowania do czatu gry w MVP · modeli AI/LLM w ścieżce sterowania · macOS w MVP.

## Instalacja

**Windows (produkcja):** `saycue-setup-<wersja>.exe` — budowany w CI
(`.github/workflows/build-windows.yml`: PyInstaller onedir + Inno Setup, instalacja
<5 min na czystym VM). Modele NIE są w instalatorze (R10) — pierwsze uruchomienie
pobiera je z manifestu; `saycue doctor` poprowadzi. Autostart: opcja w instalatorze (HKCU Run).

**Linux (produkcja):** `pipx install saycue` → `saycue doctor` pobierze modele i
przeprowadzi diagnostykę. Autostart: GUI → Integracje → (plik `~/.config/autostart/saycue.desktop`
generowany przez `saycue gui`).

## Szybki start (dev, Linux / Windows, Python 3.11+)

```bash
# 1. Środowisko i zależności
uv venv --python 3.11 .venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# 2. Modele (pobierane z manifestu models/manifest.json, weryfikacja SHA-256)
python scripts/download_models.py            # ~530 MB → ~/.cache/saycue/models/

# 3. Transkrypcja pliku WAV (sam ASR — poprzedni krok obejmuje już pełną pętlę)

# 4. Demo: pełna pętla audio → ASR → parser → akcja (wake-word + hotkey PTT Ctrl+Alt+Space)
python -m saycue            # akcje dry-run (bezpieczne); --live = realne wykonanie

# Demo end-to-end z pliku (bez mikrofonu): transkrypcja → intencja → akcja
python -m saycue --file eval/recordings/g1_01.wav

# Lista urządzeń audio / testy / benchmark / ewaluacja
python -m saycue --list-devices
pytest -m "not models"
python bench/asr_latency.py      # ASR | bench/e2e_latency.py — end-to-end | run_when_idle.py — gdy CPU wolny
python eval/run_eval.py
python bench/stress_session.py --minutes 30   # sesja stabilności G2
python -m saycue doctor         # self-diagnostyka (mikrofon/OBS/modele/FP): kody 0/1/2
python -m saycue gui            # GUI + tray (W3)
python -m saycue presets validate  # walidacja presetów YAML (§2.5)
```

**Interakcja (pętla na żywo):** powiedz **„hej asystent"** (openWakeWord, model EN — własny model PL w planie, ryzyko R6) **albo** przytrzymaj **Ctrl+Alt+Space** (push-to-talk, fallback), powiedz komendę (maks. 8 s, koniec po 600 ms ciszy), zobacz transkrypcję na ekranie. Ctrl+C kończy.

## Architektura (tydzień 1)

```
mikrofon (sounddevice 16 kHz mono, fallback: ALSA/ctypes)
  → bufor kołowy (pre-roll 400 ms)
  → wake-word (openWakeWord, cooldown 500 ms) | push-to-talk (pynput)
  → VAD (Silero ONNX, koniec mowy = 600 ms ciszy, maks. wypowiedź 8 s)
  → ASR (faster-whisper small int8, language=pl, beam=1, initial_prompt z komend)
  → transkrypcja na ekran (parser i akcje = tydzień 2)
```

Wymagania sprzętowe: CPU z ≥4 rdzeniami (np. Ryzen 5 3600 / i5-10400), ~1 GB RAM na modele, ~530 MB dysku.

## Repozytorium

```
src/saycue/        # pakiet: audio, vad, wakeword, asr, parser, actions, ui, config, telemetry
data/              # commands.yaml (frazy PL → initial_prompt dla Whisper)
models/            # TYLKO manifest.json — wagi pobierane + SHA-256 (R10)
scripts/           # download_models.py, generate_eval_recordings.py, check_manifest.py
bench/             # asr_latency.py (p50/p95 na 20 komendach)
eval/              # commands.yaml (15 fraz G1), run_eval.py, recordings/ (generowane)
tests/             # pytest (+ruff)
landing/           # strona walidacyjna (researcher, t7)
```

## Licencja

Rdzeń: **MIT** (patrz [LICENSE](LICENSE)). Modele: faster-whisper (MIT), Silero VAD (MIT), openWakeWord (Apache-2.0) — pobierane osobno, nie w repo.

## Roadmapa

| Tydzień | Cel | Bramka |
|---|---|---|
| W1 | audio → wake-word/VAD → transkrypcja | **G1:** ≥85% komend, ASR p95 ≤500 ms — **GO** (93,3%) |
| W2 | orchestrator: parser + akcje OS + OBS | **G2:** ≥90% komend, p95 ≤1,2 s — **GO** (95,0%, 19/20) |
| **W3 (tu jesteśmy)** | GUI/tray, instalator, `doctor`, telemetria, presety | **G3:** ≥60% testerów „first command" ≤10 min (tura testerów z researcherem — patrz notes/g3-report.md) |
| W4 | hardening, akcenty, **v0.1.0 publiczne** | G4 wstępne (T0+14 dni) |
