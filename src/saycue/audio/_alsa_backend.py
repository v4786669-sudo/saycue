"""Fallback audio: natywny ALSA przez ctypes (bez PortAudio, bez nagłówków dev).

Używany, gdy `sounddevice` nie może załadować libportaudio. Obsługuje
`default`, `hw:CARD,DEV` oraz `plughw:…` (resampling sprzętowy wtyczki).
"""

from __future__ import annotations

import ctypes
import logging
import threading
from ctypes import POINTER, c_char_p, c_int, c_long, c_uint, c_void_p

import numpy as np

log = logging.getLogger(__name__)

SND_PCM_STREAM_CAPTURE = 1
SND_PCM_FORMAT_S16_LE = 2
SND_PCM_ACCESS_RW_INTERLEAVED = 3

_lib = None


def _alsa_lib():
    global _lib
    if _lib is not None:
        return _lib
    for name in ("libasound.so.2", "libasound.so"):
        try:
            lib = ctypes.CDLL(name)
        except OSError:
            continue
        _lib = lib
        return lib
    raise ImportError("libasound.so.2 nie znaleziona — brak fallbacku ALSA")


class AlsaError(RuntimeError):
    pass


class AlsaPcm:
    def __init__(self, device_name: str, samplerate: int = 16000, channels: int = 1):
        lib = _alsa_lib()
        self._lib = lib
        self._handle = c_void_p()
        lib.snd_pcm_open.restype = c_int
        lib.snd_pcm_open.argtypes = [POINTER(c_void_p), c_char_p, c_int, c_int]
        lib.snd_strerror.restype = c_char_p
        lib.snd_strerror.argtypes = [c_int]

        rc = lib.snd_pcm_open(
            ctypes.byref(self._handle),
            device_name.encode(),
            SND_PCM_STREAM_CAPTURE,
            0,
        )
        if rc < 0:
            raise AlsaError(f"ALSA: nie można otworzyć '{device_name}': {self._err(rc)}")

        lib.snd_pcm_set_params.restype = c_int
        lib.snd_pcm_set_params.argtypes = [
            c_void_p,
            c_int,
            c_int,
            c_uint,
            c_uint,
            c_int,
            c_uint,
        ]
        rc = lib.snd_pcm_set_params(
            self._handle,
            SND_PCM_FORMAT_S16_LE,
            SND_PCM_ACCESS_RW_INTERLEAVED,
            channels,
            samplerate,
            1,  # soft_resample
            200_000,  # latency (us)
        )
        if rc < 0:
            self.close()
            raise AlsaError(f"ALSA: set_params {samplerate} Hz mono nieudane: {self._err(rc)}")

    def _err(self, rc: int) -> str:
        msg = self._lib.snd_strerror(rc)
        return msg.decode("utf-8", "replace") if msg else f"kod {rc}"

    def readi(self, frames: int) -> np.ndarray:
        """Odczyt `frames` ramek jako float32 [-1, 1]."""
        buf = np.zeros(frames, dtype=np.int16)
        self._lib.snd_pcm_readi.restype = c_long
        self._lib.snd_pcm_readi.argtypes = [c_void_p, c_void_p, c_uint]
        got = self._lib.snd_pcm_readi(self._handle, buf.ctypes.data_as(c_void_p), c_uint(frames))
        if got < 0:
            if got == -32:  # -EPIPE: overrun — wznowienie strumienia
                self.prepare()
                return np.zeros(frames, dtype=np.float32)
            raise AlsaError(f"ALSA: readi: {self._err(int(got))}")
        if got == 0:
            return np.zeros(0, dtype=np.float32)
        return buf[:got].astype(np.float32) / 32768.0

    def prepare(self) -> None:
        self._lib.snd_pcm_prepare.restype = c_int
        self._lib.snd_pcm_prepare.argtypes = [c_void_p]
        self._lib.snd_pcm_prepare(self._handle)

    def close(self) -> None:
        if self._handle:
            self._lib.snd_pcm_close(self._handle)
            self._handle = None


class AlsaBackend:
    def __init__(self, capture, device_name="default", samplerate=16000, blocksize=512):
        self.capture = capture
        self.device_name = device_name
        self.samplerate = samplerate
        self.blocksize = blocksize
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._pcm: AlsaPcm | None = None

    def start(self) -> None:
        self._pcm = AlsaPcm(self.device_name, self.samplerate, channels=1)
        self._thread = threading.Thread(target=self._loop, name="saycue-alsa", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        assert self._pcm is not None
        while not self._stop.is_set():
            try:
                chunk = self._pcm.readi(self.blocksize)
            except AlsaError as exc:
                log.error("ALSA: %s", exc)
                break
            if chunk.size:
                self.capture._on_chunk(chunk)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        if self._pcm is not None:
            self._pcm.close()
            self._pcm = None

    def describe(self) -> str:
        return f"ALSA (ctypes) '{self.device_name}', {self.samplerate} Hz mono"


def list_devices() -> list[dict]:
    """Lista urządzeń wejściowych z /proc/asound (bez zależności ALSA-dev)."""
    devices: list[dict] = []
    try:
        cards = {}
        for line in open("/proc/asound/cards", encoding="utf-8", errors="replace"):
            if "[" in line and "]" in line:
                idx = line.split()[0]
                cards[idx] = line[line.index("[") + 1 : line.index("]")]
        for line in open("/proc/asound/pcm", encoding="utf-8", errors="replace"):
            if "capture" not in line:
                continue
            parts = line.split(":")
            if len(parts) < 2:
                continue
            hwid = parts[0].strip()  # np. "00-00"
            card = hwid.split("-")[0]
            name = cards.get(card, hwid)
            devices.append(
                {
                    "alsa_name": f"hw:{hwid.replace('-', ',')}",
                    "description": f"{name} ({hwid}) — ALSA",
                }
            )
    except OSError:
        pass
    devices.append({"alsa_name": "default", "description": "ALSA default"})
    return devices
