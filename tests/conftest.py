"""Wspólne fixture'y testów SayCue (parser/akcje — bez sprzętu audio).

* sys.path → ``src/`` (repo nie ma jeszcze pip-installowalnego builda W2);
* syntetyczne nagrania WAV (stand-iny dla nagrań TTS) generowane do
  ``tests/fixtures/`` przy pierwszym uruchomieniu — deterministyczne,
  bez mikrofonu i bez TTS (wave ze stdlib);
* sesyjny IntentParser z aktywacją: rdzeń + obs-core + apps-open + apps-streaming.
"""

from __future__ import annotations

import math
import random
import struct
import sys
import wave
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

DATA_DIR = ROOT / "data"
PRESETS_DIR = ROOT / "presets"
FIXTURES_DIR = ROOT / "tests" / "fixtures"
SAMPLE_RATE = 16000

# arcade-dash: frazy dash (dasz/uniki) przeniesione z rdzenia (N-01, t15)
RECOMMENDED_PRESETS = ["obs-core", "apps-open", "apps-streaming", "arcade-dash"]


def _write_wav(path: Path, samples: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        frames = b"".join(
            struct.pack("<h", max(-32767, min(32767, int(s * 32767)))) for s in samples
        )
        w.writeframes(frames)


@pytest.fixture(scope="session")
def wav_fixtures() -> dict[str, Path]:
    """Trzy nagrania 16 kHz/mono/PCM16: mowa (impulsy tonu), cisza, szum."""
    files = {
        "speech": FIXTURES_DIR / "speech_pl_16k_mono.wav",
        "silence": FIXTURES_DIR / "silence_16k_mono.wav",
        "noise": FIXTURES_DIR / "noise_16k_mono.wav",
    }
    if not all(p.is_file() for p in files.values()):
        speech: list[float] = []
        for _burst in range(3):
            n = int(SAMPLE_RATE * 0.2)
            for i in range(n):
                envelope = 1.0 - i / n
                speech.append(0.4 * math.sin(2 * math.pi * 440 * i / SAMPLE_RATE) * envelope)
            speech.extend([0.0] * int(SAMPLE_RATE * 0.05))
        _write_wav(files["speech"], speech)
        _write_wav(files["silence"], [0.0] * int(SAMPLE_RATE * 0.5))
        rng = random.Random(42)
        _write_wav(files["noise"], [rng.uniform(-0.2, 0.2) for _ in range(int(SAMPLE_RATE * 0.5))])
    return files


@pytest.fixture(scope="session")
def data_dir() -> Path:
    return DATA_DIR


@pytest.fixture(scope="session")
def presets_dir() -> Path:
    return PRESETS_DIR


@pytest.fixture(scope="session")
def intent_parser():
    """Rdzeń + obs-core + apps-* (gry aktywowane w testach presety osobno)."""
    from saycue.parser import IntentParser

    return IntentParser(active_presets=RECOMMENDED_PRESETS)


@pytest.fixture(scope="session")
def merged_apps(intent_parser) -> dict:
    return dict(intent_parser.config.apps)
