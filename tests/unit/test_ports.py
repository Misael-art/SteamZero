# SPDX-License-Identifier: GPL-3.0-or-later
"""A camada neutra de portas é empacotada e preserva imports públicos legados."""

from steamzero import ports
from steamzero.domain import convert, device, mode, session, storage, sync


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
