#!/usr/bin/env python3
"""Benchmark latencji end-to-end (bramka G2: p95 ≤ 1,2 s).

Pełna pętla na nagraniach: audio → VAD → ASR → parser → akcja (mock OBS /
dry-run OS). Mierzy e2e_ms (detekcja końca mowy → akcja) oraz e2e_total_ms
(z czekaniem VAD 600 ms — budżet architektury §4, bramka G2).

    python bench/e2e_latency.py --n 2        # 2 × 20 komend = 40 próbek
    python bench/e2e_latency.py --n 1 --json-only

UWAGA: na współdzielonej maszynie (zespół agentów) wyniki są zaszumione
kontencją CPU — mierz przez bench/run_when_idle.py lub na wolnym sprzęcie.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import yaml  # noqa: E402
from faster_whisper.audio import decode_audio  # noqa: E402

from g2_harness import FakeCapture, MockObsServer  # noqa: E402
from saycue.actions import ActionContext, build_default_registry  # noqa: E402
from saycue.actions.obs import ObsClient  # noqa: E402
from saycue.asr.whisper import ASREngine  # noqa: E402
from saycue.orchestrator import Orchestrator  # noqa: E402
from saycue.parser import IntentParser  # noqa: E402
from saycue.vad.silero import SileroVAD  # noqa: E402

G2_YAML = ROOT / "eval" / "g2_commands.yaml"
ACTIVE_PRESETS = ["obs-core", "apps-open", "apps-streaming", "elite-dangerous"]
TIMEOUT_S = 120


def run_command(wav: Path, asr, parser, registry, ctx) -> dict:
    audio = np.asarray(decode_audio(str(wav), sampling_rate=16000), dtype=np.float32)
    capture = FakeCapture(audio, pad_silence_s=1.5)
    outcomes = []
    done = threading.Event()
    orch = Orchestrator(
        asr=asr,
        capture=capture,
        vad=SileroVAD(),
        wake=None,
        ptt=None,
        parser=parser,
        registry=registry,
        ctx=ctx,
        on_outcome=lambda o: (outcomes.append(o), done.set()),
    )
    thread = threading.Thread(target=orch.run_forever, daemon=True)
    thread.start()
    try:
        ok = done.wait(timeout=TIMEOUT_S)
    finally:
        orch._stop = True
        thread.join(timeout=5)
    if not ok or not outcomes:
        return {"crash": True, "asr_ms": 0, "e2e_ms": 0, "e2e_total_ms": 0}
    o = outcomes[0]
    return {
        "crash": False,
        "text": o.text,
        "intent": o.intent,
        "asr_ms": round(o.asr_ms, 1),
        "parse_ms": round(o.parse_ms, 1),
        "action_ms": round(o.action_ms, 1),
        "e2e_ms": round(o.e2e_ms, 1),
        "e2e_total_ms": round(o.e2e_total_ms, 1),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=2, help="powtórzenia zestawu 20 komend (domyślnie 2)")
    ap.add_argument("--results", type=Path, default=ROOT / "bench" / "results")
    args = ap.parse_args()

    commands = yaml.safe_load(G2_YAML.read_text(encoding="utf-8"))["phrases"]
    wavs = [(c["id"], ROOT / "eval" / "recordings" / c["wav"]) for c in commands]
    if not all(w.is_file() for _, w in wavs):
        raise SystemExit(
            "brak nagrań — python scripts/generate_eval_recordings.py --commands eval/g2_commands.yaml"
        )

    server = MockObsServer(password="")
    server.start()
    obs = ObsClient(host=server.host, port=server.port, password="")
    obs.connect()
    parser = IntentParser(active_presets=ACTIVE_PRESETS)
    registry = build_default_registry()
    ctx = ActionContext(apps=parser.config.apps, obs=obs, dry_run=True)
    asr = ASREngine(model_size="small", language="pl")

    rows = []
    for rep in range(args.n):
        for cid, wav in wavs:
            row = run_command(wav, asr, parser, registry, ctx)
            row["id"], row["rep"] = cid, rep + 1
            rows.append(row)
            print(
                f"{row['id']:<8} rep{row['rep']} crash={row['crash']} "
                f"e2e_total={row['e2e_total_ms']:.0f} ms intent={row.get('intent')}"
            )

    obs.close()
    server.stop()

    totals = sorted(r["e2e_total_ms"] for r in rows if not r["crash"] and r["e2e_total_ms"] > 0)
    crashes = sum(r["crash"] for r in rows)
    p50 = float(np.percentile(totals, 50)) if totals else 0.0
    p95 = float(np.percentile(totals, 95)) if totals else 0.0
    gate = "GO ✅" if p95 <= 1200 else "NO-GO ❌ (sprawdź obciążenie maszyny — patrz raport G2)"

    print("\n" + "=" * 60)
    print(f"e2e latency ({len(rows)} próbek, {args.n}×20 komend):")
    print(f"  p50 : {p50:6.0f} ms")
    print(f"  p95 : {p95:6.0f} ms   ← bramka G2: ≤ 1200 ms  {gate}")
    print(f"  crashy: {crashes}/{len(rows)}")

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = args.results / f"e2e_latency_{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "bench": "e2e_latency",
                "ts": stamp,
                "n_runs": len(rows),
                "crashes": crashes,
                "p50_ms": round(p50, 1),
                "p95_ms": round(p95, 1),
                "gate_threshold_ms": 1200,
                "gate_passed": p95 <= 1200,
                "rows": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"raport JSON: {out}")
    return 0 if p95 <= 1200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
