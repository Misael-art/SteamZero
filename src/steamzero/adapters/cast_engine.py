#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Motor de transmissao GStreamer — processo separado, stdlib + gi apenas.

Protocolo IPC: socket Unix, JSON por linha (delimitado por ``\n``).
Campo ``version: 1`` em toda mensagem. Comandos idempotentes.

Uso:
    python3 cast_engine.py --socket /tmp/cast-engine.sock
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import signal
import socket
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, ClassVar

import gi  # type: ignore[import-not-found]

gi.require_version("Gst", "1.0")
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
gi.require_version("GstSdp", "1.0")
gi.require_version("GstWebRTC", "1.0")
from gi.repository import (  # type: ignore[import-not-found]  # noqa: E402
    Gio,
    GLib,
    Gst,
    GstSdp,
    GstWebRTC,
)

FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(level=logging.INFO, format=FORMAT)
_log = logging.getLogger("cast-engine")

IPC_VERSION = 1
POLL_INTERVAL = 0.05
HEARTBEAT_SECONDS = 5
MAX_MESSAGE_BYTES = 65536
DEFAULT_VIDEO_BITRATE_KBPS = 4000


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    return None


def build_pipeline_description(msg: dict[str, Any]) -> str:
    """Build the send-only WebRTC pipeline from validated scalar inputs."""
    source_parts = ["pipewiresrc", "name=capture", "do-timestamp=true"]
    pipewire_fd = _nonnegative_int(msg.get("pipewire_fd"))
    pipewire_node = _nonnegative_int(msg.get("pipewire_node"))
    pipewire_serial = _nonnegative_int(msg.get("pipewire_serial"))
    if pipewire_fd is not None:
        source_parts.append(f"fd={pipewire_fd}")
    if pipewire_serial is not None:
        source_parts.append(f"target-object={pipewire_serial}")
    elif pipewire_node is not None:
        source_parts.append(f"path={pipewire_node}")

    bitrate = _nonnegative_int(msg.get("bitrate_kbps"))
    if bitrate is None or bitrate == 0:
        bitrate = DEFAULT_VIDEO_BITRATE_KBPS

    video = (
        f"{' '.join(source_parts)} ! "
        "queue leaky=downstream max-size-buffers=2 ! "
        "videoconvert ! videorate ! video/x-raw,format=I420,framerate=30/1 ! "
        f"x264enc name=encoder tune=zerolatency speed-preset=superfast bitrate={bitrate} "
        "key-int-max=60 byte-stream=true ! "
        "h264parse ! rtph264pay config-interval=-1 pt=96 ! "
        "application/x-rtp,media=video,encoding-name=H264,payload=96 ! webrtc."
    )

    audio = ""
    audio_node = _nonnegative_int(msg.get("audio_pipewire_node"))
    if msg.get("audio") is True and audio_node is not None:
        audio = (
            f" pipewiresrc name=audio_capture do-timestamp=true path={audio_node} ! "
            "queue leaky=downstream max-size-buffers=8 ! "
            "audioconvert ! audioresample ! "
            "opusenc name=audio_encoder bitrate=96000 ! rtpopuspay pt=97 ! "
            "application/x-rtp,media=audio,encoding-name=OPUS,payload=97 ! webrtc."
        )

    return f"webrtcbin name=webrtc bundle-policy=max-bundle {video}{audio}"


# --- Portal phases (internal, never serialized to IPC) --------------------
PORTAL_PHASE_IDLE = "idle"
PORTAL_PHASE_PENDING = "pending"
PORTAL_PHASE_CAPTURE_READY = "capture_ready"
PORTAL_PHASE_DENIED = "denied"
PORTAL_PHASE_CANCELLED = "cancelled"


class PortalError(Exception):
    """Erro do portal xdg-desktop-portal, com causa estável (RFC 9457)."""

    def __init__(self, cause: str) -> None:
        if cause not in {
            "portal-missing",
            "source-type-unavailable",
            "capture-denied",
            "capture-cancelled",
            "portal-invalid-response",
            "portal-timeout",
            "pipewire-remote-failed",
            "capture-revoked",
            "pipeline-start-failed",
        }:
            cause = "portal-invalid-response"
        self.cause = cause
        super().__init__(cause)


