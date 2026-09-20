# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from steamzero.core.errors import SteamZeroError
from steamzero.domain.ps3_firmware import (
    PS3_FIRMWARE_FILENAME,
    PS3_FIRMWARE_SOURCE_URL,
    PS3_FIRMWARE_VERSION,
    Ps3FirmwareSource,
    validate_ps3_firmware,
)


def test_official_source_is_exact_and_source_verified() -> None:
    source = Ps3FirmwareSource()
    source.validate()
    assert source.version == PS3_FIRMWARE_VERSION
    assert source.url == PS3_FIRMWARE_SOURCE_URL
    assert source.integrity_policy == "source-verified"


@pytest.mark.parametrize(
    "url",
    [
        "http://dbr01.ps3.update.playstation.net/PS3UPDAT.PUP",
        "https://example.invalid/PS3UPDAT.PUP",
        f"{PS3_FIRMWARE_SOURCE_URL}?mirror=1",
    ],
)
def test_source_rejects_non_allowlisted_url(url: str) -> None:
    with pytest.raises(SteamZeroError) as excinfo:
        Ps3FirmwareSource(url=url).validate()
    assert excinfo.value.code == "E-CONTENT-FW-INCOMPAT"


def test_validation_requires_name_and_integrity(tmp_path: Path) -> None:
    payload = b"official-firmware-fixture"
    path = tmp_path / PS3_FIRMWARE_FILENAME
    path.write_bytes(payload)

    artifact = validate_ps3_firmware(path, min_bytes=1)

    assert artifact.size == len(payload)
    assert artifact.sha256 == hashlib.sha256(payload).hexdigest()
    metadata = artifact.metadata().decode("utf-8")
    assert '"integrityPolicy": "source-verified"' in metadata
    assert artifact.source.filename == PS3_FIRMWARE_FILENAME


def test_validation_rejects_truncated_firmware(tmp_path: Path) -> None:
    path = tmp_path / PS3_FIRMWARE_FILENAME
    path.write_bytes(b"short")

    with pytest.raises(SteamZeroError, match="truncado"):
        validate_ps3_firmware(path)


def test_validation_rejects_wrong_filename(tmp_path: Path) -> None:
    path = tmp_path / "firmware.pup"
    path.write_bytes(b"fixture")

    with pytest.raises(SteamZeroError, match=r"PS3UPDAT\.PUP"):
        validate_ps3_firmware(path, min_bytes=1)
