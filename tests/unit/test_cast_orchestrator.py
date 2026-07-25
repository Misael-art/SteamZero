# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from steamzero.adapters.cast_orchestrator import CastOrchestrator
from steamzero.core.errors import SteamZeroError
from steamzero.core.secret import Secret
from steamzero.ports import (
    CaptureConsent,
    CastCapabilities,
    LinkSample,
    ReceiverDescriptor,
)


@pytest.fixture
def mock_provider() -> MagicMock:
    provider = MagicMock()
    provider.protocol = "game-stream"
    provider.sessions.return_value = []
    provider.preflight.return_value = (True, "")
    provider.local_capabilities.return_value = CastCapabilities(
        full_screen=True,
        application_window=True,
        hardware_encoder=True,
        max_width=3840,
        max_height=2160,
        max_frame_rate=60,
        video_codecs=("h264", "hevc"),
        audio_codecs=("opus", "aac"),
    )
    provider.discover.return_value = [
        ReceiverDescriptor(
            receiver_id="tv-sala",
            display_name="TV da Sala",
            protocol="game-stream",
            address="192.168.1.50:48010",
            transport="lan",
            paired=True,
            capabilities=CastCapabilities(
                full_screen=True,
                application_window=True,
                max_width=1920,
                max_height=1080,
                max_frame_rate=60,
                video_codecs=("h264", "hevc"),
                audio_codecs=("opus",),
                hardware_encoder=True,
            ),
        ),
    ]
    provider.start.return_value = "sess-001"
    provider.sample.return_value = LinkSample(
        rtt_ms=10,
        jitter_ms=2,
        packet_loss_pct=0.0,
        decoder_queue_frames=0,
        encoder_ms=1.0,
        dropped_frames=0,
    )
    provider.apply_stream.return_value = True
    provider.request_keyframe.return_value = True
    provider.stop.return_value = None
    provider.pair.return_value = True
    provider.ensure_running.return_value = True
    return provider


@pytest.fixture
def orchestrator(mock_provider: MagicMock, tmp_path: Path) -> Iterator[CastOrchestrator]:
    with (
        patch.object(
            CastOrchestrator,
            "_all_providers",
            return_value=[mock_provider],
        ),
        patch.object(
            CastOrchestrator,
            "_provider_for",
            return_value=mock_provider,
        ),
    ):
        orch = CastOrchestrator(data_dir=tmp_path)
        yield orch


@pytest.fixture
def consent() -> CaptureConsent:
    return CaptureConsent(granted=True, scope="monitor", audio=True)


# --- discover_receivers ------------------------------------------------------


def test_discover_returns_resolved_receivers(
    orchestrator: CastOrchestrator, mock_provider: MagicMock
) -> None:
    result = orchestrator.discover_receivers(timeout_ms=500)
    mock_provider.discover.assert_called_once_with(500)
    assert len(result) == 1
    assert result[0]["receiver_id"] == "tv-sala"
    assert result[0]["display_name"] == "TV da Sala"
    assert result[0]["protocol"] == "game-stream"
    assert result[0]["transport"] == "lan"
    assert result[0]["paired"] is True
    assert result[0]["estimated_quality"] == "excellent"
    assert result[0]["blocked_reason"] == ""
    assert "game" in result[0]["supported_modes"]


def test_discover_empty_when_no_receivers(
    orchestrator: CastOrchestrator, mock_provider: MagicMock
) -> None:
    mock_provider.discover.return_value = []
    result = orchestrator.discover_receivers(timeout_ms=100)
    assert result == []


# --- pair_receiver -----------------------------------------------------------


def test_pair_receiver_success(orchestrator: CastOrchestrator, mock_provider: MagicMock) -> None:
    result = orchestrator.pair_receiver("192.168.1.50:48010")
    mock_provider.pair.assert_called_once_with("192.168.1.50:48010", None)
    assert result is True


def test_pair_receiver_with_pin(orchestrator: CastOrchestrator, mock_provider: MagicMock) -> None:
    result = orchestrator.pair_receiver("192.168.1.50:48010", Secret("1234"))
    mock_provider.pair.assert_called_once()
    args, _ = mock_provider.pair.call_args
    assert args[0] == "192.168.1.50:48010"
    assert isinstance(args[1], Secret)
    assert args[1].reveal() == "1234"
    assert result is True


