"""Backend sounddevice (PortAudio) dla AudioCapture."""

from __future__ import annotations

import logging

import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)


class SoundDeviceBackend:
    def __init__(self, capture, device=None, samplerate=16000, blocksize=512):
        self.capture = capture
        self.device = device
        self.samplerate = samplerate
        self.blocksize = blocksize
        self._stream = None

    def start(self) -> None:
        kwargs = dict(
            samplerate=self.samplerate,
            channels=1,
            dtype="float32",
            blocksize=self.blocksize,
            callback=self._callback,
        )
        if self.device is not None:
            kwargs["device"] = self.device
        self._stream = sd.InputStream(**kwargs)
        self._stream.start()

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def _callback(self, indata, frames, time_info, status) -> None:
        if status:
            log.debug("status strumienia: %s", status)
        mono = indata[:, 0] if indata.ndim > 1 else indata
        self.capture._on_chunk(np.asarray(mono, dtype=np.float32))

    def describe(self) -> str:
        return f"sounddevice (PortAudio), {self.samplerate} Hz mono"


def list_devices():
    return sd.query_devices()
