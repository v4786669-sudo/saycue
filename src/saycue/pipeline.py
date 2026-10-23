"""Pipeline W1: IDLE → (wake/PTT/VAD) → CAPTURING → TRANSCRIBING → IDLE.

Maszyna stanów (architektura §2.1):
    IDLE ──wake-word (cooldown 500 ms) | PTT | VAD-gate──▶ LISTENING
    LISTENING ──2.0 s ciszy bez mowy──▶ IDLE (timeout)
    LISTENING ──mowa──▶ CAPTURING ──600 ms ciszy | 8 s maks──▶ TRANSCRIBING ──▶ IDLE

Wątki: callback audio (PortAudio/ALSA) → kolejka; pętla główna konsumuje.
Brak asyncio w W1 — jeden wątek sterujący jest prostszy i w pełni wystarcza.
"""

from __future__ import annotations

import logging
import queue
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .asr.whisper import ASREngine
from .audio.capture import AudioCapture, UtteranceRecorder
from .vad.silero import SileroVAD, VadSession
from .wakeword.openwakeword import WakeWordDetector
from .wakeword.ptt import PushToTalk

log = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    text: str
    asr_ms: float
    end_to_end_ms: float
    trigger: str
    audio_seconds: float


class Pipeline:
    """Łączy capture → wybudzenie → VAD → ASR. Callback dostaje wyniki."""

    def __init__(
        self,
        asr: ASREngine,
        capture: AudioCapture,
        vad: SileroVAD,
        wake: WakeWordDetector | None = None,
        ptt: PushToTalk | None = None,
        pre_roll_s: float = 0.4,
        end_silence_s: float = 0.6,
        max_utterance_s: float = 8.0,
        on_result: Callable[[PipelineResult], None] | None = None,
        debug_audio_dir: Path | None = None,
    ):
        self.asr = asr
        self.capture = capture
        self.vad = vad
        self.wake = wake
        self.ptt = ptt
        self.pre_roll_s = pre_roll_s
        self.end_silence_s = end_silence_s
        self.max_utterance_s = max_utterance_s
        self.on_result = on_result or self._print_result
        self.debug_audio_dir = debug_audio_dir
        self._stop = False
        self._triggered_at: float | None = None
        self._trigger_name = ""

    # -- pętla ----------------------------------------------------------------
    def run_forever(self) -> None:
        self.capture.start()
        if self.ptt is not None:
            self.ptt.start()
        if self.wake is not None:
            try:
                self.wake.load()
            except FileNotFoundError as exc:
                log.warning("%s — praca tylko z push-to-talk / VAD-gate.", exc)
                self.wake = None
        try:
            self._loop()
        except KeyboardInterrupt:
            log.info("zatrzymanie (Ctrl+C)")
        finally:
            self._stop = True
            if self.ptt is not None:
                self.ptt.stop()
            self.capture.stop()

    def _loop(self) -> None:
        recorder: UtteranceRecorder | None = None
        session: VadSession | None = None
        while not self._stop:
            try:
                chunk, _ts = self.capture.read(timeout=0.5)
            except queue.Empty:
                continue

            if session is None:
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
                    self.vad.reset()  # świeży stan Silero dla nowej wypowiedzi
                    self._triggered_at = time.perf_counter()
                    self._trigger_name = trigger
                    log.info("▶ %s — nasłuchuję (maks. %.0f s)", trigger, self.max_utterance_s)
                continue

            # LISTENING / CAPTURING
            assert recorder is not None
            prob = self.vad.process(chunk)
            recorder.add(chunk)
            session.push(chunk, prob)

            finish = False
            if session.maxed_out:
                log.info("■ koniec: maksymalna długość wypowiedzi (%.0f s)", self.max_utterance_s)
                finish = True
            elif session.end_of_speech:
                log.info("■ koniec: %.0f ms ciszy", self.end_silence_s * 1000)
                finish = True
            elif self._trigger_name == "ptt" and not self.ptt.is_pressed:
                if session.speech_started:
                    log.info("■ koniec: zwolniono push-to-talk")
                    finish = True
                else:
                    log.info("■ PTT zwolniony bez mowy — sesja anulowana")
                    recorder, session = None, None
                    continue
            elif session.timed_out:
                log.info("■ timeout: brak mowy przez 2.0 s po wybudzeniu")
                recorder, session = None, None
                continue

            if finish:
                audio = recorder.finish(session.cutoff_frames() if session.speech_started else None)
                self._finish(audio)
                recorder, session = None, None

    # -- wybudzenie ------------------------------------------------------------
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

    # -- zakończenie sesji ------------------------------------------------------
    def _finish(self, audio: np.ndarray) -> None:
        n = len(audio)
        if n < 1600:  # < 100 ms — za mało na komendę
            log.info("pominięto: nagranie za krótkie (%.0f ms)", n / 16)
            return
        if self.debug_audio_dir is not None:
            self._save_wav(audio)
        result = self.asr.transcribe(audio)
        end_to_end_ms = (time.perf_counter() - self._triggered_at) * 1000
        self.on_result(
            PipelineResult(
                text=result.text,
                asr_ms=result.elapsed_s * 1000,
                end_to_end_ms=end_to_end_ms,
                trigger=self._trigger_name,
                audio_seconds=result.audio_seconds,
            )
        )

    def _save_wav(self, audio: np.ndarray) -> None:
        self.debug_audio_dir.mkdir(parents=True, exist_ok=True)  # type: ignore[union-attr]
        path = self.debug_audio_dir / f"utt_{time.strftime('%H%M%S')}_{len(audio)}.wav"  # type: ignore[union-attr]
        pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(pcm.tobytes())
        log.debug("nagranie zapisane: %s", path)

    @staticmethod
    def _print_result(r: PipelineResult) -> None:
        if r.text:
            print(
                f'🎤 "{r.text}"  [ASR {r.asr_ms:.0f} ms | pętla {r.end_to_end_ms:.0f} ms | {r.trigger}]'
            )
        else:
            print(f"🎤 (cisza/brak mowy)  [ASR {r.asr_ms:.0f} ms | {r.trigger}]")
