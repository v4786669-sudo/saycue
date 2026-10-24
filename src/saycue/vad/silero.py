"""Silero VAD (ONNX) — segmentacja mowy na żywo, strumieniowo.

Model Silero VAD v6 jest wbudowany w pakiet `faster-whisper`
(`assets/silero_vad_v6.onnx`, MIT — bez osobnego pobierania), architektura
§3.6. Własny wrapper utrzymuje stan LSTM (h, c) i kontekst 64 próbek między
ramkami — wrapper z faster_whisper.vad jest bezstanowy i przeznaczony do
filtrowania całych plików, nie do strumienia.

Ramka wejściowa: 512 próbek @ 16 kHz (32 ms).

Parametry, §3.2):
- koniec mowy: 600 ms ciągłej ciszy (GUI 400–1200 ms w W3),
- maksymalna wypowiedź: 8 s (uwalnia mikrofon dla czatu/gry),
- próg prawdopodobieństwa mowy: 0.5 (domyślny Silero).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..audio.capture import SAMPLE_RATE

VAD_WINDOW = 512  # natywne okno Silero @ 16 kHz
VAD_CONTEXT = 64  # kontekst LSTM poprzedzający okno
DEFAULT_THRESHOLD = 0.5
END_SILENCE_S = 0.6
MAX_UTTERANCE_S = 8.0
TIMEOUT_NO_SPEECH_S = 2.0  # cisza po wybudzeniu → powrót do IDLE

log = logging.getLogger(__name__)


def _bundled_model_path() -> Path:
    import faster_whisper

    return Path(faster_whisper.__file__).parent / "assets" / "silero_vad_v6.onnx"


class SileroVAD:
    """Strumieniowy Silero VAD: podajesz 16 kHz float32, dostajesz p(mowa) na okno."""

    def __init__(self, threshold: float = DEFAULT_THRESHOLD, model_path: Path | None = None):
        import onnxruntime

        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        opts.enable_cpu_mem_arena = False
        opts.log_severity_level = 4
        self.session = onnxruntime.InferenceSession(
            str(model_path or _bundled_model_path()),
            providers=["CPUExecutionProvider"],
            sess_options=opts,
        )
        self.threshold = threshold
        self.reset()

    def reset(self) -> None:
        """Stan LSTM + kontekst od zera (nowa wypowiedź)."""
        self._h = np.zeros((1, 1, 128), dtype=np.float32)
        self._c = np.zeros((1, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, VAD_CONTEXT), dtype=np.float32)
        self._pending = np.zeros(0, dtype=np.float32)

    def process(self, chunk: np.ndarray) -> float | None:
        """Podaje chunk (dowolny rozmiar) i zwraca p(mowa) dla pełnego okna 512
        próbek; None, gdy okno jeszcze niepełne."""
        arr = np.asarray(chunk, dtype=np.float32).ravel()
        self._pending = np.concatenate([self._pending, arr])
        if self._pending.size < VAD_WINDOW:
            return None
        window, self._pending = self._pending[:VAD_WINDOW], self._pending[VAD_WINDOW:]
        # wejście modelu: [kontekst 64 próbek z poprzedniego okna | okno 512]
        x = np.concatenate([self._context, window.reshape(1, VAD_WINDOW)], axis=1).reshape(
            1, VAD_WINDOW + VAD_CONTEXT
        )
        out, h, c = self.session.run(None, {"input": x, "h": self._h, "c": self._c})
        self._h, self._c = h, c
        self._context = window[-VAD_CONTEXT:].reshape(1, VAD_CONTEXT)
        return float(np.asarray(out).ravel()[0])


@dataclass
class VadSession:
    """Stan jednej wypowiedzi: początek mowy, koniec mowy, timeout, maks. czas."""

    threshold: float = DEFAULT_THRESHOLD
    end_silence_s: float = END_SILENCE_S
    max_utterance_s: float = MAX_UTTERANCE_S
    timeout_no_speech_s: float = TIMEOUT_NO_SPEECH_S
    sample_rate: int = SAMPLE_RATE

    speech_started: bool = False
    speech_frames: int = 0  # ramki od startu sesji do ostatniej mowy
    silence_frames: int = 0
    total_frames: int = 0
    history: list[float] = field(default_factory=list)

    @property
    def end_silence_frames(self) -> int:
        return int(self.end_silence_s * self.sample_rate)

    @property
    def max_frames(self) -> int:
        return int(self.max_utterance_s * self.sample_rate)

    @property
    def timeout_frames(self) -> int:
        return int(self.timeout_no_speech_s * self.sample_rate)

    def push(self, chunk: np.ndarray, prob: float | None) -> None:
        self.total_frames += chunk.size
        if prob is None:
            return
        self.history.append(prob)
        if prob >= self.threshold:
            self.speech_started = True
            self.speech_frames = self.total_frames
            self.silence_frames = 0
        elif self.speech_started:
            self.silence_frames += VAD_WINDOW

    @property
    def end_of_speech(self) -> bool:
        return self.speech_started and self.silence_frames >= self.end_silence_frames

    @property
    def timed_out(self) -> bool:
        """2.0 s ciszy bez żadnej mowy po wybudzeniu."""
        return not self.speech_started and self.total_frames >= self.timeout_frames

    @property
    def maxed_out(self) -> bool:
        return self.total_frames >= self.max_frames

    def cutoff_frames(self, margin_s: float = 0.15) -> int:
        """Ramki do ostatniej mowy + margines (do przycięcia ogona ciszy)."""
        return self.speech_frames + int(margin_s * self.sample_rate)
