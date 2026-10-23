"""Fixture'y nagrań (stand-iny TTS): testy bez sprzętu audio.

Nagrania generuje deterministycznie ``tests/conftest.py`` (wave ze stdlib):
mowa (impulsy tonu 440 Hz), cisza, szum — 16 kHz / mono / PCM16.
"""

from __future__ import annotations

import wave

SAMPLE_RATE = 16000


def _open(path):
    return wave.open(str(path), "rb")


def test_fixtures_exist(wav_fixtures):
    assert wav_fixtures["speech"].is_file()
    assert wav_fixtures["silence"].is_file()
    assert wav_fixtures["noise"].is_file()


def test_fixture_format(wav_fixtures):
    for path in wav_fixtures.values():
        with _open(path) as w:
            assert w.getnchannels() == 1
            assert w.getsampwidth() == 2  # PCM16
            assert w.getframerate() == SAMPLE_RATE
            assert w.getnframes() > 0


def test_speech_has_signal_silence_has_none(wav_fixtures):
    with _open(wav_fixtures["speech"]) as w:
        speech = w.readframes(w.getnframes())
    with _open(wav_fixtures["silence"]) as w:
        silence = w.readframes(w.getnframes())
    assert any(b != 0 for b in speech)  # sygnał
    assert set(silence) == {0}  # cisza


def test_noise_varies_deterministically(wav_fixtures):
    with _open(wav_fixtures["noise"]) as w:
        noise = w.readframes(w.getnframes())
    assert len(set(noise)) > 10
