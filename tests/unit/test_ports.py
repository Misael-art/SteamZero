# SPDX-License-Identifier: GPL-3.0-or-later
"""A camada neutra de portas é empacotada e preserva imports públicos legados."""

from collections.abc import Sequence

from steamzero import ports
from steamzero.core.secret import Secret
from steamzero.domain import convert, device, mode, session, storage, sync
from steamzero.ports import (
    CaptureConsent,
    CastCapabilities,
    DisplayProfile,
    LinkSample,
    ReceiverDescriptor,
    ScreenCastProviderPort,
)


class _ConcreteProvider(ScreenCastProviderPort):
    @property
    def protocol(self) -> str:
        return "test"

    def discover(self, timeout_ms: int) -> Sequence[ReceiverDescriptor]:
        return []

    def pair(self, receiver_id: str, pin: Secret | None = None) -> bool:
        return False

    def preflight(self) -> tuple[bool, str]:
        return True, ""

    def local_capabilities(self) -> CastCapabilities:
        return CastCapabilities()

    def start(
        self,
        receiver_id: str,
        profile_id: str,
        mode: str,
        consent: CaptureConsent,
    ) -> str:
        return "sess-test"

    def sample(self, session_id: str) -> LinkSample | None:
        return None

    def apply_stream(self, session_id: str, profile_id: str, bitrate_kbps: int) -> bool:
        return True

    def request_keyframe(self, session_id: str) -> bool:
        return True

    def stop(self, session_id: str) -> None:
        pass


def test_domain_modules_reexport_the_canonical_ports() -> None:
    assert device.DevicePort is ports.DevicePort
    assert mode.DisplayPort is ports.DisplayPort
    assert mode.DisplayProfile is ports.DisplayProfile
    assert storage.StoragePort is ports.StoragePort
    assert storage.VolumeInfo is ports.VolumeInfo
    assert session.SessionPort is ports.SessionPort
    assert sync.CloudPort is ports.CloudPort
    assert convert.ConverterPort is ports.ConverterPort
    assert convert.ConversionTimeout is ports.ConversionTimeout


def test_screen_cast_provider_default_sessions_is_empty() -> None:
    provider: ScreenCastProviderPort = _ConcreteProvider()
    assert provider.sessions() == []


def test_display_profile_as_dict() -> None:
    profile = DisplayProfile(
        label="test-output",
        output="eDP-1",
        width=1920,
        height=1080,
        refresh_hz=60,
        hdr=False,
        vrr=True,
    )
    d = profile.as_dict()
    assert d["label"] == "test-output"
    assert d["width"] == 1920
    assert d["refreshHz"] == 60


def test_screen_cast_provider_default_ensure_running_is_true() -> None:
    provider: ScreenCastProviderPort = _ConcreteProvider()
    assert provider.ensure_running() is True
