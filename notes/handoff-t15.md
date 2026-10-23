# Handoff t15 → t9/orchestrator + właściciel docs (v0.3)

Zadanie: **utwardzenie parsera R-01/R-02 + dedup fraz** (findingi HIGH z t11).
Stan: ukończone na bazie 096f4d8 (WIP engineera — zachowany, uzupełniony do spec).
Autor: engineer2. Zielone: 157 testów parsera (w tym 15 regresji R-01/R-02/gramatyki),
257 testów całego repo bez markeru `models`, ruff clean.

## 1. Co się zmieniło (src/saycue/parser/ + tests/parser/)

| Plik | Zmiana |
|---|---|
| normalize.py | `normalize_verbose() -> (norm, removed_fillers)` — diagnostyka R-01: TYLKO tokeny ze stałego słownika FILLER_TOKENS (prosze/hej/asystent/ok), nigdy treść mowy → bezpieczne dla events.jsonl. `normalize_text()` bez zmian w zachowaniu (fillery tylko z początku — fix z 096f4d8 zachowany) |
| matcher.py | Parametry `min_phrase_coverage=0.7` (R-01: dokładna fraza musi pokryć ≥70% tokenów wypowiedzi — zastępuje pozycyjne „full coverage" z WIP, zgodnie ze spec v0.3), `allow_free_text=True` (wyjątek dla szablonów z wolnym slotem — slot konsumuje wolne tokeny), `min_action_score=0.8` (z WIP). `ParseResult.rewritten_fillers`. `Candidate.actionable` + `Candidate.allowed_values` (ASK z listą dozwolonych wartości, R-02) |
| slots.py | `SlotResolver.allowed(slot)` — posortowana lista dozwolonych wartości dla widoku ASK |
| types.py | `ParseResult.rewritten_fillers: tuple[str,...]`; `Candidate.actionable: bool`, `Candidate.allowed_values: tuple[str,...]` |
| pipeline.py | `IntentParser` przepuszcza `min_action_score` / `min_phrase_coverage` / `allow_free_text` do Matchera (pokrętła dla GUI) |
| tests/parser/test_review_regressions.py | +9 testów v0.3: parametr pokrycia (66.7% odrzucone, 75% przyjęte, próg 1.0 = pełne), allow_free_text (free vs strict), rewritten_fillers (tylko tokeny słownika), actionable/allowed_values w ASK, przypięte zachowanie „otworz spotify proszę" → ASK |
| tests/parser/test_grammar_consistency.py | NOWY: (c) brak duplikatów fraz core↔presety (obs-core/apps-open/apps-streaming), unikalność fraz w rdzeniu, pokrycie zestawów G1 (eval/commands.yaml) i G2 (eval/g2_commands.yaml) przez scaloną gramatykę — deterministyczna symulacja parsera BEZ ASR/modeli |

## 2. Semantyka utwardzona (kontrakt dla orchestratora/t9)

1. **R-01**: fillery usuwane TYLKO z początku wypowiedzi; dokładne dopasowanie
   wymaga pokrycia ≥70% tokenów; szablony slotów wyłączone z reguły
   (allow_free_text). „…na spotkanie o 8" / „powiedz scena pvp" / „daj mi
   ciszej muzykę w tle" → NIGDY akcja.
2. **R-02**: wykonanie wymaga score ≥ min_action_score=0.8 (fuzzy w
   [0.78, 0.8) → ASK); nierozpoznana wartość slotu szablonu → parse()=None,
   kandydat z `actionable=False` i `allowed_values` (np. „scena 3" → ASK
   z listą scen, „otworz spoty fi" → ASK z listą aplikacji).
3. **Konsekwencja przypięta testem**: „otworz spotify proszę" (filler na
   końcu) → ASK — szablon z surową wartością „spotify prosze" NIE przepada
   na fuzzy (determinizm; gdyby UX wymagał tolerancji, zmiana jest świadoma,
   w matcher.py `_match_template`/`parse`).
4. Fuzzy NIE ma dodatkowej bramki pokrycia — ratio ≥0.8 na całym zdaniu
   samo wymusza duże pokrycie (G2 toleruje szum ASR: „otworz spotify teraz"
   → fuzzy 0.81 → akcja). Dokładne + szablony pokryte regułą 70%.

## 3. Dedup fraz

Potwierdzone testem `test_no_phrase_duplicates_between_core_and_presets`:
rdzeń (data/commands.yaml) nie zawiera już żadnej frazy z obs-core/apps-open/
apps-streaming (21 fraz usuniętych w 096f4d8). Zestawy G1 (15 fraz) i G2
(20 fraz) w całości pokrywa scalona gramatyka przy aktywacji
[obs-core, apps-open, apps-streaming, elite-dangerous] — test
test_grammar_consistency.py (bez modeli; pełny eval ASR: eval/run_eval.py,
test_g2.py z markerem models).

## 4. Dla właściciela docs

Architektura v0.3 §2.3 (nie istnieje jeszcze w repo — t11 nie zdążył jej
zapisać) powinna odzwierciedlać: `min_phrase_coverage=0.7` (tokeny),
`allow_free_text` dla szablonów, `min_action_score=0.8`, `rewritten_fillers`
= licznik/tokeny stałego słownika (nigdy treść mowy), ASK z allowed_values.

## 5. N-01 (researcher → t17 → engineer2): frazy gier przeniesione z rdzenia

Decyzja (2026-10-23, właściciel parsera/danych): **pełne usunięcie press_dash z
rdzenia** (opcja researchera nr 2 — rdzeń to OBS/apps/system, klawisze gier =
presety; gołe „dash" w rdzeniu cieniowało bindy T2/HOTAS i odpalało shift+space
w symulatorach lotu przy mishearze ASR).

Zmiany:
* `data/commands.yaml` — press_dash (dasz/uniki/shift dash/dash/wiki) USUNIĘTY z rdzenia;
* `presets/arcade-dash/preset.yaml` — NOWY preset (kind: game, bez pola `game`):
  te same 5 fraz, slots keys [shift, space]; aktywny tylko gdy gracz chce;
* `presets/index.json` — przegenerowany (validate.py --index, 0 błędów);
* aktywacje zaktualizowane: tests/test_g2.py ACTIVE_PRESETS, tests/conftest.py
  RECOMMENDED_PRESETS, test_grammar_consistency G2_ACTIVATION (+ dedup vs
  WSZYSTKIE presety z katalogu).

Efekt (zweryfikowany): bez arcade-dash „dash" → None (ASK); z arcade-dash
wszystkie 5 fraz działa (origin=arcade-dash); „podwozie" z dcs → ASK z
„dcs podwozie" (0.8) na 1. miejscu. G1/G2 YAML-e eval NIE ruszane — frazy
zapewnia preset w aktywacji bramki.

ASR/PROMPT (dla engineera — cli/orchestrator to Twoje moduły): load_initial_prompt
czyta tylko data/commands.yaml, więc po przeniesieniu frazy straciły bias.
ZMIERZONE na G2: (1) prompt = core-only → g2_20 „uniki"→„wyjki" (fail);
(2) prompt = wszystkie frazy aktywne (~220 fraz) → DEGENERACJA greedy (14/20:
„otwórz"→„tłuszcz", „cisza"→„tisha" — zgodne z ostrzeżeniem z G1 o nadmiernym
biasie); (3) prompt = rdzeń + arcade-dash (= dokładnie dawny zestaw) → baseline
16/20 (wariancja ASR 16–20/20, porażki = krótkie frazy PL: tisze/shift/zana —
ta sama klasa co w raporcie G2 §4). Sugestia: prompt = frazy rdzenia + frazy
aktywnych presetów NIE-growych lub krótkich (≤2 tokeny) — do pomiaru w W4;
hotwords bez zmian (≤3 słowa).
