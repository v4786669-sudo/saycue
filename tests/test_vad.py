"""Testy VAD: logika sesji (bez modelu) + model Silero na ciszy (szybki)."""

import numpy as np
import pytest

from saycue.vad.silero import (
    END_SILENCE_S,
    MAX_UTTERANCE_S,
    VAD_WINDOW,
    SileroVAD,
    VadSession,
)

SR = 16000


def chunk(n=VAD_WINDOW):
    return np.zeros(n, dtype=np.float32)


def test_session_end_of_speech_600ms():
    s = VadSession(end_silence_s=END_SILENCE_S, max_utterance_s=MAX_UTTERANCE_S)
    # mowa
    s.push(chunk(), 0.9)
    assert s.speech_started
    assert not s.end_of_speech
    # 600 ms ciszy = 9600 ramek = 18.75 okna → po 19 oknach koniec mowy
    for _ in range(int(END_SILENCE_S * SR / VAD_WINDOW)):
        s.push(chunk(), 0.1)
        assert not s.end_of_speech
    s.push(chunk(), 0.1)
    assert s.end_of_speech


def test_session_timeout_without_speech():
    s = VadSession(timeout_no_speech_s=2.0)
    for _ in range(int(2.0 * SR / VAD_WINDOW) + 1):
        s.push(chunk(), 0.1)
    assert s.timed_out and not s.speech_started


def test_session_max_utterance_8s():
    s = VadSession(max_utterance_s=2.0)  # skrócone dla testu
    for _ in range(int(2.0 * SR / VAD_WINDOW) + 1):
        s.push(chunk(), 0.9)
    assert s.maxed_out


def test_cutoff_frames_tracks_last_speech():
    s = VadSession(end_silence_s=END_SILENCE_S)
    s.push(chunk(), 0.9)  # mowa
    s.push(chunk(), 0.1)  # cisza
    s.push(chunk(), 0.9)  # mowa — ostatnia
    s.push(chunk(), 0.1)  # cisza
    cutoff = s.cutoff_frames(margin_s=0.0)
    assert cutoff == s.speech_frames
    assert 2 * VAD_WINDOW < cutoff <= 4 * VAD_WINDOW


def test_silero_model_loads_and_silence_is_silence():
    pytest.importorskip("faster_whisper.vad")
    vad = SileroVAD()
    probs = []
    for _ in range(32):  # 1.0 s ciszy
        p = vad.process(chunk())
        if p is not None:
            probs.append(p)
    assert probs, "brak wyjścia VAD"
    assert max(probs) < 0.5, f"cisza wykryta jako mowa: {max(probs):.3f}"
