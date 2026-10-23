"""Test integracyjny pętli W1 (marker `models`): WAV → capture → VAD → ASR.

Symuluje mikrofon: ramki z nagrania TTS wchodzą do RingBuffer + kolejki
AudioCapture, pipeline wybudza się (VAD-gate), segmentuje wypowiedź i
transkrybuje. To dowód pętli audio→ASR bez urządzenia (deterministyczny).
"""

from __future__ import annotations

import threading
import time

import numpy as np
import pytest

pytestmark = pytest.mark.models

from faster_whisper.audio import decode_audio  # noqa: E402

from saycue.asr.manifest import load_manifest, verify_spec  # noqa: E402
from saycue.asr.whisper import ASREngine  # noqa: E402
from saycue.audio.capture import AudioCapture  # noqa: E402
from saycue.pipeline import Pipeline, PipelineResult  # noqa: E402
from saycue.vad.silero import SileroVAD  # noqa: E402

SR = 16000
WAV = "g1_05.wav"  # "przełącz na pvp" (piper + szum pokoju)


@pytest.fixture(scope="module")
def wav_path(tmp_path_factory):
    from pathlib import Path

    p = Path(__file__).resolve().parents[1] / "eval" / "recordings" / WAV
    if not p.is_file():
        pytest.skip("brak nagrań eval — scripts/generate_eval_recordings.py")
    return p


def test_loop_transcribes_wav(wav_path):
    spec = load_manifest()["whisper-small"]
    ok, msg = verify_spec(spec)
    if not ok:
        pytest.skip(f"model niedostępny ({msg})")

    audio = np.asarray(decode_audio(str(wav_path), sampling_rate=SR), dtype=np.float32)
    capture = _FakeCapture(audio)
    asr = ASREngine(model_size="small", language="pl")
    results: list[PipelineResult] = []
    done = threading.Event()

    def on_result(r: PipelineResult) -> None:
        results.append(r)
        done.set()

    pipeline = Pipeline(
        asr=asr,
        capture=capture,
        vad=SileroVAD(),
        wake=None,
        ptt=None,
        on_result=on_result,
        end_silence_s=0.6,
        max_utterance_s=8.0,
    )
    thread = threading.Thread(target=pipeline.run_forever, daemon=True)
    thread.start()
    try:
        assert done.wait(timeout=120), "brak transkrypcji w ciągu 120 s"
    finally:
        pipeline._stop = True
        thread.join(timeout=5)

    assert results, "pętla nie zwróciła wyniku"
    text = results[0].text.lower()
    assert "pvp" in text, f"nieoczekiwana transkrypcja: {results[0].text!r}"
    assert results[0].trigger in ("vad-gate", "wakeword", "ptt")


class _FakeCapture(AudioCapture):
    """AudioCapture, którego „mikrofon" to bufor WAV (16 kHz mono float32)."""

    def __init__(self, audio: np.ndarray):
        super().__init__()
        self._audio = np.asarray(audio, dtype=np.float32)
        self._pos = 0
        self._thread: threading.Thread | None = None
        self._running = threading.Event()

    def start(self) -> None:
        self.started = True
        self._running.set()
        self._thread = threading.Thread(target=self._play, daemon=True)
        self._thread.start()

    def _play(self) -> None:
        chunk = 512
        while self._running.is_set() and self._pos < len(self._audio):
            frame = self._audio[self._pos : self._pos + chunk]
            self._pos += chunk
            if frame.size < chunk:
                frame = np.pad(frame, (0, chunk - frame.size))
            self._on_chunk(frame)
            time.sleep(chunk / SR)  # tempo rzeczywiste (1×)
        # cisza po nagraniu, żeby VAD mógł domknąć wypowiedź (600 ms)
        end = time.monotonic() + 1.5
        while self._running.is_set() and time.monotonic() < end:
            self._on_chunk(np.zeros(chunk, dtype=np.float32))
            time.sleep(chunk / SR)

    def stop(self) -> None:
        self._running.clear()
        if self._thread is not None:
            self._thread.join(timeout=2)
