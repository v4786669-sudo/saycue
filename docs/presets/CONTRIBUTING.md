# Contributing — presety SayCue

Presety to **dane, nie kod** (architektura §2.5). Nowy preset to katalog z `preset.yaml`. Bez commitów w `src/`, bez zależności Pythona, bez zmian w rdzeniu.

Gdzie szukać: `presets/README.md` (format) i `presets/schema.json` (kontrakt). Ten plik mówi: jak zrobić PR, co odrzucimy i jak działa walidacja.

---

## 1. Szybki start

```bash
# 1) skopiuj wzorzec
cp -r presets/obs-core presets/<twoj-id>

# 2) zmień id/name/game w preset.yaml (id MUSI być równe nazwie katalogu)

# 3) z waliduj
python3 presets/validate.py presets/<twoj-id>
# → 1 presetów, 0 błędów, 0 ostrzeżeń  OK
```

Po W3 ta sama walidacja działa w aplikacji: `saycue presets validate presets/<twoj-id>`.

## 2. Format pliku (skrót)

```yaml
id: <twoj-id>              # = nazwa katalogu
version: 1.0.0             # semver
name: Czytelna nazwa
kind: game                 # game | obs | apps
platforms: [win]           # win | linux-x11 | linux-wayland | macos
game: nazwa_do_events      # tylko kind=game (trafia do events.jsonl: preset_missing)
author: twoj-pseudonim
license: MIT
requires: { obs: false }   # obs: true gdy preset używa intencji obs.*
phrases: ["...", ...]      # ≥5 słów kluczowych (initial_prompt dla Whisper)
commands:
  - id: snake_case
    intent: input.keys     # app.open | app.close | input.keys | system.volume |
                           # obs.scene | obs.mute | obs.record | obs.replay |
                           # obs.source_toggle | window.focus
    phrases: ["...", "..."] # 3–6 wariantów, PL na początku, potem EN
    slots: { keybind: bind_name }
```

Pełny kontrakt pól: `presets/schema.json` (JSON Schema draft 2020-12, `additionalProperties: false`).

## 3. Zasady fraz (to jest najważniejsze)

1. **Dłuższa fraza wygrywa** (§2.3). Jeśli chcesz wyciszyć mikrofon, fraza musi być **„wycisz mikrofon"** — gołe „wycisz" należy do głośności systemu.
2. **10–20 komend na preset**, 3–6 wariantów na komendę, **PL najpierw**, potem EN.
3. **Frazy powtarzalne między presetami gier są OK** wtedy, gdy używasz **prefiksu gry** (`elite podwozie`, `star podwozie`, `lot podwozie`, `dcs podwozie`, `mine kucnij`) — aktywacja = jedna gra + presety uniwersalne (OBS, aplikacje).
4. **Bez gerundów i zdań złożonych.** „przełącz scenę na pvp" → „scena pvp".
5. **Bez jednosylabowych słów** („on", „up", „stop"), które kolizją z mową w tle.
6. Frazy są **normalizowane przy ładowaniu**: małe litery, fold diakrytyków (ą→a), bez interpunkcji — walidator liczy kolizje po normalizacji.

## 4. Czego nie przyjmujemy (od razu odrzucimy PR)

| Odrzucenie | Powód |
|---|---|
| dowolny plik `.py/.sh/.bat/.ps1/.exe/.js` w katalogu presetu | preset nie może być kodem (§2.5, walidacja S3) |
| sekwencje/makra w grze (np. „fire combo", „auto-docking") | ryzyko banów anti-cheat — PLAN.md §3 |
| komendy `risk: high` bez uzasadnienia | rdzeń wymaga potwierdzenia głosem (§9) |
| fraza zduplikowana w tej samej aktywacji (bez prefiksu gry) | walidacja S4 |
| brak wariantów EN / brak jakiejkolwiek frazy PL | walidacja/reguła W1 |
| imiona postaci, cytaty filmowe, marki w nazwie presetu | prawa autorskie — preset ma być neutralny |
| preset bez informacji, **skąd pochodzą bindy** (domyślne ustawienia gry? własne?) | brak możliwości odtworzenia |

## 5. Co walidator egzekwuje

```
błąd:   schema (typy, wzorce, wartości enum), id == katalog, brak kodu w katalogu,
        3–6 fraz, unikalność fraz w aktywacji, ≥5 w phrases, sloty zgodne z intencją
warn:   brak frazy PL w komendzie, kolizja podciągów między intencjami
```

Uruchom: `python3 presets/validate.py --json` (do CI).

## 6. Jak zrobić PR

1. Fork + gałąź `preset/<id>`.
2. Katalog `presets/<id>/` z `preset.yaml` (+ opcjonalny `README.md` z listą bindów).
3. `python3 presets/validate.py presets/<id>` → OK **z 0 ostrzeżeń**.
4. PR: tytuł `preset(<id>): <nazwa>`. W opisie: **gra i wersja**, **skąd bindy**, **jak testowałeś**, **jakimi słowami mówisz** (PL i EN).
5. Reviewer sprawdza: frazy realne, brak kolizji, licencja MIT. Merge = wersja MINOR.
6. Preset **nie wymaga release'u aplikacji** — będzie dostępny w trybie PR do presetów (rytm tygodniowy, §2.5).

## 7. Wersjonowanie

| Zmiana | Wersja |
|---|---|
| nowe komendy / nowe frazy | MINOR |
| poprawki literówek, lepsza fraza | PATCH |
| zmiana formatu (intencje, sloty) | MAJOR + uzgodnienie z maintainerem |

## 8. Licencja i autorstwo

Wysyłając PR akceptujesz licencję **MIT** i wpisujesz się w `author`. Presety zewnętrzne (np. płatne voice packi) **nie są przyjmowane** — także ich frazy.
