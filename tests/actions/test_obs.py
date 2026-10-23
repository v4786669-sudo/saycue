"""Testy klienta obs-websocket v5 na atrapie serwera (bez OBS).

Mock wdraża minimalny protokół v5 (Hello → Identify → Identified →
Request/RequestResponse) na websockets.sync.server; sprawdzamy:
* handshake z hasłem i bez,
* akcje: scena (w tym __next__/__prev__ po liście scen), mute, record,
  replay, filter, source_toggle,
* reconnect z backoffem po zerwaniu połączenia przez serwer,
* czytelny błąd, gdy OBS nie działa (OBS < 28 / zły port).
"""

from __future__ import annotations

import base64
import hashlib
import json
import socket
import threading
import time

import pytest

from saycue.actions import (
    ActionContext,
    ObsClient,
    ObsError,
    ObsFilterAction,
    ObsMuteAction,
    ObsRecordAction,
    ObsReplayAction,
    ObsSceneAction,
    ObsSourceToggleAction,
)

try:
    from websockets.sync.server import serve as _ws_serve
except ImportError:  # pragma: no cover
    pytest.skip("websockets nie zainstalowany", allow_module_level=True)


def _auth_secret(salt: str, password: str) -> str:
    return base64.b64encode(hashlib.sha256((salt + password).encode()).digest()).decode()


def _auth_string(salt: str, challenge: str, password: str) -> str:
    return base64.b64encode(
        hashlib.sha256((challenge + _auth_secret(salt, password)).encode()).digest()
    ).decode()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class MockObsServer:
    """Atrapa obs-websocket v5; rejestruje żądania, może zrywać połączenia."""

    def __init__(self, *, password: str = "", drop_after_requests: int | None = None):
        self.host = "127.0.0.1"
        self.port = _free_port()
        self.password = password
        self.drop_after_requests = drop_after_requests
        self.requests: list[tuple[str, dict]] = []
        self.connection_count = 0
        self._conns: list = []
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

    def _handler(self, ws) -> None:
        self._conns.append(ws)
        self.connection_count += 1
        ws.send(json.dumps({
            "op": 0,
            "d": {
                "obsWebSocketVersion": "5.5.5",
                "rpcVersion": 1,
                "authentication": {"challenge": "challenge", "salt": "salt"},
            },
        }))
        ident = json.loads(ws.recv(timeout=5))
        if self.password:
            expected = _auth_string("salt", "challenge", self.password)
            if (ident.get("d") or {}).get("authentication") != expected:
                ws.close()
                return
        ws.send(json.dumps({"op": 2, "d": {"negotiatedRpcVersion": 1}}))
        self._ready.set()
        served = 0
        for raw in ws:
            msg = json.loads(raw)
            if msg.get("op") == 6:
                d = msg["d"]
                self.requests.append((d["requestType"], d.get("requestData") or {}))
                served += 1
                if self.drop_after_requests is not None and served > self.drop_after_requests:
                    ws.close()  # zerwanie POZA odpowiedzią → klient się reconnectuje
                    return
                ws.send(json.dumps({
                    "op": 7,
                    "d": {
                        "requestType": d["requestType"],
                        "requestId": d["requestId"],
                        "requestStatus": {"code": 100, "result": True},
                        "responseData": self._canned(d["requestType"]),
                    },
                }))

    def _run(self) -> None:
        self._server = _ws_serve(self._handler, self.host, self.port)
        self._server.serve_forever()  # serve() zwraca Server; blokuje serve_forever()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        for ws in self._conns:
            try:
                ws.close()
            except Exception:
                pass
        if self._server is not None:
            try:
                self._server.shutdown()
            except Exception:
                pass
        self._thread.join(timeout=5)


def _connect_wait(client: ObsClient, tries: int = 30) -> None:
    last = None
    for _ in range(tries):
        try:
            client.connect()
            return
        except ObsError as exc:
            last = exc
            time.sleep(0.05)
    raise last


@pytest.fixture()
def server():
    srv = MockObsServer()
    srv.start()
    yield srv
    srv.stop()


@pytest.fixture()
def client(server) -> ObsClient:
    c = ObsClient(host=server.host, port=server.port, timeout=3.0)
    _connect_wait(c)
    yield c
    c.close()


def test_connect_and_identify(server, client):
    assert client.connected is True
    assert server.connection_count >= 1


def test_set_scene(client, server):
    resp = client.set_scene("Live")
    assert isinstance(resp, dict)
    assert server.requests[-1] == ("SetCurrentProgramScene", {"sceneName": "Live"})


def test_toggle_mute_returns_muted(client, server):
    resp = client.toggle_mute("Mic/Aux")
    assert resp == {"inputMuted": True}
    assert server.requests[-1] == ("ToggleInputMute", {"inputName": "Mic/Aux"})


def test_set_mute(client, server):
    client.set_mute("Mic/Aux", True)
    assert server.requests[-1] == ("SetInputMute", {"inputName": "Mic/Aux", "inputMuted": True})
    client.set_mute("Mic/Aux", False)
    assert server.requests[-1] == ("SetInputMute", {"inputName": "Mic/Aux", "inputMuted": False})


def test_record_requests(client, server):
    client.start_record()
    assert server.requests[-1][0] == "StartRecord"
    client.stop_record()
    assert server.requests[-1][0] == "StopRecord"
    client.toggle_record()
    assert server.requests[-1][0] == "ToggleRecord"


def test_replay_requests(client, server):
    client.save_replay_buffer()
    assert server.requests[-1][0] == "SaveReplayBuffer"
    client.start_replay_buffer()
    assert server.requests[-1][0] == "StartReplayBuffer"
    client.stop_replay_buffer()
    assert server.requests[-1][0] == "StopReplayBuffer"


