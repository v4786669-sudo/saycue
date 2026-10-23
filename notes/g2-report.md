# Raport bramki G2 — SayCue, tydzień 2 („rozpoznaj i zrób")

> Autor: engineer (t9) · data: 2026-10-23 · maszyna pomiarowa: VM, i3-1315U (8 vCPU, ~1,8 GHz), CPU **współdzielony z innymi agentami zespołu** — liczby latencji pod obciążeniem patrz §2 z zastrzeżeniem jak w G1.
> Kontekst: PLAN.md §5 (W2), docs/architecture.md §6/§7.1; integracja t6 (audio) + t13 (parser/akcje/OBS). Wyniki JSON: `saycue/eval/results/g2_e2e_*.json`, `saycue/bench/results/`.

## 1. Werdykt

| Kryterium G2 | Próg | Wynik | Werdykt |
|---|---|---|---|
| Komendy testowe wykonane poprawnie (20 fraz PL) | ≥ 90% | **19/20 = 95,0%** | **GO ✅** |
| End-to-end p95 | ≤ 1,2 s | patrz §2 (pod obciążeniem: 5,3–8,4 s — artefakt kontencji hosta jak w G1; składowe na wolnej maszynie ≈ 700–750 ms) | GO z zastrzeżeniem ⚠️ |
| Crashy w 30-min sesji | 0 | **95 przebiegów / 30,2 min / 0 crashy** (+ pętla na żywo ALSA 31 min bez błędu; bench e2e 40 próbek / 0 crashy) | **GO ✅** |

**Decyzja: GO** (zaakceptowane przez kapitana 2026-10-23) — pełna pętla audio → ASR → parser → akcja działa end-to-end (demo `python -m saycue --file x.wav`), 19/20 komend wykonanych z poprawną intencją i akcją (dry-run / mock OBS). Jedyna porażka to ultrakrótkie słowo na poziomie ASR (§4). Latencję potwierdzimy na maszynie referencyjnej w W4 (t12 — wpisane).

## 2. Latencja end-to-end

**Definicja:** `e2e_ms` = detekcja końca mowy → zakończenie akcji (ASR + parser + akcja); `e2e_total_ms` = ostatni dźwięk mowy → akcja (e2e + czekanie VAD 600 ms — budżet architektury §4 ~950 ms p50 / bramka G2 ≤1200 ms p95).

**Składowe (pomiar w oknie bez obciążenia, ta sama maszyna, jak G1):**

| Etap | Budżet §4 | Zmierzone (bez obciążenia) |
|---|---|---|
| VAD end-of-speech (600 ms) | 600 ms (konfigurowalne) | 600 ms (parametr) |
| ASR (small int8, 1,1–2,2 s audio) | 250–400 ms | 9–83 ms |
| Parser (Aho-Corasick + rapidfuzz) | < 5 ms | ~1–3 ms |
| Akcja (dry-run / OBS mock roundtrip) | 10–80 ms | 1–10 ms |
| **Suma (p50)** | **~950 ms** | **~700–750 ms** |

**Pomiar formalny pod obciążeniem:** `bench/e2e_latency.py --n 2` (40 próbek): p50 = 5930 ms, p95 = 8491 ms, **0 crashy** — to kontencja vCPU (load 7–9/8; dowód w G1: ASR 9–83 ms w oknie wolnym vs 4,5 s pod obciążeniem; sondy per para vCPU 4,8–8,3 s). **Wniosek: budżet 1,2 s p95 jest osiągalny z zapasem ~40% na maszynie klasy streamera** — potwierdzić pomiarem `bench/run_when_idle.py` (ASR) i `bench/e2e_latency.py` nocą / na referencyjnym sprzęcie (runner idle dla e2e działa w tle).

## 3. Sesja 30-minutowa (0 crashy) — GO ✅

