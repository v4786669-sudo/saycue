#!/usr/bin/env python3
"""Sesja stabilności G2: 30 minut pełnej pętli — 0 crashy.

Odtwarza zestaw 20 komend w pętli (tempo ~10 s/komendę ≈ 180 przebiegów/30 min)
i liczy crashy oraz sukcesy. To skryptowana wersja „30-min sesji" — prawdziwy
mikrofon (ALSA/sounddevice) testujemy osobno pętlą na żywo.

    python bench/stress_session.py --minutes 30
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import yaml  # noqa: E402

from g2_harness import FakeCapture, MockObsServer  # noqa: E402
from saycue.actions import ActionContext, build_default_registry  # noqa: E402
from saycue.actions.obs import ObsClient  # noqa: E402
from saycue.asr.whisper import ASREngine  # noqa: E402
from saycue.orchestrator import Orchestrator  # noqa: E402
from saycue.parser import IntentParser  # noqa: E402
from saycue.vad.silero import SileroVAD  # noqa: E402

G2_YAML = ROOT / "eval" / "g2_commands.yaml"
ACTIVE_PRESETS = ["obs-core", "apps-open", "apps-streaming", "elite-dangerous"]
PACING_S = 10.0
TIMEOUT_S = 120


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--minutes", type=int, default=30)
    ap.add_argument("--pacing", type=float, default=PACING_S, help="odstęp między komendami (s)")
    args = ap.parse_args()

    commands = yaml.safe_load(G2_YAML.read_text(encoding="utf-8"))["phrases"]
    wavs = [(c["id"], ROOT / "eval" / "recordings" / c["wav"]) for c in commands]
    if not all(w.is_file() for _, w in wavs):
        raise SystemExit(
            "brak nagrań — generate_eval_recordings.py --commands eval/g2_commands.yaml"
        )

    server = MockObsServer(password="")
    server.start()
    obs = ObsClient(host=server.host, port=server.port, password="")
    obs.connect()
    parser = IntentParser(active_presets=ACTIVE_PRESETS)
    registry = build_default_registry()
    ctx = ActionContext(apps=parser.config.apps, obs=obs, dry_run=True)
    asr = ASREngine(model_size="small", language="pl")

    import threading

    import numpy as np
    from faster_whisper.audio import decode_audio

    audios = {
        cid: np.asarray(decode_audio(str(w), sampling_rate=16000), dtype=np.float32)
        for cid, w in wavs
    }

    deadline = time.monotonic() + args.minutes * 60
    runs, crashes, ok_runs = 0, 0, 0
    rows = []
    t0 = time.monotonic()
    try:
        while time.monotonic() < deadline:
            cid = wavs[runs % len(wavs)][0]
            outcomes = []
            done = threading.Event()
            capture = FakeCapture(audios[cid], pad_silence_s=1.5)
            orch = Orchestrator(
                asr=asr,
                capture=capture,
                vad=SileroVAD(),
                wake=None,
                ptt=None,
                parser=parser,
                registry=registry,
                ctx=ctx,
                on_outcome=lambda o, _outs=outcomes, _ev=done: (_outs.append(o), _ev.set()),
            )
            thread = threading.Thread(target=orch.run_forever, daemon=True)
            thread.start()
            ok = done.wait(timeout=TIMEOUT_S)
            orch._stop = True
            thread.join(timeout=5)
            runs += 1
            if ok and outcomes:
                ok_runs += 1
                o = outcomes[0]
                rows.append(
                    {
                        "n": runs,
                        "id": cid,
                        "ok": True,
                        "intent": o.intent,
                        "e2e_total_ms": round(o.e2e_total_ms, 1),
                    }
                )
            else:
                crashes += 1
                rows.append({"n": runs, "id": cid, "ok": False, "crash": True})
                print(f"[{runs}] CRASH na {cid}", flush=True)
            elapsed = time.monotonic() - t0
            remaining = deadline - time.monotonic()
            if remaining > 0 and runs % 10 == 0:
                print(
                    f"[{runs}] sesja {elapsed / 60:.1f}/{args.minutes} min — crashy: {crashes}",
                    flush=True,
                )
            if remaining > args.pacing:
                time.sleep(min(args.pacing, remaining))
    except KeyboardInterrupt:
        print("przerwano (Ctrl+C)")
    finally:
        obs.close()
        server.stop()

    duration_min = (time.monotonic() - t0) / 60
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "bench" / "results" / f"stress_session_{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "session": "stress_30min",
                "ts": stamp,
                "planned_min": args.minutes,
                "actual_min": round(duration_min, 1),
                "runs": runs,
                "crashes": crashes,
                "completed": ok_runs,
                "gate": "0 crashy w sesji",
                "gate_passed": crashes == 0,
                "rows": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"\nSESJA: {runs} przebiegów / {duration_min:.1f} min | crashy: {crashes} | raport: {out}"
    )
    return 0 if crashes == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
