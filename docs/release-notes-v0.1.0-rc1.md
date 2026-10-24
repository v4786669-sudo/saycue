# SayCue v0.1.0-rc1 — release candidate dla tury testerów G3

> RC1 = build dla 5 testerów (bramka G3: ≥60% „pierwsza komenda" ≤10 min).
> NIE jest to publikacja publiczna — ta nastąpi jako v0.1.0 (T0) po zamknięciu
> po utwardzeniu parsera i zamknięciu G3.

## Co jest w środku

- **Pętla głosowa:** audio (sounddevice/ALSA, pre-roll 400 ms) → wake-word „hej asystent" /
  push-to-talk (Ctrl+Alt+Space) → Silero VAD (koniec mowy 600 ms, maks. 8 s) →
  faster-whisper `small` int8 (PL) → parser (Aho-Corasick + rapidfuzz, szablony slotów)
  → akcje: aplikacje, klawisze, głośność, OBS (scena/mute/nagrywanie/replay), okno.
- **GUI:** 5 widoków (Status / Mikrofon / Komendy / Integracje / Statystyki) + tray +
  onboarding „pierwsze 5 minut" + panel „Wsparcie".
- **Diagnostyka:** `saycue doctor` (mikrofon, OBS v5, modele SHA-256, FP/h, offline;
  kody 0/1/2 + jednozdaniowe naprawy), `doctor --faq`.
- **Telemetria lokalna:** `events.jsonl` (9 zdarzeń G4, BEZ treści mowy, opt-out) +
  `metrics.jsonl` (opt-in). Zero wysyłki.
- **Presety:** obs-core + 5 gier (Elite Dangerous, Star Citizen, MSFS, DCS, Minecraft) +
  2 pakiety aplikacji (16 aplikacji) — YAML, walidowane schematem.

## Dla testerów (protokół G3)

1. Zainstaluj (Windows: `saycue-setup-0.1.0-rc1.exe`; Linux: `pipx install saycue`).
2. Pierwsze uruchomienie pobierze modele (~530 MB, manifest + SHA-256).
3. `saycue doctor` → zielono, potem 3 komendy: „otwórz notatnik", „scena pvp",
   „wycisz mikrofon". Czas do pierwszej UDANEJ komendy ≤10 min = sukces.

## Znane ograniczenia (uczciwość)

- macOS: brak. Wayland: brak globalnych hotkeyów (wake-word działa).
- OBS wymaga wersji ≥28 z włączonym WebSocket Server.
- Akcje domyślnie dry-run — realne wykonanie po `--live` / w GUI.
- Modele nie są w instalatorze (R10) — pobierane jawnie przy pierwszym starcie.
