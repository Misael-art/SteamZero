# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors

from __future__ import annotations

import json
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from steamzero.adapters.game_stream import GameStreamProvider
from steamzero.core.errors import SteamZeroError
from steamzero.core.secret import Secret
from steamzero.ports import CaptureConsent


@pytest.fixture
def provider(tmp_path: Path) -> GameStreamProvider:
    return GameStreamProvider(
        sunshine_url="http://127.0.0.1:47989",
        data_dir=tmp_path,
    )


@pytest.fixture
def consent() -> CaptureConsent:
    return CaptureConsent(granted=True, scope="monitor", audio=True)


# --- local_capabilities ----------------------------------------------------


def test_local_capabilities_from_sunshine(provider: GameStreamProvider) -> None:
    serverinfo = json.dumps(
        {
            "video_codecs": ["h264", "hevc"],
            "audio_codecs": ["opus", "aac"],
            "hardware_encoder": True,
            "display_capture": True,
        }
    ).encode()

    with (
        patch.object(provider, "_vaapi_available", return_value=False),
        patch.object(provider, "_pipewire_screencast_available", return_value=True),
        patch("urllib.request.urlopen") as mock_urlopen,
    ):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = serverinfo
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        caps = provider.local_capabilities()

    assert caps.full_screen is True
    assert caps.application_window is True
    assert caps.max_width == 3840
    assert caps.video_codecs == ("h264", "hevc")
    assert caps.audio_codecs == ("opus", "aac")
    assert caps.hardware_encoder is True


def test_local_capabilities_without_sunshine(provider: GameStreamProvider) -> None:
    with (
        patch.object(provider, "_vaapi_available", return_value=False),
        patch.object(provider, "_pipewire_screencast_available", return_value=False),
        patch("urllib.request.urlopen", side_effect=OSError("no sunshine")),
    ):
        caps = provider.local_capabilities()

    assert caps.full_screen is False
    assert caps.video_codecs == ("h264",)
    assert caps.hardware_encoder is False


# --- preflight --------------------------------------------------------------


def test_preflight_sunshine_running(provider: GameStreamProvider) -> None:
    with patch("urllib.request.urlopen") as mock:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock.return_value.__enter__.return_value = mock_resp
        ok, reason = provider.preflight()
    assert ok is True
    assert reason == ""


