"""Harness bramki G2 (t9): FakeCapture (WAV jako mikrofon) + MockObsServer.

MockObsServer — podzbiór atrapy obs-websocket v5 z tests/actions/test_obs.py
(t13, engineer2): handshake Hello/Identify (opcjonalne hasło), canned odpowiedzi
dla akcji obs-core. Wersja lokalna harnessu — kanoniczna w t13 pozostaje
w tests/actions/test_obs.py.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time

import numpy as np
import websockets

from saycue.audio.capture import AudioCapture


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class MockObsServer:
    """Atrapa obs-websocket v5; rejestruje żądania i zwraca canned odpowiedzi."""

    def __init__(self, *, password: str = ""):
        self.host = "127.0.0.1"
        self.port = _free_port()
        self.password = password
        self.requests: list[tuple[str, dict]] = []
        self._server = None
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _canned(self, request_type: str) -> dict:
        if request_type == "ToggleInputMute":
            return {"inputMuted": True}
        if request_type == "GetSceneList":
            return {
                "currentProgramSceneName": "PVP",
                "scenes": [
                    {"sceneName": "Starting Soon"},
                    {"sceneName": "PVP"},
                    {"sceneName": "BRB"},
                ],
            }
        if request_type == "GetCurrentProgramScene":
            return {"currentProgramSceneName": "PVP"}
        return {}

    def _run(self) -> None:
        asyncio.set_event_loop(asyncio.new_event_loop())

        async def handler(ws):
            # protokół obs-websocket v5: serwer wysyła Hello jako pierwszy
            await ws.send(
                json.dumps(
                    {
                        "op": 0,
                        "d": {"obsWebSocketVersion": "5.4.2", "rpcVersion": 1},
                    }
                )
            )
            identified = False
            async for raw in ws:
                msg = json.loads(raw)
                op = msg.get("op")
                if op == 1:  # Identify
                    if self.password and not msg.get("d", {}).get("authentication"):
                        await ws.close(code=4008, reason="auth required")
                        return
                    await ws.send(json.dumps({"op": 2, "d": {"negotiatedRpcVersion": 1}}))
                    identified = True
                    continue
                if op == 6 and identified:  # Request
                    d = msg.get("d", {})
                    rid = d.get("requestId")
                    self.requests.append((d.get("requestType"), d.get("requestData") or {}))
                    await ws.send(
                        json.dumps(
                            {
                                "op": 7,
                                "d": {
                                    "requestType": d.get("requestType"),
                                    "requestId": rid,
                                    "requestStatus": {"result": True, "code": 100},
                                    "responseData": self._canned(d.get("requestType")),
                                },
                            }
                        )
                    )

        async def serve():
            self._server = await websockets.serve(handler, self.host, self.port)
            self._ready.set()
            await self._server.wait_closed()

        asyncio.get_event_loop().run_until_complete(serve())

    def start(self) -> None:
        self._thread.start()
        self._ready.wait(timeout=10)

    def stop(self) -> None:
        if self._server is not None:
            try:
                self._server.shutdown()  # sync zamknięcie z innego wątku (websockets)
            except Exception:
                pass
        self._thread.join(timeout=5)


class FakeCapture(AudioCapture):
    """AudioCapture, którego „mikrofon" to bufor WAV (16 kHz mono float32).

    Odtwarza nagranie w tempie rzeczywistym (1×), potem cisza 1,5 s —
    wystarczająca, by VAD domknął wypowiedź (koniec mowy = 600 ms ciszy).
    """

    def __init__(self, audio: np.ndarray, pad_silence_s: float = 1.5):
        super().__init__()
        self._audio = np.asarray(audio, dtype=np.float32)
        self._pad = pad_silence_s
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
            time.sleep(chunk / 16000)
        end = time.monotonic() + self._pad
        while self._running.is_set() and time.monotonic() < end:
            self._on_chunk(np.zeros(chunk, dtype=np.float32))
            time.sleep(chunk / 16000)

    def stop(self) -> None:
        self._running.clear()
        if self._thread is not None:
            self._thread.join(timeout=2)
