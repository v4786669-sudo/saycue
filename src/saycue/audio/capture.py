"""Przechwytywanie audio: sounddevice 16 kHz mono, bufor kołowy, pre-roll 400 ms.

Główny backend: `sounddevice` (PortAudio) — Windows/Linux/macOS.
Fallback (środowiska bez PortAudio): natywny ALSA przez ctypes (`hw:` lub `default`),
używany automatycznie, gdy import sounddevice się nie powiedzie.
"""

from __future__ import annotations

import logging
import queue
import time
from collections import deque
from collections.abc import Callable

import numpy as np

SAMPLE_RATE = 16000
BLOCK_SAMPLES = 512  # 32 ms @ 16 kHz — natywna ramka Silero VAD
PRE_ROLL_S = 0.4
RING_CAPACITY_S = 5.0

log = logging.getLogger(__name__)


class RingBuffer:
    """Bufor kołowy mono float32 — źródło pre-rollu (400 ms przed wybudzeniem)."""

    def __init__(self, samplerate: int = SAMPLE_RATE, capacity_s: float = RING_CAPACITY_S):
        self.samplerate = samplerate
        self.capacity_frames = int(samplerate * capacity_s)
        self._chunks: deque[np.ndarray] = deque()
        self._frames = 0

    def append(self, chunk: np.ndarray) -> None:
        arr = np.asarray(chunk, dtype=np.float32).ravel()
        if arr.size == 0:
            return
        self._chunks.append(arr)
        self._frames += arr.size
        while self._frames > self.capacity_frames:
            self._frames -= len(self._chunks.popleft())

    def tail(self, seconds: float) -> np.ndarray:
        """Ostatnie `seconds` sekund audio (mniej, jeśli bufor krótszy)."""
        want = min(int(seconds * self.samplerate), self._frames)
        if want <= 0:
            return np.zeros(0, dtype=np.float32)
        parts: list[np.ndarray] = []
        remaining = want
        for chunk in reversed(self._chunks):
            if remaining <= 0:
                break
            parts.append(chunk[-remaining:] if remaining < chunk.size else chunk)
            remaining -= chunk.size
        parts.reverse()
        return np.concatenate(parts)

    @property
    def frames(self) -> int:
        return self._frames

    def clear(self) -> None:
        self._chunks.clear()
        self._frames = 0


class UtteranceRecorder:
    """Zapis wypowiedzi: pre-roll + strumień; przycięcie ogona ciszy po VAD."""

    def __init__(
        self,
        ring: RingBuffer,
        pre_roll_s: float = PRE_ROLL_S,
        max_utterance_s: float = 8.0,
    ):
        self._ring = ring
        self._pre_roll_s = pre_roll_s
        self._max_frames = int(max_utterance_s * ring.samplerate)
        self._parts: list[np.ndarray] = []
        self._frames = 0
        self._pre_roll = ring.tail(pre_roll_s)

    def add(self, chunk: np.ndarray) -> None:
        arr = np.asarray(chunk, dtype=np.float32).ravel()
        self._parts.append(arr)
        self._frames += arr.size

    @property
    def is_full(self) -> bool:
        return self._frames >= self._max_frames

    @property
    def frames(self) -> int:
        return self._frames

    def finish(self, cut_frames: int | None = None) -> np.ndarray:
        """Zwraca nagranie = pre_roll + części; `cut_frames` ucina ogon
        (liczba ramek od początku wypowiedzi do ostatniej mowy + margines)."""
        audio = np.concatenate([self._pre_roll, *self._parts]) if self._parts else self._pre_roll
        if cut_frames is not None:
            keep = self._pre_roll.size + max(0, int(cut_frames))
            audio = audio[:keep]
        return np.asarray(audio, dtype=np.float32)


class AudioCapture:
    """Strumień 16 kHz mono + bufor kołowy + kolejka ramek dla pipeline'u.

    Backend wybierany automatycznie: sounddevice → ALSA(ctypes)."""

    def __init__(
        self,
        device: int | None = None,
        alsa_device: str | None = None,
        samplerate: int = SAMPLE_RATE,
        blocksize: int = BLOCK_SAMPLES,
    ):
        self.samplerate = samplerate
        self.blocksize = blocksize
        self.ring = RingBuffer(samplerate)
        self.queue: queue.Queue[tuple[np.ndarray, float]] = queue.Queue()
        self._backend = None
        self._device = device
        self._alsa_device = alsa_device or "default"
        self.started = False

    # -- backend ------------------------------------------------------------
    def _make_backend(self):
        try:
            import sounddevice as _sd  # noqa: F401

            from ._sounddevice_backend import SoundDeviceBackend

            return SoundDeviceBackend(
                capture=self,
                device=self._device,
                samplerate=self.samplerate,
                blocksize=self.blocksize,
            )
        except OSError as exc:  # PortAudio library not found itd.
            log.warning("sounddevice niedostępny (%s) — fallback na ALSA(ctypes).", exc)
        except ImportError:
            log.warning("sounddevice nie zainstalowany — fallback na ALSA(ctypes).")
        from ._alsa_backend import AlsaBackend

        return AlsaBackend(
            capture=self,
            device_name=self._alsa_device,
            samplerate=self.samplerate,
            blocksize=self.blocksize,
        )

    # -- lifecycle ----------------------------------------------------------
    def start(self) -> None:
        if self.started:
            return
        self._backend = self._make_backend()
        self._backend.start()
        self.started = True
        log.info("audio: %s", self._backend.describe())

    def stop(self) -> None:
        if self._backend is not None:
            self._backend.stop()
        self.started = False

    def __enter__(self) -> AudioCapture:
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    # -- konsumenci ---------------------------------------------------------
    def _on_chunk(self, chunk: np.ndarray) -> None:
        self.ring.append(chunk)
        self.queue.put((chunk.copy(), time.perf_counter()))

    def read(self, timeout: float = 1.0) -> tuple[np.ndarray, float]:
        return self.queue.get(timeout=timeout)

    def on_utterance(self, callback: Callable[[np.ndarray], None]) -> None:
        """Hook: każdy chunk trafia też do callbacku (używane przez recorder)."""
        self._extra = callback  # type: ignore[attr-defined]


class AudioError(RuntimeError):
    """Nie udało się otworzyć urządzenia audio."""
