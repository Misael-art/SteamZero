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


@pytest.fixture
def _gi_patch():
    yield


_TMP = Path(tempfile.mkdtemp())


class TestCastEngineUnit:
    def _tmp_sock(self, name: str) -> str:
        return str(_TMP / name)

    def test_main_function_starts_engine(self) -> None:
        ce = _reload_engine()
        sock = self._tmp_sock("main.sock")
        with (
            patch("sys.argv", ["cast_engine.py", "--socket", sock]),
            patch.object(ce.CastEngine, "run") as mock_run,
        ):
            ce.main()
            mock_run.assert_called_once()

    def test_main_sigterm_stops_engine(self) -> None:
        ce = _reload_engine()
        eng = ce.CastEngine(self._tmp_sock("sigterm.sock"))
        ce._INSTANCE = eng
        with patch.object(eng, "_cmd_stop"):
            for sig_name in ("SIGTERM", "SIGINT"):
                sig = getattr(ce.signal, sig_name)
                handler = ce.signal.getsignal(sig)
                handler(sig, None)
            assert ce.signal.getsignal(ce.signal.SIGTERM) is not ce.signal.SIG_DFL

    def test_stop_with_pipeline_sets_state_null(self) -> None:
        ce = _reload_engine()
        eng = ce.CastEngine(self._tmp_sock("stop_pipeline.sock"))
        mock_pipeline = MagicMock()
        eng._session.pipeline = mock_pipeline
        eng._cmd_stop()
        mock_pipeline.set_state.assert_called_once_with(ce.Gst.State.NULL)
        assert eng._running is False

    def test_start_session_error_logs_and_sends_error(self, _gi_patch) -> None:
        ce = _reload_engine()
        eng = ce.CastEngine(self._tmp_sock("start_error.sock"))
        mock_conn = MagicMock()
        mock_msg = {"type": "START_SESSION"}
        with patch.object(ce.Gst, "parse_launch", side_effect=RuntimeError("boom")):
            eng._cmd_start_session(mock_conn, mock_msg, 1)
        mock_conn.sendall.assert_called_once()
        sent = json.loads(mock_conn.sendall.call_args[0][0].decode("utf-8"))
        assert sent.get("type") == "error"
        assert "boom" in sent.get("detail", "")

    def test_client_handle_empty_line_skips(self) -> None:
        ce = _reload_engine()
        eng = ce.CastEngine(self._tmp_sock("skip_line.sock"))
        mock_conn = MagicMock()
        mock_conn.recv.side_effect = [b"\n\n", b"", TimeoutError()]
        with patch.object(eng, "_dispatch") as mock_dispatch:
            eng._handle_client(mock_conn)
            mock_dispatch.assert_not_called()

    def test_client_handle_exception_logged(self) -> None:
        ce = _reload_engine()
        eng = ce.CastEngine(self._tmp_sock("client_exc.sock"))
        mock_conn = MagicMock()
        mock_conn.recv.side_effect = RuntimeError("client crash")
        eng._handle_client(mock_conn)

    def test_session_answer_parse_error_logged(self, _gi_patch) -> None:
        ce = _reload_engine()
        eng = ce.CastEngine(self._tmp_sock("answer_exc.sock"))
        eng._session.pipeline = MagicMock()
        mock_webrtc = MagicMock()
        eng._session.pipeline.get_by_name.return_value = mock_webrtc
        mock_conn = MagicMock()
        mock_msg = {"type": "ANSWER", "sdp": "bad-sdp"}
        with patch(
            "gi.repository.GstWebRTC.WebRTCSessionDescription.new",
            side_effect=RuntimeError("parse failure"),
        ):
            eng._cmd_answer(mock_conn, mock_msg, 1)
        sent = json.loads(mock_conn.sendall.call_args[0][0].decode("utf-8"))
        assert sent.get("type") == "ANSWER_OK"

    def test_session_candidate_error_logged(self, _gi_patch) -> None:
        ce = _reload_engine()
        eng = ce.CastEngine(self._tmp_sock("candidate_exc.sock"))
        eng._session.pipeline = MagicMock()
        mock_webrtc = MagicMock()
        eng._session.pipeline.get_by_name.return_value = mock_webrtc
        mock_conn = MagicMock()
        mock_msg = {
            "type": "CANDIDATE",
            "candidate": {"candidate": "c:1", "sdpMid": "0"},
        }
        mock_webrtc.add_ice_candidate.side_effect = RuntimeError("add failed")
        eng._cmd_candidate(mock_conn, mock_msg, 1)
        sent = json.loads(mock_conn.sendall.call_args[0][0].decode("utf-8"))
        assert sent.get("type") == "CANDIDATE_OK"

    def test_set_quality_without_encoder(self) -> None:
        ce = _reload_engine()
        eng = ce.CastEngine(self._tmp_sock("no_encoder.sock"))
        eng._session.pipeline = MagicMock()
        eng._session.pipeline.get_by_name.return_value = None
        mock_conn = MagicMock()
        eng._cmd_set_quality(mock_conn, {"bitrate_kbps": 3000}, 1)
        sent = json.loads(mock_conn.sendall.call_args[0][0].decode("utf-8"))
        assert sent.get("type") == "SET_QUALITY_OK"

    def test_request_keyframe_without_webrtc(self) -> None:
        ce = _reload_engine()
        eng = ce.CastEngine(self._tmp_sock("no_webrtc.sock"))
        eng._session.pipeline = MagicMock()
        eng._session.pipeline.get_by_name.return_value = None
        mock_conn = MagicMock()
        eng._cmd_request_keyframe(mock_conn, 1)
        sent = json.loads(mock_conn.sendall.call_args[0][0].decode("utf-8"))
        assert sent.get("type") == "REQUEST_KEYFRAME_OK"

    def test_get_status_without_webrtc(self) -> None:
        ce = _reload_engine()
        eng = ce.CastEngine(self._tmp_sock("status_no_webrtc.sock"))
        mock_pipeline = MagicMock()
        mock_pipeline.get_by_name.return_value = None
        eng._session.pipeline = mock_pipeline
        eng._session.running = True
        mock_conn = MagicMock()
        eng._cmd_get_status(mock_conn, 1)
        sent = json.loads(mock_conn.sendall.call_args[0][0].decode("utf-8"))
        assert sent.get("type") == "GET_STATUS_OK"
        assert "stats" not in sent

    def test_get_status_with_stats(self) -> None:
        ce = _reload_engine()
        eng = ce.CastEngine(self._tmp_sock("status_stats.sock"))
        mock_pipeline = MagicMock()
        mock_webrtc = MagicMock()
        mock_webrtc.get_stats.return_value = {"bytes_sent": "1024"}
        mock_pipeline.get_by_name.return_value = mock_webrtc
        eng._session.pipeline = mock_pipeline
        eng._session.running = True
        eng._session.start_time = 100.0
        mock_conn = MagicMock()
        with patch.object(ce.time, "monotonic", return_value=105.0):
            eng._cmd_get_status(mock_conn, 1)
        sent = json.loads(mock_conn.sendall.call_args[0][0].decode("utf-8"))
        assert sent.get("type") == "GET_STATUS_OK"
        assert sent.get("running") is True
        assert sent.get("paused") is False
        assert sent.get("duration_seconds") == 5
        assert sent.get("stats") == {"bytes_sent": "1024"}