def test_filter_request(client, server):
    client.set_source_filter_enabled("kamera", "Censor", True)
    assert server.requests[-1] == (
        "SetSourceFilterEnabled",
        {"sourceName": "kamera", "filterName": "Censor", "filterEnabled": True},
    )


def test_scene_next_prev_cycles(client, server):
    # sceny mocka: Starting Soon → PVP (aktualna) → BRB
    target_next = client.step_scene(+1)
    assert target_next == "BRB"
    assert server.requests[-1] == ("SetCurrentProgramScene", {"sceneName": "BRB"})
    target_prev = client.step_scene(-1)  # aktualna nadal PVP wg mocka
    assert target_prev == "Starting Soon"


def test_scene_action_slots(client):
    ctx = ActionContext(obs=client)
    r = ObsSceneAction().execute({"scene": "Live"}, ctx)
    assert r.ok is True and "Live" in r.message
    r = ObsSceneAction().execute({"scene": "__next__"}, ctx)
    assert r.ok is True and r.details["scene"] == "BRB"
    r = ObsSceneAction().execute({"scene": "__prev__"}, ctx)
    assert r.ok is True and r.details["scene"] == "Starting Soon"


def test_mute_action_states(client, server):
    ctx = ActionContext(obs=client)
    r = ObsMuteAction().execute({"source": "Mic/Aux", "state": "toggle"}, ctx)
    assert r.ok is True and r.details["muted"] is True
    r = ObsMuteAction().execute({"source": "Mic/Aux", "state": "on"}, ctx)
    assert r.ok is True and server.requests[-1][0] == "SetInputMute"
    assert server.requests[-1][1]["inputMuted"] is True
    r = ObsMuteAction().execute({"source": "Mic/Aux", "state": "off"}, ctx)
    assert r.ok is True and server.requests[-1][1]["inputMuted"] is False


def test_record_and_replay_actions(client, server):
    ctx = ActionContext(obs=client)
    assert ObsRecordAction().execute({"state": "start"}, ctx).ok is True
    assert server.requests[-1][0] == "StartRecord"
    assert ObsRecordAction().execute({"state": "stop"}, ctx).ok is True
    assert server.requests[-1][0] == "StopRecord"
    assert ObsRecordAction().execute({"state": "toggle"}, ctx).ok is True
    assert server.requests[-1][0] == "ToggleRecord"
    assert ObsReplayAction().execute({"action": "save"}, ctx).ok is True
    assert server.requests[-1][0] == "SaveReplayBuffer"
    assert ObsReplayAction().execute({}, ctx).ok is True  # domyślnie save
    assert server.requests[-1][0] == "SaveReplayBuffer"


def test_filter_and_source_toggle_actions(client, server):
    ctx = ActionContext(obs=client)
    r = ObsFilterAction().execute(
        {"source": "kamera", "filter": "Censor", "state": "on"}, ctx
    )
    assert r.ok is True
    assert server.requests[-1] == (
        "SetSourceFilterEnabled",
        {"sourceName": "kamera", "filterName": "Censor", "filterEnabled": True},
    )
    r = ObsSourceToggleAction().execute({"source": "Alerts"}, ctx)
    assert r.ok is True and r.details["muted"] is True
    assert server.requests[-1] == ("ToggleInputMute", {"inputName": "Alerts"})


def test_actions_without_obs_client():
    ctx = ActionContext(obs=None)
    for action in (
        ObsSceneAction(),
        ObsMuteAction(),
        ObsRecordAction(),
        ObsReplayAction(),
        ObsFilterAction(),
        ObsSourceToggleAction(),
    ):
        assert action.available(ctx) is False
        r = action.execute({"scene": "x", "source": "y", "state": "toggle"}, ctx)
        assert r.ok is False and r.error == "obs_not_connected"


def test_connect_failure_readable_error():
    client = ObsClient(host="127.0.0.1", port=_free_port(), timeout=0.5, reconnect=False)
    with pytest.raises(ObsError) as exc_info:
        client.connect()
    assert exc_info.value.code == "connect_failed"
    assert "OBS" in str(exc_info.value)  # komunikat o OBS ≥ 28


def test_auth_with_password():
    srv = MockObsServer(password="sekret123")
    srv.start()
    try:
        good = ObsClient(host=srv.host, port=srv.port, password="sekret123", timeout=3.0)
        _connect_wait(good)
        assert good.connected is True
        good.close()
        bad = ObsClient(host=srv.host, port=srv.port, password="zle-haslo", timeout=3.0)
        with pytest.raises(ObsError) as exc_info:
            _connect_wait(bad, tries=5)
        assert exc_info.value.code == "identify_failed"
    finally:
        srv.stop()


def test_reconnect_after_drop():
    srv = MockObsServer(drop_after_requests=1)
    srv.start()
    try:
        client = ObsClient(
            host=srv.host, port=srv.port, timeout=3.0,
            reconnect=True, backoff=(0.05, 0.05),
        )
        _connect_wait(client)
        assert client.connected is True
        client.set_scene("PVP")  # 1. żądanie — serwer odpowiada i zrywa PRZY 2.
        assert client.connected is True  # zerwanie nastąpi dopiero przy 2. żądaniu
        resp = client.request("StartRecord")  # serwer zrywa bez odpowiedzi → retry
        assert isinstance(resp, dict)
        assert srv.connection_count == 2
        types = [t for t, _ in srv.requests]
        assert types.count("StartRecord") == 2  # oryginał + retry po reconnect
        client.close()
    finally:
        srv.stop()
