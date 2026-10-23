"""Testy orchestratora (maszyna stanów §2.1) — bez modeli ASR.

Komponenty: FakeASR (deterministyczny tekst), FakeParser/FakeRegistry
(słowniki), prawdziwe SileroVAD nie jest potrzebne — testujemy przejścia
stanów przez `_process_utterance` oraz e2e timings.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from saycue.orchestrator import Orchestrator, Outcome, State

SR = 16000


class FakeASR:
    def __init__(self, text: str = "otwórz spotify", elapsed_s: float = 0.05):
        self.text = text
        self.elapsed_s = elapsed_s
        self.loaded = False

    def load(self) -> None:
        self.loaded = True

    def transcribe(self, audio: np.ndarray):
        return SimpleNamespace(
            text=self.text,
            elapsed_s=self.elapsed_s,
            language="pl",
            language_probability=1.0,
            audio_seconds=len(audio) / SR,
        )


class FakeParser:
    def __init__(self, result=None, candidates=None):
        self.result = result
        self.candidates_list = candidates or []

    def parse(self, text):
        return self.result

    def candidates(self, text, k=3):
        return self.candidates_list[:k]


class FakeRegistry:
    def __init__(self, ok: bool = True, message: str = "wykonano"):
        self.ok = ok
        self.message = message
        self.calls: list[tuple[str, dict]] = []

    def execute(self, intent, slots, ctx):
        self.calls.append((intent, dict(slots)))
        return SimpleNamespace(ok=self.ok, message=self.message, error=None if self.ok else "boom")


def make_result(intent="app.open", slots=None):
    return SimpleNamespace(
        intent=intent,
        slots=slots or {"target": "spotify"},
        score=1.0,
        matched=("otwórz spotify",),
        source="exact",
        command_id="open_spotify",
        origin="apps-open",
    )


def make_orch(**kwargs):
    defaults = dict(
        asr=FakeASR(),
        capture=None,
        vad=None,
        wake=None,
        ptt=None,
        parser=FakeParser(make_result()),
        registry=FakeRegistry(),
        ctx=SimpleNamespace(dry_run=True),
        on_outcome=None,
    )
    defaults.update(kwargs)
    return Orchestrator(**defaults)


def test_feedback_flow_states_and_slots():
    seen: list[State] = []
    outcomes: list[Outcome] = []
    orch = make_orch(
        on_state=seen.append,
        on_outcome=outcomes.append,
    )
    orch._finish_reason = "eos"
    orch._last_speech_ts = 1000.0
    orch._process_utterance(np.zeros(SR, dtype=np.float32))

    assert seen == [
        State.TRANSCRIBING,
        State.PARSING,
        State.ACTING,
        State.FEEDBACK,
    ]
    o = outcomes[0]
    assert o.intent == "app.open"
    assert o.slots == {"target": "spotify"}
    assert o.state is State.FEEDBACK
    assert o.action_ok is True
    assert o.action_message == "wykonano"


def test_ask_flow_when_no_intent():
    cand = [SimpleNamespace(phrase="otwórz spotify"), SimpleNamespace(phrase="scena pvp")]
    orch = make_orch(
        parser=FakeParser(result=None, candidates=cand),
    )
    outcomes: list[Outcome] = []
    orch.on_outcome = outcomes.append
    orch._finish_reason = "eos"
    orch._last_speech_ts = 1000.0
    orch._process_utterance(np.zeros(SR, dtype=np.float32))

    o = outcomes[0]
    assert o.state is State.ASK
    assert o.intent is None
    assert [c.phrase for c in o.candidates] == ["otwórz spotify", "scena pvp"]


def test_action_failure_goes_ask_with_message():
    orch = make_orch(registry=FakeRegistry(ok=False, message="nie udało się"))
    outcomes: list[Outcome] = []
    orch.on_outcome = outcomes.append
    orch._finish_reason = "eos"
    orch._last_speech_ts = 1000.0
    orch._process_utterance(np.zeros(SR, dtype=np.float32))

    o = outcomes[0]
    assert o.state is State.ASK
    assert o.action_ok is False
    assert o.action_error == "boom"


def test_empty_transcription_goes_ask():
    orch = make_orch(asr=FakeASR(text=""))
    outcomes: list[Outcome] = []
    orch.on_outcome = outcomes.append
    orch._finish_reason = "eos"
    orch._last_speech_ts = 1000.0
    orch._process_utterance(np.zeros(SR, dtype=np.float32))
    assert outcomes[0].state is State.ASK
    assert outcomes[0].intent is None


def test_short_audio_skipped():
    orch = make_orch()
    outcomes: list[Outcome] = []
    orch.on_outcome = outcomes.append
    orch._process_utterance(np.zeros(1200, dtype=np.float32))  # < 100 ms
    assert outcomes == []


def test_e2e_total_includes_vad_wait_only_for_eos():
    orch = make_orch()
    outcomes: list[Outcome] = []
    orch.on_outcome = outcomes.append

    orch._last_speech_ts = 1000.0
    orch._process_utterance(np.zeros(SR, dtype=np.float32), "eos")
    assert outcomes[0].e2e_total_ms == pytest.approx(outcomes[0].e2e_ms + 600, abs=1)

    orch2 = make_orch()
    outcomes2: list[Outcome] = []
    orch2.on_outcome = outcomes2.append
    # zwolnienie PTT — bez czekania VAD (finish_reason przekazany jawnie)
    orch2._last_speech_ts = 1000.0
    orch2._process_utterance(np.zeros(SR, dtype=np.float32), "ptt")
    assert outcomes2[0].e2e_total_ms == pytest.approx(outcomes2[0].e2e_ms, abs=1)


def test_registry_receives_parsed_slots():
    registry = FakeRegistry()
    orch = make_orch(
        parser=FakeParser(make_result(intent="input.keys", slots={"keys": ["shift", "space"]})),
        registry=registry,
    )
    orch.on_outcome = lambda o: None
    orch._finish_reason = "eos"
    orch._last_speech_ts = 1000.0
    orch._process_utterance(np.zeros(SR, dtype=np.float32))
    assert registry.calls == [("input.keys", {"keys": ["shift", "space"]})]


def test_silence_never_triggers_pipeline():
    """Niezmiennik „cisza ≠ komenda": VAD-gate nie wybudza na czystej ciszy.

    To jest prawdziwa ochrona przed hallucinacjami ASR na ciszy (flaky
    tests/test_asr.py pod obciążeniem) — ASR nigdy nie dostaje ciszy od VAD.
    Używa prawdziwego Silero VAD (model wbudowany w faster-whisper)."""
    import threading

    from g2_harness import FakeCapture
    from saycue.vad.silero import SileroVAD

    outcomes: list[Outcome] = []
    done = threading.Event()
    capture = FakeCapture(np.zeros(3 * SR, dtype=np.float32), pad_silence_s=1.0)
    orch = Orchestrator(
        asr=FakeASR(text="cisza"),  # gdyby ASR dostał ciszę, „usłyszałby" komendę
        capture=capture,
        vad=SileroVAD(),
        wake=None,
        ptt=None,
        parser=FakeParser(make_result(intent="obs.mute", slots={"source": "Mic/Aux"})),
        registry=FakeRegistry(),
        ctx=SimpleNamespace(dry_run=True),
        on_outcome=lambda o: (outcomes.append(o), done.set()),
    )
    thread = threading.Thread(target=orch.run_forever, daemon=True)
    thread.start()
    try:
        # 4 s ciszy — VAD-gate nie może wybudzić sesji
        assert not done.wait(timeout=4.0)
    finally:
        orch._stop = True
        thread.join(timeout=5)
    assert outcomes == [], f"cisza wywołała komendę: {outcomes}"
