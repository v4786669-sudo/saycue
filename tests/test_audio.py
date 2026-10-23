"""Testy warstwy audio: bufor kołowy, pre-roll, recorder (bez urządzenia)."""

import numpy as np

from saycue.audio.capture import PRE_ROLL_S, RingBuffer, UtteranceRecorder

SR = 16000


def make_chunk(n, start=0.0):
    return np.arange(start, start + n, dtype=np.float32) / 1000.0


def test_ring_buffer_keeps_capacity():
    rb = RingBuffer(samplerate=SR, capacity_s=1.0)
    for _ in range(40):  # 40 × 512 = 20480 ramek = 1.28 s
        rb.append(make_chunk(512))
    assert rb.frames <= SR  # maks. 1.0 s


def test_ring_buffer_tail():
    rb = RingBuffer(samplerate=SR, capacity_s=2.0)
    rb.append(np.zeros(SR, dtype=np.float32))  # 1.0 s
    rb.append(np.ones(SR // 2, dtype=np.float32))  # 0.5 s
    tail = rb.tail(0.4)
    assert tail.size == int(0.4 * SR)
    assert np.all(tail == 1.0)  # ostatnie 0.4 s to jedynki


def test_ring_buffer_tail_short():
    rb = RingBuffer(samplerate=SR)
    rb.append(np.ones(1000, dtype=np.float32))
    tail = rb.tail(PRE_ROLL_S)
    assert tail.size == 1000  # mniej niż żądany pre-roll


def test_pre_roll_in_recorder():
    rb = RingBuffer(samplerate=SR)
    rb.append(np.ones(int(0.4 * SR), dtype=np.float32))  # pre-roll: same jedynki
    rec = UtteranceRecorder(rb, pre_roll_s=0.4, max_utterance_s=8.0)
    rec.add(np.zeros(int(0.5 * SR), dtype=np.float32))
    audio = rec.finish()
    assert audio.size == int(0.9 * SR)
    # pre-roll na początku, nowe ramki potem
    assert np.all(audio[: int(0.4 * SR)] == 1.0)
    assert np.all(audio[int(0.4 * SR) :] == 0.0)


def test_recorder_cutoff_trims_tail():
    rb = RingBuffer(samplerate=SR)
    rec = UtteranceRecorder(rb, pre_roll_s=0.0, max_utterance_s=8.0)
    rec.add(np.ones(SR, dtype=np.float32))  # 1.0 s mowy
    audio = rec.finish(cut_frames=int(0.6 * SR))
    assert audio.size == int(0.6 * SR)


def test_recorder_max_full():
    rb = RingBuffer(samplerate=SR)
    rec = UtteranceRecorder(rb, pre_roll_s=0.0, max_utterance_s=2.0)
    rec.add(np.ones(2 * SR, dtype=np.float32))
    assert rec.is_full
