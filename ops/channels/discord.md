# Discord — struktura serwera SayCue (tydzień 0)

> Struktura serwera wsparcia: kanały beta i presetów, zgłaszanie błędów, tryb PR do presetów.
> Cel: **mieć miejsce, do którego prowadzi landing i posty, zanim będzie produkt**. Puste kanały nie szkodzą; brak kanałów = utracony ruch z W4.

## Uprawnienia (minimalnie)

- Kanały `#regulamin` i `#status` — **tylko do odczytu** dla członków poza modem (read-only announcement).
- Reszta — pisanie dla wszystkich, którzy zaakceptowali regulamin (bramka reakcyjna albo role).
- Tylko moderatorzy (`@maintainer`) mogą oznaczać `@everyone` (żadnych masowych pingów).
- Boty: żadne (albo tylko jeden do powiadomień GitHuba — do decyzji po W2).

## Kanały (kolejność = kolejność wyświetlania)

| # | Kanał | Typ | Opis (topic) |
|---|---|---|---|
| 1 | `#regulamin` | read-only | „Bądź człowiekiem. Zero pytań o makra omijające anticheat. Zero treści medycznych — to nie produkt medyczny." |
| 2 | `#status` | read-only announce | „Kamienie milowe, release notes, okna serwisu." |
| 3 | `#powitanie` | opis kanału, nie kanał | (zostawiamy w onboarding flow) |
| 4 | **`#beta`** | dyskusja | „Testujesz? Tu zgłaszasz błędy i pytania o buildy. Wersja + system + `saycue doctor --json`." |
| 5 | **`#presets`** | dyskusja | „Presety YAML: propozycje, popisy, zgłoszenia braków. PR do repo albo plik tutaj." |
| 6 | `#obs-i-streaming` | dyskusja | „Sceny, mute, replay, obs-websocket — konfiguracje i gotowe pomysły." |
| 7 | `#showcase` | dyskusja | „Twoje setupy, overlaye, wideo. Zgoda na pokazanie = zgoda na użycie w devlogu." |
| 8 | `#pomysly` | dyskusja | „Pomysły na funkcje. Zanim napiszesz: czy to mieści się w obecnym zakresie?" |
| 9 | `#oferty-wsparcia` | read-only | „Sponsorzy i patroni: statusy wieczoru. Bez sprzedaży w DM." |
| 10 | `#mod` | prywatny | „Moderacja, zgłoszenia, decyzje." |

## Role

| Rola | Kto | Uprawnienia |
|---|---|---|
| `@maintainer` | opiekun projektu | wszystko, pin messages |
| `@contributor` | osoby z zaakceptowanym PR presetów | pisanie we wszystkich kanałach publicznych |
| `@beta-tester` | **5 testerów W3 + osoby z W4** | `#beta` priorytet, dostęp do buildów |
| `@patron-15` / `@patron-25` / `@patron-40` | z Patreon (rola nadawana ręcznie lub przez bota) | `#oferty-wsparcia` + wzmianka w roadmapie |
| `@everyone` | wszyscy | pisanie w kanałach dyskusyjnych |

## Onboarding (3 kroki, wklejane w `#regulamin`)

1. **Przeczytaj „czego nie robimy"**: to asystent komend, nie AI; nie zrobimy makr do gier z anty-cheat; nie jesteśmy produktem medycznym.
2. **Powiedz, po co jesteś**: beta-tester / preset / OBS / zwykły ciekawski. Jedno zdanie w `#powitanie` (kanał do utworzenia po pierwszym tygodniu, gdy będzie ruch).
3. **Testujesz?** W `#beta` napisz system + wersję + wynik `saycue doctor --json`. To najszybsza droga do naprawy.

## Zasady moderacji (wpisać do regulaminu)

- **Bez reklam i bez DM do członków.** Sprzedaż sponsorów wyłącznie w `#oferty-wsparcia`.
- **Bez treści medycznych i bez porad lekarskich.** Medycyna to etap 2 i nie tu.
- Wsparcie tylko asynchroniczne: wątek lub zgłoszenie. Nie robimy „onboarding calls" poza wersją Streamer.
- Publikujemy logi tylko jeśli się zgodzisz — i w formie `doctor --json` (bez transkrypcji).

## Czego NIE tworzymy na start

- `#ogolny` zamiast tematycznych (rozmywa sygnał, który potrzebujemy do bramki).
- Automatycznych botów „welcome + ticket" — to koszt utrzymania, zanim mamy użytkowników (koszt wsparcia = ryzyko nr 1).
- Kanału `#medycyna` — byłby zaproszeniem do tematu, którego prawnie nie obsługujemy.