def test_pair_receiver_failure(orchestrator: CastOrchestrator, mock_provider: MagicMock) -> None:
    mock_provider.pair.return_value = False
    result = orchestrator.pair_receiver("192.168.1.50:48010")
    assert result is False


# --- start_stream ------------------------------------------------------------


def test_start_stream_preflight_fails(
    orchestrator: CastOrchestrator, mock_provider: MagicMock
) -> None:
    mock_provider.preflight.return_value = (False, "engine-missing")
    with pytest.raises(SteamZeroError, match="E-CAST-ENGINE-MISSING"):
        orchestrator.start_stream("tv-sala")
    mock_provider.preflight.assert_called_once()
    mock_provider.start.assert_not_called()


def test_start_stream_full_flow(
    orchestrator: CastOrchestrator, mock_provider: MagicMock, consent: CaptureConsent
) -> None:
    result = orchestrator.start_stream("tv-sala", "balanced", "game", consent)

    mock_provider.preflight.assert_called_once()
    mock_provider.discover.assert_called_once()
    mock_provider.local_capabilities.assert_called_once()
    mock_provider.start.assert_called_once()

    assert result["protocol"] == "game-stream"
    assert result["mode"] == "game"
    assert result["state"] == "streaming"
    assert result["transport"] == "lan"
    assert result["estimatedQuality"] == "excellent"
    assert result["stream"]["videoCodec"] == "h264"
    assert result["resilience"]["degraded"] is False
    assert orchestrator.has_active_session is True


def test_start_stream_receiver_not_found(
    orchestrator: CastOrchestrator, mock_provider: MagicMock, consent: CaptureConsent
) -> None:
    mock_provider.discover.return_value = []
    with pytest.raises(SteamZeroError, match="E-CAST-NO-RECEIVER"):
        orchestrator.start_stream("unknown-receiver", "balanced", "game", consent)


def test_start_stream_receiver_blocked(
    orchestrator: CastOrchestrator, mock_provider: MagicMock, consent: CaptureConsent
) -> None:
    mock_provider.discover.return_value = [
        ReceiverDescriptor(
            receiver_id="blocked-tv",
            display_name="TV Bloqueada",
            protocol="game-stream",
            address="10.0.0.1:48010",
            transport="lan",
            paired=False,
            capabilities=CastCapabilities(
                max_width=1920,
                max_height=1080,
                max_frame_rate=60,
                video_codecs=("hevc",),
                audio_codecs=("opus",),
            ),
        ),
    ]
    with pytest.raises(SteamZeroError, match="E-CAST-RECEIVER-INCOMPATIBLE"):
        orchestrator.start_stream("blocked-tv", "balanced", "game", consent)


# --- stop_stream -------------------------------------------------------------


def test_stop_stream_idempotent(orchestrator: CastOrchestrator) -> None:
    orchestrator.stop_stream()
    assert orchestrator.has_active_session is False
    orchestrator.stop_stream()
    assert orchestrator.has_active_session is False


def test_stop_stream_cleans_session(
    orchestrator: CastOrchestrator, mock_provider: MagicMock, consent: CaptureConsent
) -> None:
    orchestrator.start_stream("tv-sala", "balanced", "game", consent)
    assert orchestrator.has_active_session is True

    orchestrator.stop_stream()
    mock_provider.stop.assert_called_once_with("sess-001")
    assert orchestrator.has_active_session is False
    assert orchestrator.session_status() is None


# --- session_status ----------------------------------------------------------


def test_session_status_returns_none_when_no_session(
    orchestrator: CastOrchestrator,
) -> None:
    assert orchestrator.session_status() is None


def test_session_status_returns_public_session(
    orchestrator: CastOrchestrator, mock_provider: MagicMock, consent: CaptureConsent
) -> None:
    orchestrator.start_stream("tv-sala", "balanced", "game", consent)
    status = orchestrator.session_status()
    assert mock_provider.sample.call_count >= 1
    mock_provider.sample.assert_any_call("sess-001")
    assert status is not None
    assert status["state"] == "streaming"
    assert status["resilience"]["degraded"] is False


