#!/usr/bin/env python3
"""Czeka na wolny CPU (load < próg) i dopiero wtedy mierzy latencję ASR.

Pomiar na współdzielonej maszynie (zespół agentów + aplikacje użytkownika)
jest zaszumiony — p95 > 4 s przy load ~7/8 vCPU nie mówi nic o silniku.
Ten runner czeka na okno z niskim obciążeniem i uruchamia pełny benchmark.

    python bench/run_when_idle.py --max-wait-min 120 --load 2.0
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = Path(sys.executable)


def load_avg(minutes: int = 1) -> float:
    return os.getloadavg()[0 if minutes == 1 else (1 if minutes == 5 else 2)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--load", type=float, default=2.0, help="próg 1-min load (domyślnie 2.0)")
    ap.add_argument("--max-wait-min", type=int, default=120)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--model", default="small")
    args = ap.parse_args()

    deadline = time.monotonic() + args.max_wait_min * 60
    waited = 0.0
    while True:
        load = load_avg(1)
        if load <= args.load:
            print(f"[run_when_idle] load {load:.2f} ≤ {args.load} — start pomiaru "
                  f"(po {waited / 60:.1f} min oczekiwania)", flush=True)
            r = subprocess.run(
                [str(PY), str(ROOT / "bench" / "asr_latency.py"),
                 "--n", str(args.n), "--model", args.model],
                cwd=ROOT,
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