class PortalScreenCastClient:
    """Cliente assíncrono do xdg-desktop-portal ScreenCast.

    Abre uma sessão no portal do compositor Wayland, solicita consentimento
    do usuário e retorna o descritor remoto do PipeWire (fd + node/serial).

    Toda comunicação D-Bus acontece num GLib MainLoop dedicado — nunca
    bloqueia o handler IPC. O cancelamento é seguro via ``threading.Event``.
    """

    PORTAL_BUS_NAME = "org.freedesktop.portal.Desktop"
    PORTAL_OBJ_PATH = "/org/freedesktop/portal/desktop"
    PORTAL_IFACE = "org.freedesktop.portal.ScreenCast"
    REQUEST_IFACE = "org.freedesktop.portal.Request"
    SESSION_IFACE = "org.freedesktop.portal.Session"

    _SCOPE_BITS: ClassVar[dict[str, int]] = {
        "monitor": 1,
        "window": 2,
        "virtual": 4,
    }

    def capture(
        self,
        scope: str,
        audio: bool,
        cancel: threading.Event | None = None,
    ) -> dict[str, Any]:
        """Executa o fluxo do portal num thread dedicado com GLib MainLoop.

        Retorna ``{"fd": int, "node_id": int | None, "serial": int | None}``.
        Levanta ``PortalError`` com causa estável em caso de falha.
        """
        cancel = cancel or threading.Event()
        result: list[dict[str, Any]] = []
        error: list[PortalError] = []
        done = threading.Event()
        self._run_portal_loop(scope, audio, result, error, done, cancel)
        if error:
            raise error[0]
        if not result:
            raise PortalError("portal-invalid-response")
        return result[0]

    # --- Loop GLib dedicado ------------------------------------------------

    def _run_portal_loop(
        self,
        scope: str,
        audio: bool,
        result: list[dict[str, Any]],
        error: list[PortalError],
        done: threading.Event,
        cancel: threading.Event,
    ) -> None:
        loop = GLib.MainLoop.new(None, False)
        GLib.idle_add(lambda: self._do_capture(scope, audio, result, error, done, cancel, loop))
        loop.run()

    def _do_capture(
        self,
        scope: str,
        audio: bool,
        result: list[dict[str, Any]],
        error: list[PortalError],
        done: threading.Event,
        cancel: threading.Event,
        loop: Any,
    ) -> None:
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            self._bus = bus
            portal = Gio.DBusProxy.new_sync(
                bus,
                Gio.DBusProxyFlags.NONE,
                None,
                self.PORTAL_BUS_NAME,
                self.PORTAL_OBJ_PATH,
                self.PORTAL_IFACE,
                None,
            )

            version_prop = portal.get_cached_property("version")
            if version_prop is None:
                raise PortalError("portal-missing")

            avail_sources = self._query_uint32(bus, portal, "AvailableSourceTypes")
            avail_cursors = self._query_uint32(bus, portal, "AvailableCursorModes")

            scope_bit = self._SCOPE_BITS.get(scope, 0)
            if not scope_bit or not (avail_sources & scope_bit):
                raise PortalError("source-type-unavailable")

            cursor_mode = self._pick_cursor_mode(avail_cursors)
            if cursor_mode is None:
                raise PortalError("portal-missing")

            if cancel.is_set():
                raise PortalError("capture-cancelled")

            # --- CreateSession ---
            session_resp = self._call_with_response(
                bus,
                portal,
                "CreateSession",
                GLib.Variant(
                    "(a{sv})", ({"session_handle_token": GLib.Variant("s", secrets.token_hex(16))},)
                ),
                loop,
                cancel,
            )
            session_handle = self._unpack_session_handle(session_resp)
            if not session_handle:
                raise PortalError("portal-invalid-response")

            if cancel.is_set():
                self._close_session(bus, session_handle)
                raise PortalError("capture-cancelled")

            # --- SelectSources ---
            select_opts: dict[str, GLib.Variant] = {
                "types": GLib.Variant("u", scope_bit),
                "cursor_mode": GLib.Variant("u", cursor_mode),
                "multiple": GLib.Variant("b", False),
            }
            if audio:
                select_opts["enable_audio"] = GLib.Variant("b", True)
            self._call_with_response(
                bus,
                portal,
                "SelectSources",
                GLib.Variant("(oa{sv})", (session_handle, select_opts)),
                loop,
                cancel,
            )

            if cancel.is_set():
                self._close_session(bus, session_handle)
                raise PortalError("capture-cancelled")

            # --- Start ---
            start_resp = self._call_with_response(
                bus,
                portal,
                "Start",
                GLib.Variant(
                    "(osa{sv})",
                    (
                        session_handle,
                        "",
                        {"multiple": GLib.Variant("b", False)},
                    ),
                ),
                loop,
                cancel,
            )
            if cancel.is_set():
                self._close_session(bus, session_handle)
                raise PortalError("capture-cancelled")

            stream_results = self._unpack_stream_results(start_resp)
            if not stream_results:
                self._close_session(bus, session_handle)
                raise PortalError("portal-invalid-response")

            # --- OpenPipeWireRemote ---
            try:
                pw_result, fd_list = portal.call_with_unix_fd_list_sync(
                    "OpenPipeWireRemote",
                    GLib.Variant("(oa{sv})", (session_handle, {})),
                    Gio.DBusCallFlags.NONE,
                    -1,
                    None,
                    None,
                )
                unpacked = pw_result.unpack()
                fd_index = int(unpacked[0])
                fd = fd_list.get(fd_index) if fd_list is not None else -1
            except Exception as exc:
                self._close_session(bus, session_handle)
                raise PortalError("pipewire-remote-failed") from exc
            if fd < 0:
                self._close_session(bus, session_handle)
                raise PortalError("pipewire-remote-failed")

            result.append(
                {
                    "fd": fd,
                    "node_id": stream_results.get("node_id"),
                    "serial": stream_results.get("serial"),
                    "session_handle": session_handle,
                }
            )
        except PortalError as exc:
            error.append(exc)
        except Exception:
            _log.exception("portal capture failed")
            error.append(PortalError("portal-invalid-response"))
        finally:
            done.set()
            loop.quit()

    # --- Helpers D-Bus -----------------------------------------------------

    def _query_uint32(self, bus: Any, portal: Any, prop: str = "AvailableSourceTypes") -> int:
        try:
            result = portal.call_sync(
                "org.freedesktop.DBus.Properties.Get",
                GLib.Variant("(ss)", (self.PORTAL_IFACE, prop)),
                Gio.DBusCallFlags.NONE,
                -1,
                None,
            )
            val = result.unpack()[0]
            return int(val) if val is not None else 0
        except Exception:
            return 0

    def _pick_cursor_mode(self, available: int) -> int | None:
        for mode in (4, 2, 1):
            if available & mode:
                return mode
        return None

    def _request_path(self, bus: Any, token: str) -> str:
        sender = bus.get_unique_name().lstrip(":").replace(".", "_")
        return f"/org/freedesktop/portal/desktop/request/{sender}/{token}"

    def _call_with_response(
        self,
        bus: Any,
        proxy: Any,
        method: str,
        variant: Any,
        loop: Any,
        cancel: threading.Event,
    ) -> Any:
        token = secrets.token_hex(16)
        request_path = self._request_path(bus, token)

        options_v = GLib.Variant("a{sv}", {"handle_token": GLib.Variant("s", token)})

        signal_data: list[Any] = []
        sub_ids: list[int] = []
        request_paths = [request_path]

        def _on_response(
            _connection: Any,
            _sender: str,
            _obj_path: str,
            _iface: str,
            _sig_name: str,
            params: Any,
            _user_data: Any,
        ) -> None:
            if params is not None:
                signal_data.append(params)
            loop.quit()

        def _subscribe(path: str) -> None:
            sub_ids.append(
                bus.signal_subscribe(
                    None,
                    self.REQUEST_IFACE,
                    "Response",
                    path,
                    None,
                    Gio.DBusSignalFlags.NONE,
                    _on_response,
                    None,
                )
            )

        _subscribe(request_path)
        merged = self._merge_options(variant, options_v)
        try:
            call_result = proxy.call_sync(method, merged, Gio.DBusCallFlags.NONE, -1, None)
            returned = call_result.unpack()
            actual_path = str(returned[0]) if returned else request_path
            if actual_path and actual_path != request_path:
                request_paths.append(actual_path)
                _subscribe(actual_path)
        except Exception as exc:
            for subscription_id in sub_ids:
                bus.signal_unsubscribe(subscription_id)
            raise PortalError("portal-invalid-response") from exc

        deadline = time.monotonic() + 120.0
        context = loop.get_context()
        while not signal_data and not cancel.is_set() and time.monotonic() < deadline:
            while context.pending():
                context.iteration(False)
            time.sleep(0.01)

        for subscription_id in sub_ids:
            bus.signal_unsubscribe(subscription_id)

        if cancel.is_set():
            for path in request_paths:
                self._close_request(bus, path)
            raise PortalError("capture-cancelled")
        if not signal_data:
            raise PortalError("portal-timeout")

        return self._unpack_response(signal_data[0])

    def _merge_options(self, variant: Any, extra_opts: Any) -> Any:
        type_str = variant.get_type_string()
        if type_str == "(a{sv})":
            merged = self._variant_dict(variant.get_child_value(0))
            merged.update(self._variant_dict(extra_opts))
            return GLib.Variant("(a{sv})", (merged,))
        if type_str in ("(osa{sv})", "(o sa{sv})"):
            obj = variant.get_child_value(0).unpack()
            parent = variant.get_child_value(1).unpack()
            merged = self._variant_dict(variant.get_child_value(2))
            merged.update(self._variant_dict(extra_opts))
            return GLib.Variant("(osa{sv})", (obj, parent, merged))
        return variant

    @staticmethod
    def _variant_dict(value: Any) -> dict[str, Any]:
        """Return an ``a{sv}`` mapping without unboxing its variant values."""
        result: dict[str, Any] = {}
        for index in range(value.n_children()):
            entry = value.get_child_value(index)
            key = str(entry.get_child_value(0).unpack())
            wrapped = entry.get_child_value(1)
            result[key] = wrapped.get_variant()
        return result

    @staticmethod
    def _unpack_response(response: Any) -> tuple[int, dict[str, Any]]:
        raw = response.unpack() if hasattr(response, "unpack") else response
        if not isinstance(raw, (tuple, list)) or len(raw) < 2:
            raise PortalError("portal-invalid-response")
        code = int(raw[0])
        results = raw[1] if isinstance(raw[1], dict) else {}
        if code == 1:
            raise PortalError("capture-denied")
        if code == 2:
            raise PortalError("capture-cancelled")
        if code != 0:
            raise PortalError("portal-invalid-response")
        return code, results

    def _unpack_session_handle(self, response: Any) -> str | None:
        try:
            _, results = self._unpack_response(response)
            return str(results.get("session_handle", ""))
        except Exception:
            return None

    def _unpack_stream_results(self, response: Any) -> dict[str, Any] | None:
        try:
            _, results = self._unpack_response(response)
            streams_raw = results.get("streams", [])
            if not streams_raw:
                return None

            for stream_info in streams_raw:
                if isinstance(stream_info, (list, tuple)) and len(stream_info) >= 2:
                    node_id = int(stream_info[0])
                    props = stream_info[1] if isinstance(stream_info[1], dict) else {}
                elif isinstance(stream_info, dict):
                    node_id = int(stream_info.get("node_id", 0))
                    props = stream_info.get("properties", {})
                else:
                    node_id = 0
                    props = {}

                serial = None
                pw_serial_raw = props.get("pipewire-serial", props.get("pipewire.serial"))
                if pw_serial_raw is not None:
                    serial = int(pw_serial_raw)
                if node_id > 0 or serial is not None:
                    return {"node_id": node_id or None, "serial": serial}

            return None
        except PortalError:
            raise
        except Exception:
            return None

    def _close_session(self, bus: Any, session_handle: str) -> None:
        try:
            session_proxy = Gio.DBusProxy.new_sync(
                bus,
                Gio.DBusProxyFlags.NONE,
                None,
                self.PORTAL_BUS_NAME,
                session_handle,
                self.SESSION_IFACE,
                None,
            )
            session_proxy.call_sync(
                "Close",
                GLib.Variant("()", ()),
                Gio.DBusCallFlags.NONE,
                -1,
                None,
            )
        except Exception as exc:
            _log.debug("close session ignored: %s", exc)

    def _close_request(self, bus: Any, request_handle: str) -> None:
        try:
            request = Gio.DBusProxy.new_sync(
                bus,
                Gio.DBusProxyFlags.NONE,
                None,
                self.PORTAL_BUS_NAME,
                request_handle,
                self.REQUEST_IFACE,
                None,
            )
            request.call_sync("Close", GLib.Variant("()", ()), Gio.DBusCallFlags.NONE, -1, None)
        except Exception as exc:
            _log.debug("close request ignored: %s", exc)

    def close(self, session_handle: str | None) -> None:
        bus = getattr(self, "_bus", None)
        if bus is not None and session_handle:
            self._close_session(bus, session_handle)

    def watch_closed(self, session_handle: str, callback: Any) -> int | None:
        bus = getattr(self, "_bus", None)
        if bus is None:
            return None

        def _on_closed(*_args: Any) -> None:
            callback()

        return int(
            bus.signal_subscribe(
                self.PORTAL_BUS_NAME,
                self.SESSION_IFACE,
                "Closed",
                session_handle,
                None,
                Gio.DBusSignalFlags.NONE,
                _on_closed,
                None,
            )
        )

    def unwatch_closed(self, subscription_id: int | None) -> None:
        bus = getattr(self, "_bus", None)
        if bus is not None and subscription_id is not None:
            with suppress(Exception):
                bus.signal_unsubscribe(subscription_id)


