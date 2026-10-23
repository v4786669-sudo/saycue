"""Klient obs-websocket v5 + akcje OBS (scena, mute, record, replay, filtr, source toggle).

Protokół v5 zaimplementowany bezpośrednio na ``websockets`` (architektura
§3.4 — alternatywa do obsws-python, pełna kontrola nad reconnectem/backoffem).
OBS ≥ 28 ma wbudowany obs-websocket (Narzędzia → WebSocket Server).

Akcje:
* ``obs.scene`` — SetCurrentProgramScene; slot ``scene`` może być
  ``__next__``/``__prev__`` (cykliczne przełączanie po liście scen z OBS —
  decyzja t13/kapitan, presety obs-core);
* ``obs.mute`` — ToggleInputMute / SetInputMute;
* ``obs.record`` — StartRecord / StopRecord / ToggleRecord;
* ``obs.replay`` — SaveReplayBuffer / StartReplayBuffer / StopReplayBuffer;
* ``obs.filter`` — SetSourceFilterEnabled (np. cenzura, §3.4);
* ``obs.source_toggle`` — ToggleInputMute (MVP: źródła audio; mapowanie
  widoczności scen-itemów to zadanie GUI/t9).
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from collections.abc import Mapping, Sequence
from typing import Any

from .base import Action, ActionContext, ActionResult

try:
    from websockets.exceptions import ConnectionClosed  # noqa: F401
    from websockets.sync.client import connect as _ws_connect

    _WS_AVAILABLE = True
except ImportError:  # pragma: no cover
    _ws_connect = None
    _WS_AVAILABLE = False

log = logging.getLogger(__name__)

OP_HELLO = 0
OP_IDENTIFY = 1
OP_IDENTIFIED = 2
OP_EVENT = 5
OP_REQUEST = 6
OP_REQUEST_RESPONSE = 7

OBS_REQUIREMENTS = "wymagany OBS ≥ 28 z włączonym obs-websocket (Narzędzia → WebSocket Server)"


class ObsError(Exception):
    def __init__(self, code: str, message: str, request_type: str | None = None):
        self.code = code
        self.message = message
        self.request_type = request_type
        super().__init__(f"OBS {code}: {message}" + (f" [{request_type}]" if request_type else ""))


class ObsClient:
    """Klient obs-websocket v5 (sync) z automatycznym reconnectem i backoffem.

    Reconnect: przy utracie połączenia żądanie jest ponawiane raz, po
    ponownym handshake (Identify z hasłem). Backoff: 0.5, 1, 2, 4, 8, 15 s.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 4455,
        password: str = "",
        *,
        timeout: float = 5.0,
        reconnect: bool = True,
        backoff: Sequence[float] = (0.5, 1.0, 2.0, 4.0, 8.0, 15.0),
        event_subscriptions: int = 0,
    ):
        self.host = host
        self.port = int(port)
        self.password = password
        self.timeout = float(timeout)
        self.reconnect = reconnect
        self.backoff = tuple(float(b) for b in backoff)
        self.event_subscriptions = int(event_subscriptions or 0)
        self._ws = None
        self._connected = False
        self._request_id = 0

    @property
    def uri(self) -> str:
        return f"ws://{self.host}:{self.port}"

    @property
    def connected(self) -> bool:
        return self._connected

    # -------------------------------------------------------------- handshake

    def connect(self) -> None:
        """Łączy i identyfikuje (Hello → Identify → Identified). Raises ObsError."""
        self.close()
        if not _WS_AVAILABLE:
            raise ObsError(
                "missing_dependency", "zainstaluj `websockets` (pip install websockets>=12)"
            )
        try:
            self._ws = _ws_connect(self.uri, open_timeout=self.timeout, legacy=True)
        except Exception as exc:
            raise ObsError(
                "connect_failed",
                f"{type(exc).__name__}: {exc} — {OBS_REQUIREMENTS} ({self.uri})",
            ) from exc
        try:
            hello = self._recv(op_timeout=self.timeout)
            if hello.get("op") != OP_HELLO:
                raise ObsError("handshake_failed", "oczekiwano Hello (op=0)")
            self._send({"op": OP_IDENTIFY, "d": self._identify_payload(hello)})
            identified = self._recv_until(OP_IDENTIFIED)
            if identified is None:
                raise ObsError(
                    "identify_failed",
                    "brak Identified (złe hasło lub nieobsługiwana wersja OBS)",
                )
            self._connected = True
            log.info("OBS połączony: %s", self.uri)
        except ObsError:
            self.close()
            raise
        except Exception as exc:
            self.close()
            raise ObsError("connect_failed", f"{type(exc).__name__}: {exc}") from exc

    def _identify_payload(self, hello: Mapping[str, Any]) -> dict[str, Any]:
        auth = (hello.get("d") or {}).get("authentication") or {}
        payload: dict[str, Any] = {"rpcVersion": 1}
        if self.password:
            salt = str(auth.get("salt") or "")
            challenge = str(auth.get("challenge") or "")
            secret = base64.b64encode(
                hashlib.sha256((salt + self.password).encode()).digest()
            ).decode()
            payload["authentication"] = base64.b64encode(
                hashlib.sha256((challenge + secret).encode()).digest()
            ).decode()
        if self.event_subscriptions:
            payload["eventSubscriptions"] = self.event_subscriptions
        return payload

    # ------------------------------------------------------------------- I/O

    def _send(self, msg: Mapping[str, Any]) -> None:
        assert self._ws is not None
        self._ws.send(json.dumps(msg))

    def _recv(self, op_timeout: float | None = None) -> dict[str, Any]:
        assert self._ws is not None
        raw = self._ws.recv(timeout=op_timeout if op_timeout is not None else self.timeout)
        return json.loads(raw)

    def _recv_until(self, op: int, op_timeout: float | None = None) -> dict[str, Any] | None:
        deadline = time.monotonic() + (op_timeout if op_timeout is not None else self.timeout)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            try:
                msg = self._recv(op_timeout=max(0.05, remaining))
            except (ConnectionClosed, TimeoutError):
                return None
            if msg.get("op") == op:
                return msg
            # zdarzenia (op=5) pomijamy

    def _recv_response(self, request_id: str, op_timeout: float | None = None) -> dict[str, Any]:
        deadline = time.monotonic() + (op_timeout if op_timeout is not None else self.timeout)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"OBS nie odpowiedział na żądanie {request_id} w czasie")
            msg = self._recv(op_timeout=max(0.05, remaining))
            if msg.get("op") == OP_REQUEST_RESPONSE and (msg.get("d") or {}).get(
                "requestId"
            ) == str(request_id):
                return msg

    # ----------------------------------------------------------------- request

    def request(
        self,
        request_type: str,
        request_data: Mapping[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Żądanie v5; przy utracie połączenia — reconnect + 1 retry."""
        if not self._connected:
            self.connect()
        payload = {
            "op": OP_REQUEST,
            "d": {"requestType": request_type, "requestId": str(self._request_id)},
        }
        if request_data:
            payload["d"]["requestData"] = dict(request_data)
        self._request_id += 1
        request_id = payload["d"]["requestId"]
        for attempt in (0, 1):
            try:
                self._send(payload)
                msg = self._recv_response(request_id, op_timeout=timeout)
            except ObsError:
                raise
            except Exception as exc:
                if not (self.reconnect and attempt == 0):
                    raise ObsError(
                        "request_failed", f"{type(exc).__name__}: {exc}", request_type
                    ) from exc
                self._reconnect_after_failure(attempt)
                continue
            status = (msg.get("d") or {}).get("requestStatus") or {}
            code = status.get("code")
            if code != 100:
                raise ObsError(str(code), str(status.get("comment") or "błąd OBS"), request_type)
            return (msg["d"].get("responseData") or {}) if msg.get("d") else {}
        raise ObsError("request_failed", "wyczerpano retry", request_type)  # pragma: no cover

    def _reconnect_after_failure(self, attempt: int) -> None:
        self.close()
        delay = self.backoff[min(attempt, len(self.backoff) - 1)] if self.backoff else 0.5
        log.warning("OBS: utrata połączenia — ponowne łączenie za %.2f s", delay)
        time.sleep(delay)
        self.connect()

    def close(self) -> None:
        self._connected = False
        ws, self._ws = self._ws, None
        if ws is not None:
            try:
                ws.close()
            except Exception:  # pragma: no cover
                pass

    # ------------------------------------------------------- typowane żądania

    def set_scene(self, scene_name: str) -> dict[str, Any]:
        return self.request("SetCurrentProgramScene", {"sceneName": scene_name})

    def get_scene_list(self) -> dict[str, Any]:
        return self.request("GetSceneList")

    def current_scene_name(self) -> str:
        resp = self.request("GetCurrentProgramScene")
        return str((resp or {}).get("currentProgramSceneName") or "")

    def toggle_mute(self, source: str) -> dict[str, Any]:
        return self.request("ToggleInputMute", {"inputName": source})

    def set_mute(self, source: str, muted: bool) -> dict[str, Any]:
        return self.request("SetInputMute", {"inputName": source, "inputMuted": bool(muted)})

    def start_record(self) -> dict[str, Any]:
        return self.request("StartRecord")

    def stop_record(self) -> dict[str, Any]:
        return self.request("StopRecord")

    def toggle_record(self) -> dict[str, Any]:
        return self.request("ToggleRecord")

    def start_replay_buffer(self) -> dict[str, Any]:
        return self.request("StartReplayBuffer")

    def save_replay_buffer(self) -> dict[str, Any]:
        return self.request("SaveReplayBuffer")

    def stop_replay_buffer(self) -> dict[str, Any]:
        return self.request("StopReplayBuffer")

    def set_source_filter_enabled(
        self, source: str, filter_name: str, enabled: bool
    ) -> dict[str, Any]:
        return self.request(
            "SetSourceFilterEnabled",
            {"sourceName": source, "filterName": filter_name, "filterEnabled": bool(enabled)},
        )

    # -------------------------------------------------- cykliczne przełączanie

    def step_scene(self, direction: int) -> str:
        """Następna/poprzednia scena po liście scen z OBS (+1 / -1, cyklicznie)."""
        scene_list = self.get_scene_list()
        scenes = [str(s.get("sceneName") or "") for s in (scene_list.get("scenes") or [])]
        scenes = [s for s in scenes if s]
        if not scenes:
            raise ObsError("no_scenes", "OBS nie ma żadnych scen")
        current = self.current_scene_name()
        try:
            idx = scenes.index(current)
        except ValueError:
            idx = 0
        target = scenes[(idx + direction) % len(scenes)]
        self.set_scene(target)
        return target


# ------------------------------------------------------------------ akcje


def _obs_client(ctx: ActionContext) -> ObsClient | None:
    obs = getattr(ctx, "obs", None)
    return obs if isinstance(obs, ObsClient) else None


def _latency(t0: float) -> float:
    return (time.monotonic() - t0) * 1000


class ObsSceneAction(Action):
    id = "obs_scene"
    intent = "obs.scene"
    description = "Przełącz scenę OBS (scena z nazwy lub __next__/__prev__)."

    def execute(self, slots: Mapping[str, Any], ctx: ActionContext) -> ActionResult:
        t0 = time.monotonic()
        client = _obs_client(ctx)
        if client is None or not client.connected:
            return ActionResult(False, error="obs_not_connected", message=OBS_REQUIREMENTS)
        scene = str((slots or {}).get("scene") or "").strip()
        if not scene:
            return ActionResult(False, error="missing_slot:scene", message="brak slotu scene")
        try:
            if scene == "__next__":
                target = client.step_scene(+1)
                return ActionResult(
                    True,
                    message=f"scena → {target}",
                    details={"scene": target, "direction": "next"},
                    latency_ms=_latency(t0),
                )
            if scene == "__prev__":
                target = client.step_scene(-1)
                return ActionResult(
                    True,
                    message=f"scena → {target}",
                    details={"scene": target, "direction": "prev"},
                    latency_ms=_latency(t0),
                )
            client.set_scene(scene)
            return ActionResult(True, message=f"scena → {scene}", latency_ms=_latency(t0))
        except ObsError as exc:
            return ActionResult(
                False,
                error=f"obs_error:{exc.code}:{exc.message}",
                message=str(exc),
                latency_ms=_latency(t0),
            )

    def available(self, ctx: ActionContext | None = None) -> bool:
        client = _obs_client(ctx) if ctx is not None else None
        return bool(client and client.connected)

    def availability_reason(self, ctx: ActionContext | None = None) -> str:
        return "" if self.available(ctx) else f"OBS niepołączony ({OBS_REQUIREMENTS})"


class ObsMuteAction(Action):
    id = "obs_mute"
    intent = "obs.mute"
    description = "Wycisz/odcisz źródło OBS (toggle/on/off)."

    def execute(self, slots: Mapping[str, Any], ctx: ActionContext) -> ActionResult:
        t0 = time.monotonic()
        client = _obs_client(ctx)
        if client is None or not client.connected:
            return ActionResult(False, error="obs_not_connected", message=OBS_REQUIREMENTS)
        source = str((slots or {}).get("source") or "mic").strip()
        state = str((slots or {}).get("state") or "toggle").strip().lower()
        try:
            if state == "toggle":
                resp = client.toggle_mute(source)
                return ActionResult(
                    True,
                    message=f"mute {source!r} → {resp.get('inputMuted')}",
                    details={"source": source, "muted": resp.get("inputMuted")},
                    latency_ms=_latency(t0),
                )
            muted = state in ("on", "true", "1")
            client.set_mute(source, muted)
            return ActionResult(
                True,
                message=f"mute {source!r} = {muted}",
                details={"source": source, "muted": muted},
                latency_ms=_latency(t0),
            )
        except ObsError as exc:
            return ActionResult(
                False,
                error=f"obs_error:{exc.code}:{exc.message}",
                message=str(exc),
                latency_ms=_latency(t0),
            )

    def available(self, ctx: ActionContext | None = None) -> bool:
        client = _obs_client(ctx) if ctx is not None else None
        return bool(client and client.connected)

    def availability_reason(self, ctx: ActionContext | None = None) -> str:
        return "" if self.available(ctx) else "OBS niepołączony"


class ObsRecordAction(Action):
    id = "obs_record"
    intent = "obs.record"
    description = "Nagrywanie OBS: start/stop/toggle."

    def execute(self, slots: Mapping[str, Any], ctx: ActionContext) -> ActionResult:
        t0 = time.monotonic()
        client = _obs_client(ctx)
        if client is None or not client.connected:
            return ActionResult(False, error="obs_not_connected", message=OBS_REQUIREMENTS)
        state = str((slots or {}).get("state") or "toggle").strip().lower()
        try:
            if state == "start":
                client.start_record()
            elif state == "stop":
                client.stop_record()
            else:
                client.toggle_record()
            return ActionResult(True, message=f"record → {state}", latency_ms=_latency(t0))
        except ObsError as exc:
            return ActionResult(
                False,
                error=f"obs_error:{exc.code}:{exc.message}",
                message=str(exc),
                latency_ms=_latency(t0),
            )

    def available(self, ctx: ActionContext | None = None) -> bool:
        client = _obs_client(ctx) if ctx is not None else None
        return bool(client and client.connected)

    def availability_reason(self, ctx: ActionContext | None = None) -> str:
        return "" if self.available(ctx) else "OBS niepołączony"


class ObsReplayAction(Action):
    id = "obs_replay"
    intent = "obs.replay"
    description = "Replay buffer OBS: save/start/stop (wymaga włączonego bufora)."

    def execute(self, slots: Mapping[str, Any], ctx: ActionContext) -> ActionResult:
        t0 = time.monotonic()
        client = _obs_client(ctx)
        if client is None or not client.connected:
            return ActionResult(False, error="obs_not_connected", message=OBS_REQUIREMENTS)
        action = str((slots or {}).get("action") or "save").strip().lower()
        try:
            if action == "start":
                client.start_replay_buffer()
            elif action == "stop":
                client.stop_replay_buffer()
            else:
                client.save_replay_buffer()
            return ActionResult(True, message=f"replay → {action}", latency_ms=_latency(t0))
        except ObsError as exc:
            return ActionResult(
                False,
                error=f"obs_error:{exc.code}:{exc.message}",
                message=str(exc),
                latency_ms=_latency(t0),
            )

    def available(self, ctx: ActionContext | None = None) -> bool:
        client = _obs_client(ctx) if ctx is not None else None
        return bool(client and client.connected)

    def availability_reason(self, ctx: ActionContext | None = None) -> str:
        return "" if self.available(ctx) else "OBS niepołączony"


class ObsFilterAction(Action):
    id = "obs_filter"
    intent = "obs.filter"
    description = "Włącz/wyłącz filtr źródła OBS (np. cenzura, §3.4)."

    def execute(self, slots: Mapping[str, Any], ctx: ActionContext) -> ActionResult:
        t0 = time.monotonic()
        client = _obs_client(ctx)
        if client is None or not client.connected:
            return ActionResult(False, error="obs_not_connected", message=OBS_REQUIREMENTS)
        slots = dict(slots or {})
        source = str(slots.get("source") or "").strip()
        filter_name = str(slots.get("filter") or "").strip()
        if not source or not filter_name:
            return ActionResult(
                False,
                error="missing_slot:source/filter",
                message="obs.filter wymaga slotów source i filter",
            )
        state = str(slots.get("state") or "toggle").strip().lower()
        enabled = state in ("on", "true", "1")
        try:
            client.set_source_filter_enabled(source, filter_name, enabled)
            return ActionResult(
                True,
                message=f"filtr {filter_name!r} ({source!r}) = {enabled}",
                latency_ms=_latency(t0),
            )
        except ObsError as exc:
            return ActionResult(
                False,
                error=f"obs_error:{exc.code}:{exc.message}",
                message=str(exc),
                latency_ms=_latency(t0),
            )

    def available(self, ctx: ActionContext | None = None) -> bool:
        client = _obs_client(ctx) if ctx is not None else None
        return bool(client and client.connected)

    def availability_reason(self, ctx: ActionContext | None = None) -> str:
        return "" if self.available(ctx) else "OBS niepołączony"


class ObsSourceToggleAction(Action):
    id = "obs_source_toggle"
    intent = "obs.source_toggle"
    description = "Toggle źródła OBS (MVP: ToggleInputMute dla źródeł audio)."

    def execute(self, slots: Mapping[str, Any], ctx: ActionContext) -> ActionResult:
        t0 = time.monotonic()
        client = _obs_client(ctx)
        if client is None or not client.connected:
            return ActionResult(False, error="obs_not_connected", message=OBS_REQUIREMENTS)
        source = str((slots or {}).get("source") or "").strip()
        if not source:
            return ActionResult(False, error="missing_slot:source", message="brak slotu source")
        try:
            resp = client.toggle_mute(source)
            return ActionResult(
                True,
                message=f"toggle {source!r} → muted={resp.get('inputMuted')}",
                details={"source": source, "muted": resp.get("inputMuted")},
                latency_ms=_latency(t0),
            )
        except ObsError as exc:
            return ActionResult(
                False,
                error=f"obs_error:{exc.code}:{exc.message}",
                message=str(exc),
                latency_ms=_latency(t0),
            )

    def available(self, ctx: ActionContext | None = None) -> bool:
        client = _obs_client(ctx) if ctx is not None else None
        return bool(client and client.connected)

    def availability_reason(self, ctx: ActionContext | None = None) -> str:
        return "" if self.available(ctx) else "OBS niepołączony"
