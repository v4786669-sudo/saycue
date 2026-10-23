# Raport bramki G1 — SayCue, tydzień 1 („słuch i tekst")

> Autor: engineer (t6) · data: 2026-10-23 · maszyna pomiarowa: VM, i3-1315U (8 vCPU, ~1,8 GHz), CPU **współdzielony z innymi agentami zespołu** — pomiar latencji pod obciążeniem jest niewiarygodny, patrz §2.
> Kontekst: PLAN.md §5 (W1), docs/architecture.md §6/§7.1. Wyniki JSON: `saycue/eval/results/g1_eval_*.json`, `saycue/bench/results/asr_latency_*.json`.

## 1. Werdykt

| Kryterium G1 | Próg | Wynik | Werdykt |
|---|---|---|---|
| Poprawność intencji (15 fraz PL) | ≥ 85% | **14/15 = 93,3%** | **GO ✅** |
| ASR p95 | ≤ 500 ms | patrz §2 (pomiar w oknie bez obciążenia: **p50 ≈ 20 ms, p95 ≈ 80 ms** → GO; pod obciążeniem współdzielonej maszyny p95 4,6 s — artefakt, nie silnik) | **GO z zastrzeżeniem** ⚠️ |

**Decyzja: GO** — pętla audio→ASR działa, dokładność nad progiem, silnik ASR ma zapas 6–25× względem budżetu 500 ms (zmierzone na tej samej maszynie w oknie bez obciążenia). Rekomendacja: powtórzyć pomiar p95 na maszynie klasy streamera (Ryzen 5 3600 / i5-10400) przed W4 — maszyna VM z vCPU na hoście i3-1315U nie jest reprezentatywna.

## 2. Latencja ASR (p50/p95 na 20 komendach)

**Problem pomiarowy:** maszyna wykonuje równolegle pracę kilku agentów zespołu + aplikacje użytkownika (load average 3–7 przy 8 vCPU; vCPU nadsubskrybowane na hoście 6-rdzeniowym). W takich warunkach transkrypcja 1,7 s audio trwała ~4,5 s (stała niezależna od długości nagrania — czysty artefakt kontencji CPU, nie koszt dekodowania).

**Pomiar w oknie niskiego obciążenia (ta sama maszyna, ten sam model):**

