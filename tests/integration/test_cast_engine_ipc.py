from __future__ import annotations

import importlib
import json
import os
import socket
import tempfile
import threading
import time
from contextlib import suppress
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from steamzero.adapters.screencast_web import WebReceiverProvider


class _MockPortalOK:
    """Mock portal that returns success immediately."""

    def capture(
        self, scope: str = "monitor", audio: bool = False, cancel: threading.Event | None = None
    ) -> dict:
        read_fd, write_fd = os.pipe()
        os.close(write_fd)
        return {"fd": read_fd, "node_id": 42, "serial": None}


def _mock_gi_modules() -> dict[str, MagicMock]:
    mock_gst = MagicMock()
    mock_gst.State.NULL = 0
    mock_gst.State.PLAYING = 4
    mock_gst.State.PAUSED = 3
    mock_gst.Promise = MagicMock()

    mock_webrtc = MagicMock()
    mock_webrtc.WebRTCSessionDescription = MagicMock()
    mock_webrtc.WebRTCSDPType.ANSWER = 1

    mock_glib = MagicMock()
    mock_glib.MainLoop = MagicMock()
    mock_glib.MainLoop.new = MagicMock(return_value=MagicMock())
    mock_glib.MainLoop.new.return_value.run = MagicMock()
    mock_glib.MainLoop.new.return_value.quit = MagicMock()
    mock_glib.idle_add = MagicMock(side_effect=lambda fn: fn())
    mock_glib.Variant = MagicMock()

    mock_gio = MagicMock()
    mock_gio.BusType = MagicMock()
    mock_gio.BusType.SESSION = 1
    mock_gio.DBusProxyFlags = MagicMock()
    mock_gio.DBusProxyFlags.NONE = 0
    mock_gio.DBusCallFlags = MagicMock()
    mock_gio.DBusCallFlags.NONE = 0
    mock_gio.bus_get_sync = MagicMock()
    mock_gio.DBusProxy = MagicMock()
    mock_gio.DBusProxy.new_sync = MagicMock(return_value=MagicMock())
    mock_gio.UnixFDList = MagicMock()

    mock_repo = MagicMock()
    mock_repo.Gst = mock_gst
    mock_repo.GstWebRTC = mock_webrtc
    mock_repo.GLib = mock_glib
    mock_repo.Gio = mock_gio

    return {
        "gi": MagicMock(),
        "gi.repository": mock_repo,
        "gi.repository.Gst": mock_gst,
        "gi.repository.GstWebRTC": mock_webrtc,
        "gi.repository.GLib": mock_glib,
        "gi.repository.Gio": mock_gio,
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

    def test_start_session_invalid_scope_returns_error(self, _gi_patch) -> None:
        ce = _reload_engine()
        eng = ce.CastEngine(self._tmp_sock("start_error.sock"))
        mock_conn = MagicMock()
        mock_msg = {"type": "START_SESSION", "scope": "invalid"}
        eng._cmd_start_session(mock_conn, mock_msg, 1)
        mock_conn.sendall.assert_called_once()
        sent = json.loads(mock_conn.sendall.call_args[0][0].decode("utf-8"))
        assert sent.get("type") == "error"

    def test_negotiation_uses_installed_pygobject_promise_signature(self) -> None:
        ce = _reload_engine()
        eng = ce.CastEngine(self._tmp_sock("negotiation-signature.sock"))
        pipeline = MagicMock()
        webrtc = MagicMock()
        pipeline.get_by_name.return_value = webrtc
        conn = MagicMock()

        with patch.object(ce.Gst, "parse_launch", return_value=pipeline):
            eng._build_and_start_pipeline(conn, fd=3, serial=None, node_id=42)

        negotiation_callback = next(
            call.args[1]
            for call in webrtc.connect.call_args_list
            if call.args[0] == "on-negotiation-needed"
        )
        negotiation_callback(webrtc)

        promise_call = ce.Gst.Promise.new_with_change_func.call_args
        assert len(promise_call.args) == 2
        webrtc.emit.assert_called_with(
            "create-offer",
            None,
            ce.Gst.Promise.new_with_change_func.return_value,
        )

    def test_pipeline_is_send_only_capture_encode_and_rtp(self) -> None:
        ce = _reload_engine()
        description = ce.build_pipeline_description(
            {"pipewire_fd": 12, "pipewire_node": 42, "bitrate_kbps": 3500}
        )

        for element in (
            "pipewiresrc",
            "videoconvert",
            "x264enc name=encoder",
            "h264parse",
            "rtph264pay",
            "webrtcbin name=webrtc",
        ):
            assert element in description
        for receiver_element in ("rtph264depay", "avdec_h264", "autovideosink"):
            assert receiver_element not in description
        assert "fd=12" in description
        assert "path=42" in description
        assert "bitrate=3500" in description

    def test_pipeline_prefers_pipewire_serial_over_legacy_node(self) -> None:
        ce = _reload_engine()
        description = ce.build_pipeline_description(
            {"pipewire_fd": 12, "pipewire_node": 42, "pipewire_serial": 9001}
        )

        assert "target-object=9001" in description
        assert "path=42" not in description

    def test_portal_response_codes_and_stream_shapes(self) -> None:
        ce = _reload_engine()
        client = ce.PortalScreenCastClient()

        assert client._unpack_response((0, {"ok": True})) == (0, {"ok": True})
        with pytest.raises(ce.PortalError, match="capture-denied"):
            client._unpack_response((1, {}))
        with pytest.raises(ce.PortalError, match="capture-cancelled"):
            client._unpack_response((2, {}))

        assert client._unpack_stream_results(
            (0, {"streams": [(42, {"pipewire-serial": 9001})]})
        ) == {"node_id": 42, "serial": 9001}
        assert client._unpack_stream_results((0, {"streams": [(42, {})]})) == {
            "node_id": 42,
            "serial": None,
        }

    def test_portal_scope_and_cursor_selection_never_degrade(self) -> None:
        ce = _reload_engine()
        client = ce.PortalScreenCastClient()

        assert client._SCOPE_BITS == {"monitor": 1, "window": 2, "virtual": 4}
        assert client._pick_cursor_mode(7) == 4
        assert client._pick_cursor_mode(3) == 2
        assert client._pick_cursor_mode(1) == 1
        assert client._pick_cursor_mode(0) is None

    def test_teardown_invalidates_generation_and_closes_owned_resources(self) -> None:
        ce = _reload_engine()
        eng = ce.CastEngine(self._tmp_sock("teardown.sock"))
        read_fd, write_fd = os.pipe()
        os.close(write_fd)
        pipeline = MagicMock()
        portal = MagicMock()
        eng._session = ce.SessionState(
            pipeline=pipeline,
            portal_fd=read_fd,
            portal_session="/private/session",
            portal_client=portal,
            portal_closed_subscription=17,
            generation=4,
        )

        eng._teardown_session(4)

        pipeline.set_state.assert_called_once_with(ce.Gst.State.NULL)
        portal.unwatch_closed.assert_called_once_with(17)
        portal.close.assert_called_once_with("/private/session")
        with pytest.raises(OSError):
            os.fstat(read_fd)
        assert eng._session.generation == 5

        eng._teardown_session(4)
        pipeline.set_state.assert_called_once()

    def test_public_status_never_contains_portal_resources(self) -> None:
        ce = _reload_engine()
        eng = ce.CastEngine(self._tmp_sock("public-status.sock"))
        eng._session.portal_phase = ce.PORTAL_PHASE_PENDING
        eng._session.portal_fd = 123
        eng._session.portal_session = "/private/session"
        conn = MagicMock()

        eng._cmd_get_status(conn, 1)

        payload = json.loads(conn.sendall.call_args.args[0])
        assert payload["capture_state"] == "requesting"
        assert "portal_phase" not in payload
        assert "portal_fd" not in payload
        assert "portal_session" not in payload

    def test_pipeline_adds_opus_only_with_valid_audio_node(self) -> None:
        ce = _reload_engine()
        with_audio = ce.build_pipeline_description({"audio": True, "audio_pipewire_node": 77})
        without_audio_node = ce.build_pipeline_description({"audio": True})

        assert "opusenc name=audio_encoder" in with_audio
        assert "rtpopuspay" in with_audio
        assert "audio_capture" not in without_audio_node

    def test_pipeline_rejects_untrusted_pipewire_scalars(self) -> None:
        ce = _reload_engine()
        description = ce.build_pipeline_description(
            {
                "pipewire_fd": "12 ! fakesink",
                "pipewire_node": -1,
                "bitrate_kbps": "4000 ! filesink",
            }
        )

        assert "fakesink" not in description
        assert "filesink" not in description
        assert f"bitrate={ce.DEFAULT_VIDEO_BITRATE_KBPS}" in description

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
        eng._cmd_candidate(mock_conn, mock_msg, 1)
        sent = json.loads(mock_conn.sendall.call_args[0][0].decode("utf-8"))
        assert sent.get("type") == "CANDIDATE_OK"
        mock_webrtc.emit.assert_called_once_with("add-ice-candidate", 0, "c:1")

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
    _engine_module._portal_client_factory = _MockPortalOK
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
    eng._cmd_stop()
    t.join(timeout=1)
    _engine_module._portal_client_factory = _MockPortalOK
    with suppress(FileNotFoundError):
        os.unlink(sock_path)


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


def _wait_until(predicate, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


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
        ce._portal_client_factory = _MockPortalOK
        resp = _ipc_call(sock_path, {"version": ce.IPC_VERSION, "type": "START_SESSION"})
        assert resp.get("type") == "START_SESSION_OK"

        def _paused_false() -> bool:
            status = _ipc_call(sock_path, {"version": ce.IPC_VERSION, "type": "GET_STATUS"})
            return status.get("paused") is False

        assert _wait_until(_paused_false)
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
        ce._portal_client_factory = _MockPortalOK
        resp = _ipc_call(sock_path, {"version": ce.IPC_VERSION, "type": "START_SESSION"})
        assert resp.get("type") == "START_SESSION_OK"

        def _running_true() -> bool:
            status = _ipc_call(sock_path, {"version": ce.IPC_VERSION, "type": "GET_STATUS"})
            return status.get("running") is True

        assert _wait_until(_running_true)
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


def test_provider_and_engine_exchange_signaling_on_persistent_connection(
    _engine_module,
) -> None:
    socket_dir = Path(tempfile.mkdtemp())
    socket_path = str(socket_dir / "persistent-engine.sock")
    engine = _engine_module.CastEngine(socket_path)
    engine_thread = threading.Thread(target=engine.run, daemon=True)
    engine_thread.start()
    assert _wait_until(lambda: Path(socket_path).is_socket())

    provider = WebReceiverProvider.__new__(WebReceiverProvider)
    provider._engine_socket = socket_path
    provider._ipc_conn = None
    provider._ipc_lock = threading.Lock()
    provider._lock = threading.Lock()
    provider._session_id = "integration-session"
    provider._session_phase = "negotiating"
    provider._session_failure = ""
    provider._ipc_listener = None
    provider._ipc_stop = threading.Event()
    provider._sse_writers = []

    with patch.object(provider, "_push_sse") as push_sse:
        provider._ensure_ipc_connection()
        _engine_module._portal_client_factory = _MockPortalOK
        assert provider._send_ipc({"type": "START_SESSION"}) is True
        assert _wait_until(lambda: engine._session.running)

        engine._send_control_event(
            {"version": _engine_module.IPC_VERSION, "type": "OFFER_CREATED", "sdp": "v=0"}
        )
        assert _wait_until(lambda: push_sse.call_count == 1)
        push_sse.assert_called_once_with("offer", {"sdp": "v=0"})

        engine._send_control_event(
            {
                "version": _engine_module.IPC_VERSION,
                "type": "CANDIDATE",
                "candidate": {
                    "candidate": "candidate:engine",
                    "sdpMLineIndex": 0,
                },
            }
        )
        assert _wait_until(lambda: push_sse.call_count == 2)
        push_sse.assert_any_call(
            "candidate",
            {
                "candidate": {
                    "candidate": "candidate:engine",
                    "sdpMLineIndex": 0,
                }
            },
        )

        provider._on_signal_message(
            json.dumps({"type": "answer", "sdp": "v=0\no=browser\n"}).encode("utf-8")
        )
        assert _wait_until(lambda: engine._session.answer == "v=0\no=browser\n")

        provider._on_signal_message(
            json.dumps(
                {
                    "type": "candidate",
                    "candidate": {
                        "candidate": "candidate:browser",
                        "sdpMLineIndex": 0,
                    },
                }
            ).encode("utf-8")
        )
        webrtc = engine._session.pipeline.get_by_name("webrtc")
        assert _wait_until(
            lambda: any(
                call.args == ("add-ice-candidate", 0, "candidate:browser")
                for call in webrtc.emit.call_args_list
            )
        )

    provider._stop_ipc_listener()
    assert provider._ipc_conn is None
    engine._cmd_stop()
    engine_thread.join(timeout=1)
    assert not engine_thread.is_alive()
