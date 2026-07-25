from __future__ import annotations

import importlib
import json
import socket
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _mock_gi_modules() -> dict[str, MagicMock]:
    mock_gst = MagicMock()
    mock_gst.State.NULL = 0
    mock_gst.State.PLAYING = 4
    mock_gst.State.PAUSED = 3
    mock_gst.Promise = MagicMock()

    mock_webrtc = MagicMock()
    mock_webrtc.WebRTCSessionDescription = MagicMock()
    mock_webrtc.WebRTCSDPType.ANSWER = 1

    return {
        "gi": MagicMock(),
        "gi.repository": MagicMock(),
        "gi.repository.Gst": mock_gst,
        "gi.repository.GstWebRTC": mock_webrtc,
    }


def _reload_engine():
    """Reload cast_engine module with mocked gi."""
    with patch.dict("sys.modules", _mock_gi_modules(), clear=False):
        import steamzero.adapters.cast_engine as ce

        importlib.reload(ce)
        return ce


@pytest.fixture(scope="session")
def _engine_module():
    return _reload_engine()


@pytest.fixture
def engine_env(_engine_module):
    sock_path = str(Path(tempfile.mkdtemp()) / "engine.sock")
    eng = _engine_module.CastEngine(sock_path)
    t = threading.Thread(target=eng.run, daemon=True)
    t.start()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if Path(sock_path).is_socket():
            break
        time.sleep(0.05)
    yield sock_path, _engine_module
    try:
        import os

        os.unlink(sock_path)
    except FileNotFoundError:
        pass


def _ipc_call(sock_path: str, msg: dict, timeout: float = 2.0) -> dict:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(sock_path)
    payload = json.dumps(msg, default=str).encode("utf-8") + b"\n"
    sock.sendall(payload)
    buf = b""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            chunk = sock.recv(4096)
        except TimeoutError:
            continue
        if not chunk:
            break
        buf += chunk
        if b"\n" in buf:
            break
    sock.close()
    line = buf.split(b"\n", 1)[0]
    return json.loads(line.decode("utf-8")) if line else {}


class TestEngineProtocol:
    def test_unknown_command(self, engine_env) -> None:
        sock_path, ce = engine_env
        resp = _ipc_call(sock_path, {"version": ce.IPC_VERSION, "type": "UNKNOWN"})
        assert resp.get("type") == "error"
        assert "unknown command" in resp.get("detail", "")

    def test_wrong_version(self, engine_env) -> None:
        sock_path, _ce = engine_env
        resp = _ipc_call(sock_path, {"version": 999, "type": "GET_STATUS"})
        assert resp.get("type") == "error"
        assert "unsupported version" in resp.get("detail", "")

    def test_get_status_idle(self, engine_env) -> None:
        sock_path, ce = engine_env
        resp = _ipc_call(sock_path, {"version": ce.IPC_VERSION, "type": "GET_STATUS"})
        assert resp.get("type") == "GET_STATUS_OK"
        assert resp.get("running") is False
        assert resp.get("paused") is False

    def test_set_quality_before_start(self, engine_env) -> None:
        sock_path, ce = engine_env
        resp = _ipc_call(
            sock_path, {"version": ce.IPC_VERSION, "type": "SET_QUALITY", "bitrate_kbps": 5000}
        )
        assert resp.get("type") == "SET_QUALITY_OK"

    def test_pause_resume_idle(self, engine_env) -> None:
        sock_path, ce = engine_env
        resp = _ipc_call(sock_path, {"version": ce.IPC_VERSION, "type": "PAUSE_SESSION"})
        assert resp.get("type") == "PAUSE_SESSION_OK"

        resp = _ipc_call(sock_path, {"version": ce.IPC_VERSION, "type": "RESUME_SESSION"})
        assert resp.get("type") == "RESUME_SESSION_OK"

    def test_offer_and_candidate(self, engine_env) -> None:
        sock_path, ce = engine_env
        resp = _ipc_call(
            sock_path, {"version": ce.IPC_VERSION, "type": "OFFER", "sdp": "v=0\no=test\n"}
        )
        assert resp.get("type") == "OFFER_OK"

        resp = _ipc_call(
            sock_path,
            {
                "version": ce.IPC_VERSION,
                "type": "CANDIDATE",
                "candidate": {"candidate": "candidate:1 ...", "sdpMid": "0"},
            },
        )
        assert resp.get("type") == "CANDIDATE_OK"

    def test_answer_without_session(self, engine_env) -> None:
        sock_path, ce = engine_env
        resp = _ipc_call(
            sock_path, {"version": ce.IPC_VERSION, "type": "ANSWER", "sdp": "v=0\no=answer\n"}
        )
        assert resp.get("type") == "ANSWER_OK"

    def test_request_keyframe_without_session(self, engine_env) -> None:
        sock_path, ce = engine_env
        resp = _ipc_call(sock_path, {"version": ce.IPC_VERSION, "type": "REQUEST_KEYFRAME"})
        assert resp.get("type") == "REQUEST_KEYFRAME_OK"

    def test_invalid_json(self, engine_env) -> None:
        sock_path, _ce = engine_env
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.connect(sock_path)
        sock.sendall(b"not json\n")
        buf = b""
        try:
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                if b"\n" in buf:
                    break
        except TimeoutError:
            pass
        sock.close()
        resp = json.loads(buf.split(b"\n", 1)[0].decode("utf-8"))
        assert resp.get("type") == "error"

    def test_stop_engine(self, engine_env) -> None:
        sock_path, ce = engine_env
        resp = _ipc_call(sock_path, {"version": ce.IPC_VERSION, "type": "STOP"})
        assert resp == {}
