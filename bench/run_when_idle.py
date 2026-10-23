#!/usr/bin/env python3
"""Czeka na wolny CPU (load < próg) i dopiero wtedy mierzy latencję ASR.

Pomiar na współdzielonej maszynie (zespół agentów + aplikacje użytkownika)
jest zaszumiony — p95 > 4 s przy load ~7/8 vCPU nie mówi nic o silniku.
Runner czeka na okno z niskim obciążeniem, robi szybką sondę (5 przebiegów)
i dopiero przy medianie sondy < 300 ms uruchamia pełny benchmark.

    python bench/run_when_idle.py --max-wait-min 150 --load 2.5
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = Path(sys.executable)


def load_avg(minutes: int = 1) -> float:
    return os.getloadavg()[0 if minutes == 1 else (1 if minutes == 5 else 2)]


def probe() -> float | None:
    """5 transkrypcji jednego pliku; zwraca medianę ms lub None przy błędzie."""
    import numpy as np
    from faster_whisper import WhisperModel
    from faster_whisper.audio import decode_audio

    wavs = sorted((ROOT / "eval" / "recordings").glob("*.wav"))
    if not wavs:
        return None
    audio = np.asarray(decode_audio(str(wavs[4]), sampling_rate=16000), dtype=np.float32)
    model = WhisperModel(
        str(Path.home() / ".cache" / "saycue" / "models" / "whisper-small"),
        device="cpu",
        compute_type="int8",
        cpu_threads=4,
    )
    model.transcribe(
        np.zeros(16000, dtype=np.float32), language="pl", beam_size=1,
        temperature=0, vad_filter=False,
    )  # warm-up
    times = []
    for _ in range(5):
        t0 = time.perf_counter()
        segs, _ = model.transcribe(
            audio, language="pl", beam_size=1, temperature=0, vad_filter=False
        )
        list(segs)
        times.append((time.perf_counter() - t0) * 1000)
    return float(sorted(times)[len(times) // 2])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--load", type=float, default=2.5, help="próg 1-min load (domyślnie 2.5)")
    ap.add_argument("--max-wait-min", type=int, default=150)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--model", default="small")
    args = ap.parse_args()

    deadline = time.monotonic() + args.max_wait_min * 60
    waited = 0.0
    while True:
        load = load_avg(1)
        if load <= args.load:
            print(f"[run_when_idle] load {load:.2f} ≤ {args.load} — sonda (5 przebiegów)…",
                  flush=True)
            try:
                median = probe()
            except Exception as exc:
                print(f"[run_when_idle] sonda nieudana: {exc}", flush=True)
                median = None
            if median is not None:
                print(f"[run_when_idle] sonda: mediana {median:.0f} ms "
                      f"({'OK' if median < 300 else 'za wolno — dalej czekam'})", flush=True)
                if median < 300:
                    print(f"[run_when_idle] start pełnego benchmarku "
                          f"(po {waited / 60:.1f} min oczekiwania)", flush=True)
                    r = subprocess.run(
                        [str(PY), str(ROOT / "bench" / "asr_latency.py"),
                         "--n", str(args.n), "--model", args.model],
                        cwd=ROOT,
                    )
                    # dopisz medianę sondy do najnowszego raportu
                    results = sorted((ROOT / "bench" / "results").glob("asr_latency_*.json"))
                    if results:
                        rep = json.loads(results[-1].read_text(encoding="utf-8"))
                        rep["probe_median_ms"] = round(median, 1)
                        results[-1].write_text(
                            json.dumps(rep, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8",
                        )
                    return r.returncode
        if time.monotonic() > deadline:
            print(f"[run_when_idle] timeout po {args.max_wait_min} min; load wciąż {load:.2f} "
                  f"(próg {args.load}). Pomiar pominięty — uruchom ponownie w nocy.",
                  flush=True)
            return 2
        time.sleep(20)


if __name__ == "__main__":
    raise SystemExit(main())
