<p align="center">
  <img src="https://raw.githubusercontent.com/v4786669-sudo/saycue/main/assets/banner.svg" alt="SayCue — mówisz, stream się nie psuje" width="820">
</p>

<p align="center">
  <a href="#instalacja"><b>Instalacja</b></a> ·
  <a href="#funkcje"><b>Funkcje</b></a> ·
  <a href="#jak-to-działa"><b>Jak to działa</b></a> ·
  <a href="SECURITY.md"><b>Bezpieczeństwo</b></a> ·
  <a href="presets/README.md"><b>Presety</b></a> ·
  <a href="../../releases"><b>Releases</b></a>
</p>

# SayCue

**Offline'owy asystent głosowy dla streamerów i graczy.** Mówisz krótką komendę — scena w OBS się zmienia, mikrofon się wycisza, nagranie startuje. Bez klikania, bez chmury, bez opóźnień na wizji.

Całe rozpoznawanie mowy odbywa się na Twoim komputerze. Po pierwszym pobraniu modeli aplikacja nie potrzebuje internetu — Twoje nagrania nie opuszczają urządzenia, a telemetria nie zawiera treści wypowiedzi.

> **Status:** wersja przedpremierowa. Aplikacja jest w pełni użyteczna lokalnie, ale w tym wydaniu akcje działają w trybie **podglądu** — pokazują, co zostałyby wykonane, zamiast wykonywać je od razu.

## Funkcje

- **Komendy głosowe dla OBS** — zmiana sceny, mute źródła, start/stop nagrywania, zapis replay buffer, przełączanie źródeł.
- **Sterowanie komputerem** — otwieranie i zamykanie aplikacji, pojedyncze kombinacje klawiszy, głośność systemu.
- **Słowo budzenia i push-to-talk** — „hej asystent" albo przytrzymanie `Ctrl+Alt+Space`, gdy mikrofon nie jest wspólny.
- **Tryb podglądu** — każda akcja najpierw widoczna w Statusie; realne wykonanie po włączeniu trybu live.
- **Gotowe presety** — OBS, pięć gier (Elite Dangerous, Star Citizen, Microsoft Flight Simulator, DCS World, Minecraft) i zestaw aplikacji streamera; wszystkie w YAML, wszystkie edytowalne.
- **Diagnostyka** — `saycue doctor` sprawdza mikrofon, połączenie z OBS, modele i stabilność wykrywania mowy.
- **Prywatność** — brak chmury w ścieżce sterowania, lokalne logi, przejrzysta telemetria (szczegóły: [SECURITY.md](SECURITY.md)).

## Wymagania

| | |
|---|---|
| System | Windows 10/11 · Linux X11 (Wayland: OBS i otwieranie aplikacji, bez wstrzykiwania klawiszy) |
| Sprzęt | procesor z 4 rdzeniami, 4 GB RAM (8 GB komfortowo), ~600 MB miejsca na modele |
| Oprogramowanie | OBS Studio 28+ z obs-websocket v5 (dla komend OBS) |
| Do uruchomienia ze źródeł | Python 3.11+ |

## Instalacja

### Windows

Pobierz `saycue-setup-<wersja>.exe` z zakładki [Releases](../../releases) i uruchom. Instalator dodaje skrót w menu Start, a `doctor` można włączyć z tego samego skrótu. Pierwsze uruchomienie pobiera modele (~530 MB) i weryfikuje je sumą SHA-256.

### Linux

```bash
pipx install saycue
saycue doctor      # mikrofon, OBS, modele — z jednozdaniowymi podpowiedziami naprawy
saycue             # uruchamia asystenta
```

### Ze źródeł

```bash
git clone https://github.com/v4786669-sudo/saycue.git && cd saycue
make dev                      # uv venv + zależności (również dev/testy)
python scripts/download_models.py
python -m saycue              # tryb podglądu; --live = realne wykonanie
python -m saycue gui          # GUI + tray
python -m saycue doctor       # diagnostyka środowiska
```

Z pliku nagrania, bez mikrofonu:

```bash
python -m saycue --file eval/recordings/g1_01.wav
```

## Jak to działa

```
mikrofon (16 kHz mono, pre-roll 400 ms)
  → słowo budzenia (openWakeWord) lub push-to-talk
  → detekcja mowy (Silero VAD; koniec wypowiedzi po 600 ms ciszy, maks. 8 s)
  → rozpoznawanie mowy (faster-whisper small, int8, język PL, prompt z listy komend)
  → parser gramatyki (normalizacja PL, dopasowanie fraz, szablony ze slotami)
  → akcja (OBS WebSocket v5, aplikacje, klawisze, głośność)
  → potwierdzenie w trayu
```

Parser jest deterministyczny: ta sama wypowiedź daje tę samą komendę. W ścieżce decyzyjnej nie ma modeli językowych — to celowe, bo odpowiedź musi być przewidywalna i natychmiastowa.

## Struktura repozytorium

```
src/saycue/        # pakiet: audio, vad, wakeword, asr, parser, actions, ui, config, telemetry
data/              # commands.yaml — gramatyka rdzenia
presets/           # presety YAML (OBS, gry, aplikacje) + schema + walidator
models/            # manifest modeli (wagi pobierane osobno, weryfikacja SHA-256)
bench/             # pomiary latencji: ASR, end-to-end, stabilność sesji
eval/              # zbiór nagrań ewaluacyjnych i skrypt pomiaru
tests/             # testy jednostkowe i integracyjne (pytest, ruff)
landing/           # strona walidacyjna (statyczna, bez zewnętrznych trackerów)
installer/         # PyInstaller (spec) i Inno Setup
```

## Rozwój

```bash
make test        # pytest (bez modeli i urządzeń audio)
make lint        # ruff check + format
make eval        # pomiar dokładności na zbiorze nagrań
make bench       # latencja ASR (p50/p95)
```

Presety dodaje się jako dane: nowa gra to jeden katalog z `preset.yaml`. Format, reguły fraz i walidacja: [presets/README.md](presets/README.md) oraz [docs/presets/CONTRIBUTING.md](docs/presets/CONTRIBUTING.md).

## Bezpieczeństwo

SayCue potrzebuje mikrofonu, dostępu do OBS WebSocket i — dla komend klawiszowych — wstrzykiwania klawiszy. Co dokładnie robi, jakich uprawnień wymaga i czego nie robi opisuje [SECURITY.md](SECURITY.md). Znaleziony problem bezpieczeństwa zgłoś prywatnie na adres podany w tym dokumencie.

## Licencja

Rdzeń: [MIT](LICENSE). Modele pobierane osobno: faster-whisper (MIT), Silero VAD (MIT), openWakeWord (Apache-2.0).

## Kontakt

- Błędy i propozycje: [Issues](../../issues)
- Społeczność i wczesne wersje: [Discord](https://discord.gg/7xYByRMV98)
- Wydania: [Releases](../../releases)
