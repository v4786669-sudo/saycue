#!/usr/bin/env python3
"""Ewaluacja bramki G1: 15 fraz PL → ASR → % poprawnych intencji.

Przebieg:
1. ładuje eval/commands.yaml (15 fraz, PL),
2. dla każdego nagrania eval/recordings/<id>.wav uruchamia ASR
   (faster-whisper small int8, pl, beam=1, initial_prompt z data/commands.yaml),
3. normalizuje transkrypcję (saycue.parser.normalize) i porównuje z frazami:
   dokładnie lub fuzzy (difflib ≥ 0.85) — najlepsze dopasowanie wygrywa,
4. intencja OK ⇔ dopasowana fraza ma TĘ SAMĄ intencję co fraza referencyjna
   (metryka G1: „poprawnie rozpoznane intencje", architektura §7.1),
5. zapisuje eval/results/g1_eval_<ts>.json + wypisuje tabelę.

Próg G1: ≥85% (13/15). Wyjście: 0=go, 1=no-go.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from saycue.asr.whisper import ASREngine  # noqa: E402
from saycue.parser.normalize import fuzzy_similarity, normalize  # noqa: E402

GATE_THRESHOLD = 0.85  # G1: ≥85% poprawnych intencji
FUZZY_MIN = 0.85  # próg „ścisłego" dopasowania frazy (metryka informacyjna)
PARSER_FUZZY_MIN = 0.78  # próg fuzzy parsera, architektura §2.3 (difflib ≥ 0.78)
PARSER_LEV_MAX = 1  # architektura §2.3: levenshtein ≤ 1 na słowach kluczowych


def cpu_info() -> str:
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    import platform

    return platform.processor() or "unknown"


def levenshtein(a: str, b: str) -> int:
    """Odległość Levenshteina dwóch znormalizowanych tekstów (dynamicznie)."""
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def match_phrase(transcript: str, phrases: list[dict], fuzzy_min: float) -> tuple[dict, float, bool]:
    """Najlepsze dopasowanie transkrypcji do fraz.

    Zwraca (entry, score, accepted): accepted=True, gdy dokładne trafienie,
    fuzzy ≥ fuzzy_min lub levenshtein ≤ 1 (reguły parsera, architektura §2.3)."""
    norm = normalize(transcript)
    best, best_score = None, 0.0
    for entry in phrases:
        ref = normalize(entry["phrase"])
        if norm == ref:
            return entry, 1.0, True
        score = fuzzy_similarity(norm, ref) if abs(len(norm) - len(ref)) <= 12 else 0.0
        if score > best_score:
            best, best_score = entry, score
    if best is None:
        return None, 0.0, False
    accepted = best_score >= fuzzy_min or levenshtein(norm, normalize(best["phrase"])) <= PARSER_LEV_MAX
    return best, best_score, accepted


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--recordings", type=Path, default=ROOT / "eval" / "recordings")
    ap.add_argument("--model", default="small", choices=["small", "medium", "tiny"])
    ap.add_argument("--results", type=Path, default=ROOT / "eval" / "results")
    ap.add_argument("--fuzzy-min", type=float, default=FUZZY_MIN)
    args = ap.parse_args()

    commands = yaml.safe_load((ROOT / "eval" / "commands.yaml").read_text(encoding="utf-8"))
    phrases: list[dict] = commands["phrases"]
    recordings: dict[str, Path] = {}
    for entry in phrases:
        wav = args.recordings / f"{entry['id']}.wav"
        if not wav.is_file():
            raise SystemExit(
                f"brak nagrania {wav} — uruchom: python scripts/generate_eval_recordings.py"
            )
        recordings[entry["id"]] = wav

    from faster_whisper.audio import decode_audio

    engine = ASREngine(model_size=args.model, language="pl")
    engine.load()
    print(
        f"CPU : {cpu_info()} | model: faster-whisper {args.model} {engine.compute_type} "
        f"(beam={engine.beam_size}, threads={engine.cpu_threads})"
    )
    print(f"nagrań: {len(recordings)} | próg G1: ≥{GATE_THRESHOLD:.0%} intencji\n")
    print(f"{'id':<8}{'fraza (referencja)':<26}{'transkrypcja':<26}{'dopasowanie':<14}intent")

    rows = []
    t0 = time.perf_counter()
    for entry in phrases:
        pid = entry["id"]
        audio = decode_audio(str(recordings[pid]), sampling_rate=16000)
        result = engine.transcribe(np.asarray(audio, dtype=np.float32))
        matched, score, accepted = match_phrase(result.text, phrases, args.fuzzy_min)
        strict_ok = matched is not None and score >= args.fuzzy_min and matched["id"] == entry["id"]
        # metryka G1: intencja OK ⇔ parser W2 zaakceptuje dopasowanie (exact/fuzzy/lev)
        intent_ok = accepted and matched is not None and matched["intent"] == entry["intent"]
        phrase_ok = matched is not None and matched["id"] == entry["id"]
        rows.append(
            {
                "id": pid,
                "reference": entry["phrase"],
                "reference_intent": entry["intent"],
                "transcript": result.text,
                "matched_phrase": matched["phrase"] if matched else None,
                "matched_intent": matched["intent"] if matched else None,
                "similarity": round(score, 3),
                "intent_ok": intent_ok,
                "phrase_ok": phrase_ok,
                "strict_ok": strict_ok,
                "accepted": accepted,
                "asr_ms": round(result.elapsed_s * 1000, 1),
                "language_probability": round(result.language_probability, 2),
            }
        )
        flag = "OK " if intent_ok else "FAIL"
        match_txt = f"{matched['id']}@{score:.2f}" if matched else "—"
        print(f"{pid:<8}{entry['phrase']:<26}{result.text or '(pusto)':<26}{match_txt:<14}{flag}")

    total_s = time.perf_counter() - t0
    intent_ok_n = sum(r["intent_ok"] for r in rows)
    phrase_ok_n = sum(r["phrase_ok"] for r in rows)
    accuracy = intent_ok_n / len(rows)
    phrase_acc = phrase_ok_n / len(rows)
    strict_n = sum(r["strict_ok"] for r in rows)
    strict_acc = strict_n / len(rows)
    gate = "GO ✅" if accuracy >= GATE_THRESHOLD else "NO-GO ❌"

    print("\n" + "=" * 78)
    print(
        f"G1: {intent_ok_n}/{len(rows)} poprawnych intencji = {accuracy:.1%}  →  {gate} "
        f"(próg ≥{GATE_THRESHOLD:.0%})"
    )
    print(f"frazy dokładne/dopasowane: {phrase_ok_n}/{len(rows)} = {phrase_acc:.1%}")
    print(f"ścisłe (fuzzy ≥ {args.fuzzy_min:g}): {strict_n}/{len(rows)} = {strict_acc:.1%}")
    print(f"czas ewaluacji łącznie: {total_s:.1f} s")

    args.results.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    report = {
        "gate": "G1",
        "ts": stamp,
        "cpu": cpu_info(),
        "model": {
            "engine": "faster-whisper",
            "size": args.model,
            "compute_type": engine.compute_type,
            "beam": engine.beam_size,
            "language": "pl",
            "initial_prompt": bool(engine.initial_prompt),
        },
        "recordings": "piper TTS (pl_PL-gosia-medium) + szum pokoju SNR 15 dB (proxy; "
        "nagrania ludzkie w W4)",
        "threshold_intent": GATE_THRESHOLD,
        "intent_accuracy": round(accuracy, 4),
        "phrase_accuracy": round(phrase_acc, 4),
        "strict_accuracy": round(strict_acc, 4),
        "n_total": len(rows),
        "n_intent_ok": intent_ok_n,
        "gate_passed": accuracy >= GATE_THRESHOLD,
        "rows": rows,
    }
    out = args.results / f"g1_eval_{stamp}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"raport JSON: {out}")
    return 0 if report["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