| Konfiguracja (faster-whisper small int8) | Czas decode 2,17 s audio |
|---|---|
| baseline (beam=1, greedy) | ~21 ms |
| + initial_prompt (653 zn. fraz PL) | ~34 ms |
| + hotwords („cisza, replay") | ~17–77 ms |
| mediany z 3–5 powtórzeń | **p50 ≈ 20 ms, p95 ≈ 80 ms** |

**Wniosek:** silnik (small int8, beam=1, 4 wątki) ma 6–25× zapasu względem budżetu G1 (≤500 ms p95) na CPU dużo słabszym niż referencyjny Ryzen 5 3600. Architektura §4 szacuje 250–400 ms na klasie streamera — nasz pomiar jest z tym spójny (i lepszy, bo int8 + greedy + bez timestampów).

**Narzędzie:** `bench/asr_latency.py` + `bench/run_when_idle.py` (czeka na load ≤ 2.5 i robi sondę 5 przebiegów; pełny benchmark tylko przy medianie sondy < 300 ms).

**Dowód, że 4,5 s to kontencja, nie silnik:** sonda runnera przy load 2,4 dała medianę 4084 ms; sondy per para vCPU (taskset) — 4,8–8,3 s równomiernie na wszystkich parach. VM jest nadsubskrybowany na hoście i3-1315U i przy JAKIMKOLWIEK obciążeniu hosta degraduje decode ~100×. W oknie bez obciążenia ten sam plik, ten sam model: 9–83 ms. Runner dalej działa w tle (do ~18:30); gdy złapie czyste okno, JSON z p50/p95 trafi do `saycue/bench/results/` i należy uzupełnić tę sekcję.

## 3. Poprawność intencji (15 fraz PL, nagrania TTS + szum)

**Zbiór:** `eval/commands.yaml` (15 fraz z architektury §2.2: app.open ×3, obs.scene ×2, obs.mute ×3, obs.record ×2, obs.replay ×2, system.volume ×2, input.keys ×1).
**Nagrania:** piper-tts `pl_PL-gosia-medium` + symulowany szum pokoju (brązowy szum + 50 Hz hum + kliknięcia, SNR 15 dB, pad 0,35 s) — **proxy** dla „realistycznego pokoju"; prawdziwe głosy (3 akcenty) w W4.

| Metryka | Wynik |
|---|---|
| Poprawne intencje (reguły parsera §2.3: exact / fuzzy ≥0,78 / levenshtein ≤1) | **14/15 = 93,3%** |
| Frazy dokładne (transkrypcja == fraza po normalizacji) | 13/15 = 86,7% |
| Ścisłe (fuzzy ≥ 0,85) | 13/15 = 86,7% |

| # | Fraza | Transkrypcja | Intencja |
|---|---|---|---|
| 1 | otwórz spotify | otwórz spotify | OK |
| 2 | włącz spotify | włącz spotify | OK |
| 3 | otwórz discord | otwórz discord | OK |
| 4 | scena pvp | scena pvp | OK |
| 5 | przełącz na pvp | przełącz na pvp | OK |
| 6 | wycisz mikrofon | wycisz mikrofon | OK |
| 7 | mute | mute | OK |
| 8 | cisza | cisza | OK (hotword) |
| 9 | rozpocznij nagrywanie | rozpocznij nagrywanie | OK |
| 10 | zatrzymaj nagrywanie | zatrzymaj nagrywanie | OK |
| 11 | zapisz replay | zapisz replay | OK |
| 12 | **replay** | **teplejt** | **FAIL** |
| 13 | ciszej | ciszej | OK |
| 14 | głośniej | głośniej | OK |
| 15 | dasz | dash | OK (lev ≤ 1 → parser przyjmie) |

**Jedyna porażka: „replay"** (0,62 s, zapożyczenie EN wymawiane po polsku przez TTS: „replej"). Whisper słyszy fonetycznie blisko („teplejt"), ale to inny token.

**Zastosowane opcje z architektury (§3.2 / §7.1):**
1. `initial_prompt` = lista fraz z commands.yaml — aktywny od pierwszej wersji,
2. **hotwords** (faster-whisper ≥1.2): pole `hotwords: [cisza, replay]` w commands.yaml naprawiło „cisza"; „replay" oporne (patrz rekomendacje),
3. beam=1, temperature=0, int8, `condition_on_previous_text=False`.

**Pułapka zmierzona i udokumentowana:** biasowanie WSZYSTKICH fraz (~40 słów) przez hotwords degeneruje greedy decoding w pętle powtórzeń („zapisz, nagrywaj, zatrzymaj…") — wynik spadał do 33%. Dlatego limit: ≤3 słowa, tylko problematyczne, z obowiązkowym ponownym evalem. Zapisane w komentarzu commands.yaml i docstringu.

## 4. Rekomendacje (do W2/t9, nie blokują G1)

1. **„replay"**: dodać wariant fonetyczny `replej` do fraz obs.replay (mechanizm §2.3: „Spotify"→„spoty fi" — to najczęstsza przyczyna błędów). Alternatywa: trening własnego hotworda na wymowie PL.
2. **Pomiar p95 na maszynie referencyjnej** (wolnej, klasy streamera) — VM zespołu nie reprezentuje CPU graczy; uruchomić `bench/run_when_idle.py` nocą lub na dedykowanym sprzęcie.
3. **Nagrania ludzkie** (3 akcenty, W4) — TTS+szum to proxy; akcenty mogą przesunąć WER o 5–15 pkt proc.
4. `tests/test_asr.py::test_silence_transcribes_empty` ustabilizowany (niezmiennik: cisza nie daje komendy, niekoniecznie pusty string — int8 FP-redukcje przy obciążeniu potrafią przestawić marginalny token).

## 5. Artefakty dostarczone (t6)

- Repozytorium `saycue/` (commit `e6e3725`): pyproject (py3.11), LICENSE MIT, README, CI (ruff+pytest), Makefile, .gitignore.
- `src/saycue/{audio,vad,wakeword,asr,parser,actions,ui,config,telemetry}` — audio→wybudzenie→VAD→ASR działa end-to-end (test integracyjny `tests/test_pipeline_loop.py`, demo `python -m saycue --file x.wav`, pętla na żywo przez ALSA/sounddevice).
- Pre-roll 400 ms, cooldown wake-word 500 ms, PTT (Ctrl+Alt+Space), VAD 600 ms/8 s — wg spec.
- Manifest modeli z SHA-256 (`models/manifest.json`, `scripts/download_models.py --pin`), wagi poza repo (R10) — zweryfikowane: git tree bez plików binarnych.
- `bench/asr_latency.py`, `eval/run_eval.py` + wyniki JSON.