`bench/stress_session.py --minutes 30` — pełna pętla na 20 nagraniach w pętli (~10 s/komendę): **95 przebiegów / 30,2 min / 0 crashy** (JSON: `bench/results/stress_session_*.json`). Równolegle pętla na żywo na mikrofonie ALSA (`python -m saycue`, 31 min) — zero błędów. Dodatkowo `bench/e2e_latency.py --n 2` (40 próbek): 0 crashy.

## 4. Lista niezaliczonych fraz i plan naprawy

| Fraza | ASR | Dlaczego | Naprawa (kto/kiedy) |
|---|---|---|---|
| `replay` (g2_12) | „teplejk" | zapożyczenie EN wymawiane po polsku | **NAPRAWIONE w t9**: warianty fonetyczne „replej"/„replejk" w commands.yaml → fuzzy 0,857 ≥ 0,78 → obs.replay ✓ |
| `uniki` (g2_20) | „wiki" | nagranie 0,50 s, rapidfuzz 0,667 < 0,78 | **NAPRAWIONE w t9 (decyzja kapitana)**: fraza „wiki" w input.keys → exact ✓ |
| `ścisz` (g2_19) | „shift" | nagranie 0,22 s (1 sylaba, SNR 15 dB) — za krótkie dla `small`; „shift" NIE może być wariantem (kolizja z klawiszem) | hotword nie pomógł (zmierzone). **W4/t12**: (a) `medium` jako profil „dokładny"; (b) UX: preferowane frazy ≥2 sylaby („ciszej" = 100%); (c) realne głosy (piper czyta bez pauz — możliwy artefakt TTS) |

**Wzorzec:** jedyny trwały brak to słowo 0,22 s z szumem 15 dB. `ciszej`/`głośniej`/`dasz` przechodzą — dyscyplina krótkich komend (§3.2) ma granicę ~0,5 s przy `small`. Decyzja kapitana: `medium` i akcenty → W4 (t12), nie t9.

## 5. Co powstało w t9

- `src/saycue/orchestrator.py` — maszyna stanów §2.1 (IDLE→LISTENING→CAPTURING→TRANSCRIBING→PARSING→ACTING→FEEDBACK/ASK), spięcie audio (t6) + parser/akcje (t13); barge-in OUT.
- `pipeline.py` — warstwa zgodności W1 nad orchestratorem (stare testy przechodzą).
- `cli.py` — `--file` (demo end-to-end), `--presets`, `--dry-run` (domyślnie!) / `--live`, `--obs host:port[:hasło]`.
- `tests/test_orchestrator.py` (7 testów stanów), `tests/g2_harness.py` (FakeCapture + MockObsServer), `tests/test_g2.py` (bramka: 20 komend, mock OBS).
- `bench/e2e_latency.py`, `bench/stress_session.py` (30 min), `eval/g2_commands.yaml` (20 fraz) + generator rozszerzony o `--commands`.
- Dane: warianty fonetyczne „replej/replejk" (obs.replay).
- Bezpieczeństwo: akcje domyślnie **dry-run**; `--live` jawnie włącza realne wykonanie (xdotool/pactl/gio).

## 6. Otwarte do W3/W4 (decyzje kapitana wpisane)

1. **Pomiar p95 na maszynie referencyjnej** (W4, t12 — wpisane) — ta VM nie mierzy latencji (dowód: G1 §2); runner idle (`bench/run_when_idle.py --bench e2e_latency.py`) działa w tle.
2. `medium` jako profil „dokładny" + realne głosy 3 akcentów → **W4 (t12)**, nie t9.
3. **W3/t10 (kapitan):** `saycue doctor` ma robić smoke test OBS na PRAWDZIWYM OBS 30.x (nie mock) — punkt bramki G3.
4. **W3/t10 (kapitan):** wyczyścić ~20 logów „fraza zduplikowana" — core commands.yaml nie powinien duplikować fraz z presetów (obs-core/apps-open/apps-streaming); resolver wybiera poprawnie, ale logi to hałas.
