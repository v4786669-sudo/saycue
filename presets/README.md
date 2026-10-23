# Presety SayCue (deklaratywne YAML)

Każdy preset to **jeden katalog** z jednym plikiem `preset.yaml` — dane, nie kod (architektura §2.5). Loader czyta katalog, waliduje go względem `schema.json` i kopiuje do katalogu użytkownika bez restartu aplikacji.

```
presets/
├── schema.json                 # JSON Schema (draft 2020-12) — twardy kontrakt pliku
├── presets.schema.json         # alias nazwy (kompatybilność z architekturą §2.5)
├── validate.py                 # walidator: schemat + reguły jakości + kolizje fraz
├── test_validate.py            # testy walidatora (negatywne przypadki; bez zależności)
├── README.md                   # format i zasady fraz (ten plik)
├── index.json                  # generowany: python3 presets/validate.py --index
├── obs-core/preset.yaml        # 1  OBS: sceny, mute, nagranie, replay (17 komend)
├── elite-dangerous/preset.yaml # 2  ED (15 komend)
├── star-citizen/preset.yaml    # 3  SC Flight (11 komend, prefiks "star")
├── msfs/preset.yaml            # 4  MSFS (10 komend, prefiks "lot")
├── dcs/preset.yaml             # 5  DCS (11 komend, prefiks "dcs")
├── minecraft/preset.yaml       # 6  Minecraft (7 komend, prefiks "mine")
├── apps-open/preset.yaml       # 7–14  osiem aplikacji: otwórz/zamknij (12 komend)
└── apps-streaming/preset.yaml  # 15–16  głośność + narzędzia streamera (10 komend)
```

> Uwaga: drzewo docelowe to **`presets/`** w katalogu pakietu (architektura §8). Ten katalog (w `saycue/`) jest źródłem treści do wpięcia w W3 przez engineera; loader w `src/saycue/presets/` dostarcza engineer2 (t13). Do tego czasu waliduj lokalnie: `python3 presets/validate.py`.

## Format pliku

```yaml
id: elite-dangerous            # = nazwa katalogu
version: 1.0.0
name: Elite Dangerous
kind: game                     # game | obs | apps
platforms: [win, linux-x11]
game: elite_dangerous          # id do events.jsonl (preset_missing)
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

- **Frazy PL na początku**, warianty EN po nich; **3–6 wariantów na komendę**; małe litery, bez interpunkcji (parser i tak normalizuje: fold diakrytyków, wg §2.3).
- **Intencje** (MVP): `app.open`, `app.close`, `input.keys`, `system.volume`, `obs.scene`, `obs.mute`, `obs.record`, `obs.replay`, `obs.source_toggle`, `window.focus`.
- **Sloty** — walidator sprawdza dopasowanie do intencji (§ `SLOT_RULES` w `validate.py`): `app.open`→`target`, `app.close`→`target`, `input.keys`→`keys`|`keybind`, `system.volume`→`direction`(+`step`), `obs.scene`→`scene`, `obs.mute`/`obs.source_toggle`→`source`(+`state`), `obs.record`/`obs.replay`→`action`|`buffer`, `window.focus`→`target`.
- **Bez makr do gier** z anty-cheat: żadnych komend wykonujących wieloetapowe sekwencje w grze (PLAN.md §3). Dozwolone są pojedyncze klawisze/bindy, które gra sama udostępnia.

## Zasady fraz (anty-kolizje)

1. **Dłuższa fraza wygrywa** (architektura §2.3). Dlatego do „wyciszenia mikrofonu" używamy **„wycisz mikrofon"**, a nie gołego „wycisz" — gołe „wycisz" jest zarezerwowane dla `system.volume` (głośniki).
2. **Nie duplikuj fraz między presetami gry a OBS** — preset OBS ma wyłączność na: „scena …", „następna scena", „nagrywaj", „stop nagrywania", „replay".
3. **Nie używaj gołych słów jednosylabowych** („on", „up", „stop") bez kontekstu — kolizja z mową w tle.
4. **Każda fraza w presecie musi być unikalna w obrębie całego katalogu `presets/`** — walidator to sprawdza (duplikat = błąd, nie ostrzeżenie).

## Reguły jakości egzekwowane przez `validate.py`

| Reguła | Poziom |
|---|---|
| zgodność ze `schema.json` | błąd |
| `id` = nazwa katalogu | błąd |
| brak plików `.py`/`.sh`/`.exe`/`.dll` w katalogu presetu | błąd („preset nie może być kodem", §2.5) |
| 3–6 fraz, każda unikalna w **całym** katalogu | błąd |
| fraza PL przed EN (heurystyka: obecność diakrytyków lub słów PL) | ostrzeżenie |
| ≥ 5 fraz w `phrases` (initial_prompt) | błąd |
| kolizje **podciągów** między różnymi intencjami (np. „wycisz" ⊂ „wycisz mikrofon") | ostrzeżenie z podpowiedzią (dopuszczalne, jeśli wygrywa dłuższa) |

## Dodawanie presetu (PR) — 6 kroków

1. `cp -r presets/obs-core presets/<twoja-gra>` i zmień `id`, `name`, `game`.
2. Wpisz 8–20 komend; każda 3–6 wariantów PL + EN. **Nie** kopiuj fraz z innych presetów.
3. `python3 presets/validate.py presets/<twoja-gra>` — musi być `OK` (0 errors, 0 warnings).
4. Uruchom `saycue presets validate presets/<twoja-gra>` (po W3) — ta sama walidacja w aplikacji.
5. Otwórz PR: tytuł `preset(<id>): <gra>`, opis: dla kogo, jakie bindy zakładasz, na czym testowałeś.
6. Po merge walidator CI dopisze preset do `presets/index.json` (generowany, nie edytuj ręcznie).

**Za co odrzucimy PR:** kod w presecie, frazy zduplikowane z innym presetem, obietnica „makra na anticheat", brak wariantu EN, brak informacji o źródle bindów.

## Wersjonowanie

`MAJOR` = zmiana formatu/niekompatybilność; `MINOR` = nowe komendy/frazy; `PATCH` = poprawki literówek i fraz. Użytkownik z subskrypcją Streamer dostaje aktualizacje presetów; wersja jest widoczna w GUI.

## Licencja

Presety są na **MIT** — tak jak rdzeń. Wysyłając PR, zgadzasz się na licencję MIT i podajesz się w polu `author`. Nie przyjmujemy presetów z zamkniętymi wallhackami, cheatami ani tekstami chronionymi prawem autorskim (imiona postaci, cytaty z filmów).