def test_preflight_binary_found(provider: GameStreamProvider) -> None:
    with (
        patch("urllib.request.urlopen", side_effect=OSError("not running")),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value.returncode = 0
        ok, reason = provider.preflight()
    assert ok is True
    assert reason == ""


def test_preflight_nothing_available(provider: GameStreamProvider) -> None:
    with (
        patch("urllib.request.urlopen", side_effect=OSError("not running")),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value.returncode = 1
        ok, reason = provider.preflight()
    assert ok is False
    assert reason == "engine-missing"


# --- discover ---------------------------------------------------------------


def test_discover_handles_oserror_gracefully(provider: GameStreamProvider) -> None:
    with patch("socket.socket") as mock_sock_cls:
        mock_sock = MagicMock()
        mock_sock_cls.return_value = mock_sock
        mock_sock.sendto.side_effect = OSError("network unreachable")
        receivers = provider.discover(timeout_ms=100)
    assert receivers == []


def test_discover_finds_receivers(provider: GameStreamProvider) -> None:
    receiver_info = json.dumps(
        {
            "receiver_id": "tv-sala",
            "display_name": "TV da Sala (Moonlight)",
            "transport": "lan",
            "paired": True,
            "capabilities": {
                "full_screen": True,
                "max_width": 1920,
                "max_height": 1080,
                "max_frame_rate": 60,
                "video_codecs": ["h264", "hevc"],
                "audio_codecs": ["opus"],
            },
        }
    ).encode()

    with (
        patch("socket.socket") as mock_sock_cls,
        patch("urllib.request.urlopen") as mock_http,
    ):
        mock_sock = MagicMock()
        mock_sock_cls.return_value = mock_sock

        _call_count = 0

        def recv_side_effect(*_a, **_kw):
            nonlocal _call_count
            _call_count += 1
            if _call_count == 1:
                return (b"STEAMZERO_RECEIVER", ("192.168.1.50", 47999))
            raise TimeoutError()

        mock_sock.recvfrom.side_effect = recv_side_effect

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = receiver_info
        mock_http.return_value.__enter__.return_value = mock_resp

        receivers = provider.discover(timeout_ms=1000)

    assert len(receivers) == 1
    assert receivers[0].receiver_id == "tv-sala"
    assert receivers[0].display_name == "TV da Sala (Moonlight)"
    assert receivers[0].transport == "lan"
    assert receivers[0].paired is True


def test_discover_empty_when_no_receivers(provider: GameStreamProvider) -> None:
    with patch("socket.socket") as mock_sock_cls:
        mock_sock = MagicMock()
        mock_sock_cls.return_value = mock_sock
        mock_sock.recvfrom.side_effect = TimeoutError()

        receivers = provider.discover(timeout_ms=100)

    assert receivers == []


# --- pair -------------------------------------------------------------------


def test_pair_with_explicit_pin(provider: GameStreamProvider) -> None:
    with patch("urllib.request.urlopen") as mock:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock.return_value.__enter__.return_value = mock_resp
        result = provider.pair("192.168.1.50:48010", pin=Secret("1234"))
    assert result is True


def test_pair_with_sunshine_pin(provider: GameStreamProvider) -> None:
    responses = {
        "/api/pin": json.dumps({"pin": "5678"}).encode(),
        "/pair": json.dumps({"status": "ok"}).encode(),
    }

    def side_effect(req, *_a, **_kw):
        path = req.full_url.replace("http://127.0.0.1:47989", "")
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = responses.get(path, b"{}")
        return MagicMock(__enter__=lambda _: mock_resp)

    with patch("urllib.request.urlopen", side_effect=side_effect):
        result = provider.pair("192.168.1.50:48010")
    assert result is True


def test_pair_fails_when_sunshine_pin_not_a_dict(provider: GameStreamProvider) -> None:
    with patch("urllib.request.urlopen") as mock:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(["not", "a", "dict"]).encode()
        mock.return_value.__enter__.return_value = mock_resp
        result = provider.pair("192.168.1.50:48010")
    assert result is False


def test_pair_failure(provider: GameStreamProvider) -> None:
    with patch("urllib.request.urlopen", side_effect=OSError("unreachable")):
        result = provider.pair("192.168.1.50:48010")
    assert result is False


# --- start ------------------------------------------------------------------


def test_start_session(provider: GameStreamProvider, consent: CaptureConsent) -> None:
    resp_data = json.dumps({"session_id": "abc-123"}).encode()
    with patch("urllib.request.urlopen") as mock:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = resp_data
        mock.return_value.__enter__.return_value = mock_resp
        sid = provider.start("192.168.1.50:48010", "balanced", "game", consent)
    assert sid == "abc-123"


def test_start_requires_consent(provider: GameStreamProvider) -> None:
    no_consent = CaptureConsent(granted=False, scope="none")
    with pytest.raises(SteamZeroError, match="autorizacao"):
        provider.start("192.168.1.50:48010", "balanced", "game", no_consent)


def test_start_sunshine_failure(provider: GameStreamProvider, consent: CaptureConsent) -> None:
    with (
        patch("urllib.request.urlopen", side_effect=OSError("sunshine down")),
        pytest.raises(SteamZeroError, match="sunshine"),
    ):
        provider.start("192.168.1.50:48010", "balanced", "game", consent)


# --- sample -----------------------------------------------------------------


def test_sample_active_session(provider: GameStreamProvider) -> None:
    stats = json.dumps(
        {
            "rtt_ms": 12,
            "jitter_ms": 3,
            "packet_loss": 0.5,
            "decoder_queue": 1,
            "encoder_ms": 2.1,
            "dropped_frames": 0,
        }
    ).encode()
    with patch("urllib.request.urlopen") as mock:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = stats
        mock.return_value.__enter__.return_value = mock_resp
        sample = provider.sample("abc-123")
    assert sample is not None
    assert sample.rtt_ms == 12
    assert sample.packet_loss_pct == 0.5
    assert sample.encoder_ms == 2.1


def test_sample_no_session(provider: GameStreamProvider) -> None:
    with patch("urllib.request.urlopen", side_effect=OSError("no session")):
        sample = provider.sample("abc-123")
    assert sample is None


# --- apply_stream, request_keyframe, stop ----------------------------------


def test_apply_stream_success(provider: GameStreamProvider) -> None:
    ok_resp = json.dumps({"status": "ok"}).encode()
    with patch("urllib.request.urlopen") as mock:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = ok_resp
        mock.return_value.__enter__.return_value = mock_resp
        result = provider.apply_stream("abc-123", "balanced", 8000)
    assert result is True


def test_apply_stream_failure(provider: GameStreamProvider) -> None:
    with patch("urllib.request.urlopen", side_effect=OSError("fail")):
        result = provider.apply_stream("abc-123", "balanced", 8000)
    assert result is False


def test_request_keyframe_success(provider: GameStreamProvider) -> None:
    ok_resp = json.dumps({"status": "ok"}).encode()
    with patch("urllib.request.urlopen") as mock:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = ok_resp
        mock.return_value.__enter__.return_value = mock_resp
        result = provider.request_keyframe("abc-123")
    assert result is True


def test_request_keyframe_failure(provider: GameStreamProvider) -> None:
    with patch("urllib.request.urlopen", side_effect=OSError("fail")):
        result = provider.request_keyframe("abc-123")
    assert result is False


def test_stop_session(provider: GameStreamProvider) -> None:
    ok_resp = json.dumps({"status": "ok"}).encode()
    with patch("urllib.request.urlopen") as mock:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = ok_resp
        mock.return_value.__enter__.return_value = mock_resp
        provider.stop("abc-123")
    assert provider._session is None


def test_stop_idempotent_when_no_session(provider: GameStreamProvider) -> None:
    with patch("urllib.request.urlopen", side_effect=OSError("no session")):
        provider.stop("nonexistent")
    assert provider._session is None


# --- Sunshine management ----------------------------------------------------


def test_ensure_running_when_already_up(provider: GameStreamProvider) -> None:
    with patch("urllib.request.urlopen") as mock:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock.return_value.__enter__.return_value = mock_resp
        result = provider.ensure_running()
    assert result is True


def test_ensure_running_starts_sunshine(provider: GameStreamProvider) -> None:
    mock_resp = MagicMock()
    mock_resp.status = 200
    resp_ctx = MagicMock(__enter__=lambda _: mock_resp)
    with (
        patch("urllib.request.urlopen") as mock_urlopen,
        patch("subprocess.Popen") as mock_popen,
        patch("time.sleep"),
    ):
        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc
        mock_urlopen.side_effect = [
            OSError("down"),
            OSError("down"),
            resp_ctx,
        ]
        result = provider.ensure_running()
    assert result is True


# --- Protocol property ------------------------------------------------------


def test_protocol(provider: GameStreamProvider) -> None:
    assert provider.protocol == "game-stream"


# --- Error codes ------------------------------------------------------------


def test_start_without_consent_raises_e_cast_consent_required(
    provider: GameStreamProvider,
) -> None:
    no_consent = CaptureConsent(granted=False, scope="none")
    with pytest.raises(SteamZeroError) as excinfo:
        provider.start("tv", "balanced", "game", no_consent)
    assert excinfo.value.code == "E-CAST-CONSENT-REQUIRED"


def test_sunshine_api_unreachable_raises_e_cast_link_lost(
    provider: GameStreamProvider,
) -> None:
    with (
        patch("urllib.request.urlopen", side_effect=urllib.error.URLError("no route")),
        pytest.raises(SteamZeroError) as excinfo,
    ):
        provider._sunshine_api("GET", "/api/serverinfo")
    assert excinfo.value.code in ("E-CAST-LINK-LOST", "E-CAST-ENGINE-MISSING")


# --- local_capabilities fallback -------------------------------------------


def test_local_capabilities_with_empty_codecs_lists(provider: GameStreamProvider) -> None:
    empty_info = json.dumps(
        {
            "video_codecs": [],
            "audio_codecs": [],
            "hardware_encoder": False,
            "display_capture": False,
        }
    ).encode()
    with (
        patch.object(provider, "_vaapi_available", return_value=False),
        patch.object(provider, "_pipewire_screencast_available", return_value=False),
        patch("urllib.request.urlopen") as mock_urlopen,
    ):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = empty_info
        mock_urlopen.return_value.__enter__.return_value = mock_resp
        caps = provider.local_capabilities()
    assert caps.video_codecs == ("h264",)
    assert caps.audio_codecs == ("opus",)


def test_local_caps_fallback_without_sunshine(provider: GameStreamProvider) -> None:
    with (
        patch.object(provider, "_vaapi_available", return_value=False),
        patch.object(provider, "_pipewire_screencast_available", return_value=False),
        patch("urllib.request.urlopen", side_effect=OSError("no sunshine")),
    ):
        caps = provider.local_capabilities()
    assert caps.video_codecs == ("h264",)
    assert caps.audio_codecs == ("opus",)
    assert caps.max_width == 3840
    assert caps.max_height == 2160


# --- Receiver probe rejects malformed --------------------------------------


def test_probe_malformed_response(provider: GameStreamProvider) -> None:
    with (
        patch("socket.socket") as mock_sock_cls,
        patch("urllib.request.urlopen") as mock_http,
    ):
        mock_sock = MagicMock()
        mock_sock_cls.return_value = mock_sock
        mock_sock.recvfrom.return_value = (b"STEAMZERO_RECEIVER", ("10.0.0.5", 47999))

        mock_http.side_effect = OSError("no service")

        receivers = provider.discover(timeout_ms=500)
    assert receivers == []


# --- Sunshine binary detection ---------------------------------------------


def test_sunshine_binary_available(provider: GameStreamProvider) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        assert provider._sunshine_binary_available() is True


def test_sunshine_binary_not_available(provider: GameStreamProvider) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        assert provider._sunshine_binary_available() is False


# --- PipeWire / VA-API detection -------------------------------------------


def test_vaapi_available(provider: GameStreamProvider) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        assert provider._vaapi_available() is True


def test_pipewire_available(provider: GameStreamProvider) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        assert provider._pipewire_screencast_available() is True


# --- Sessions (WI-S2) --------------------------------------------------------


def test_sessions_empty_when_no_sessions(provider: GameStreamProvider) -> None:
    assert provider.sessions() == []


def test_sessions_returns_alive_only(provider: GameStreamProvider) -> None:
    provider._persist_session("alive-1", "tv-sala")
    provider._persist_session("dead-1", "tv-cozinha")
    provider._persist_session("alive-2", "quarto")
    stats = json.dumps({"rtt_ms": 10}).encode()

    def side_effect(req, *_a, **_kw):
        mock = MagicMock()
        mock.status = 200
        mock.read.return_value = stats
        url = req.full_url if hasattr(req, "full_url") else ""
        if "dead-1" in url:
            raise OSError("session gone")
        return MagicMock(__enter__=lambda _: mock)

    with patch("urllib.request.urlopen", side_effect=side_effect):
        result = provider.sessions()

    assert "alive-1" in result
    assert "alive-2" in result
    assert "dead-1" not in result


def test_sessions_persist_across_provider_recreation(provider: GameStreamProvider) -> None:
    provider._persist_session("persist-99", "tv-sala")
    stats = json.dumps({"rtt_ms": 10}).encode()

    with patch("urllib.request.urlopen") as mock:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = stats
        mock.return_value.__enter__.return_value = mock_resp
        result = provider.sessions()
    assert result == ["persist-99"]

    new_provider = GameStreamProvider(
        sunshine_url="http://127.0.0.1:47989",
        data_dir=provider._data_dir,
    )

    with patch("urllib.request.urlopen") as mock:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = stats
        mock.return_value.__enter__.return_value = mock_resp
        result = new_provider.sessions()
    assert result == ["persist-99"]


def test_stop_cleans_journal(provider: GameStreamProvider, consent: CaptureConsent) -> None:
    provider._persist_session("clean-me", "tv-sala")
    with patch("urllib.request.urlopen") as mock:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"rtt_ms": 5}).encode()
        mock.return_value.__enter__.return_value = mock_resp
        provider.stop("clean-me")
    assert provider.sessions() == []


def test_stop_idempotent_on_unknown_session(provider: GameStreamProvider) -> None:
    provider.stop("never-existed")
    assert provider._session is None
    assert provider.sessions() == []


def test_start_persists_session(provider: GameStreamProvider, consent: CaptureConsent) -> None:
    resp_data = json.dumps({"session_id": "persist-42"}).encode()
    stats = json.dumps({"rtt_ms": 10}).encode()

    call_count = 0

    def urlopen_side_effect(req, *_a, **_kw):
        nonlocal call_count
        call_count += 1
        mock = MagicMock()
        mock.status = 200
        if call_count == 1:
            mock.read.return_value = resp_data
        else:
            mock.read.return_value = stats
        return MagicMock(__enter__=lambda _: mock)

    with patch("urllib.request.urlopen", side_effect=urlopen_side_effect):
        provider.start("192.168.1.50:48010", "balanced", "game", consent)
        assert "persist-42" in provider.sessions()
