"""Orchestrator — maszyna stanów §2.1: audio → ASR → parser → akcje.

    IDLE ──wake-word (cooldown 500 ms) | PTT | VAD-gate──▶ LISTENING
    LISTENING ──2.0 s ciszy bez mowy──▶ IDLE (timeout)
    LISTENING ──mowa──▶ CAPTURING ──600 ms ciszy | 8 s maks──▶ TRANSCRIBING
    TRANSCRIBING ──tekst──▶ PARSING
    PARSING ──intent──▶ ACTING ──▶ FEEDBACK ──▶ IDLE
    PARSING ──brak intencji (score < próg)──▶ ASK (kandydaci) ──▶ IDLE

Barge-in: świadomie OUT (architektura §5.2). Wątki: callback audio →
kolejka; pętla główna konsumuje; akcje i ASR w pętli (blokujące, krótkie).

Punkt spięcia t6 (audio) + t13 (parser/akcje): `IntentParser` (parse /
candidates / set_active_presets) i `Registry` + `ActionContext` z §3.3.
"""

from __future__ import annotations

import logging
import queue
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np

from .asr.whisper import ASREngine
from .audio.capture import AudioCapture, UtteranceRecorder
from .vad.silero import SileroVAD, VadSession
from .wakeword.openwakeword import WakeWordDetector
from .wakeword.ptt import PushToTalk

log = logging.getLogger(__name__)


