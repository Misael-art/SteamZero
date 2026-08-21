# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Costura (Onda 6): instalador puro — template, alvos, render, filtragem."""

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.adapters.enhancements.installer import (
    EnhancementDefinition,
    EnhancementTarget,
    expand_path_template,
    filter_managed,
    first_compatible_format,
    identity_parts,
    installation_files,
    render_definitions,
    resolve_enhancement_target,
    role_for_kind,
    validate_policy,
)
from steamzero.adapters.enhancements.renderers import ENHANCEMENT_MARKER
from steamzero.core.errors import SteamZeroError
from steamzero.domain.game_enhancements import EnhancementKind, ProviderRole


def _manifest(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "duckstation",
        "paths": {"enhancementsDir": "{XDG_CONFIG_HOME}/duckstation/enhancements"},
        "enhancements": {
            "formats": ["pcsx2-pnach", "duckstation-ini"],
            "supplied": [],
        },
    }
    base.update(overrides)
    return base


def _paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    return tmp_path / "config", tmp_path / "data", tmp_path / "state"


def test_expand_path_template_resolves_xdg_tokens() -> None:
    config, data, state = _paths(Path("/dummy-root"))
    assert expand_path_template(
        "{XDG_CONFIG_HOME}/emu/settings.ini", config_home=config, data_home=data, state_home=state
    ) == Path("/dummy-root/config/emu/settings.ini")
    assert expand_path_template(
        "{XDG_DATA_HOME}/emu", config_home=config, data_home=data, state_home=state
    ) == Path("/dummy-root/data/emu")
    assert expand_path_template(
        "{XDG_STATE_HOME}/emu", config_home=config, data_home=data, state_home=state
    ) == Path("/dummy-root/state/emu")


def test_expand_path_template_rejects_unknown_token_and_relative_path(tmp_path: Path) -> None:
    config, data, state = _paths(tmp_path)
    with pytest.raises(SteamZeroError, match="token desconhecido"):
        expand_path_template("{HOME}/emu", config_home=config, data_home=data, state_home=state)
    with pytest.raises(SteamZeroError, match="não é absoluto"):
        expand_path_template("relativo", config_home=config, data_home=data, state_home=state)


def test_resolve_enhancement_target_requires_dir_and_formats(tmp_path: Path) -> None:
    config, data, state = _paths(tmp_path)
    target = resolve_enhancement_target(
        _manifest(), config_home=config, data_home=data, state_home=state
    )
    assert target is not None
    assert target.emulator_id == "duckstation"
    assert target.target_dir == config / "duckstation" / "enhancements"
    assert target.formats == ("pcsx2-pnach", "duckstation-ini")
    assert (
        resolve_enhancement_target(
            _manifest() | {"paths": {}}, config_home=config, data_home=data, state_home=state
        )
        is None
    )
    assert (
        resolve_enhancement_target(
            _manifest() | {"enhancements": {"formats": []}},
            config_home=config,
            data_home=data,
            state_home=state,
        )
        is None
    )
    assert (
        resolve_enhancement_target({}, config_home=config, data_home=data, state_home=state) is None
    )


def test_first_compatible_format_follows_precedence_by_kind() -> None:
    assert first_compatible_format(EnhancementKind.CHEAT, ("duckstation-ini", "pcsx2-pnach")) == (
        "pcsx2-pnach"
    )
    assert first_compatible_format(EnhancementKind.MOD, ("pcsx2-pnach", "duckstation-ini")) == (
        "duckstation-ini"
    )
    assert first_compatible_format(EnhancementKind.CHEAT, ("duckstation-ini",)) is None
    assert first_compatible_format(EnhancementKind.CHEAT, ()) is None


def test_identity_parts_derives_serial_and_title_ids() -> None:
    assert identity_parts("switch-title-id", "0100abcd1234e000") == (None, ("0100ABCD1234E000",))
    assert identity_parts("psx-serial", "slus_005.55") == ("slus_005.55", ())
    assert identity_parts("ps2-elf-crc32", "A1B2C3D4") == ("A1B2C3D4", ())
    assert identity_parts("gc-game-id", "GM8E01") == (None, ())
    assert identity_parts(None, None) == (None, ())


def test_definition_from_mapping_validates_shape() -> None:
    definition = EnhancementDefinition.from_mapping(
        {
            "kind": "cheat",
            "category": "performance",
            "title": "60 FPS",
            "source": "forum",
            "codes": ["20123456 00000000"],
            "version": "1.0",
        }
    )
    assert definition.title == "60 FPS"
    assert definition.codes == ("20123456 00000000",)
    with pytest.raises(SteamZeroError, match="campo desconhecido"):
        EnhancementDefinition.from_mapping(
            {"kind": "cheat", "category": "x", "title": "y", "source": "z", "evil": 1}
        )
    with pytest.raises(SteamZeroError, match="tipo de melhoria"):
        EnhancementDefinition.from_mapping(
            {"kind": "trainer", "category": "x", "title": "y", "source": "z"}
        )
    with pytest.raises(SteamZeroError, match="cheat exige"):
        EnhancementDefinition.from_mapping(
            {"kind": "cheat", "category": "x", "title": "y", "source": "z"}
        )
    with pytest.raises(SteamZeroError, match="mod técnico exige"):
        EnhancementDefinition.from_mapping(
            {"kind": "mod", "category": "x", "title": "y", "source": "z"}
        )