_GI_PATCH = patch.dict("sys.modules", _mock_gi_modules(), clear=False)
_GI_PATCH.start()


def _reload_engine():
    """Reload cast_engine module with mocked gi."""
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
    def test_start_session_success(self, engine_env) -> None:
        sock_path, ce = engine_env
        resp = _ipc_call(sock_path, {"version": ce.IPC_VERSION, "type": "START_SESSION"})
        assert resp.get("type") == "START_SESSION_OK"

    def test_start_session_already_running(self, engine_env) -> None:
        sock_path, ce = engine_env
        resp = _ipc_call(sock_path, {"version": ce.IPC_VERSION, "type": "START_SESSION"})
        assert resp.get("type") == "START_SESSION_OK"
        resp = _ipc_call(sock_path, {"version": ce.IPC_VERSION, "type": "START_SESSION"})
        assert resp.get("type") == "START_SESSION_OK"
        assert resp.get("detail") == "already running"

    def test_stop_session_with_pipeline(self, engine_env) -> None:
        sock_path, ce = engine_env
        resp = _ipc_call(sock_path, {"version": ce.IPC_VERSION, "type": "START_SESSION"})
        assert resp.get("type") == "START_SESSION_OK"
        resp = _ipc_call(sock_path, {"version": ce.IPC_VERSION, "type": "STOP_SESSION"})
        assert resp.get("type") == "STOP_SESSION_OK"

    def test_stop_session_already_stopped(self, engine_env) -> None:
        sock_path, ce = engine_env
        resp = _ipc_call(sock_path, {"version": ce.IPC_VERSION, "type": "STOP_SESSION"})
        assert resp.get("type") == "STOP_SESSION_OK"
        assert resp.get("detail") == "already stopped"

    def test_pause_resume_with_pipeline(self, engine_env) -> None:
        sock_path, ce = engine_env
        resp = _ipc_call(sock_path, {"version": ce.IPC_VERSION, "type": "START_SESSION"})
        assert resp.get("type") == "START_SESSION_OK"
        resp = _ipc_call(sock_path, {"version": ce.IPC_VERSION, "type": "PAUSE_SESSION"})
        assert resp.get("type") == "PAUSE_SESSION_OK"
        status = _ipc_call(sock_path, {"version": ce.IPC_VERSION, "type": "GET_STATUS"})
        assert status.get("paused") is True
        resp = _ipc_call(sock_path, {"version": ce.IPC_VERSION, "type": "RESUME_SESSION"})
        assert resp.get("type") == "RESUME_SESSION_OK"

    def test_set_quality_with_pipeline(self, engine_env) -> None:
        sock_path, ce = engine_env
        resp = _ipc_call(sock_path, {"version": ce.IPC_VERSION, "type": "START_SESSION"})
        assert resp.get("type") == "START_SESSION_OK"
        resp = _ipc_call(
            sock_path,
            {"version": ce.IPC_VERSION, "type": "SET_QUALITY", "bitrate_kbps": 5000},
        )
        assert resp.get("type") == "SET_QUALITY_OK"

    def test_request_keyframe_with_pipeline(self, engine_env) -> None:
        sock_path, ce = engine_env
        resp = _ipc_call(sock_path, {"version": ce.IPC_VERSION, "type": "START_SESSION"})
        assert resp.get("type") == "START_SESSION_OK"
        resp = _ipc_call(sock_path, {"version": ce.IPC_VERSION, "type": "REQUEST_KEYFRAME"})
        assert resp.get("type") == "REQUEST_KEYFRAME_OK"

    def test_answer_with_pipeline(self, engine_env) -> None:
        sock_path, ce = engine_env
        resp = _ipc_call(sock_path, {"version": ce.IPC_VERSION, "type": "START_SESSION"})
        assert resp.get("type") == "START_SESSION_OK"
        resp = _ipc_call(
            sock_path,
            {"version": ce.IPC_VERSION, "type": "ANSWER", "sdp": "v=0\no=answer\n"},
        )
        assert resp.get("type") == "ANSWER_OK"

    def test_candidate_with_pipeline(self, engine_env) -> None:
        sock_path, ce = engine_env
        resp = _ipc_call(sock_path, {"version": ce.IPC_VERSION, "type": "START_SESSION"})
        assert resp.get("type") == "START_SESSION_OK"
        resp = _ipc_call(
            sock_path,
            {
                "version": ce.IPC_VERSION,
                "type": "CANDIDATE",
                "candidate": {
                    "candidate": "candidate:1 1 UDP 2122252543 192.168.1.1 5000 typ host",
                    "sdpMid": "0",
                },
            },
        )
        assert resp.get("type") == "CANDIDATE_OK"

    def test_get_status_running(self, engine_env) -> None:
        sock_path, ce = engine_env
        resp = _ipc_call(sock_path, {"version": ce.IPC_VERSION, "type": "START_SESSION"})
        assert resp.get("type") == "START_SESSION_OK"
        status = _ipc_call(sock_path, {"version": ce.IPC_VERSION, "type": "GET_STATUS"})
        assert status.get("running") is True

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

    def test_stop_with_pipeline(self, engine_env) -> None:
        sock_path, ce = engine_env
        resp = _ipc_call(sock_path, {"version": ce.IPC_VERSION, "type": "START_SESSION"})
        assert resp.get("type") == "START_SESSION_OK"
        resp = _ipc_call(sock_path, {"version": ce.IPC_VERSION, "type": "STOP"})
        assert resp == {}

    def test_stop_engine(self, engine_env) -> None:
        sock_path, ce = engine_env
        resp = _ipc_call(sock_path, {"version": ce.IPC_VERSION, "type": "STOP"})
        assert resp == {}
