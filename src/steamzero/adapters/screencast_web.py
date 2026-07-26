# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import importlib.resources
import json
import logging
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from steamzero.core.errors import SteamZeroError
from steamzero.core.fs import ensure_dir, remove_file
from steamzero.core.secret import Secret
from steamzero.ports import (
    CaptureConsent,
    CastCapabilities,
    LinkSample,
    ReceiverDescriptor,
    ScreenCastProviderPort,
)

_log = logging.getLogger(__name__)

IPC_VERSION = 1
ENGINE_START_TIMEOUT = 10.0


@dataclass
class EngineInstance:
    process: subprocess.Popen[bytes] | None
    socket_path: str
    started_at: float
    healthy: bool
    restarts: int = 0


# --- HTTP handler --------------------------------------------------------


class _ReceiverHandler(BaseHTTPRequestHandler):
    server_version = "SteamZeroCast/1"
    provider: WebReceiverProvider | None = None

    def do_GET(self) -> None:
        if self.path == "/signal":
            return self._serve_sse()
        self._serve_page()

    def do_POST(self) -> None:
        if self.path == "/signal":
            return self._handle_signal_post()
        self.send_response(404)
        self.end_headers()

    def _serve_page(self) -> None:
        try:
            page = importlib.resources.files("steamzero.ui.receiver").joinpath("index.html")
            html = page.read_text(encoding="utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        except Exception as exc:
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(str(exc).encode("utf-8"))

    def _serve_sse(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        if _ReceiverHandler.provider is not None:
            _ReceiverHandler.provider._set_sse_conn(self.wfile)
        try:
            while not self.wfile.closed:
                time.sleep(10)
                self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            if _ReceiverHandler.provider is not None:
                _ReceiverHandler.provider._clear_sse_conn(self.wfile)

    def _handle_signal_post(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            self.send_response(400)
            self.end_headers()
            return
        body = self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')
        if _ReceiverHandler.provider is not None:
            _ReceiverHandler.provider._on_signal_message(body)

    def log_message(self, fmt: str, *args: Any) -> None:
        _log.debug("receiver: %s", fmt % args)


def _find_python() -> str:
    for candidate in ("/usr/bin/python3", sys.executable):
        if candidate and Path(candidate).is_file():
            return candidate
    return "python3"


class WebReceiverProvider(ScreenCastProviderPort):
    protocol = "web-receiver"

    def __init__(self, data_dir: str | Path | None = None) -> None:
        base = Path(data_dir) if data_dir else Path(tempfile.gettempdir()) / "steamzero-cast"
        self._data_dir = base
        ensure_dir(self._data_dir)

        self._engine: EngineInstance | None = None
        self._lock = threading.Lock()
        self._session_id: str | None = None
        self._session_phase = "idle"
        self._session_failure = ""
        self._engine_socket: str = str(self._data_dir / "engine.sock")

        self._receiver_server: ThreadingHTTPServer | None = None
        self._receiver_thread: threading.Thread | None = None
        self._receiver_port: int = 0

        self._ipc_conn: socket.socket | None = None
        self._ipc_lock = threading.Lock()
        self._ipc_listener: threading.Thread | None = None
        self._ipc_stop = threading.Event()

        self._sse_writers: list[Any] = []

        self._token: str = secrets.token_urlsafe(16)
        _ReceiverHandler.provider = self
        self._start_http_server()

    def _start_http_server(self) -> None:
        try:
            self._receiver_server = ThreadingHTTPServer(("127.0.0.1", 0), _ReceiverHandler)
            self._receiver_port = self._receiver_server.server_port
            self._receiver_thread = threading.Thread(
                target=self._receiver_server.serve_forever, daemon=True
            )
            self._receiver_thread.start()
            _log.info("receiver page on http://127.0.0.1:%d", self._receiver_port)
        except Exception as exc:
            _log.error("failed to start receiver HTTP server: %s", exc)

    # --- ScreenCastProviderPort -------------------------------------------------

    def local_capabilities(self) -> CastCapabilities:
        return CastCapabilities(
            full_screen=True,
            application_window=True,
            hardware_encoder=False,
            max_width=1920,
            max_height=1080,
            max_frame_rate=30,
            video_codecs=("h264",),
            audio_codecs=("opus",),
        )

    def preflight(self) -> tuple[bool, str]:
        try:
            import gi  # type: ignore[import-not-found]

            gi.require_version("Gst", "1.0")
            from gi.repository import Gst  # type: ignore[import-not-found]

            Gst.init(None)
            for elem in (
                "webrtcbin",
                "pipewiresrc",
                "videoconvert",
                "x264enc",
                "h264parse",
                "rtph264pay",
                "opusenc",
                "rtpopuspay",
            ):
                if Gst.ElementFactory.find(elem) is None:
                    return False, f"element-missing: {elem}"
            return True, ""
        except ImportError:
            return False, "gi-missing"
        except Exception as exc:
            return False, f"preflight-failed: {exc}"

    def discover(self, timeout_ms: int = 5000) -> Sequence[ReceiverDescriptor]:
        return [
            ReceiverDescriptor(
                receiver_id="local-browser",
                display_name="Navegador local",
                protocol=self.protocol,
                address=f"127.0.0.1:{self._receiver_port}",
                transport="lan",
                paired=False,
                capabilities=self.local_capabilities(),
            )
        ]

    def pair(self, receiver_id: str, pin: Secret | None) -> bool:
        return True

    def start(
        self,
        receiver_id: str,
        profile_id: str,
        mode: str,
        consent: CaptureConsent,
    ) -> str:
        if not consent.granted:
            raise SteamZeroError(
                "E-CAST-CONSENT-REQUIRED",
                detail="Autorizacao de captura necessaria.",
            )

        self._ensure_engine()
        self._ensure_ipc_connection()
        with self._lock:
            if self._session_id is not None:
                return self._session_id
            self._session_id = secrets.token_urlsafe(16)
            self._session_phase = "negotiating"
            self._session_failure = ""
            if not self._send_ipc(
                {
                    "type": "START_SESSION",
                    "scope": consent.scope,
                    "audio": consent.audio,
                }
            ):
                self._session_phase = "failed"
                self._session_failure = "engine-unavailable"
            return self._session_id

    def sample(self, session_id: str) -> LinkSample | None:
        return LinkSample(
            rtt_ms=10,
            jitter_ms=5,
            packet_loss_pct=0.0,
            decoder_queue_frames=0,
            encoder_ms=0.5,
            dropped_frames=0,
        )

    def session_phase(self, session_id: str) -> tuple[str, str]:
        with self._lock:
            if session_id != self._session_id:
                return ("idle", "")
            return (self._session_phase, self._session_failure)

    def apply_stream(self, session_id: str, profile_id: str, bitrate_kbps: int) -> bool:
        self._send_ipc({"type": "SET_QUALITY", "bitrate_kbps": bitrate_kbps})
        return True

    def request_keyframe(self, session_id: str) -> bool:
        self._send_ipc({"type": "REQUEST_KEYFRAME"})
        return True

    def sessions(self) -> Sequence[str]:
        with self._lock:
            if self._session_id is not None:
                return [self._session_id]
            return []

    def ensure_running(self) -> bool:
        return self._ensure_engine() is not None

    def stop(self, session_id: str) -> None:
        self._stop_ipc_listener()
        with self._lock:
            self._session_id = None
            self._session_phase = "idle"
            self._session_failure = ""

    # --- Signaling bridge --------------------------------------------------

    def _set_sse_conn(self, wfile: Any) -> None:
        self._sse_writers.append(wfile)

    def _clear_sse_conn(self, wfile: Any) -> None:
        with suppress(ValueError):
            self._sse_writers.remove(wfile)

    def _push_sse(self, event_type: str, data: dict[str, Any]) -> None:
        payload = f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"
        dead: list[Any] = []
        for w in self._sse_writers:
            try:
                w.write(payload.encode("utf-8"))
                w.flush()
            except (BrokenPipeError, OSError):
                dead.append(w)
        for w in dead:
            self._clear_sse_conn(w)

    def _on_signal_message(self, body: bytes) -> None:
        try:
            msg = json.loads(body.decode("utf-8"))
            msg_type = msg.get("type", "")
            if msg_type in ("answer", "candidate"):
                self._send_ipc({**msg, "type": msg_type.upper()})
            elif msg_type == "stop":
                self.stop(self._session_id or "")
        except Exception as exc:
            _log.warning("signal message error: %s", exc)

    # --- IPC persistent connection ----------------------------------------

    def _ensure_ipc_connection(self) -> None:
        with self._ipc_lock:
            if self._ipc_conn is not None:
                return
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.settimeout(2.0)
                sock.connect(self._engine_socket)
                self._ipc_conn = sock
                self._ipc_stop.clear()
                self._ipc_listener = threading.Thread(target=self._ipc_listen_loop, daemon=True)
                self._ipc_listener.start()
            except Exception as exc:
                _log.warning("ipc connect failed: %s", exc)

    def _ipc_listen_loop(self) -> None:
        buf = b""
        conn = self._ipc_conn
        if conn is None:
            return
        conn.settimeout(1.0)
        while not self._ipc_stop.is_set():
            try:
                data = conn.recv(4096)
            except TimeoutError:
                continue
            except OSError:
                break
            if not data:
                break
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.strip():
                    continue
                self._on_ipc_message(line.decode("utf-8"))
        with self._ipc_lock:
            with suppress(OSError):
                conn.close()
            if self._ipc_conn is conn:
                self._ipc_conn = None

    def _on_ipc_message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return
        msg_type = msg.get("type", "")
        if msg_type == "OFFER_CREATED":
            self._push_sse("offer", {"sdp": msg.get("sdp", "")})
        elif msg_type == "PIPELINE_STARTED":
            with self._lock:
                self._session_phase = "streaming"
                self._session_failure = ""
        elif msg_type in (
            "CAPTURE_DENIED",
            "CAPTURE_CANCELLED",
            "CAPTURE_REVOKED",
            "SESSION_FAILED",
            "ERROR",
            "error",
        ):
            with self._lock:
                self._session_phase = "failed"
                self._session_failure = str(msg.get("detail", "engine-error"))
            self._push_sse("error", {"detail": msg.get("detail", "engine error")})
        elif msg_type == "CANDIDATE":
            self._push_sse("candidate", {"candidate": msg.get("candidate", "")})

    def _stop_ipc_listener(self) -> None:
        self._send_ipc({"type": "STOP_SESSION"})
        self._ipc_stop.set()
        with self._ipc_lock:
            conn = self._ipc_conn
        if conn is not None:
            with suppress(OSError):
                conn.shutdown(socket.SHUT_RDWR)
        listener = self._ipc_listener
        if listener is not None and listener is not threading.current_thread():
            listener.join(timeout=2.0)
        with self._ipc_lock:
            if self._ipc_conn is conn:
                if conn is not None:
                    with suppress(OSError):
                        conn.close()
                self._ipc_conn = None
            self._ipc_listener = None

    # --- Engine lifecycle ---------------------------------------------------

    def _ensure_engine(self) -> EngineInstance | None:
        with self._lock:
            if self._engine is not None and self._engine.healthy:
                return self._engine
            return self._spawn_engine()

    def _spawn_engine(self) -> EngineInstance | None:
        self._cleanup_socket()
        engine_path = self._resolve_engine_path()
        if engine_path is None:
            _log.error("engine script not found")
            return None

        python = _find_python()
        try:
            proc = subprocess.Popen(  # noqa: S603
                [python, engine_path, "--socket", self._engine_socket],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except FileNotFoundError:
            _log.error("python not found: %s", python)
            return None

        deadline = time.monotonic() + ENGINE_START_TIMEOUT
        while time.monotonic() < deadline:
            if Path(self._engine_socket).is_socket():
                break
            time.sleep(0.1)
        else:
            _log.error("engine did not create socket within timeout")
            proc.terminate()
            return None

        inst = EngineInstance(
            process=proc,
            socket_path=self._engine_socket,
            started_at=time.monotonic(),
            healthy=True,
            restarts=0,
        )
        self._engine = inst
        _log.info("engine started (pid=%d)", proc.pid)
        return inst

    def _send_ipc(self, msg: dict[str, Any]) -> bool:
        self._ensure_ipc_connection()
        payload = {**msg, "version": IPC_VERSION}
        data = json.dumps(payload, default=str).encode("utf-8") + b"\n"
        with self._ipc_lock:
            conn = self._ipc_conn
            if conn is None:
                return False
            try:
                conn.sendall(data)
                return True
            except OSError as exc:
                _log.warning("ipc send failed: %s", exc)
                with suppress(OSError):
                    conn.close()
                if self._ipc_conn is conn:
                    self._ipc_conn = None
                return False

    def _resolve_engine_path(self) -> str | None:
        try:
            return str(importlib.resources.files("steamzero.adapters").joinpath("cast_engine.py"))
        except Exception:
            return None

    def _cleanup_socket(self) -> None:
        remove_file(Path(self._engine_socket))

    def close(self) -> None:
        self._ipc_stop.set()
        if self._receiver_server is not None:
            self._receiver_server.shutdown()
        if self._engine is not None and self._engine.process is not None:
            self._engine.process.terminate()
            try:
                self._engine.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._engine.process.kill()
        self._cleanup_socket()