def test_render_definitions_picks_compatible_format_and_skips_rest(tmp_path: Path) -> None:
    config, data, state = _paths(tmp_path)
    target = resolve_enhancement_target(
        _manifest(), config_home=config, data_home=data, state_home=state
    )
    assert target is not None
    cheat = EnhancementDefinition.from_mapping(
        {
            "kind": "cheat",
            "category": "performance",
            "title": "Widescreen",
            "source": "forum",
            "codes": ["20123456 00000000"],
        }
    )
    mod = EnhancementDefinition.from_mapping(
        {
            "kind": "mod",
            "category": "compatibility",
            "title": "SPU fix",
            "source": "pack",
            "settingLines": ["DitheringMode=1"],
        }
    )
    rendered, skipped = render_definitions(
        (cheat, mod), target=target, scheme="psx-serial", value="SLUS_005.55"
    )
    assert [file.relative_path for file in rendered] == [
        "SLUS_005.55.pnach",
        "SLUS_005.55.ini",
    ]
    assert skipped == []
    rendered_only_cheat, skipped_none = render_definitions(
        (cheat,),
        target=_manifest_formats_only(("duckstation-ini",), tmp_path),
        scheme="psx-serial",
        value="SLUS_005.55",
    )
    assert rendered_only_cheat == []
    assert skipped_none[0]["reason"].startswith("emulador não declara formato")


def _manifest_formats_only(formats: tuple[str, ...], tmp_path: Path) -> EnhancementTarget:
    config, data, state = _paths(tmp_path)
    target = resolve_enhancement_target(
        _manifest() | {"enhancements": {"formats": list(formats), "supplied": []}},
        config_home=config,
        data_home=data,
        state_home=state,
    )
    assert target is not None
    return target


def test_installation_files_dedupes_and_enforces_containment(tmp_path: Path) -> None:
    from steamzero.adapters.enhancements.renderers import RenderedEnhancementFile

    config, data, state = _paths(tmp_path)
    target = resolve_enhancement_target(
        _manifest(), config_home=config, data_home=data, state_home=state
    )
    assert target is not None
    first = RenderedEnhancementFile("SLUS_005.55.ini", b"aaa", "duckstation-ini")
    second = RenderedEnhancementFile("SLUS_005.55.ini", b"bbb", "duckstation-ini")
    writes = installation_files([first, second], target_dir=target.target_dir)
    assert writes == {target.target_dir / "SLUS_005.55.ini": b"bbb"}
    with pytest.raises(SteamZeroError, match="caminho relativo inválido"):
        installation_files(
            [RenderedEnhancementFile("../escape", b"x", "duckstation-ini")],
            target_dir=target.target_dir,
        )


def test_filter_managed_ownership_and_idempotency(tmp_path: Path) -> None:
    config, data, state = _paths(tmp_path)
    target = resolve_enhancement_target(
        _manifest(), config_home=config, data_home=data, state_home=state
    )
    assert target is not None
    path = target.target_dir / "SLUS_005.55.ini"
    ours = (ENHANCEMENT_MARKER + "\n[Audio]\n").encode("ascii")
    new_ours = (ENHANCEMENT_MARKER + "\n[Audio]\nEmulationSpeed=200.0000\n").encode("ascii")
    foreign = b"[Audio]\n# feito a mao\n"

    to_do, skipped = filter_managed({path: new_ours}, existing={})
    assert to_do == {path: new_ours}
    assert skipped == []

    to_do, skipped = filter_managed({path: ours}, existing={path: ours})
    assert to_do == {}
    assert skipped == []

    to_do, skipped = filter_managed({path: new_ours}, existing={path: ours})
    assert to_do == {path: new_ours}
    assert skipped == []

    to_do, skipped = filter_managed({path: new_ours}, existing={path: foreign})
    assert to_do == {}
    assert skipped[0]["path"] == str(path)
    assert "marcador de ownership" in skipped[0]["reason"]


def test_role_for_kind_and_policy_at_point_of_use() -> None:
    config, data, state = _paths(Path("/dummy-root"))
    target = resolve_enhancement_target(
        _manifest() | {"enhancements": {"formats": ["pcsx2-pnach"], "supplied": ["cheat"]}},
        config_home=config,
        data_home=data,
        state_home=state,
    )
    assert target is not None
    assert role_for_kind(target, EnhancementKind.CHEAT) is ProviderRole.EMULATOR_SUPPLIED
    assert role_for_kind(target, EnhancementKind.MOD) is ProviderRole.STEAMZERO_SUPPLIED

    validate_policy(
        EnhancementKind.CHEAT, "performance", role=ProviderRole.STEAMZERO_SUPPLIED, source="forum"
    )
    with pytest.raises(SteamZeroError, match="E-ENHANCEMENT-DENIED"):
        validate_policy(
            EnhancementKind.CHEAT, "gameplay", role=ProviderRole.STEAMZERO_SUPPLIED, source="forum"
        )
    with pytest.raises(SteamZeroError, match="proveniência"):
        validate_policy(
            EnhancementKind.CHEAT, "performance", role=ProviderRole.STEAMZERO_SUPPLIED, source=None
        )


def test_definition_round_trip_preserves_fields() -> None:
    definition = EnhancementDefinition.from_mapping(
        {
            "kind": "mod",
            "category": "audio",
            "title": "Volume fix",
            "source": "pack",
            "description": "audio",
            "settingLines": ["DitheringMode=1"],
        }
    )
    assert EnhancementDefinition.from_mapping(definition.to_mapping()) == definition
