# SPDX-License-Identifier: GPL-3.0-or-later
"""Renderers de arquivos de melhoria por jogo (Onda 3 do
SZ-EMULATION-ENHANCEMENTS): formato válido por emulador, marcador de
ownership obrigatório e recusa de arquivo de terceiros."""

from __future__ import annotations

import pytest

from steamzero.adapters.enhancements.renderers import (
    ENHANCEMENT_MARKER,
    EnhancementFileFormat,
    EnhancementRecipe,
    manageability_check,
    render_cemu_rules,
    render_dolphin_gameini,
    render_duckstation_ini,
    render_file,
    render_pcsx2_pnach,
    render_rpcs3_yaml,
)
from steamzero.core.errors import SteamZeroError
from steamzero.domain.game_enhancements import EnhancementKind

_CODE = ("C0000000 00000003", "60000000 00000000")


def _recipe(
    category: str = "quality-of-life",
    codes: tuple[str, ...] = _CODE,
    kind: EnhancementKind = EnhancementKind.MOD,
    title: str = "Ridge Racer Revolution",
) -> EnhancementRecipe:
    return EnhancementRecipe(
        kind=kind,
        category=category,
        title=title,
        source="github:steamzero-tests",
        codes=codes,
        version="1.0",
    )


def test_every_rendered_file_carries_ownership_marker() -> None:
    files = [
        render_rpcs3_yaml(_recipe(), "BLUS30443"),
        render_cemu_rules(_recipe(), ("0005000012345678",)),
        render_pcsx2_pnach(_recipe(kind=EnhancementKind.CHEAT), "SLUS-20152"),
        render_dolphin_gameini(_recipe(kind=EnhancementKind.CHEAT), "GM8E01"),
        render_duckstation_ini(_recipe(), ("AspectRatio = 16:9",), "SLUS_005.55"),
    ]
    for rendered in files:
        assert rendered.data.startswith(ENHANCEMENT_MARKER.encode())
        assert ENHANCEMENT_MARKER.encode() in rendered.data.splitlines()[0]


def test_manageability_allows_create_and_marked_replace_but_refuses_third_party() -> None:
    assert manageability_check(None) == (True, "criável")
    marked = render_pcsx2_pnach(_recipe(kind=EnhancementKind.CHEAT), "SLUS-20152").data
    assert manageability_check(marked) == (True, "marcado pelo SteamZero")
    assert manageability_check(b"# alguem escreveu isto\n[Gecko]\n")[0] is False


def test_rpcs3_yaml_structure_and_be32_ops() -> None:
    rendered = render_rpcs3_yaml(_recipe(category="performance"), "BLUS30443")
    text = rendered.data.decode()
    assert rendered.relative_path == "steamzero-BLUS30443.yml"
    assert rendered.format is EnhancementFileFormat.RPCS3_YAML
    assert "Version: 1.0" in text
    assert "Metadata:" in text
    assert "- [be32, 0xC0000000, 0x00000003, 0x00000000]" in text
    assert 'Category: "performance"' in text


def test_rpcs3_yaml_refuses_gameplay_category() -> None:
    with pytest.raises(SteamZeroError) as exc:
        render_rpcs3_yaml(_recipe(category="gameplay"), "BLUS30443")
    assert exc.value.code == "E-ENHANCEMENT-DENIED"


def test_cemu_rules_definition_and_cheat_section() -> None:
    rendered = render_cemu_rules(
        _recipe(kind=EnhancementKind.CHEAT), ("0005000012345678", "0005000C12345678")
    )
    text = rendered.data.decode()
    assert rendered.relative_path == "steamzero-0005000012345678/rules.txt"
    assert "[Definition]" in text
    assert "titleIds = 0005000012345678, 0005000C12345678" in text
    assert "[Ridge Racer Revolution]" in text
    assert all(code in text for code in _CODE)


def test_cemu_rules_requires_title_ids() -> None:
    with pytest.raises(SteamZeroError):
        render_cemu_rules(_recipe(kind=EnhancementKind.CHEAT), ())


def test_pnach_serial_filename_and_header() -> None:
    rendered = render_pcsx2_pnach(
        _recipe(kind=EnhancementKind.CHEAT, title="Ridge Racer"), "SLUS-20152"
    )
    text = rendered.data.decode()
    assert rendered.relative_path == "SLUS-20152.pnach"
    assert text.startswith("gametitle=Ridge Racer") is False  # marcador vem primeiro
    assert "gametitle=Ridge Racer" in text
    assert all(code in text for code in _CODE)


def test_pnach_rejects_bad_serial_and_bad_codes() -> None:
    with pytest.raises(SteamZeroError):
        render_pcsx2_pnach(_recipe(kind=EnhancementKind.CHEAT), "SLUS 20152 ../../etc")
    with pytest.raises(SteamZeroError):
        render_pcsx2_pnach(
            _recipe(kind=EnhancementKind.CHEAT, codes=("not-a-code-line",)),
            "SLUS-20152",
        )


def test_dolphin_gameini_gecko_section() -> None:
    rendered = render_dolphin_gameini(_recipe(kind=EnhancementKind.CHEAT), "GM8E01")
    text = rendered.data.decode()
    assert rendered.relative_path == "GM8E01.ini"
    assert "[Gecko]" in text
    assert "$SteamZero-" in text
    assert all(code in text for code in _CODE)


def test_duckstation_ini_section_mapping_and_technical_only() -> None:
    rendered = render_duckstation_ini(
        _recipe(category="quality-of-life"), ("AspectRatio = 16:9",), "SLUS_005.55"
    )
    assert rendered.relative_path == "SLUS_005.55.ini"
    assert "[Display]" in rendered.data.decode()
    assert (
        "[Audio]"
        in render_duckstation_ini(
            _recipe(category="audio"), ("BitDepth = 16",), "SLUS_005.55"
        ).data.decode()
    )
    assert (
        "[EmuCore]"
        in render_duckstation_ini(
            _recipe(category="compatibility"), ("SynchronizeTightness = 0",), "SLUS_005.55"
        ).data.decode()
    )
    with pytest.raises(SteamZeroError):
        render_duckstation_ini(_recipe(category="unlock"), ("AspectRatio = 16:9",), "SLUS_005.55")
    with pytest.raises(SteamZeroError):
        render_duckstation_ini(_recipe(), (), "SLUS_005.55")


def test_dispatch_unknown_format_and_required_args() -> None:
    with pytest.raises(SteamZeroError):
        render_file("nintendo-super-magic", _recipe())
    with pytest.raises(SteamZeroError):
        render_file(
            EnhancementFileFormat.PCSX2_PNACH,
            _recipe(kind=EnhancementKind.CHEAT),
        )
    rendered = render_file(
        "pcsx2-pnach",
        _recipe(kind=EnhancementKind.CHEAT),
        serial="SLUS-20152",
    )
    assert rendered.relative_path == "SLUS-20152.pnach"


def test_switch_identity_recipe_renders_into_other_platform_formats() -> None:
    """A receita é agnóstica de plataforma: a mesma melhoria (categoria
    técnica, proveniência declarada) pode ser renderizada para qualquer
    emulador que consuma um dos formatos suportados."""
    from steamzero.domain.game_identity import GameIdentity

    identity = GameIdentity.switch("0100ABCD12340001")
    recipe = EnhancementRecipe(
        kind=EnhancementKind.MOD,
        category="performance",
        title=identity.value,
        source="nsecm",
    )
    rules = render_cemu_rules(recipe, (identity.value,))
    assert identity.value in rules.data.decode()
    assert rules.data.startswith(ENHANCEMENT_MARKER.encode())
