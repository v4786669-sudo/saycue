# Handoff t13 → engineer / t9 (integracyjne)

Zadanie: **Parser + akcje OS + OBS (mock)** — deterministyczna warstwa bez żywego
mikrofonu; testy na plikach WAV i atrapie serwera OBS.
Stan: **ukończone, 209 testów zielonych** (tests/parser + tests/actions).
Autor: engineer2, 2026-10-23. Równolegle z t6 (łańcuch audio — nie dotykane).

## 1. Co powstało (mapa plików)

```
src/saycue/parser/
  normalize.py    # W1 normalize() BEZ ZMIAN + nowy normalize_text() (§2.3 pełny:
                  #   NFKC→lower→interpunkcja→fold PL→usunięcie „proszę/hej/asystent/ok")
  fuzzy.py        # rapidfuzz.fuzz.ratio (fallback difflib)
  types.py        # ParseResult (intent, slots, score, matched, source, command_id, origin)
                  # Candidate (widok ASK „czy chodziło ci o…")
  matcher.py      # pyahocorasick (dokładne) + rapidfuzz ≥0.78; dłuższa fraza wygrywa;
                  # szablony "otwórz {target}" / "scena {scene}" z rozwiązywaniem slotów
                  # po słownikach (apps.yaml/presety/sceny); parse() + candidates()
  presets.py      # PresetLoader: presets/<id>/preset.yaml + presets/schema.json (t8);
                  # normalizacja: keybind→keys, obs.record action→state, obs.replay buffer→action
  rules.py        # RulesLoader (data/commands.yaml + data/apps.yaml, JSON Schema 2020-12),
                  # merge rdzeń+presety (aktywacja), ConfigStore + hot-reload
                  # (watchdog, fallback PollingWatcher; błędna konfiguracja NIE podmienia
                  #  działającej — last_error)
  pipeline.py     # IntentParser — punkt integracji t9: parse()/candidates()/
                  # set_active_presets()/watch
  schemas/        # commands.schema.json (z polem hotwords — patrz pkt 4),
                  # apps.schema.json
src/saycue/actions/
  base.py         # kontrakt §3.3: Action / ActionContext(dry_run!) / ActionResult
  registry.py     # Registry + build_default_registry() (11 intencji)
  app_open.py     # Win: Popen (+explorer shell:AppsFolder dla AUMID); Linux: gio launch;
                  # URL w przeglądarce; resolve_app() z aliasami + fuzzy ≥0.78
  app_close.py    # DECYZJA t13: grzeczne zamknięcie — Win: WM_CLOSE przez ctypes
                  # (bez taskkill); Linux: xdotool search --class + wmctrl -ic
  window_focus.py # Win: SetForegroundWindow (ctypes); Linux: xdotool windowactivate
  input_keys.py   # pydirectinput (lazy import) / xdotool key --clearmodifiers;
                  # combo = keyDown wszystkich → keyUp odwrotnie; "shift+x" dzielone na [+]
  system_volume.py# pycaw (lazy) / pactl; sloty direction+step ORAZ delta (format W1)
  obs.py          # ObsClient: obs-websocket v5 bezpośrednio na `websockets`
                  # (Hello→Identify z hasłem→Identified; reconnect z backoffem
                  #  0.5–15 s + 1 retry; timeouty); akcje: obs.scene (w tym
                  #  __next__/__prev__ = cykliczne po GetSceneList), obs.mute,
                  #  obs.record, obs.replay, obs.filter, obs.source_toggle
  win32.py        # ctypes: EnumWindows + QueryFullProcessImageNameW + PostMessageW(WM_CLOSE)
data/
  commands.yaml   # rdzeń = dotychczasowe komendy W1 + hotwords (dodatek engineera)
                  # + open_kalkulator + 2 szablony {target}/{scene}; OBS/apps domyślnie
                  # z PRESETÓW (obs-core/apps-open/apps-streaming)
  apps.yaml       # NOWY: rdzeń mapowania aplikacji (blender, kalkulator, discord+alias dc)
tests/
  conftest.py     # sys.path→src; syntetyczne WAV 16 kHz do tests/fixtures/ (wave z stdlib,
                  # deterministyczne — stand-in nagrań TTS; *.wav jest w .gitignore)
  parser/  test_normalize, test_matcher, test_commands_intent (82 pary tekst→intent,
           w tym 77 pozytywnych — kryterium ≥40 spełnione), test_presets, test_rules,
           test_pipeline, test_fixtures
  actions/ test_registry, test_app_open, test_app_close, test_input_keys,
           test_system_volume, test_obs (MockObsServer = atrapa obs-websocket v5:
           handshake+hasło, 16 testów, w tym reconnect po zerwaniu i __next__/__prev__)
```

## 2. Uruchamianie

```bash
cd saycue && .venv/bin/python -m pytest tests/parser tests/actions -q   # 209 passed
.venv/bin/ruff check src/saycue/parser src/saycue/actions tests/parser tests/actions tests/conftest.py  # clean
```

## 3. NOWE ZALEŻNOŚCI — dopisz do pyproject.toml (ja nie dotykam pliku)

