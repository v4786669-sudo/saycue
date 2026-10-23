#!/usr/bin/env python3
"""Benchmark latencji ASR (bramka G1: p95 ≤ 500 ms na CPU).

Mierzy czas samego `transcribe()` (bez VAD/wake-worda) na 20 komendach
z eval/recordings (lub wygenerowanych). Wyniki: p50/p95/średnia/max + JSON.

    python bench/asr_latency.py              # small int8, 20 przebiegów
    python bench/asr_latency.py --model medium --n 20
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from saycue.asr.whisper import ASREngine  # noqa: E402

N_RUNS = 20


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


def load_wavs(recordings: Path, n: int) -> list[np.ndarray]:
    from faster_whisper.audio import decode_audio

    wavs = sorted(recordings.glob("*.wav"))
    if not wavs:
        raise SystemExit(
            f"brak nagrań w {recordings} — uruchom: python scripts/generate_eval_recordings.py"
        )
    audios = [np.asarray(decode_audio(str(w), sampling_rate=16000), dtype=np.float32) for w in wavs]
    # 20 przebiegów: cykl po nagraniach
    return [audios[i % len(audios)] for i in range(n)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="small", choices=["small", "medium", "tiny"])
    ap.add_argument("--n", type=int, default=N_RUNS, help="liczba przebiegów (domyślnie 20)")
    ap.add_argument("--recordings", type=Path, default=ROOT / "eval" / "recordings")
    ap.add_argument("--results", type=Path, default=ROOT / "bench" / "results")
    ap.add_argument("--cpu-threads", type=int, default=4)
    args = ap.parse_args()

    audios = load_wavs(args.recordings, args.n)
    engine = ASREngine(model_size=args.model, cpu_threads=args.cpu_threads, language="pl")

    # warm-up: pierwsze wywołanie zawiera lazy init CTranslate2
    warm = engine.transcribe(np.zeros(16000, dtype=np.float32))
    print(
        f"CPU : {cpu_info()} | model: faster-whisper {args.model} {engine.compute_type} "
        f"(beam={engine.beam_size}, threads={engine.cpu_threads})"
    )
    print(f"warm-up: {warm.elapsed_s * 1000:.0f} ms (1 s ciszy)\n")
    print(f"{'#':<4}{'plik':<26}{'audio':>8}{'ASR (ms)':>10}")

    times: list[float] = []
    durations: list[float] = []
    for i, audio in enumerate(audios, 1):
        result = engine.transcribe(audio)
        times.append(result.elapsed_s * 1000)
        durations.append(result.audio_seconds)
        src = sorted(args.recordings.glob("*.wav"))[
            (i - 1) % len(sorted(args.recordings.glob("*.wav")))
        ]
        print(f"{i:<4}{src.name:<26}{result.audio_seconds:>7.2f}s{result.elapsed_s * 1000:>9.0f}")

    times_sorted = np.sort(times)
    p50 = float(np.percentile(times_sorted, 50))
    p95 = float(np.percentile(times_sorted, 95))
    mean = float(np.mean(times_sorted))
    max_t = float(np.max(times_sorted))
    gate = "GO ✅" if p95 <= 500 else "NO-GO ❌"

    print("\n" + "=" * 62)
    print(f"ASR latencja ({args.n} komend, ~{np.mean(durations):.1f} s audio):")
    print(f"  p50   : {p50:6.1f} ms")
    print(f"  p95   : {p95:6.1f} ms   ← bramka G1: ≤ 500 ms  {gate}")
    print(f"  średnia: {mean:6.1f} ms | max: {max_t:6.1f} ms")

    args.results.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    report = {
        "bench": "asr_latency",
        "ts": stamp,
        "cpu": cpu_info(),
        "model": {
            "engine": "faster-whisper",
            "size": args.model,
            "compute_type": engine.compute_type,
            "beam": engine.beam_size,
            "cpu_threads": engine.cpu_threads,
            "language": "pl",
            "initial_prompt": bool(engine.initial_prompt),
        },
        "n_runs": args.n,
        "audio_seconds_mean": round(float(np.mean(durations)), 2),
        "p50_ms": round(p50, 1),
        "p95_ms": round(p95, 1),
        "mean_ms": round(mean, 1),
        "max_ms": round(max_t, 1),
        "gate_threshold_ms": 500,
        "gate_passed": p95 <= 500,
        "all_ms": [round(t, 1) for t in times],
    }
    out = args.results / f"asr_latency_{stamp}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"raport JSON: {out}")
    return 0 if report["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
