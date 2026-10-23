# Bezpieczeństwo i prywatność — SayCue

> SayCue to **offline'owy asystent komend głosowych** (nie asystent AI). Ten dokument mówi wprost, co robi, jakich uprawnień potrzebuje i czego **nie** robi — żebyś mógł ufać temu, co instalujesz na swoim komputerze.

## Co robi (w jednym zdaniu)

Nasłuchuje komendy → rozpoznaje mowę **lokalnie** → dopasowuje do znanej frazy → wykonuje akcję (OBS, aplikacje, klawisze, głośność).

## Jakie uprawnienia i dlaczego

| Uprawnienie / dostęp | Po co |
|---|---|
| **Mikrofon** | nasłuchiwanie komend (słowo budzenia lub przycisk PTT) |
| **OBS WebSocket** (lokalny, port localhost) | zmiana scen, mute, nagranie, replay — wymaga jawnego włączenia w OBS 28+ |
| **Wstrzykiwanie klawiszy** (tylko X11) | komendy `input.keys` — wyłącznie to, co sam zdefiniujesz |
| **Uruchamianie aplikacji** | `app.open` / `app.close` |
| **Sieć** | **wyłącznie**: jednorazowe pobranie modeli (~530 MB) + opcjonalna telemetria (opt-in) |

## Czego NIE robi

- ❌ **Nie wysyła nagrań ani treści mowy do chmury** — rozpoznawanie jest w 100% lokalne.
- ❌ **Nie loguje treści wypowiedzi** — telemetria zapisuje tylko typ zdarzenia i metryki (patrz niżej).
- ❌ Nie ma keyloggera, nie skanuje dysku, nie działa w tle bez Twojej wiedzy (tray/autostart są wyłączalne).
- ❌ Nie obchodzi anty-cheatów i nie czyta pamięci gier.
- ❌ Nie jest produktem medycznym.

## Dane i telemetria

- `metrics.jsonl` — lokalne metryki (czas, typ intencji). **Opt-in**; transkrypcja zapisywana tylko, gdy sam to włączysz.
- `events.jsonl` — zdarzenia (pierwsza komenda, błędy, zdarzenia zakupowe). **Bez treści mowy**, opt-out.
- Proces nie wykonuje żadnych żądań sieciowych poza jawnym pobraniem modeli (sprawdzane testem).

## Jak to zweryfikować

- Kod jest otwarty (MIT) — przejrzyj `src/`.
- `saycue doctor --json` — diagnostyka mikrofonu, OBS, modeli, uprawnień.
- Test `tests/test_privacy.py` — gwarantuje, że telemetria nie zawiera pól z treścią mowy.

## Zasady odpowiedzialnego działania

- Komendy wykonują **tylko** to, co zdefiniowano w `commands.yaml` i presetach.
- Akcje wysokiego ryzyka (kasowanie, wysyłanie wiadomości, iniekcja tekstu do aplikacji) **nie są** w MVP.

## Zgłaszanie problemów bezpieczeństwa

- Otwórz issue w tym repo albo napisz na Discord (`#beta`).
- Wrażliwe znaleziska: napisz do nas najpierw, nie publikuj publicznie exploita przed naprawą.
