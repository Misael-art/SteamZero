# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Onda 1: identidade de título tipada por plataforma (dominio)."""

from __future__ import annotations

import pytest

from steamzero.domain.game_identity import (
    GameIdentity,
    IdentityScheme,
    identity_from_gc_wii_disc_id,
    identity_from_ps1_ps2_volume_id,
    identity_from_ps2_elf_crc32,
    identity_from_ps3_sfb,
    identity_from_wiiu_meta_xml,
    scheme_for_platform,
    validate_identity_value,
)


@pytest.mark.parametrize(
    ("scheme", "value", "expected"),
    [
        (IdentityScheme.SWITCH_TITLE_ID, "0100000000010000", True),
        (IdentityScheme.SWITCH_TITLE_ID, "0100deadbeef0012", True),
        (IdentityScheme.SWITCH_TITLE_ID, "010000000001000", False),  # 15 chars
        (IdentityScheme.SWITCH_TITLE_ID, "XYZ", False),
        (IdentityScheme.PS2_SERIAL, "SLUS-20152", True),
        (IdentityScheme.PS2_SERIAL, "SLUS_201.52", True),
        (IdentityScheme.PSX_SERIAL, "SCUS-94163", True),
        (IdentityScheme.PSX_SERIAL, "SLES_005.55", True),
        (IdentityScheme.PS2_SERIAL, "XYZ", False),
        (IdentityScheme.GC_GAME_ID, "GM8E01", True),
        (IdentityScheme.GC_GAME_ID, "GM8E01EXTRA", False),
        (IdentityScheme.WII_GAME_ID, "RZDE01", True),
        (IdentityScheme.PS3_TITLE_ID, "BLUS30443", True),
        (IdentityScheme.PS3_TITLE_ID, "BCES00001", True),
        (IdentityScheme.PS3_TITLE_ID, "BLUS30443X", False),
        (IdentityScheme.WIIU_PRODUCT_ID, "WUP-P-AYME", False),  # hifen nao entra
        (IdentityScheme.WIIU_PRODUCT_ID, "WUPPAYME", True),
        (IdentityScheme.PS2_ELF_CRC32, "A1B2C3D4", True),
        (IdentityScheme.PS2_ELF_CRC32, "A1B2C3D", False),
        (IdentityScheme.UNKNOWN, "qualquer", False),
    ],
)
def test_validate_identity_value(scheme: IdentityScheme, value: str, expected: bool) -> None:
    assert validate_identity_value(scheme, value) is expected


def test_scheme_for_platform_maps_expected_schemes() -> None:
    assert IdentityScheme.SWITCH_TITLE_ID in scheme_for_platform("switch")
    assert IdentityScheme.PSX_SERIAL in scheme_for_platform("playstation")
    assert IdentityScheme.PS2_SERIAL in scheme_for_platform("playstation-2")
    assert IdentityScheme.PS2_ELF_CRC32 in scheme_for_platform("playstation-2")
    assert IdentityScheme.PS3_TITLE_ID in scheme_for_platform("playstation-3")
    assert IdentityScheme.WIIU_PRODUCT_ID in scheme_for_platform("wii-u")
    assert IdentityScheme.GC_GAME_ID in scheme_for_platform("nintendo-console")
    assert scheme_for_platform("snes") == ()


def test_game_identity_is_typed_and_frozen() -> None:
    identity = GameIdentity("playstation-2", IdentityScheme.PS2_SERIAL, "slus-20152")
    assert identity.lookup_key() == "SLUS-20152"
    assert identity.matches(GameIdentity("playstation-2", IdentityScheme.PS2_SERIAL, "SLUS-20152"))
    assert not identity.matches(
        GameIdentity("playstation-2", IdentityScheme.PS2_SERIAL, "SLUS-20333")
    )
    other_platform = GameIdentity("playstation", IdentityScheme.PSX_SERIAL, "SLUS-20152")
    assert not identity.matches(other_platform)


def test_game_identity_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        GameIdentity("switch", IdentityScheme.SWITCH_TITLE_ID, "not-a-title-id")
    with pytest.raises(ValueError):
        GameIdentity("", IdentityScheme.SWITCH_TITLE_ID, "0100000000010000")


def test_switch_helper_and_unknown() -> None:
    switch = GameIdentity.switch("0100000000010000")
    assert switch.scheme is IdentityScheme.SWITCH_TITLE_ID
    unknown = GameIdentity.unknown("snes")
    assert not unknown.is_known
    assert unknown.scheme is IdentityScheme.UNKNOWN