def test_session_status_detects_link_lost(
    orchestrator: CastOrchestrator, mock_provider: MagicMock, consent: CaptureConsent
) -> None:
    mock_provider.sample.side_effect = SteamZeroError("E-CAST-LINK-LOST", detail="link lost")
    orchestrator.start_stream("tv-sala", "balanced", "game", consent)
    status = orchestrator.session_status()
    assert status is not None
    assert status["state"] == "reconnecting"
    assert "fault" in status
    assert status["fault"] == "linkLost"
    assert "recovery" in status


# --- active_sessions ---------------------------------------------------------


def test_active_sessions_empty(orchestrator: CastOrchestrator, mock_provider: MagicMock) -> None:
    mock_provider.sessions.return_value = []
    assert orchestrator.active_sessions() == []


def test_active_sessions_returns_alive(
    orchestrator: CastOrchestrator, mock_provider: MagicMock
) -> None:
    mock_provider.sessions.return_value = ["sess-a", "sess-b"]
    mock_provider.sample.return_value = LinkSample(
        rtt_ms=5,
        jitter_ms=1,
        packet_loss_pct=0.0,
        decoder_queue_frames=0,
        encoder_ms=0.5,
        dropped_frames=0,
    )
    result = orchestrator.active_sessions()
    assert len(result) == 2
    assert result[0]["session_id"] == "sess-a"
    assert result[1]["session_id"] == "sess-b"


# --- ensure_engine -----------------------------------------------------------


def test_ensure_engine_returns_true(
    orchestrator: CastOrchestrator, mock_provider: MagicMock
) -> None:
    assert orchestrator.ensure_engine() is True
    mock_provider.ensure_running.assert_called_once()


def test_ensure_engine_returns_false(
    orchestrator: CastOrchestrator, mock_provider: MagicMock
) -> None:
    mock_provider.ensure_running.return_value = False
    assert orchestrator.ensure_engine() is False


# --- reconcile ---------------------------------------------------------------


def test_reconcile_cleans_orphan_sessions(tmp_path: Path) -> None:
    mock_provider = MagicMock()
    mock_provider.sessions.return_value = ["orphan-1", "orphan-2"]
    with (
        patch.object(
            CastOrchestrator,
            "_all_providers",
            return_value=[mock_provider],
        ),
    ):
        orch = CastOrchestrator(data_dir=tmp_path)
    assert mock_provider.stop.call_count == 2
    mock_provider.stop.assert_any_call("orphan-1")
    mock_provider.stop.assert_any_call("orphan-2")
    assert orch.has_active_session is False


def test_start_stream_with_unknown_mode_falls_back_to_automatic(
    orchestrator: CastOrchestrator, mock_provider: MagicMock, consent: CaptureConsent
) -> None:
    result = orchestrator.start_stream("tv-sala", "balanced", "invalid-mode", consent)
    assert result["mode"] in ("game", "gameWindow", "mirror", "automatic")


# --- provider resolution ---


def test_provider_for_unknown_protocol_raises_error(tmp_path: Path) -> None:
    with patch.dict(
        CastOrchestrator._PROVIDER_PROTOCOLS,  # type: ignore[attr-defined]
        {"game-stream": MagicMock},
        clear=True,
    ):
        orch = CastOrchestrator(data_dir=tmp_path)
    with pytest.raises(SteamZeroError, match="E-CAST-UNKNOWN-PROTOCOL"):
        orch._provider_for("unknown-protocol")


def test_provider_for_known_protocol_creates_provider(tmp_path: Path) -> None:
    mock_cls = MagicMock()
    mock_instance = MagicMock()
    mock_cls.return_value = mock_instance
    with patch.dict(
        CastOrchestrator._PROVIDER_PROTOCOLS,  # type: ignore[attr-defined]
        {"test-proto": mock_cls},
        clear=True,
    ):
        orch = CastOrchestrator(data_dir=tmp_path)
        result = orch._provider_for("test-proto")
    assert result is mock_instance
    mock_cls.assert_called_once_with(data_dir=tmp_path)


def test_active_provider_calls_provider_for(tmp_path: Path) -> None:
    mock_provider = MagicMock()
    mock_provider.protocol = "test"
    with (
        patch.object(
            CastOrchestrator,
            "_all_providers",
            return_value=[mock_provider],
        ),
        patch.object(
            CastOrchestrator,
            "_provider_for",
            return_value=mock_provider,
        ),
    ):
        orch = CastOrchestrator(data_dir=tmp_path)
        assert orch._active_provider() is mock_provider
