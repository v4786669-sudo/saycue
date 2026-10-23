"""Bramka G2 (t9): 20 komend end-to-end — audio → ASR → parser → akcja.

Komponenty: prawdziwy ASR (whisper-small, marker `models`), prawdziwy parser
z presetami, prawdziwy Registry; akcje OBS wykonują się na MockObsServer
(atrapa obs-websocket v5), akcje OS w dry-run. Nagrania: piper TTS + szum
pokoju (proxy — prawdziwe głosy w W4).

Kryteria G2 (PLAN §5): ≥90% komend wykonanych poprawnie; end-to-end
p95 ≤1,2 s; 0 crashy w 30-min sesji (osobno: bench/stress_session.py).
Ten test asertuje poprawność ≥90% i zapisuje czasy do eval/results/g2_*.json;
werdykt latencji (zależny od obciążenia maszyny) ocenia notes/g2-report.md.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import yaml

pytestmark = pytest.mark.models

from faster_whisper.audio import decode_audio  # noqa: E402

from g2_harness import FakeCapture, MockObsServer  # noqa: E402
from saycue.actions import ActionContext, build_default_registry  # noqa: E402
from saycue.actions.obs import ObsClient  # noqa: E402
from saycue.asr.manifest import load_manifest, verify_spec  # noqa: E402
from saycue.asr.whisper import ASREngine  # noqa: E402
from saycue.orchestrator import Orchestrator, Outcome  # noqa: E402
from saycue.parser import IntentParser  # noqa: E402
from saycue.vad.silero import SileroVAD  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
G2_YAML = ROOT / "eval" / "g2_commands.yaml"
GATE_MIN_CORRECT = 0.90  # ≥90% (18/20)
ACTIVE_PRESETS = ["obs-core", "apps-open", "apps-streaming", "elite-dangerous"]
TIMEOUT_S = 120


@pytest.fixture(scope="module")
def recordings_dir() -> Path:
    d = ROOT / "eval" / "recordings"
    if not d.is_dir():
        pytest.skip("brak nagrań eval — scripts/generate_eval_recordings.py")
    return d


@pytest.fixture(scope="module")
def env(recordings_dir):
    spec = load_manifest()["whisper-small"]
    ok, msg = verify_spec(spec)
    if not ok:
        pytest.skip(f"model niedostępny ({msg}) — scripts/download_models.py")

    server = MockObsServer(password="")
    server.start()
    obs = ObsClient(host=server.host, port=server.port, password="")
    obs.connect()
    assert obs.connected

    parser = IntentParser(active_presets=ACTIVE_PRESETS)
    registry = build_default_registry()
    ctx = ActionContext(apps=parser.config.apps, obs=obs, dry_run=True)
    engine = ASREngine(model_size="small", language="pl")
    yield {"parser": parser, "registry": registry, "ctx": ctx, "engine": engine, "server": server}
    obs.close()
    server.stop()


def _run_one(env, wav: Path) -> Outcome:
    audio = np.asarray(decode_audio(str(wav), sampling_rate=16000), dtype=np.float32)
    capture = FakeCapture(audio, pad_silence_s=1.5)
    asr = env["engine"]
    outcomes: list[Outcome] = []
    done = threading.Event()

    orchestrator = Orchestrator(
        asr=asr,
        capture=capture,
        vad=SileroVAD(),
        wake=None,
        ptt=None,
        parser=env["parser"],
        registry=env["registry"],
        ctx=env["ctx"],
        on_outcome=lambda o: (outcomes.append(o), done.set()),
    )
    thread = threading.Thread(target=orchestrator.run_forever, daemon=True)
    thread.start()
    try:
        if not done.wait(timeout=TIMEOUT_S):
            pytest.fail(f"brak wyniku dla {wav.name} w ciągu {TIMEOUT_S} s")
    finally:
        orchestrator._stop = True
        thread.join(timeout=5)
    assert outcomes, f"brak wyniku dla {wav.name}"
    return outcomes[0]


def _expected_slots_match(entry: dict, outcome: Outcome) -> bool:
    expected = entry.get("slots")
    if not expected:
        return True
    return outcome.slots == dict(expected)


def test_g2_20_commands(env, recordings_dir):
    commands = yaml.safe_load(G2_YAML.read_text(encoding="utf-8"))
    phrases = commands["phrases"]
    rows = []
    for entry in phrases:
        wav = recordings_dir / entry["wav"]
        assert wav.is_file(), f"brak {wav}"
        try:
            outcome = _run_one(env, wav)
        except Exception as exc:  # crash w pętli = twarda porażka komendy
            rows.append(
                {
                    "id": entry["id"],
                    "phrase": entry["phrase"],
                    "expected_intent": entry["intent"],
                    "crash": f"{type(exc).__name__}: {exc}",
                    "ok": False,
                }
            )
            continue
        ok = (
            outcome.intent == entry["intent"]
            and outcome.action_ok is True
            and _expected_slots_match(entry, outcome)
        )
        rows.append(
            {
                "id": entry["id"],
                "phrase": entry["phrase"],
                "expected_intent": entry["intent"],
                "transcript": outcome.text,
                "intent": outcome.intent,
                "slots": outcome.slots,
                "parse_source": outcome.parse_source,
                "action_ok": outcome.action_ok,
                "action_message": outcome.action_message,
                "ok": ok,
                "crash": None,
                "asr_ms": round(outcome.asr_ms, 1),
                "e2e_ms": round(outcome.e2e_ms, 1),
                "e2e_total_ms": round(outcome.e2e_total_ms, 1),
            }
        )

    n_ok = sum(r["ok"] for r in rows)
    accuracy = n_ok / len(rows)
    e2e_totals = sorted(r["e2e_total_ms"] for r in rows if r["e2e_total_ms"] > 0)
    p95 = float(np.percentile(e2e_totals, 95)) if e2e_totals else 0.0

    print(f"\nG2: {n_ok}/{len(rows)} komend wykonanych poprawnie = {accuracy:.1%}")
    for r in rows:
        mark = "OK " if r["ok"] else "FAIL"
        extra = r["crash"] or r.get("transcript", "")[:40]
        print(f"  {mark} {r['id']:<7} {r['phrase']:<22} → {r['intent'] or '-'} {extra}")
    print(f"  e2e p95 (z czekaniem VAD 600 ms): {p95:.0f} ms | prób: {len(e2e_totals)}")

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "eval" / "results" / f"g2_e2e_{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "gate": "G2",
                "ts": stamp,
                "correct": n_ok,
                "total": len(rows),
                "accuracy": round(accuracy, 4),
                "p95_e2e_total_ms": round(p95, 1),
                "rows": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"raport JSON: {out}")

    assert accuracy >= GATE_MIN_CORRECT, (
        f"G2 accuracy {accuracy:.1%} < {GATE_MIN_CORRECT:.0%} — lista powyżej"
    )
