# Pre-release checklist — aplikacje (8 aplikacji)

Sprawdzane **na W3**, po tym jak engineer wpięte presety i `saycue presets validate`.
Każda pozycja = polecenie głosowe → oczekiwany efekt na **obu platformach** (Win 10/11 i Linux X11).

## 1. Aplikacje — otwórz/zamknij (`apps-open`)

| Komenda (PL) | target | Windows (exe/AUMID) | Linux (.desktop) | Uwagi |
|---|---|---|---|---|
| „otwórz obs" / „zamknij obs" | obs | `obs64.exe` | `com.obsproject.Studio.desktop` | OBS musi być zamknięty „grzecznie" — użytkownik pyta „czy zapisać?" |
| „otwórz spotify" / „zamknij spotify" | spotify | `Spotify.exe` (Microsoft Store: AUMID `SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify`) | `spotify.desktop` | na Win Store AUMID może być inny — sprawdzić `Get-StartApps` |
| „otwórz discord" / „zamknij discord" | discord | `Update.exe --processStart Discord.exe` | `discord.desktop` | Discord lubi wracać do traya; app.close = zamknięcie okna |
| „otwórz przeglądarkę" / „zamknij przeglądarkę" | browser | `msedge.exe` | `firefox.desktop` | użytkownik może chcieć Chrome — nadpisywalne w GUI |
| „otwórz notatnik" | notepad | `notepad.exe` | `org.gnome.TextEditor.desktop` | na Ubuntu 20.04: `gedit.desktop` |
| „otwórz czat gpt" | chatgpt | `msedge.exe` + URL | `firefox.desktop` + URL | otwiera w przeglądarce (`url`), nie w aplikacji |
| „otwórz steam" | steam | `steam.exe` | `steam.desktop` | — |
| „otwórz pliki" / „otwórz eksplorator" | explorer | `explorer.exe` | `org.gnome.Nautilus.desktop` | KDE: `dolphin.desktop` |

## 2. Narzędzia streamera (`apps-streaming`)

| Komenda (PL) | intent | Oczekiwany efekt | Uwagi |
|---|---|---|---|
| „głośniej" / „ciszej" | system.volume | ±2 kroki głośności systemu | **nie rusza mikrofonu OBS** |
| „wycisz system" / „cisza w kompie" | system.volume | głośność systemu do 0 | **gołe „wycisz" należy do mikrofonu (obs-core)** — patrz §2.3 |
| „otwórz statystyki" | app.open analytics | otwiera dashboard Twitcha w przeglądarce | wymaga zalogowania |
| „otwórz czat" | app.open chat | otwiera popout czatu w przeglądarce | kolizja z „mine otwórz czat" jest rozstrzygana przez dłuższą frazę |
| „otwórz planer" | app.open planer | otwiera kalendarz | — |
| „otwórz mikser" | app.open mixer | Win: `sndvol.exe`; Linux: `pavucontrol` | na Win 11 mixer bywa inną ścieżką — sprawdzić |
| „otwórz notatki" | app.open obsidian | otwiera Obsidian | opcjonalne — tylko jeśli tester ma |
| „przełącz na panel" | window.focus streamdeck | podnosi kartę panelu | sprawdzić na dwóch monitorach |

## 3. Weryfikacja OBS (pod presety aplikacji)

- [ ] OBS ≥ 28 i obs-websocket v5 włączony (Tools → WebSocket Server Settings) → `saycue doctor --json` pokazuje `obs: connected`.
- [ ] Sceny w presejcie `obs-core` (Live / Gameplay / PVP / Starting Soon / BRB / Ending) **istnieją** w OBS testera albo zostały zmapowane w GUI.
- [ ] „wycisz mikrofon" zmienia stan `Mic/Aux`; „mikrofon" przełącza.
- [ ] „nagrywaj"/„stop nagrywania" tworzy plik nagrania; „zapisz replay" zapisuje replay buffer.

## 4. Jak raportować

Wynik idzie do `notes/testers.md` (dziennik testów), kolumna „Komendy 5/5" i „Quote".
Nowa aplikacja → PR do `presets/apps-open` (patrz `docs/presets/CONTRIBUTING.md`).
