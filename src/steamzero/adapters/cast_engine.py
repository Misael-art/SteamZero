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
import signal
import socket
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

import gi  # type: ignore[import-not-found]

gi.require_version("Gst", "1.0")
from gi.repository import Gst  # type: ignore[import-not-found]  # noqa: E402

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
    if pipewire_fd is not None:
        source_parts.append(f"fd={pipewire_fd}")
    if pipewire_node is not None:
        source_parts.append(f"path={pipewire_node}")

    bitrate = _nonnegative_int(msg.get("bitrate_kbps"))
    if bitrate is None or bitrate == 0:
        bitrate = DEFAULT_VIDEO_BITRATE_KBPS

    video = (
        f"{' '.join(source_parts)} ! "
        "queue leaky=downstream max-size-buffers=2 ! "
        "videoconvert ! video/x-raw,format=I420,framerate=30/1 ! "
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


@dataclass
class SessionState:
    offer: str | None = None
    answer: str | None = None
    pipeline: Any = None
    running: bool = False
    paused: bool = False
    start_time: float = 0.0
    portal_session: Any = None
    portal_fd: int | None = None
    control_conn: socket.socket | None = None


_INSTANCE: CastEngine | None = None


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

    def _handle_client(self, conn: socket.socket) -> None:
        buf = b""
        try:
            conn.settimeout(POLL_INTERVAL)
            while self._running:
                try:
                    data = conn.recv(4096)
                except TimeoutError:
                    continue
                if not data:
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

        with self._lock:
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
        if self._session.running:
            self._send(
                conn,
                {
                    "version": IPC_VERSION,
                    "type": "START_SESSION_OK",
                    "seq": seq,
                    "detail": "already running",
                },
            )
            return
        try:
            gi.require_version("GstWebRTC", "1.0")

            Gst.init(None)
            pipeline = Gst.parse_launch(build_pipeline_description(msg))
            webrtc = pipeline.get_by_name("webrtc")
            if webrtc is None:
                raise RuntimeError("pipeline did not create webrtcbin")

            def on_offer_created(promise: Any, _webrtc: Any) -> None:
                try:
                    reply = promise.get_reply()
                    offer = reply["offer"]
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

            self._session.control_conn = conn
            pipeline.set_state(Gst.State.PLAYING)
            self._session.pipeline = pipeline
            self._session.running = True
            self._session.start_time = time.monotonic()
            _log.info("session started")
            self._send(conn, {"version": IPC_VERSION, "type": "START_SESSION_OK", "seq": seq})
        except Exception as exc:
            _log.error("start session failed: %s", exc)
            self._send(
                conn,
                {
                    "version": IPC_VERSION,
                    "type": "error",
                    "seq": seq,
                    "detail": str(exc),
                },
            )

    def _send_control_event(self, payload: dict[str, Any]) -> None:
        with self._lock:
            conn = self._session.control_conn
        if conn is not None:
            self._send(conn, payload)

    def _cmd_stop_session(self, conn: socket.socket, seq: int) -> None:
        if not self._session.running and self._session.pipeline is None:
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
        try:
            if self._session.pipeline is not None:
                self._session.pipeline.set_state(Gst.State.NULL)
            self._session = SessionState()
            _log.info("session stopped")
        except Exception as exc:
            _log.error("stop session failed: %s", exc)
        self._send(conn, {"version": IPC_VERSION, "type": "STOP_SESSION_OK", "seq": seq})

    def _cmd_pause_session(self, conn: socket.socket, seq: int) -> None:
        if self._session.pipeline is not None:
            self._session.pipeline.set_state(Gst.State.PAUSED)
            self._session.paused = True
            _log.info("session paused")
        self._send(conn, {"version": IPC_VERSION, "type": "PAUSE_SESSION_OK", "seq": seq})

    def _cmd_resume_session(self, conn: socket.socket, seq: int) -> None:
        if self._session.pipeline is not None:
            self._session.pipeline.set_state(Gst.State.PLAYING)
            self._session.paused = False
            _log.info("session resumed")
        self._send(conn, {"version": IPC_VERSION, "type": "RESUME_SESSION_OK", "seq": seq})

    def _cmd_set_quality(self, conn: socket.socket, msg: dict[str, Any], seq: int) -> None:
        bitrate = msg.get("bitrate_kbps", 2000)
        if self._session.pipeline is not None:
            encoder = self._session.pipeline.get_by_name("encoder")
            if encoder is not None:
                encoder.set_property("bitrate", bitrate)
        self._send(conn, {"version": IPC_VERSION, "type": "SET_QUALITY_OK", "seq": seq})

    def _cmd_request_keyframe(self, conn: socket.socket, seq: int) -> None:
        if self._session.pipeline is not None:
            webrtc = self._session.pipeline.get_by_name("webrtc")
            if webrtc is not None:
                with suppress(Exception):
                    webrtc.emit("request-keyframe")
        self._send(conn, {"version": IPC_VERSION, "type": "REQUEST_KEYFRAME_OK", "seq": seq})

    def _cmd_get_status(self, conn: socket.socket, seq: int) -> None:
        status: dict[str, Any] = {
            "running": self._session.running,
            "paused": self._session.paused,
            "duration_seconds": (
                int(time.monotonic() - self._session.start_time) if self._session.start_time else 0
            ),
        }
        if self._session.pipeline is not None:
            webrtc = self._session.pipeline.get_by_name("webrtc")
            if webrtc is not None and hasattr(webrtc, "get_stats"):
                with suppress(Exception):
                    stats = webrtc.get_stats()
                    status["stats"] = {k: str(v) for k, v in stats.items()}
        self._send(conn, {"version": IPC_VERSION, "type": "GET_STATUS_OK", "seq": seq, **status})

    def _cmd_offer(self, conn: socket.socket, msg: dict[str, Any], seq: int) -> None:
        self._session.offer = msg.get("sdp", "")
        self._send(conn, {"version": IPC_VERSION, "type": "OFFER_OK", "seq": seq})

    def _cmd_answer(self, conn: socket.socket, msg: dict[str, Any], seq: int) -> None:
        self._session.answer = msg.get("sdp", "")
        if self._session.pipeline is not None and msg.get("sdp"):
            try:
                from gi.repository import GstSdp, GstWebRTC

                webrtc = self._session.pipeline.get_by_name("webrtc")
                if webrtc is not None:
                    result, sdp_message = GstSdp.SDPMessage.new_from_text(msg["sdp"])
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
            except Exception as exc:
                _log.error("set remote description failed: %s", exc)
        self._send(conn, {"version": IPC_VERSION, "type": "ANSWER_OK", "seq": seq})

    def _cmd_candidate(self, conn: socket.socket, msg: dict[str, Any], seq: int) -> None:
        if self._session.pipeline is not None and msg.get("candidate"):
            try:
                webrtc = self._session.pipeline.get_by_name("webrtc")
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
        if self._session.pipeline is not None:
            with suppress(Exception):
                self._session.pipeline.set_state(Gst.State.NULL)
        self._running = False


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", required=True)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.getLogger().setLevel(getattr(logging, args.log_level.upper(), logging.INFO))

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
