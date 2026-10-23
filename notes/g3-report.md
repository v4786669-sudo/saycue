# Raport W3 / bramka G3 — SayCue (stan: część inżynierska gotowa, tura testerów umówiona z researcherem)

> Autor: engineer (t10) · data: 2026-10-23 · maszyna pomiarowa: VM (i3-1315U, współdzielona).
> Podział pracy (decyzja kapitana 2026-10-23): parser (R-01/R-02, dedup) przejął engineer2 (t15);
> ten raport obejmuje: GUI, instalator, doctor, telemetrię, panel „Wsparcie", integrację presetów
> oraz HARNESS G3. Tura 5 testerów = wspólne domknięcie z engineer2 i researcherem.

## 1. Co jest gotowe i zmierzone

| Element | Status | Dowód |
|---|---|---|
| GUI PySide6: 5 widoków (§3.5) + onboarding „pierwsze 5 minut" + tray + autostart | ✅ | `saycue gui`; smoke offscreen: 5 zakładek, panel wsparcia liczy 0,8 h → „UWAGA (>0,7 h)"; tests/ui/test_gui.py |
| Panel „Wsparcie" (G4g): godziny/kategorie, próg 0,7 h, dodawanie ticketów, eksport CSV | ✅ | tests/ui + tests/telemetry (support_hours) |
| Telemetria: metrics.jsonl (opt-in, asr_text tylko tam) + events.jsonl (9 zdarzeń, ON/opt-out, NIGDY treści mowy) | ✅ | 11 testów w tests/telemetry/; test_privacy.py skanuje zakazane pola (asr_text/text/phrase/transcript) + opt-out wyłącza zapis |
| `saycue doctor [--json] [--faq] [--obs …]`: mikrofon (RMS), OBS handshake v5, modele (SHA-256 vs manifest), FP/h 24 h, hotkey, autostart, offline; kody 0/1/2 + jednozdaniowa naprawa | ✅ | **doctor na tej maszynie: 3,4 s (≤60 s ✓)**, exit 2 (brak OBS = uczciwy błąd z naprawą); docs/faq.md wygenerowane; tests/doctor/ |
| Instalator: PyInstaller onedir (spec) + Inno Setup (.iss) + CI windows-latest + autostart rejestr | ✅ | **build na Linuxie wykonany i uruchomiony** (binary `saycue doctor` działa — 7 czeków); .github/workflows/build-windows.yml; pipx w README |
| Integracja presetów po stronie GUI (loader t13, bez ruszania parser/) | ✅ | zakładka Komendy pokazuje rdzeń+presety; `saycue presets validate` (8 presetów, 0 błędów) |
| CI: ruff+pytest (245 testów) + manifest + **presety** (validate.py --json + zakaz .py w katalogach presetów — R-04) | ✅ | .github/workflows/ci.yml |
| Parser R-01/R-02 + dedup 21 fraz — zrobione przeze mnie, **przekazane engineer2/t15** (commit 096f4d8) | ✅ handover | 150 testów parsera zielonych w momencie przekazania |

## 2. Bramka G3 — stan i plan

**Kryterium:** ≥60% z 5 testerów wykona pierwszą komendę w ≤10 min bez pomocy;
`doctor --json` OK ≤60 s na 3 maszynach.

**Zmierzalne teraz:**
- doctor na tej maszynie: **3,4 s** ✓ (cel ≤60 s). Drugą i trzecią maszynę dadzą testerzy (procedura poniżej).
- Harness pomiaru aktywacji gotowy: `events.jsonl → first_command` (raz na instalację, G4a) + onboarding GUI.

**Do zrobienia razem (kapitan planuje wspólne domknięcie):**
1. **Researcher:** rekrutacja wg notes/testers.md (profile T1–T5, nagroda Starter Pack) — ja przygotowałem protokół testu poniżej.
2. **engineer2:** utwardzenie parsera (t15) musi być w wersji testowanej PRZED turą testerów.
3. **Kapitan:** wyznaczenie okna testowego (1 tydzień) po zbudowaniu instalatora Windows w CI.

## 3. Protokół tury testerów (do rozdania, 10 min na osobę)

1. **Tester dostaje:** link do `saycue-setup.exe` (Windows) albo `pipx install saycue` (Linux) + jedną kartkę z 3 komendami („otwórz notatnik", „scena pvp", „wycisz mikrofon") — BEZ pomocy dalej.
2. **Mierzymy:** czas od uruchomienia instalatora do pierwszej UDANEJ komendy (zdarzenie `first_command` w `events.jsonl` + zegar obserwatora). Sukces ≤10 min = PASS.
3. **Po teście:** `saycue doctor --json` na maszynie testera (≤60 s) + karta zgłoszeń: kategoria (obs/mic/preset/instalacja/inne) zamiast opisu (prywatność).
4. **Lista błędów** trafia do notes/g3-report.md (aktualizacja po turze) — oczekiwane klasy: instalator na czystym VM (Windows), OBS <28, Wayland, za cichy mikrofon (doctor już je diagnozuje).

## 4. Decyzje do kapitana

- **Status G3: NIE-domknięty** — tura testerów wymaga ludzi (researcher) i instalatora Windows z CI. Cała infrastruktura pomiaru i wsparcia jest gotowa.
- Rekomendacja: uruchomić build-windows.yml na tagu `v0.1.0-rc1` i dopiero wtedy ogłaszać turę.
- R-06 (asr_text w metrics): świadomie zgodne z §2.4 (asr_text tylko w metrics, tylko opt-in) — do decyzji, czy chcemy OSOBNY przełącznik na asr_text wewnątrz metrics.