class State(StrEnum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    CAPTURING = "CAPTURING"
    TRANSCRIBING = "TRANSCRIBING"
    PARSING = "PARSING"
    ACTING = "ACTING"
    FEEDBACK = "FEEDBACK"
    ASK = "ASK"


@dataclass
class Outcome:
    """Wynik jednego przebiegu pętli (transkrypcja → intencja → akcja)."""

    trigger: str = ""
    text: str = ""
    state: State = State.FEEDBACK
    intent: str | None = None
    slots: dict[str, Any] = field(default_factory=dict)
    parse_source: str | None = None
    parse_score: float | None = None
    candidates: list = field(default_factory=list)  # list[Candidate] dla ASK
    action_ok: bool | None = None
    action_message: str = ""
    action_error: str | None = None
    # czasy (ms): e2e_ms = detekcja końca mowy → akcja/ASK (ASR+parser+akcja);
    # e2e_total_ms = ostatni dźwięk mowy → akcja/ASK (e2e + czekanie VAD 600 ms,
    # budżet architektury §4 ~950 ms / bramka G2 ≤1200 ms p95).
    asr_ms: float = 0.0
    parse_ms: float = 0.0
    action_ms: float = 0.0
    e2e_ms: float = 0.0
    e2e_total_ms: float = 0.0
    audio_seconds: float = 0.0


class Orchestrator:
    """Łączy capture → wybudzenie → VAD → ASR → parser → akcje (§2.1)."""

    def __init__(
        self,
        asr: ASREngine,
        capture: AudioCapture,
        vad: SileroVAD,
        wake: WakeWordDetector | None = None,
        ptt: PushToTalk | None = None,
        parser: Any = None,  # IntentParser (lazy import — parser to zależność t13)
        registry: Any = None,  # Registry akcji
        ctx: Any = None,  # ActionContext
        pre_roll_s: float = 0.4,
        end_silence_s: float = 0.6,
        max_utterance_s: float = 8.0,
        on_state: Callable[[State], None] | None = None,
        on_outcome: Callable[[Outcome], None] | None = None,
        on_text: Callable[[str, State], None] | None = None,
        debug_audio_dir: Path | None = None,
        telemetry: Any = None,  # Telemetry (W3): events.jsonl + metrics.jsonl
    ):
        self.asr = asr
        self.capture = capture
        self.vad = vad
        self.wake = wake
        self.ptt = ptt
        self.parser = parser
        self.registry = registry
        self.ctx = ctx
        self.pre_roll_s = pre_roll_s
        self.end_silence_s = end_silence_s
        self.max_utterance_s = max_utterance_s
        self.on_state = on_state
        self.on_outcome = on_outcome or self._print_outcome
        self.on_text = on_text
        self.debug_audio_dir = debug_audio_dir
        self.telemetry = telemetry
        self._stop = False
        self.state = State.IDLE
        self._triggered_at: float | None = None
        self._trigger_name = ""
        self._last_speech_ts: float | None = None  # mono clock, koniec mowy

    # ---------------------------------------------------------------- stany

    def _set_state(self, state: State) -> None:
        self.state = state
        if self.on_state is not None:
            self.on_state(state)

    # ----------------------------------------------------------------- pętla

    def run_forever(self) -> None:
        self._finish_reason = "eos"
        self.capture.start()
        if self.ptt is not None:
            self.ptt.start()
        if self.wake is not None:
            try:
                self.wake.load()
            except FileNotFoundError as exc:
                log.warning("%s — praca tylko z push-to-talk / VAD-gate.", exc)
                self.wake = None
        self.asr.load()
        try:
            self._loop()
        except KeyboardInterrupt:
            log.info("zatrzymanie (Ctrl+C)")
        finally:
            self._stop = True
            if self.ptt is not None:
                self.ptt.stop()
            self.capture.stop()
            if self.telemetry is not None:
                self.telemetry.close()

    def _loop(self) -> None:
        recorder: UtteranceRecorder | None = None
        session: VadSession | None = None
        while not self._stop:
            try:
                chunk, _ts = self.capture.read(timeout=0.5)
            except queue.Empty:
                continue

            if session is None:
                self._set_state(State.IDLE)
                trigger = self._await_trigger(chunk)
                if trigger:
                    recorder = UtteranceRecorder(
                        self.capture.ring, self.pre_roll_s, self.max_utterance_s
                    )
                    session = VadSession(
                        threshold=self.vad.threshold,
                        end_silence_s=self.end_silence_s,
                        max_utterance_s=self.max_utterance_s,
                    )
                    self.vad.reset()
                    self._triggered_at = time.perf_counter()
                    self._trigger_name = trigger
                    self._set_state(State.LISTENING)
                    log.info("▶ %s — nasłuchuję (maks. %.0f s)", trigger, self.max_utterance_s)
                continue

            assert recorder is not None
            prob = self.vad.process(chunk)
            recorder.add(chunk)
            session.push(chunk, prob)
            if session.speech_started:
                self._set_state(State.CAPTURING)

            finish: str | None = None
            if session.maxed_out:
                log.info("■ koniec: maksymalna długość wypowiedzi (%.0f s)", self.max_utterance_s)
                finish = "max"
            elif session.end_of_speech:
                log.info("■ koniec: %.0f ms ciszy", self.end_silence_s * 1000)
                finish = "eos"
            elif self._trigger_name == "ptt" and not self.ptt.is_pressed:
                if session.speech_started:
                    log.info("■ koniec: zwolniono push-to-talk")
                    finish = "ptt"
                else:
                    log.info("■ PTT zwolniony bez mowy — sesja anulowana")
                    recorder, session = None, None
                    continue
            elif session.timed_out:
                log.info("■ timeout: brak mowy przez 2.0 s po wybudzeniu")
                if self.telemetry is not None and self._trigger_name == "wakeword":
                    self.telemetry.wakeword_fp(1)  # wybudzenie bez mowy = FP (G4f)
                recorder, session = None, None
                continue

            if finish:
                self._last_speech_ts = time.perf_counter()
                audio = recorder.finish(session.cutoff_frames() if session.speech_started else None)
                self._process_utterance(audio, finish)
                recorder, session = None, None
                self._set_state(State.IDLE)

    # -------------------------------------------------------------- wybudzenie

    def _await_trigger(self, chunk: np.ndarray) -> str | None:
        if self.ptt is not None and self.ptt.is_pressed:
            return "ptt"
        if self.wake is not None and self.wake.feed(chunk):
            return "wakeword"
        # VAD-gate: dowolna mowa uruchamia sesję (awaryjne wejście, architektura §3.1)
        if self.wake is None and self.ptt is None:
            prob = self.vad.process(chunk)
            if prob is not None and prob >= self.vad.threshold:
                return "vad-gate"
        return None

    # --------------------------------------------------------- ASR→parser→akcje

    def _process_utterance(self, audio: np.ndarray, finish_reason: str = "eos") -> None:
        self._finish_reason = finish_reason
        n = len(audio)
        if n < 1600:  # < 100 ms — za mało na komendę
            log.info("pominięto: nagranie za krótkie (%.0f ms)", n / 16)
            return
        if self.debug_audio_dir is not None:
            self._save_wav(audio)

        outcome = Outcome(trigger=self._trigger_name)
        self._set_state(State.TRANSCRIBING)
        result = self.asr.transcribe(audio)
        outcome.text = result.text.strip()
        outcome.asr_ms = result.elapsed_s * 1000
        outcome.audio_seconds = result.audio_seconds
        if self.on_text is not None:
            self.on_text(outcome.text, self.state)
        if not outcome.text:
            outcome.state = State.ASK
            self._emit(outcome)
            return

        self._set_state(State.PARSING)
        t0 = time.perf_counter()
        parsed = self.parser.parse(outcome.text) if self.parser is not None else None
        outcome.parse_ms = (time.perf_counter() - t0) * 1000
        if parsed is None:
            outcome.state = State.ASK
            if self.parser is not None:
                outcome.candidates = self.parser.candidates(outcome.text, k=3)
            if self.telemetry is not None:
                # intent_guess = fraza z commands.yaml (string z listy) lub null (§2.4)
                guess = outcome.candidates[0].phrase if outcome.candidates else None
                self.telemetry.command_miss(intent_guess=guess)
            self._emit(outcome)
            return

        outcome.intent = parsed.intent
        outcome.slots = dict(parsed.slots)
        outcome.parse_source = parsed.source
        outcome.parse_score = parsed.score

        self._set_state(State.ACTING)
        t0 = time.perf_counter()
        if self.registry is not None and self.ctx is not None:
            action_result = self.registry.execute(parsed.intent, parsed.slots, self.ctx)
            outcome.action_ok = action_result.ok
            outcome.action_message = action_result.message
            outcome.action_error = action_result.error
        else:
            outcome.action_ok = None
            outcome.action_message = "rejestr akcji niepodpięty (dry-run orchestratora)"
        outcome.action_ms = (time.perf_counter() - t0) * 1000
        outcome.e2e_ms = (time.perf_counter() - self._last_speech_ts) * 1000
        # budżet §4 liczy od ostatniego dźwięku mowy: + czekanie VAD tylko przy EOS
        vad_wait_ms = self.end_silence_s * 1000 if finish_reason == "eos" else 0.0
        outcome.e2e_total_ms = outcome.e2e_ms + vad_wait_ms
        outcome.state = State.FEEDBACK if outcome.action_ok else State.ASK
        self._set_state(outcome.state)
        if self.telemetry is not None:
            if outcome.action_ok:
                self.telemetry.first_command(success=True)  # raz na instalację (G4a)
            # metrics.jsonl: tylko przy świadomej zgodzie (asr_text tylko tam)
            self.telemetry.log_metric(
                outcome.intent,
                bool(outcome.action_ok),
                outcome.e2e_total_ms,
                asr_text=outcome.text,
            )
        self._emit(outcome)

    def _emit(self, outcome: Outcome) -> None:
        outcome.e2e_ms = (
            (time.perf_counter() - self._last_speech_ts) * 1000
            if self._last_speech_ts is not None
            else outcome.e2e_ms
        )
        vad_wait_ms = (
            self.end_silence_s * 1000 if getattr(self, "_finish_reason", "eos") == "eos" else 0.0
        )
        outcome.e2e_total_ms = outcome.e2e_ms + vad_wait_ms
        self.on_outcome(outcome)

    # ------------------------------------------------------------------- demo

    @staticmethod
    def _print_outcome(o: Outcome) -> None:
        if o.state is State.FEEDBACK and o.intent:
            print(
                f'🎤 "{o.text}" → {o.intent} {o.slots or ""} | '
                f"✓ {o.action_message} [ASR {o.asr_ms:.0f} ms | parser {o.parse_ms:.1f} ms | "
                f"akcja {o.action_ms:.0f} ms | e2e {o.e2e_ms:.0f} ms | "
                f"e2e+VAD {o.e2e_total_ms:.0f} ms]"
            )
        elif o.state is State.ASK:
            cand = ", ".join(c.phrase for c in o.candidates[:3]) or "—"
            msg = o.action_message or "nie zrozumiałem"
            print(
                f'🎤 "{o.text}" → ? {msg} (czy chodziło ci o: {cand}) '
                f"[ASR {o.asr_ms:.0f} ms | e2e {o.e2e_ms:.0f} ms]"
            )
        else:
            print(f"🎤 (cisza) [ASR {o.asr_ms:.0f} ms]")

    def _save_wav(self, audio: np.ndarray) -> None:
        assert self.debug_audio_dir is not None
        self.debug_audio_dir.mkdir(parents=True, exist_ok=True)
        path = self.debug_audio_dir / f"utt_{time.strftime('%H%M%S')}_{len(audio)}.wav"
        pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(pcm.tobytes())
        log.debug("nagranie zapisane: %s", path)
