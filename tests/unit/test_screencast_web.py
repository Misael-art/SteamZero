from __future__ import annotations

import http.client
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import steamzero.adapters.screencast_web as sw_mod
from steamzero.adapters.screencast_web import (
    IPC_VERSION,
    WebReceiverProvider,
    _ReceiverHandler,
)
from steamzero.ports import CaptureConsent, ReceiverDescriptor


@pytest.fixture
def mocked_provider(tmp_path: Any) -> WebReceiverProvider:
    with (
        patch("steamzero.adapters.screencast_web.ThreadingHTTPServer"),
        patch.object(WebReceiverProvider, "_ensure_engine", return_value=None),
        patch.object(WebReceiverProvider, "_ensure_ipc_connection"),
        patch.object(WebReceiverProvider, "_send_ipc"),
        patch.object(WebReceiverProvider, "_spawn_engine", return_value=None),
        patch.object(WebReceiverProvider, "_stop_ipc_listener"),
    ):
        p = WebReceiverProvider(data_dir=str(tmp_path))
        return p


@pytest.fixture
def provider(tmp_path: Any) -> WebReceiverProvider:
    """Real HTTP server, mocked engine/IPC internals."""
    with (
        patch.object(WebReceiverProvider, "_ensure_engine", return_value=None),
        patch.object(WebReceiverProvider, "_ensure_ipc_connection"),
        patch.object(WebReceiverProvider, "_send_ipc"),
        patch.object(WebReceiverProvider, "_spawn_engine", return_value=None),
        patch.object(WebReceiverProvider, "_stop_ipc_listener"),
    ):
        p = WebReceiverProvider(data_dir=str(tmp_path))
    yield p
    p._ipc_stop.set()
    if p._receiver_server is not None:
        p._receiver_server.shutdown()


