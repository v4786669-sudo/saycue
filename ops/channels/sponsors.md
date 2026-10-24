# Sponsoring — GitHub Sponsors + Patreon (przygotowanie na tydzień 0)

> Tiery wsparcia i kanały płatności.
> **Stan faktyczny:** konta zakłada się dopiero wtedy, gdy repo jest publiczne — dziś przygotowujemy treść i strukturę, żeby w momencie publikacji wkleić je w 15 minut.

## Dwie platformy, dwa różne zadania

| Platforma | Rola | Prowizja | Uwagi |
|---|---|---|---|
| **GitHub Sponsors** | naturalne dla OSS: „wspieram projekt, nie kupuję produktu" | **0% dla konta osobistego**, do 6% dla organizacji (3% karta + 3% GitHub) — [docs.github.com](https://docs.github.com/en/sponsors/getting-started-with-github-sponsors/about-github-sponsors) | wypłata wymaga zamieszkania w kraju z listy — Polska jest na liście; płatności jednorazowe też |
| **Patreon** | wsparcie z treści beta i społeczności | prowizje platformy + processing; poziom dla nas bez znaczenia przy ~10–30 patronach | dobre dla osób spoza Gita; wymaga konsekwencji w publikacji |

**Wybór:** **GitHub Sponsors jako główny** (0%, zero tarcia, jest tu, gdzie leży kod), **Patreon jako alternatywa dla ludzi spoza GitHub-a**. Nie budujemy własnego systemu płatności dla wsparcia.

## Tiery (treść wpisywana do Sponsors / Patreon)

| Tier | Cena | Co daje (nazwa: co konkretnie) | Co mówimy wprost, czego NIE daje |
|---|---|---|---|
| **Kibic** | **15 zł/mies.** | dostęp do `#beta` na Discordzie; imię w `SPONSORS.md` (opcjonalnie); wczesny dostęp do prognoz roadmapy | żadnych funkcji, których nie ma w MIT; żadnych presetów |
| **Patron** | **25 zł/mies.** | beta buildy przed publicznym release'em; głos w kolejności przy 3 największych propozycjach; priorytet w `#beta` | nie daje Streamer Packa (to sprzedaż, nie sponsoring) |
| **Sponsor** | **40 zł/mies.** | to co wyżej + Twoje imię w trzech miejscach: `SPONSORS.md`, devlogu YT, README; jednorazowy „preset na życzenie" (jeden, wykonany przez nas) | nie jest to faktura B2B, brak SLA |
| **Jednorazowe** | dowolna kwota | podziękowanie w `SPONSORS.md` | j.w. |
| **Organizacja** | rozmowa | możliwość wskazania priorytetu (bez gwarancji terminu) | brak prawa veta nad kierunkiem; bez wsparcia premium |

**Zasada twarda:** sponsoring nigdy nie odbiera nic z darmowego rdzenia i nigdy nie jest „paywall z torebką powstrzymującą". Jeśli musimy używać „patron staje się klientem", to znaczy, że oferta jest źle zbudowana.

## Jednorazowy pakiet dla Sponsorów — pod co go realizować

Zamiast obiecywać feature'y: **sponsor może zażyczyć jeden preset** (gra/OSB/aplikacja z listy zgłoszeń). Koszt po naszej stronie to 0,2 h pracy w YAML (architekt §2.5). To realna, nielimitowana wysoka wartość przy niskim koszcie — i nie tworzy długu technicznego.

## Treść nagłówka GitHub Sponsors (kopiuj-wklej)

> **SayCue** — offline'owy asystent głosowy dla streamerów. Mówisz: „scena pvp", „wycisz", „zapisz replay" — OBS reaguje w sekundę. Zero chmury, zero AI w ścieżce sterowania, rdzeń MIT.
>
> Co finansujesz: presety gier i OBS (każdy to praca kuratorska, nie tylko kod), obsługa 5 testerów na winorośli i pierwsze tysiące instalacji, testy na akcentach i hałasie.
>
> Co dostajesz: wczesny dostęp do bety, głos w kolejności funkcji, imię w `SPONSORS.md`. **Nie dostajesz** zamkniętych funkcji — rdzeń zawsze MIT.

## Treść „celu" (Patreon)

> **Cel 1: 500 zł/mies.** — pokrywa dwóch testerów sprzętu (Windows + Linux X11) i presety dla nowych gier.
> **Cel 2: 1 500 zł/mies.** — utrzymuje autora przy tabletce na wsparcie: `doctor` CLI i FAQ aktualizowany co tydzień (koszt wsparcia to ryzyko nr 1 tego projektu).
> **Cel 3: 3 000 zł/mies.** — pozwala na dedykowany lineał „medyczny" (dyktowanie + komendy EHR) — tylko po opinii prawnej MDR.

## Zaimplementowanie konta (checklista)

- [ ] GitHub Sponsors: ustawienia konta osobistego → Sponsors → profil + tier'y; dodać `FUNDING.yml` (`github: …`, `patreon: …`) do repo.
- [ ] `SPONSORS.md` (lista patronów, opcja anonimowości) w repozytorium.
- [ ] Patreon: ustawić walutę **PLN**, tier 15/25/40, spójne opisy (jak wyżej).
- [ ] Role Discord: `@patron-15/25/40` + uprawnienie do `#oferty-wsparcia`.
- [ ] Test płatności: 1 zł przez stronę; sprawdzić, czy wypłata trafia do banku.
- [ ] Odnotować datę założenia kont i pierwszy kamień (0 patronów → X).

## Co mierzymy (obserwujący → patroni, próg 1%)

- liczba obserwujących repo (GitHub API `GET /repos/{owner}/{repo}` → `subscribers_count`),
- liczba patronów (Sponsors API / ręcznie co tydzień),
- przelicznik: `patroni / followers`. **Próg 1% = kanał ma sens, <0,3% = wyłączyć i przenieść energię do presetów.**
