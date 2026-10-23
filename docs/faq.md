# FAQ — SayCue (generowane przez `saycue doctor --faq`)

> Ten plik jest GENEROWANY — nie edytuj ręcznie. Źródło: szablony w
> `src/saycue/doctor/` + statystyki lokalne z `events.jsonl`.
> Ostatnia generacja: 2026-10-23 17:35.

## Najczęstsze 5 problemów (z Twoich logów)

- Kategorie ticketów wsparcia: brak danych
- Nierozpoznane komendy (90 dni): 0

Jeśli powyżej jest „brak danych" — nie zgłaszałeś jeszcze problemów. Dobrze!

## OBS nie łączy się / „obs_not_connected"

1. Potrzebny **OBS 28 lub nowszy** (wbudowany WebSocket).
2. W OBS: **Narzędzia → WebSocket Server → Włącz** (+ opcjonalne hasło).
3. W SayCue: **Integracje** → podaj host/port/hasło → „Testuj połączenie".
4. Diagnostyka: `saycue doctor --obs 127.0.0.1:4455[:hasło]`.

## Wayland — hotkey/klawisze nie działają

Wayland blokuje globalne hotkeye i wstrzykiwanie klawiszy (architektura §3.3).
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
  sterowania, macOS. Pełna lista: README + PLAN.md §3.