class TestWebReceiverProvider:
    def test_protocol(self, mocked_provider: WebReceiverProvider) -> None:
        assert mocked_provider.protocol == "web-receiver"

    def test_local_capabilities(self, mocked_provider: WebReceiverProvider) -> None:
        caps = mocked_provider.local_capabilities()
        assert caps.max_width == 1920
        assert caps.max_height == 1080
        assert caps.max_frame_rate == 30
        assert "h264" in caps.video_codecs
        assert "opus" in caps.audio_codecs
        assert caps.hardware_encoder is False

    def test_discover(self, mocked_provider: WebReceiverProvider) -> None:
        result = mocked_provider.discover(100)
        assert len(result) == 1
        desc = result[0]
        assert isinstance(desc, ReceiverDescriptor)
        assert desc.receiver_id == "local-browser"
        assert desc.protocol == "web-receiver"
        assert desc.transport == "lan"
        assert desc.paired is False

    def test_pair(self, mocked_provider: WebReceiverProvider) -> None:
        assert mocked_provider.pair("local-browser", None) is True

    def test_start_without_consent(self, mocked_provider: WebReceiverProvider) -> None:
        from steamzero.core.errors import SteamZeroError

        with pytest.raises(SteamZeroError, match="E-CAST-CONSENT-REQUIRED"):
            mock_consent = CaptureConsent(granted=False)
            mocked_provider.start("local-browser", "balanced", "game", mock_consent)

    def test_sessions_empty(self, mocked_provider: WebReceiverProvider) -> None:
        assert mocked_provider.sessions() == []

    def test_ensure_running(self, mocked_provider: WebReceiverProvider) -> None:
        assert mocked_provider.ensure_running() is True

    def test_stop_idempotent(self, mocked_provider: WebReceiverProvider) -> None:
        mocked_provider.stop("any-session")
        assert mocked_provider.sessions() == []

    def test_sample(self, mocked_provider: WebReceiverProvider) -> None:
        sample = mocked_provider.sample("any-session")
        assert sample is not None
        assert sample.rtt_ms == 10

    def test_apply_stream(self, mocked_provider: WebReceiverProvider) -> None:
        assert mocked_provider.apply_stream("any-session", "high", 5000) is True

    def test_request_keyframe(self, mocked_provider: WebReceiverProvider) -> None:
        assert mocked_provider.request_keyframe("any-session") is True

    # --- HTTP handler -------------------------------------------------------

    def test_serve_page_returns_html(self, provider: WebReceiverProvider) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", provider._receiver_port, timeout=5)
        conn.request("GET", "/")
        resp = conn.getresponse()
        assert resp.status == 200
        assert resp.getheader("Content-Type") == "text/html; charset=utf-8"
        body = resp.read()
        assert len(body) > 0
        conn.close()

    def test_serve_sse_returns_headers(self, provider: WebReceiverProvider) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", provider._receiver_port, timeout=5)
        conn.request("GET", "/signal")
        resp = conn.getresponse()
        assert resp.status == 200
        assert resp.getheader("Content-Type") == "text/event-stream"
        conn.close()

    def test_sse_cleanup_on_close(self, provider: WebReceiverProvider) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", provider._receiver_port, timeout=5)
        conn.request("GET", "/signal")
        resp = conn.getresponse()
        assert resp.status == 200
        conn.close()

    def test_signal_post_answer(self, provider: WebReceiverProvider) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", provider._receiver_port, timeout=5)
        body = json.dumps({"type": "answer", "sdp": "v=0"}).encode("utf-8")
        conn.request("POST", "/signal", body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["ok"] is True
        conn.close()

    def test_signal_post_candidate(self, provider: WebReceiverProvider) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", provider._receiver_port, timeout=5)
        body = json.dumps({"type": "candidate", "candidate": "cand:1"}).encode("utf-8")
        conn.request("POST", "/signal", body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        assert resp.status == 200
        conn.close()

    def test_signal_post_stop(self, provider: WebReceiverProvider) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", provider._receiver_port, timeout=5)
        body = json.dumps({"type": "stop"}).encode("utf-8")
        conn.request("POST", "/signal", body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        assert resp.status == 200
        conn.close()

    def test_post_unknown_path_returns_404(self, provider: WebReceiverProvider) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", provider._receiver_port, timeout=5)
        conn.request("POST", "/unknown")
        resp = conn.getresponse()
        assert resp.status == 404
        conn.close()

    def test_signal_post_empty_body_returns_400(self, provider: WebReceiverProvider) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", provider._receiver_port, timeout=5)
        conn.request("POST", "/signal", body=b"", headers={"Content-Length": "0"})
        resp = conn.getresponse()
        assert resp.status == 400
        conn.close()

    # --- Preflight ----------------------------------------------------------

    def _mock_gi(self, mock_gst: MagicMock) -> dict:
        mock_gi = MagicMock()
        mock_repo = MagicMock()
        mock_repo.Gst = mock_gst
        mock_gi.repository = mock_repo
        return {"gi": mock_gi, "gi.repository": mock_repo, "gi.repository.Gst": mock_gst}

    def test_preflight_ok(self, provider: WebReceiverProvider) -> None:
        mock_gst = MagicMock()
        mock_gst.ElementFactory.find = MagicMock(return_value=MagicMock())
        with patch.dict("sys.modules", self._mock_gi(mock_gst)):
            ok, msg = provider.preflight()
        assert ok is True
        assert msg == ""
        for attr in ("gi", "Gst"):
            if hasattr(sw_mod, attr):
                delattr(sw_mod, attr)

    def test_preflight_gi_missing(self, provider: WebReceiverProvider) -> None:
        # Also remove from sys.modules for isolation against other test
        # suites that may have injected gi into sys.modules.
        saved = {k: sys.modules.pop(k, None) for k in ("gi", "gi.repository", "gi.repository.Gst")}
        for attr in ("gi", "Gst"):
            if hasattr(sw_mod, attr):
                delattr(sw_mod, attr)
        try:
            ok, msg = provider.preflight()
        finally:
            for k, v in saved.items():
                if v is not None:
                    sys.modules[k] = v
        assert ok is False
        assert msg == "gi-missing"

    def test_preflight_element_missing(self, provider: WebReceiverProvider) -> None:
        for attr in ("gi", "Gst"):
            if hasattr(sw_mod, attr):
                delattr(sw_mod, attr)
        mock_gst = MagicMock()
        mock_gst.ElementFactory.find = MagicMock(return_value=None)
        mods = self._mock_gi(mock_gst)
        with patch.dict("sys.modules", mods):
            ok, msg = provider.preflight()
        assert ok is False, f"expected False, got True with msg={msg}"
        assert msg == "element-missing: webrtcbin"
        for attr in ("gi", "Gst"):
            if hasattr(sw_mod, attr):
                delattr(sw_mod, attr)

    def test_preflight_exception(self, provider: WebReceiverProvider) -> None:
        mock_gst = MagicMock()
        mock_gst.ElementFactory.find.side_effect = RuntimeError("boom")
        with patch.dict("sys.modules", self._mock_gi(mock_gst)):
            ok, msg = provider.preflight()
        assert ok is False
        assert "preflight-failed" in msg
        for attr in ("gi", "Gst"):
            if hasattr(sw_mod, attr):
                delattr(sw_mod, attr)

    # --- IPC / signaling ----------------------------------------------------

    def test_send_ipc_encodes_message(self, provider: WebReceiverProvider) -> None:
        with patch("steamzero.adapters.screencast_web.socket.socket") as mock_sock:
            mock_sock_instance = MagicMock()
            mock_sock.return_value = mock_sock_instance
            provider._send_ipc({"type": "TEST"})
            mock_sock_instance.connect.assert_called_once()
            sent_data = mock_sock_instance.sendall.call_args[0][0]
            decoded = json.loads(sent_data.decode("utf-8").strip())
            assert decoded["type"] == "TEST"
            assert decoded["version"] == IPC_VERSION

    def test_send_ipc_handles_exception(self, provider: WebReceiverProvider) -> None:
        with patch("steamzero.adapters.screencast_web.socket.socket") as mock_sock:
            mock_sock.side_effect = OSError("no socket")
            provider._send_ipc({"type": "TEST"})

    def test_on_signal_message_answer(self, provider: WebReceiverProvider) -> None:
        with patch.object(provider, "_send_ipc") as mock_send:
            provider._on_signal_message(
                json.dumps({"type": "answer", "sdp": "v=0"}).encode("utf-8")
            )
            mock_send.assert_called_once_with({"type": "answer", "sdp": "v=0"})

    def test_on_signal_message_candidate(self, provider: WebReceiverProvider) -> None:
        with patch.object(provider, "_send_ipc") as mock_send:
            provider._on_signal_message(
                json.dumps({"type": "candidate", "candidate": "cand:1"}).encode("utf-8")
            )
            mock_send.assert_called_once_with({"type": "candidate", "candidate": "cand:1"})

    def test_on_signal_message_stop(self, provider: WebReceiverProvider) -> None:
        with patch.object(provider, "stop") as mock_stop:
            provider._on_signal_message(json.dumps({"type": "stop"}).encode("utf-8"))
            mock_stop.assert_called_once()

    def test_on_signal_message_invalid_json(self, provider: WebReceiverProvider) -> None:
        provider._on_signal_message(b"not json")

    def test_on_signal_message_unknown_type(self, provider: WebReceiverProvider) -> None:
        provider._on_signal_message(json.dumps({"type": "unknown_type"}).encode("utf-8"))

    def test_on_ipc_message_offer_created(self, provider: WebReceiverProvider) -> None:
        with patch.object(provider, "_push_sse") as mock_push:
            provider._on_ipc_message(
                json.dumps({"type": "OFFER_CREATED", "sdp": "v=0"}).encode("utf-8")
            )
            mock_push.assert_called_once_with("offer", {"sdp": "v=0"})

    def test_on_ipc_message_error(self, provider: WebReceiverProvider) -> None:
        with patch.object(provider, "_push_sse") as mock_push:
            provider._on_ipc_message(
                json.dumps({"type": "ERROR", "detail": "engine oom"}).encode("utf-8")
            )
            mock_push.assert_called_once_with("error", {"detail": "engine oom"})

    def test_on_ipc_message_candidate(self, provider: WebReceiverProvider) -> None:
        with patch.object(provider, "_push_sse") as mock_push:
            provider._on_ipc_message(
                json.dumps({"type": "CANDIDATE", "candidate": "cand:1"}).encode("utf-8")
            )
            mock_push.assert_called_once_with("candidate", {"candidate": "cand:1"})

    def test_on_ipc_message_invalid_raw(self, provider: WebReceiverProvider) -> None:
        provider._on_ipc_message("not json")

    def test_on_ipc_message_unknown_type(self, provider: WebReceiverProvider) -> None:
        with patch.object(provider, "_push_sse") as mock_push:
            provider._on_ipc_message(json.dumps({"type": "UNKNOWN_EVENT"}).encode("utf-8"))
            mock_push.assert_not_called()

    def test_push_sse(self, provider: WebReceiverProvider) -> None:
        writer = MagicMock()
        provider._sse_writers.append(writer)
        provider._push_sse("offer", {"sdp": "v=0"})
        writer.write.assert_called_once()
        writer.flush.assert_called_once()

    def test_push_sse_removes_dead_writer(self, provider: WebReceiverProvider) -> None:
        writer = MagicMock()
        writer.write.side_effect = BrokenPipeError()
        provider._sse_writers.append(writer)
        provider._push_sse("offer", {"sdp": "v=0"})
        assert writer not in provider._sse_writers

    def test_set_sse_conn_adds_writer(self, provider: WebReceiverProvider) -> None:
        writer = MagicMock()
        provider._set_sse_conn(writer)
        assert writer in provider._sse_writers

    def test_clear_sse_conn_removes_writer(self, provider: WebReceiverProvider) -> None:
        writer = MagicMock()
        provider._sse_writers.append(writer)
        provider._clear_sse_conn(writer)
        assert writer not in provider._sse_writers

    def test_clear_sse_conn_missing_writer(self, provider: WebReceiverProvider) -> None:
        writer = MagicMock()
        provider._clear_sse_conn(writer)

    # --- Engine lifecycle ---------------------------------------------------

    def test_ensure_engine_returns_existing(self, provider: WebReceiverProvider) -> None:
        mock_inst = MagicMock()
        mock_inst.healthy = True
        provider._engine = mock_inst
        result = provider._ensure_engine()
        assert result is mock_inst

    def test_ensure_engine_spawns_when_unhealthy(self, provider: WebReceiverProvider) -> None:
        with patch.object(provider, "_spawn_engine", return_value="new-inst") as mock_spawn:
            provider._engine = None
            result = provider._ensure_engine()
            assert result == "new-inst"
            mock_spawn.assert_called_once()

    def test_spawn_engine_returns_none_when_path_missing(
        self, provider: WebReceiverProvider
    ) -> None:
        with patch.object(provider, "_resolve_engine_path", return_value=None):
            result = provider._spawn_engine()
            assert result is None

    def test_spawn_engine_handles_python_not_found(self, provider: WebReceiverProvider) -> None:
        fake_path = "/_f_" + __name__
        with (
            patch.object(provider, "_resolve_engine_path", return_value=fake_path),
            patch(
                "steamzero.adapters.screencast_web._find_python",
                return_value="/nonexistent/python",
            ),
            patch(
                "steamzero.adapters.screencast_web.subprocess.Popen",
                side_effect=FileNotFoundError,
            ),
        ):
            result = provider._spawn_engine()
            assert result is None

    def test_spawn_engine_timeout(self, provider: WebReceiverProvider) -> None:
        fake_path = "/_f_" + __name__
        with (
            patch.object(provider, "_resolve_engine_path", return_value=fake_path),
            patch(
                "steamzero.adapters.screencast_web._find_python",
                return_value="/usr/bin/python3",
            ),
            patch("steamzero.adapters.screencast_web.subprocess.Popen") as mock_popen,
            patch("steamzero.adapters.screencast_web.Path.is_socket", return_value=False),
        ):
            proc = MagicMock()
            mock_popen.return_value = proc
            result = provider._spawn_engine()
            assert result is None
            proc.terminate.assert_called_once()

    def test_spawn_engine_success(self, provider: WebReceiverProvider) -> None:
        fake_path = "/_f_" + __name__
        proc = MagicMock()
        proc.pid = 12345
        with (
            patch.object(provider, "_resolve_engine_path", return_value=fake_path),
            patch(
                "steamzero.adapters.screencast_web._find_python",
                return_value="/usr/bin/python3",
            ),
            patch("steamzero.adapters.screencast_web.subprocess.Popen", return_value=proc),
            patch("steamzero.adapters.screencast_web.Path.is_socket", return_value=True),
        ):
            result = provider._spawn_engine()
            assert result is not None
            assert result.healthy is True
            assert result.process is proc
            assert provider._engine is result

    def test_resolve_engine_path(self) -> None:
        path = WebReceiverProvider._resolve_engine_path(None)
        assert path is not None
        assert path.endswith("cast_engine.py")

    def test_cleanup_socket(self, tmp_path: Path) -> None:
        sock = tmp_path / "test.sock"
        sock.write_text("")
        provider_obj = WebReceiverProvider.__new__(WebReceiverProvider)
        provider_obj._engine_socket = str(sock)
        provider_obj._cleanup_socket()
        assert not sock.exists()

    def test_find_python(self) -> None:
        from steamzero.adapters.screencast_web import _find_python

        py = _find_python()
        assert py is not None
        assert isinstance(py, str)

    def test_find_python_fallback(self) -> None:
        from steamzero.adapters.screencast_web import _find_python

        with patch("steamzero.adapters.screencast_web.Path.is_file", return_value=False):
            py = _find_python()
        assert py == "python3"

    # --- close --------------------------------------------------------------

    def test_close_without_server(self, mocked_provider: WebReceiverProvider) -> None:
        mocked_provider._receiver_server = None
        mocked_provider._engine = None
        mocked_provider.close()

    def test_close_with_server_and_engine(self, provider: WebReceiverProvider) -> None:
        proc = MagicMock()
        provider._engine = MagicMock()
        provider._engine.process = proc
        provider.close()
        proc.terminate.assert_called_once()

    def test_sessions_returns_id_when_session_active(self, provider: WebReceiverProvider) -> None:
        provider._session_id = "test-session"
        assert provider.sessions() == ["test-session"]

    def test_serve_page_500_on_error(self, provider: WebReceiverProvider) -> None:
        with patch(
            "steamzero.adapters.screencast_web.importlib.resources.files",
            side_effect=RuntimeError("no such resource"),
        ):
            conn = http.client.HTTPConnection("127.0.0.1", provider._receiver_port, timeout=5)
            conn.request("GET", "/")
            resp = conn.getresponse()
            assert resp.status == 500
            conn.close()

    def test_start_with_consent_creates_session(self, provider: WebReceiverProvider) -> None:
        consent = CaptureConsent(granted=True)
        session_id = provider.start("local-browser", "balanced", "game", consent)
        assert session_id is not None
        assert len(session_id) > 0
        assert provider.sessions() == [session_id]

    def test_start_twice_returns_same_session(self, provider: WebReceiverProvider) -> None:
        consent = CaptureConsent(granted=True)
        s1 = provider.start("local-browser", "balanced", "game", consent)
        s2 = provider.start("local-browser", "high", "desktop", consent)
        assert s1 == s2
        assert provider.sessions() == [s1]

    def test_close_kills_engine_on_timeout(self, provider: WebReceiverProvider) -> None:
        proc = MagicMock()
        proc.wait.side_effect = subprocess.TimeoutExpired(["cmd"], 5)
        provider._engine = MagicMock()
        provider._engine.process = proc
        provider.close()
        proc.terminate.assert_called_once()
        proc.kill.assert_called_once()

    def test_sse_without_provider(self, provider: WebReceiverProvider) -> None:
        original = _ReceiverHandler.provider
        _ReceiverHandler.provider = None
        conn = http.client.HTTPConnection("127.0.0.1", provider._receiver_port, timeout=5)
        conn.request("GET", "/signal")
        resp = conn.getresponse()
        assert resp.status == 200
        conn.close()
        _ReceiverHandler.provider = original

    def test_signal_post_without_provider(self, provider: WebReceiverProvider) -> None:
        original = _ReceiverHandler.provider
        _ReceiverHandler.provider = None
        conn = http.client.HTTPConnection("127.0.0.1", provider._receiver_port, timeout=5)
        body = json.dumps({"type": "answer", "sdp": "v=0"}).encode("utf-8")
        conn.request("POST", "/signal", body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        assert resp.status == 200
        conn.close()
        _ReceiverHandler.provider = original

    def test_http_server_start_failure_logs_error(self, tmp_path: Path) -> None:
        with patch(
            "steamzero.adapters.screencast_web.ThreadingHTTPServer",
            side_effect=OSError("port in use"),
        ):
            p = WebReceiverProvider(data_dir=str(tmp_path))
            assert p._receiver_server is None

    def test_ensure_ipc_connect_failure(self, provider: WebReceiverProvider) -> None:
        with patch(
            "steamzero.adapters.screencast_web.socket.socket",
            side_effect=OSError("no such file"),
        ):
            provider._ipc_conn = None
            provider._ensure_ipc_connection()
            assert provider._ipc_conn is None

    def test_ipc_listen_loop_oserror_breaks(self, provider: WebReceiverProvider) -> None:
        mock_sock = MagicMock()
        mock_sock.settimeout = MagicMock()
        mock_sock.recv.side_effect = OSError("disconnected")
        provider._ipc_conn = mock_sock
        provider._ipc_listen_loop()

    def test_ipc_listen_loop_timeout_continues(self, provider: WebReceiverProvider) -> None:
        mock_sock = MagicMock()
        mock_sock.settimeout = MagicMock()
        mock_sock.recv.side_effect = [TimeoutError(), b""]
        provider._ipc_conn = mock_sock
        provider._ipc_listen_loop()

    def test_ipc_listen_loop_parses_lines(self, provider: WebReceiverProvider) -> None:
        mock_sock = MagicMock()
        mock_sock.settimeout = MagicMock()
        msg = json.dumps({"type": "OFFER_CREATED", "sdp": "v=0"})
        with patch.object(provider, "_on_ipc_message") as mock_dispatch:
            mock_sock.recv.side_effect = [(msg + "\n").encode("utf-8"), b""]
            provider._ipc_conn = mock_sock
            provider._ipc_listen_loop()
            mock_dispatch.assert_called_once_with(msg)

    def test_ipc_listen_loop_skips_empty_lines(self, provider: WebReceiverProvider) -> None:
        mock_sock = MagicMock()
        mock_sock.settimeout = MagicMock()
        mock_sock.recv.side_effect = [b"\n\n", b""]
        provider._ipc_conn = mock_sock
        provider._ipc_listen_loop()

    def test_ipc_listen_loop_no_conn(self, provider: WebReceiverProvider) -> None:
        provider._ipc_conn = None
        provider._ipc_listen_loop()

    def test_resolve_engine_path_returns_none_on_error(self) -> None:
        with patch(
            "steamzero.adapters.screencast_web.importlib.resources.files",
            side_effect=Exception("no package"),
        ):
            result = WebReceiverProvider._resolve_engine_path(None)
            assert result is None