Zainstalowane do .venv (pip 24.0 przywrócony przez `python -m ensurepip`):

| pakiet | wersja | gdzie | uwagi |
|---|---|---|---|
| pyahocorasick | 2.3.1 | `[parser]` extra | już zadeklarowane w pyproject (`parser = [pyahocorasick>=2.0, rapidfuzz>=3.0]`) |
| rapidfuzz | 3.14.6 | `[parser]` | j.w. |
| jsonschema | 4.26.0 (+attrs, referencing, jsonschema-specifications, rpds-py) | **nowe** | walidacja commands.yaml/apps.yaml/presetów; architektura §2.5 wymaga |
| watchdog | 6.0.0 | **nowe** | hot-reload; jest fallback polling (bez watchdog działa) |
| websockets | 17.3 | **nowe** | klient obs-websocket v5 — ZAMIAST obsws-python (decyzja: pełna kontrola reconnectu, §3.4; extra `obs` w pyproject do zmiany: `websockets>=12`) |
| pydirectinput | — (Win) | `[win]` extra | lazy import; **nie instalowałem** (tylko Windows) |
| pycaw | — (Win) | `[win]` extra | lazy import; j.w. |

Systemowe (Linux, bez pip): `xdotool` (keys/focus/close), `wmctrl` (close), `pactl` (volume).
Sugestia extras: `actions = ["python-xlib>=0.33", "watchdog>=4.0", "jsonschema>=4.18", "websockets>=12"]`,
`win = ["pydirectinput>=1.0", "pycaw>=20240210"]`.

## 4. Decyzje implementacyjne (kapitan, 2026-10-23 — uwzględnione)

1. **Presety + aktywacja**: rdzeń + aktywne presety (jedna gra + obs-core + apps-* naraz).
   Identyczna fraza + ten sam intent → **później aktywowany preset wygrywa** (komenda
   wcześniejsza traci TYLko tę frazę); ta sama fraza + inny intent → ValidationError.
   Prefiksy gier („elite/lot/dcs/star/mine") to zwykłe frazy — bez aktywacji gra nie odpowiada.
2. **Konflikty §2.3**: „wycisz mikrofon" > „wycisz" (gołe „wycisz" → mikrofon, NIE głośniki);
   „cisza w kompie" → system.volume (apps-streaming). Zweryfikowane testami na żywych danych.
3. **obs.scene `__next__`/`__prev__`**: cykliczne przełączanie po GetSceneList +
   GetCurrentProgramScene (ObsClient.step_scene(±1)); obs-core działa od razu.
4. **app.close**: WM_CLOSE (ctypes, bez pywin32; procesy z exe+args: „Update.exe
   --processStart Discord.exe" → update.exe i discord.exe); Linux: xdotool search --class
   → wmctrl -ic (polite _NET_CLOSE_WINDOW).
5. `commands.yaml` dostał od engineera pole `hotwords` (bias Whispera) — schema core to dopuszcza.
6. `websockets` sync-client wywoływany z `legacy=True` (ObsClient sam zamyka połączenie).

## 5. Integracja t9 — API

```python
from saycue.parser import IntentParser
p = IntentParser(active_presets=["obs-core", "apps-open", "apps-streaming", "elite-dangerous"])
r = p.parse(tekst)                 # ParseResult|None (score<0.78 → None → ASK: p.candidates(tekst, 3))
p.set_active_presets([...])        # przebudowa matchera (hot-swap gry)

from saycue.actions import build_default_registry, ActionContext, ObsClient
registry = build_default_registry()
obs = ObsClient(host, port, password)   # obs.connect() / obs.close()
ctx = ActionContext(apps=p.config.apps, obs=obs, dry_run=False)
res = registry.execute(r.intent, r.slots, ctx)   # ActionResult(ok, message, error, details)
```

Domyślna aktywacja = sam rdzeń; presety wybiera orchestrator/GUI. Presety wymagające OBS
(`requires.obs`) nie blokują parsowania — obs.* zwracają `ActionResult(ok=False,
error="obs_not_connected")` gdy klient niepodłączony.

## 6. Limity / do weryfikacji

* `obs.source_toggle` w MVP = ToggleInputMute (źródła audio); widoczność scene-itemów
  (alerty/browser) to mapowanie GUI — zostawione t9.
* `pydirectinput` i `pycaw` mają ścieżki live **nieprzetestowane na Windowsie** (testy
  dry-run + planowane cmd; ręczny smoke na maszynie z Windows w W2).
* `window.focus` Linux wymaga WM z EWMH; Wayland — best effort (jak w §3.3).
* `tests/test_asr.py::test_silence_transcribes_empty` (W1, engineera) bywa flaky przy
  pełnym przebiegu, sam przechodzi — poza zakresem t13.
* Fixtures WAV generowane przy pierwszym uruchomieniu testów (deterministyczne, wave stdlib).
* Parser deterministyczny: ten sam tekst = ten sam wynik (testowana własność).
* Szablony `{target}/{scene}` to rozszerzenie rdzenia — presety ich nie używają (schemat t8 bez zmian).