@dataclass
class SessionState:
    offer: str | None = None
    answer: str | None = None
    pipeline: Any = None
    running: bool = False
    paused: bool = False
    start_time: float = 0.0
    portal_session: Any = None
    portal_client: Any = None
    portal_closed_subscription: int | None = None
    portal_fd: int | None = None
    portal_serial: int | None = None
    portal_node_id: int | None = None
    portal_phase: str = PORTAL_PHASE_IDLE
    portal_cancel: threading.Event | None = None
    portal_thread: threading.Thread | None = None
    generation: int = 0
    control_conn: socket.socket | None = None


_INSTANCE: CastEngine | None = None
_portal_client_factory: Any = None  # test injection point


class CastEngine:
    def __init__(self, socket_path: str) -> None:
        self._socket_path = socket_path
        self._running = False
        self._session = SessionState()
        self._lock = threading.RLock()
        self._server: socket.socket | None = None
        self._main_bus_watch: Any = None
        self._loop: Any = None

    def run(self) -> None:
        self._running = True
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(self._socket_path)
            server.listen(5)
            self._server = server
            _log.info("engine ready on %s", self._socket_path)
            server.settimeout(POLL_INTERVAL)
            while self._running:
                try:
                    conn, _addr = server.accept()
                except TimeoutError:
                    continue
                except OSError:
                    break
                t = threading.Thread(target=self._handle_client, args=(conn,), daemon=True)
                t.start()
        finally:
            server.close()
            self._server = None

    def _handle_client(self, conn: socket.socket) -> None:
        buf = b""
        try:
            conn.settimeout(POLL_INTERVAL)
            while self._running:
                try:
                    data = conn.recv(4096)
                except TimeoutError:
                    # Não é falha: as sondagens periódicas mantêm o loop vivo
                    # enquanto não há mensagem. Estado distinto de EOF/processo
                    # morto para o diagnóstico.
                    continue
                if not data:
                    # EOF limpo: o cliente fechou a conexão normalmente.
                    _log.info("client eof (fechamento limpo)")
                    break
                buf += data
                if len(buf) > MAX_MESSAGE_BYTES:
                    self._send(
                        conn,
                        {
                            "version": IPC_VERSION,
                            "type": "error",
                            "detail": "message too large",
                        },
                    )
                    break
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    self._dispatch(conn, line.decode("utf-8"))
        except OSError as exc:
            # Processo/cliente morto (reset) ou socket quebrado — distinto do
            # EOF limpo acima.
            _log.info("client peer gone: %s", exc)
        except Exception as exc:
            _log.error("client error: %s", exc)
        finally:
            with self._lock:
                if self._session.control_conn is conn:
                    self._session.control_conn = None
            conn.close()

    def _dispatch(self, conn: socket.socket, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError as exc:
            self._send(conn, {"version": IPC_VERSION, "type": "error", "detail": str(exc)})
            return
        cmd = msg.get("type", "")
        seq = msg.get("seq", 0)
        version = msg.get("version", 1)
        _log.debug("recv %s seq=%s", cmd, seq)

        if version != IPC_VERSION:
            self._send(
                conn,
                {
                    "version": IPC_VERSION,
                    "type": "error",
                    "seq": seq,
                    "detail": f"unsupported version {version}",
                },
            )
            return

        if cmd == "START_SESSION":
            self._cmd_start_session(conn, msg, seq)
        elif cmd == "STOP_SESSION":
            self._cmd_stop_session(conn, seq)
        elif cmd == "PAUSE_SESSION":
            self._cmd_pause_session(conn, seq)
        elif cmd == "RESUME_SESSION":
            self._cmd_resume_session(conn, seq)
        elif cmd == "SET_QUALITY":
            self._cmd_set_quality(conn, msg, seq)
        elif cmd == "REQUEST_KEYFRAME":
            self._cmd_request_keyframe(conn, seq)
        elif cmd == "GET_STATUS":
            self._cmd_get_status(conn, seq)
        elif cmd == "OFFER":
            self._cmd_offer(conn, msg, seq)
        elif cmd == "ANSWER":
            self._cmd_answer(conn, msg, seq)
        elif cmd == "CANDIDATE":
            self._cmd_candidate(conn, msg, seq)
        elif cmd == "STOP":
            self._cmd_stop()
        else:
            self._send(
                conn,
                {
                    "version": IPC_VERSION,
                    "type": "error",
                    "seq": seq,
                    "detail": f"unknown command: {cmd}",
                },
            )

    def _send(self, conn: socket.socket, payload: dict[str, Any]) -> None:
        with suppress(OSError):
            data = json.dumps(payload, default=str).encode("utf-8") + b"\n"
            conn.sendall(data)

    def _cmd_start_session(self, conn: socket.socket, msg: dict[str, Any], seq: int) -> None:
        scope = msg.get("scope", "monitor")
        audio = msg.get("audio", False)
        if scope not in ("monitor", "window", "virtual"):
            self._send(
                conn,
                {
                    "version": IPC_VERSION,
                    "type": "error",
                    "seq": seq,
                    "detail": f"invalid scope: {scope}",
                },
            )
            return
        # G32: o check-e-cria é ATÔMICO sob o lock. Sessões chegam de conexões
        # diferentes em threads distintas; sem serialização uma conexão nova
        # lê a referência antiga e inicia uma segunda sessão em vez de
        # reconhecer "already running", e o estado publicado perde o commit.
        with self._lock:
            # "Sessão ativa" = qualquer fase depois de STARTED, não só
            # PENDING/running: entre a fase CAPTURE_READY e o commit de
            # running=True há construção do pipeline numa thread assíncrona.
            # Se o cheque testasse só `running or PENDING`, uma conexão nova
            # nessa janela criava uma segunda sessão em vez de responder
            # "already running".
            if self._session.running or self._session.portal_phase != PORTAL_PHASE_IDLE:
                self._send(
                    conn,
                    {
                        "version": IPC_VERSION,
                        "type": "START_SESSION_OK",
                        "seq": seq,
                        "detail": "already running",
                        "running": True,
                        "ready": False,
                    },
                )
                return
            cancel = threading.Event()
            generation = self._session.generation + 1
            self._session = SessionState(
                control_conn=conn,
                portal_phase=PORTAL_PHASE_PENDING,
                portal_cancel=cancel,
                generation=generation,
            )
        # Estado commitado antes de o cliente prosseguir.
        self._send(
            conn,
            {
                "version": IPC_VERSION,
                "type": "START_SESSION_OK",
                "seq": seq,
                "running": False,
                "portal_phase": PORTAL_PHASE_PENDING,
            },
        )
        try:
            self._start_portal_async(scope, audio, conn, generation, cancel)
            _log.info("portal session pending (scope=%s, audio=%s)", scope, audio)
        except Exception as exc:
            _log.error("start portal failed: %s", exc)
            self._send(
                conn,
                {
                    "version": IPC_VERSION,
                    "type": "error",
                    "seq": seq,
                    "detail": str(exc),
                },
            )

    def _start_portal_async(
        self,
        scope: str,
        audio: bool,
        conn: socket.socket,
        generation: int,
        cancel: threading.Event,
    ) -> None:
        global _portal_client_factory
        portal_cls = (
            _portal_client_factory if _portal_client_factory is not None else PortalScreenCastClient
        )
        portal = portal_cls() if callable(portal_cls) else portal_cls

        def _portal_worker() -> None:
            try:
                caps = portal.capture(scope=scope, audio=audio, cancel=cancel)
                self._on_portal_ready(
                    caps["fd"],
                    caps.get("serial"),
                    caps.get("node_id"),
                    caps.get("session_handle"),
                    portal,
                    conn,
                    generation,
                )
            except PortalError as exc:
                _log.warning("portal failed: %s", exc.cause)
                with self._lock:
                    if self._session.generation != generation:
                        return
                    self._session.portal_phase = PORTAL_PHASE_IDLE
                event_type = {
                    "capture-denied": "CAPTURE_DENIED",
                    "capture-cancelled": "CAPTURE_CANCELLED",
                    "capture-revoked": "CAPTURE_REVOKED",
                }.get(exc.cause, "SESSION_FAILED")
                self._send_control_event(
                    {
                        "version": IPC_VERSION,
                        "type": event_type,
                        "detail": exc.cause,
                    }
                )
            except Exception:
                _log.exception("portal worker failed")
                self._send_control_event(
                    {
                        "version": IPC_VERSION,
                        "type": "SESSION_FAILED",
                        "detail": "portal-invalid-response",
                    }
                )

        t = threading.Thread(target=_portal_worker, daemon=True)
        with self._lock:
            if self._session.generation == generation:
                self._session.portal_thread = t
        t.start()

    def _on_portal_ready(
        self,
        fd: int,
        serial: int | None,
        node_id: int | None,
        session_handle: str | None,
        portal: Any,
        conn: socket.socket,
        generation: int,
    ) -> None:
        with self._lock:
            if self._session.generation != generation:
                with suppress(OSError):
                    os.close(fd)
                if hasattr(portal, "close"):
                    portal.close(session_handle)
                return
            self._session.portal_fd = fd
            self._session.portal_serial = serial
            self._session.portal_node_id = node_id
            self._session.portal_session = session_handle
            self._session.portal_client = portal
            self._session.portal_phase = PORTAL_PHASE_CAPTURE_READY
            if session_handle and hasattr(portal, "watch_closed"):
                self._session.portal_closed_subscription = portal.watch_closed(
                    session_handle,
                    lambda: self._on_portal_closed(generation),
                )
        _log.info("portal capture ready")
        self._send_control_event({"version": IPC_VERSION, "type": "CAPTURE_READY"})
        try:
            self._build_and_start_pipeline(conn, fd, serial, node_id)
        except Exception:
            _log.exception("pipeline build failed")
            self._send_control_event(
                {
                    "version": IPC_VERSION,
                    "type": "SESSION_FAILED",
                    "detail": "pipeline-start-failed",
                }
            )
            self._teardown_session(generation)

    def _on_portal_closed(self, generation: int) -> None:
        with self._lock:
            if self._session.generation != generation:
                return
        self._send_control_event(
            {
                "version": IPC_VERSION,
                "type": "CAPTURE_REVOKED",
                "detail": "capture-revoked",
            }
        )
        self._teardown_session(generation)

    def _build_and_start_pipeline(
        self,
        conn: socket.socket,
        fd: int,
        serial: int | None,
        node_id: int | None,
    ) -> None:
        pipeline_msg: dict[str, Any] = {
            "pipewire_fd": fd,
            "pipewire_serial": serial,
        }
        if node_id is not None:
            pipeline_msg["pipewire_node"] = node_id
        _log.info(
            "building pipeline (pipewire node=%s, serial=%s)",
            node_id,
            serial,
        )
        pipeline = Gst.parse_launch(build_pipeline_description(pipeline_msg))
        _log.info("pipeline parsed")
        webrtc = pipeline.get_by_name("webrtc")
        if webrtc is None:
            raise RuntimeError("pipeline did not create webrtcbin")

        def on_offer_created(promise: Any, _webrtc: Any) -> None:
            try:
                reply = promise.get_reply()
                offer = reply.get_value("offer")
                if offer is None:
                    raise RuntimeError("offer missing from WebRTC promise")
                offer_sdp = offer.sdp.as_text()
                local_promise = Gst.Promise.new()
                webrtc.emit("set-local-description", offer, local_promise)
                local_promise.interrupt()
                with self._lock:
                    self._session.offer = offer_sdp
                _log.info("offer created")
                self._send_control_event(
                    {
                        "version": IPC_VERSION,
                        "type": "OFFER_CREATED",
                        "sdp": offer_sdp,
                    }
                )
            except Exception as exc:
                _log.error("offer creation failed: %s", exc)
                self._send_control_event(
                    {
                        "version": IPC_VERSION,
                        "type": "SESSION_FAILED",
                        "detail": "offer-creation-failed",
                    }
                )

        def on_negotiation_needed(element: Any) -> None:
            promise = Gst.Promise.new_with_change_func(on_offer_created, element)
            element.emit("create-offer", None, promise)

        webrtc.connect("on-negotiation-needed", on_negotiation_needed)

        def on_ice_candidate(_webrtc: Any, sdp_mline_index: int, candidate: str) -> None:
            self._send_control_event(
                {
                    "version": IPC_VERSION,
                    "type": "CANDIDATE",
                    "candidate": {
                        "candidate": candidate,
                        "sdpMLineIndex": sdp_mline_index,
                    },
                }
            )

        webrtc.connect("on-ice-candidate", on_ice_candidate)

        _log.info("starting pipeline")
        state_result = pipeline.set_state(Gst.State.PLAYING)
        if state_result == Gst.StateChangeReturn.FAILURE:
            pipeline.set_state(Gst.State.NULL)
            raise RuntimeError("pipeline rejected PLAYING state")
        with self._lock:
            self._session.pipeline = pipeline
            self._session.running = True
            self._session.start_time = time.monotonic()
        _log.info("pipeline started")

    def _send_control_event(self, payload: dict[str, Any]) -> None:
        with self._lock:
            conn = self._session.control_conn
        if conn is not None:
            self._send(conn, payload)

    def _cmd_stop_session(self, conn: socket.socket, seq: int) -> None:
        with self._lock:
            is_idle = (
                not self._session.running
                and self._session.pipeline is None
                and self._session.portal_phase != PORTAL_PHASE_PENDING
            )
        if is_idle:
            self._send(
                conn,
                {
                    "version": IPC_VERSION,
                    "type": "STOP_SESSION_OK",
                    "seq": seq,
                    "detail": "already stopped",
                },
            )
            return
        generation = self._session.generation
        self._teardown_session(generation)
        _log.info("session stopped")
        self._send(conn, {"version": IPC_VERSION, "type": "STOP_SESSION_OK", "seq": seq})

    def _teardown_session(self, generation: int | None = None) -> None:
        with self._lock:
            state = self._session
            if generation is not None and state.generation != generation:
                return
            if state.portal_cancel is not None:
                state.portal_cancel.set()
            self._session = SessionState(
                generation=state.generation + 1,
                control_conn=state.control_conn,
            )

        if state.pipeline is not None:
            with suppress(Exception):
                state.pipeline.set_state(Gst.State.NULL)
        portal = state.portal_client
        if portal is not None and hasattr(portal, "unwatch_closed"):
            portal.unwatch_closed(state.portal_closed_subscription)
        if state.portal_fd is not None:
            with suppress(OSError):
                os.close(state.portal_fd)
        if portal is not None and hasattr(portal, "close"):
            portal.close(state.portal_session)

    def _cmd_pause_session(self, conn: socket.socket, seq: int) -> None:
        # G32: o estado de pausa é commitado SOB o lock e independente do
        # pipeline (o portal é assíncrono). Sem isso, PAUSE respondia OK mas
        # `paused` continuava False quando o pipeline ainda não existia, e um
        # GET_STATUS imediato via um estado que o OK já declarava no passado.
        with self._lock:
            pipeline = self._session.pipeline
            if pipeline is not None:
                pipeline.set_state(Gst.State.PAUSED)
            self._session.paused = True
            _log.info("session paused")
        self._send(
            conn,
            {"version": IPC_VERSION, "type": "PAUSE_SESSION_OK", "seq": seq, "paused": True},
        )

    def _cmd_resume_session(self, conn: socket.socket, seq: int) -> None:
        with self._lock:
            pipeline = self._session.pipeline
            if pipeline is not None:
                pipeline.set_state(Gst.State.PLAYING)
            self._session.paused = False
            _log.info("session resumed")
        self._send(
            conn,
            {"version": IPC_VERSION, "type": "RESUME_SESSION_OK", "seq": seq, "paused": False},
        )

    def _cmd_set_quality(self, conn: socket.socket, msg: dict[str, Any], seq: int) -> None:
        bitrate = msg.get("bitrate_kbps", 2000)
        with self._lock:
            pipeline = self._session.pipeline
            if pipeline is not None:
                encoder = pipeline.get_by_name("encoder")
                if encoder is not None:
                    encoder.set_property("bitrate", bitrate)
        self._send(conn, {"version": IPC_VERSION, "type": "SET_QUALITY_OK", "seq": seq})

    def _cmd_request_keyframe(self, conn: socket.socket, seq: int) -> None:
        with self._lock:
            pipeline = self._session.pipeline
            if pipeline is not None:
                webrtc = pipeline.get_by_name("webrtc")
                if webrtc is not None:
                    with suppress(Exception):
                        webrtc.emit("request-keyframe")
        self._send(conn, {"version": IPC_VERSION, "type": "REQUEST_KEYFRAME_OK", "seq": seq})

    def _cmd_get_status(self, conn: socket.socket, seq: int) -> None:
        with self._lock:
            running = self._session.running
            paused = self._session.paused
            portal_phase = self._session.portal_phase
            pipeline = self._session.pipeline
            start_time = self._session.start_time
        status: dict[str, Any] = {
            "running": running,
            "paused": paused,
            "ready": bool(running),
            "capture_state": (
                "streaming"
                if running
                else "requesting"
                if portal_phase == PORTAL_PHASE_PENDING
                else "ready"
                if portal_phase == PORTAL_PHASE_CAPTURE_READY
                else "idle"
            ),
            "duration_seconds": (int(time.monotonic() - start_time) if start_time else 0),
        }
        if pipeline is not None:
            webrtc = pipeline.get_by_name("webrtc")
            if webrtc is not None and hasattr(webrtc, "get_stats"):
                with suppress(Exception):
                    stats = webrtc.get_stats()
                    status["stats"] = {k: str(v) for k, v in stats.items()}
        self._send(conn, {"version": IPC_VERSION, "type": "GET_STATUS_OK", "seq": seq, **status})

    def _cmd_offer(self, conn: socket.socket, msg: dict[str, Any], seq: int) -> None:
        with self._lock:
            self._session.offer = msg.get("sdp", "")
        self._send(conn, {"version": IPC_VERSION, "type": "OFFER_OK", "seq": seq})

    def _cmd_answer(self, conn: socket.socket, msg: dict[str, Any], seq: int) -> None:
        sdp = msg.get("sdp", "")
        with self._lock:
            self._session.answer = sdp
        if self._session.pipeline is not None and sdp:
            try:
                webrtc = self._session.pipeline.get_by_name("webrtc")
                if webrtc is not None:
                    result, sdp_message = GstSdp.SDPMessage.new_from_text(sdp)
                    if result != GstSdp.SDPResult.OK:
                        raise RuntimeError("invalid answer SDP")
                    answer = GstWebRTC.WebRTCSessionDescription.new(
                        GstWebRTC.WebRTCSDPType.ANSWER,
                        sdp_message,
                    )
                    promise = Gst.Promise.new()
                    webrtc.emit("set-remote-description", answer, promise)
                    promise.wait()
                    _log.info("remote description set from answer")
                    self._send_control_event({"version": IPC_VERSION, "type": "PIPELINE_STARTED"})
            except Exception as exc:
                _log.error("set remote description failed: %s", exc)
        self._send(conn, {"version": IPC_VERSION, "type": "ANSWER_OK", "seq": seq})

    def _cmd_candidate(self, conn: socket.socket, msg: dict[str, Any], seq: int) -> None:
        if msg.get("candidate"):
            try:
                with self._lock:
                    pipeline = self._session.pipeline
                if pipeline is not None:
                    webrtc = pipeline.get_by_name("webrtc")
                    if webrtc is not None:
                        candidate = msg["candidate"]
                        if isinstance(candidate, dict):
                            value = str(candidate.get("candidate", ""))
                            mline_index = _nonnegative_int(candidate.get("sdpMLineIndex"))
                            webrtc.emit(
                                "add-ice-candidate",
                                mline_index if mline_index is not None else 0,
                                value,
                            )
                        else:
                            webrtc.emit("add-ice-candidate", 0, str(candidate))
            except Exception as exc:
                _log.error("add ice candidate failed: %s", exc)
        self._send(conn, {"version": IPC_VERSION, "type": "CANDIDATE_OK", "seq": seq})

    def _cmd_stop(self) -> None:
        _log.info("engine stop requested")
        self._teardown_session()
        self._running = False


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", required=True)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.getLogger().setLevel(getattr(logging, args.log_level.upper(), logging.INFO))
    Gst.init(None)

    engine = CastEngine(args.socket)
    global _INSTANCE
    _INSTANCE = engine

    def sigterm(_signo: int, _frame: object) -> None:
        _log.info("SIGTERM received")
        engine._cmd_stop()

    signal.signal(signal.SIGTERM, sigterm)
    signal.signal(signal.SIGINT, sigterm)

    engine.run()


if __name__ == "__main__":
    main()
