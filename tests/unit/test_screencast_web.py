from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from steamzero.adapters.screencast_web import WebReceiverProvider
from steamzero.ports import CaptureConsent, ReceiverDescriptor


@pytest.fixture
def provider(tmp_path: Any) -> WebReceiverProvider:
    with (
        patch("steamzero.adapters.screencast_web.ThreadingHTTPServer"),
    ):
        p = WebReceiverProvider(data_dir=str(tmp_path))
        return p


class TestWebReceiverProvider:
    def test_protocol(self, provider: WebReceiverProvider) -> None:
        assert provider.protocol == "web-receiver"

    def test_local_capabilities(self, provider: WebReceiverProvider) -> None:
        caps = provider.local_capabilities()
        assert caps.max_width == 1920
        assert caps.max_height == 1080
        assert caps.max_frame_rate == 30
        assert "h264" in caps.video_codecs
        assert "opus" in caps.audio_codecs
        assert caps.hardware_encoder is False

    def test_discover(self, provider: WebReceiverProvider) -> None:
        result = provider.discover(100)
        assert len(result) == 1
        desc = result[0]
        assert isinstance(desc, ReceiverDescriptor)
        assert desc.receiver_id == "local-browser"
        assert desc.protocol == "web-receiver"
        assert desc.transport == "lan"
        assert desc.paired is False

    def test_pair(self, provider: WebReceiverProvider) -> None:
        assert provider.pair("local-browser", None) is True

    def test_start_without_consent(self, provider: WebReceiverProvider) -> None:
        from steamzero.core.errors import SteamZeroError

        with pytest.raises(SteamZeroError, match="E-CAST-CONSENT-REQUIRED"):
            provider.start("local-browser", "balanced", "game", CaptureConsent(granted=False))

    def test_sessions_empty(self, provider: WebReceiverProvider) -> None:
        assert provider.sessions() == []

    def test_ensure_running(self, provider: WebReceiverProvider) -> None:
        assert provider.ensure_running() is True

    def test_stop_idempotent(self, provider: WebReceiverProvider) -> None:
        provider.stop("any-session")
        assert provider.sessions() == []

    def test_sample(self, provider: WebReceiverProvider) -> None:
        sample = provider.sample("any-session")
        assert sample is not None
        assert sample.rtt_ms == 10

    def test_apply_stream(self, provider: WebReceiverProvider) -> None:
        assert provider.apply_stream("any-session", "high", 5000) is True

    def test_request_keyframe(self, provider: WebReceiverProvider) -> None:
        assert provider.request_keyframe("any-session") is True
