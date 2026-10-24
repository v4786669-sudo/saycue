# Presety SayCue — deklaratywne YAML

Preset to **jeden katalog z jednym plikiem `preset.yaml`**: dane, nie kod. Loader waliduje katalog względem `schema.json` i wczytuje go bez restartu aplikacji.

```
presets/
├── schema.json                 # JSON Schema (draft 2020-12) — kontrakt pliku presetu
├── validate.py                 # walidator: schemat + reguły jakości + kolizje fraz
├── test_validate.py            # testy walidatora (przypadki negatywne)
├── README.md                   # format i zasady fraz (ten plik)
├── index.json                  # generowany: python3 presets/validate.py --index
├── obs-core/preset.yaml        # OBS: sceny, mute, nagrywanie, replay
├── elite-dangerous/preset.yaml # Elite Dangerous
├── star-citizen/preset.yaml    # Star Citizen (Flight)
├── msfs/preset.yaml            # Microsoft Flight Simulator
├── dcs/preset.yaml             # DCS World
├── minecraft/preset.yaml       # Minecraft
├── apps-open/preset.yaml       # aplikacje: otwórz / zamknij
└── apps-streaming/preset.yaml  # głośność systemu + narzędzia streamera
```

Walidacja lokalna: `python3 presets/validate.py` (wszystkie) albo `python3 presets/validate.py presets/<id>` (jeden). W instalacji ta sama walidacja jest dostępna jako `saycue presets validate`.

## Format pliku

```yaml
id: elite-dangerous            # = nazwa katalogu
version: 1.0.0
name: Elite Dangerous
kind: game                     # game | obs | apps
platforms: [win, linux-x11]
game: elite_dangerous          # id trafiające do events.jsonl (preset_missing)
author: SayCue contributors
license: MIT
requires: { obs: false }       # preset nie wymaga OBS
phrases: [...]                 # frazy presetu (m.in. initial_prompt dla Whisper)
apps: [...]                    # opcjonalne mapowania app.open (kind=apps/game)
scenes: [...]                  # opcjonalne sugerowane nazwy scen OBS
keys: {...}                    # opcjonalne domyślne bindy (slot keybind)
commands:
  - id: ed_lights
    intent: input.keys
    phrases: ["światła", "lights", "lights on", "lights off", "włącz światła"]
    slots: { keybind: ed_lights }
```

- **Frazy: polski najpierw**, potem warianty angielskie — od 3 do 6 na komendę, małe litery, bez interpunkcji. Parser normalizuje tekst (fold diakrytyków, usunięcie interpunkcji), więc nie trzeba tego robić ręcznie.
- **Intencje:** `app.open`, `app.close`, `input.keys`, `system.volume`, `obs.scene`, `obs.mute`, `obs.record`, `obs.replay`, `obs.source_toggle`, `window.focus`.
- **Sloty** sprawdzane są pod kątem intencji (`SLOT_RULES` w `validate.py`): `app.open`→`target`, `app.close`→`target`, `input.keys`→`keys`|`keybind`, `system.volume`→`direction` (+`step`), `obs.scene`→`scene`, `obs.mute`/`obs.source_toggle`→`source` (+`state`), `obs.record`/`obs.replay`→`action`|`buffer`, `window.focus`→`target`.
- **Bez makr do gier.** Preset nie wykonuje wieloetapowych sekwencji w grze. Dozwolone są pojedyncze klawisze i bindy, które gra udostępnia w swoich ustawieniach.

## Zasady fraz

1. **Dłuższa fraza wygrywa.** Dlatego mikrofon wycisza się frazą **„wycisz mikrofon"**, a gołe „wycisz" jest zarezerwowane dla głośności systemu.
2. **Preset OBS ma wyłączność** na: „scena …", „następna scena", „nagrywaj", „stop nagrywania", „replay".
3. **Bez gołych jednosylabówek** („on", „up", „stop") — kolidują z mową w tle.
4. **Unikalność fraz w obrębie aktywnych presetów.** Presety gier są wzajemnie wyłączne (aktywna jest jedna gra), a OBS i aplikacje są uniwersalne. Gry rozdziela prefiks słowny w frazie („elite podwozie", „lot podwozie", „dcs podwozie", „star podwozie", „mine kucnij").

## Reguły jakości egzekwowane przez `validate.py`

| Reguła | Poziom |
|---|---|
| zgodność ze `schema.json` | błąd |
| `id` = nazwa katalogu | błąd |
| brak plików wykonywalnych (`.py`/`.sh`/`.exe`/`.dll`) w katalogu presetu | błąd |
| 3–6 fraz, każda unikalna w obrębie aktywnych presetów | błąd |
| ≥ 5 fraz w `phrases` (initial_prompt) | błąd |
| fraza PL obecna w każdej komendzie | ostrzeżenie |
| kolizje podciągów między intencjami (np. „wycisz" ⊂ „wycisz mikrofon") | ostrzeżenie |

## Dodawanie presetu — 6 kroków

1. `cp -r presets/obs-core presets/<twoja-gra>` i zmień `id`, `name`, `game`.
2. Wpisz 8–20 komend po 3–6 wariantów (PL + EN). Nie kopiuj fraz z innych presetów.
3. `python3 presets/validate.py presets/<twoja-gra>` — wynik musi być `OK` (0 błędów, 0 ostrzeżeń).
4. Sprawdź to samo w aplikacji: `saycue presets validate presets/<twoja-gra>`.
5. Otwórz PR z tytułem `preset(<id>): <gra>`; w opisie: dla kogo jest preset, jakich bindów wymaga, na czym testowałeś.
6. Po merge `presets/index.json` regeneruje CI (plik generowany — nie edytuj ręcznie).

**PR odrzucimy, gdy:** zawiera kod, powiela frazy innego presetu, obiecuje makra omijające anty-cheat, nie ma wariantu angielskiego lub nie podaje źródła bindów.

## Wersjonowanie

`MAJOR` — zmiana formatu lub niekompatybilność; `MINOR` — nowe komendy lub frazy; `PATCH` — poprawki fraz i literówek. Subskrybenci pakietu Streamer otrzymują aktualizacje presetów automatycznie; wersja jest widoczna w GUI.

## Licencja

Presety są na **MIT**, tak jak rdzeń. Wysyłając PR, akceptujesz licencję MIT i podajesz się w polu `author`. Nie przyjmujemy presetów z cheatami, wallhackami ani treściami chronionymi prawem autorskim.