def test_identity_to_dict_hides_unknown_scheme() -> None:
    known = GameIdentity("switch", IdentityScheme.SWITCH_TITLE_ID, "0100000000010000")
    assert known.to_dict()["scheme"] == "switch-title-id"
    unknown = GameIdentity.unknown("snes")
    assert unknown.to_dict()["scheme"] is None
    assert unknown.to_dict()["value"] is None


def test_ps1_ps2_volume_id_extracts_serial() -> None:
    volume = b"SLUS_005.55" + b" " * 21
    identity = identity_from_ps1_ps2_volume_id(volume, platform="playstation")
    assert identity is not None
    assert identity.scheme is IdentityScheme.PSX_SERIAL
    assert identity.value == "SLUS_005.55"
    identity = identity_from_ps1_ps2_volume_id(volume, platform="playstation-2")
    assert identity is not None
    assert identity.scheme is IdentityScheme.PS2_SERIAL


def test_ps1_ps2_volume_id_with_file_version_suffix() -> None:
    volume = b"SLES_005.55;1" + b" " * 20
    identity = identity_from_ps1_ps2_volume_id(volume, platform="playstation")
    assert identity is not None
    assert identity.value == "SLES_005.55"


def test_ps1_ps2_volume_id_with_long_title_uses_first_token() -> None:
    volume = b"GRAN TURISMO 2" + b" " * 16
    assert identity_from_ps1_ps2_volume_id(volume, platform="playstation") is None
    volume = b"SLUS-94163 GRAN TURISMO 2"
    identity = identity_from_ps1_ps2_volume_id(volume, platform="playstation")
    assert identity is not None
    assert identity.value == "SLUS-94163"


def test_ps1_ps2_volume_id_truncated_returns_none() -> None:
    assert identity_from_ps1_ps2_volume_id(b"", platform="playstation") is None
    assert identity_from_ps1_ps2_volume_id(b"SL", platform="playstation") is None


def test_gc_wii_disc_id_extracts_6_bytes() -> None:
    identity = identity_from_gc_wii_disc_id(b"GM8E01", is_wii=False)
    assert identity is not None
    assert identity.scheme is IdentityScheme.GC_GAME_ID
    assert identity.value == "GM8E01"
    identity = identity_from_gc_wii_disc_id(b"RZDE01", is_wii=True)
    assert identity is not None
    assert identity.scheme is IdentityScheme.WII_GAME_ID


def test_gc_wii_disc_id_truncated_or_junk_returns_none() -> None:
    assert identity_from_gc_wii_disc_id(b"GM8", is_wii=False) is None
    assert identity_from_gc_wii_disc_id(b"!@#$%^", is_wii=False) is None


def _sfb_payload(title_id: bytes) -> bytes:
    payload = bytearray(b"..S" + b"\x00" * 0x60)
    payload[0x10 : 0x10 + len(title_id)] = title_id
    return bytes(payload)


def test_ps3_sfb_extracts_title_id() -> None:
    identity = identity_from_ps3_sfb(_sfb_payload(b"BLUS30443"))
    assert identity is not None
    assert identity.scheme is IdentityScheme.PS3_TITLE_ID
    assert identity.value == "BLUS30443"


def test_ps3_sfb_requires_magic() -> None:
    assert identity_from_ps3_sfb(b"junk" + b"\x00" * 40) is None
    assert identity_from_ps3_sfb(b"") is None
    assert identity_from_ps3_sfb(b"..S" + b"\x00" * 0x1F) is None


def test_ps3_sfb_falls_back_to_region_scan() -> None:
    payload = bytearray(b"..S" + b"\x00" * 0x60)
    payload[0x22 : 0x22 + len(b"BCES00001")] = b"BCES00001"
    identity = identity_from_ps3_sfb(bytes(payload))
    assert identity is not None
    assert identity.value == "BCES00001"


def test_wiiu_meta_xml_product_id() -> None:
    xml = "<meta><product_id>WUPPAYME</product_id></meta>"
    identity = identity_from_wiiu_meta_xml(xml)
    assert identity is not None
    assert identity.value == "WUPPAYME"
    assert identity_from_wiiu_meta_xml("<meta></meta>") is None
    assert identity_from_wiiu_meta_xml("") is None
    # Sem parser XML: entidade externa nao e interpretada, apenas ignorada.
    dangling = "<meta><product_id>WUPPAYME</product_id></meta><!DOCTYPE foo>"
    assert identity_from_wiiu_meta_xml(dangling) is not None


def test_ps2_elf_crc32_formats_identity() -> None:
    identity = identity_from_ps2_elf_crc32(0x1A2B3C4D)
    assert identity.scheme is IdentityScheme.PS2_ELF_CRC32
    assert identity.value == "1A2B3C4D"
    assert validate_identity_value(IdentityScheme.PS2_ELF_CRC32, identity.value)
