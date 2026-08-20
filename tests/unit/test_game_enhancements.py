# SPDX-License-Identifier: GPL-3.0-or-later
"""Testes da fachada única de melhorias por jogo (Onda 2 do
SZ-EMULATION-ENHANCEMENTS): papel do provedor declarado no manifesto,
invariante anti-cheat com nega padrão e vista unificada sobre as mesmas
tabelas dos donos Switch."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from steamzero.core.errors import SteamZeroError
from steamzero.domain.game_enhancements import (
    EnhancementDecision,
    EnhancementKind,
    GameEnhancementManager,
    ProviderRole,
    policy_decision,
    resolve_provider_role,
)
from steamzero.domain.game_identity import GameIdentity
from steamzero.domain.switch_cheats import CheatType, InstalledCheat
from steamzero.domain.switch_mods import InstalledMod, ModType
from steamzero.ports import (
    CheatCandidate,
    CheatIdentity,
    ModCandidate,
    ModIdentity,
)

P1 = GameIdentity.switch("0100ABCD12340001")


@dataclass
class _FakeModStore:
    rows: list[InstalledMod] = field(default_factory=list)

    def list_installed(self, game_id: str) -> list[InstalledMod]:
        return [row for row in self.rows if row.game_id == game_id]


@dataclass
class _FakeCheatStore:
    rows: list[InstalledCheat] = field(default_factory=list)

    def list_installed(self, game_id: str) -> list[InstalledCheat]:
        return [row for row in self.rows if row.game_id == game_id]


@dataclass
class _FakeModCatalog:
    by_title: list[ModCandidate] = field(default_factory=list)
    by_build: list[ModCandidate] = field(default_factory=list)

    def search_by_title_id(self, title_id: str) -> list[ModCandidate]:
        return self.by_title

    def search_by_build_id(self, title_id: str, build_id: str) -> list[ModCandidate]:
        return self.by_build

    def refresh_catalog(self) -> int:
        return 0


@dataclass
class _FakeCheatCatalog:
    by_title: list[CheatCandidate] = field(default_factory=list)
    by_build: list[CheatCandidate] = field(default_factory=list)

    def search_by_title_id(self, title_id: str) -> list[CheatCandidate]:
        return self.by_title

    def search_by_build_id(self, title_id: str, build_id: str) -> list[CheatCandidate]:
        return self.by_build

    def refresh_catalog(self) -> int:
        return 0


def _manager(mod_store=None, cheat_store=None, mod_catalog=None, cheat_catalog=None):
    return GameEnhancementManager(
        mod_catalog=mod_catalog or _FakeModCatalog(),
        mod_store=mod_store or _FakeModStore(),
        cheat_catalog=cheat_catalog or _FakeCheatCatalog(),
        cheat_store=cheat_store or _FakeCheatStore(),
        game_selector=lambda identity: identity.value,
    )


_MOD = InstalledMod(
    id="mod-1",
    game_id="0100ABCD12340001",
    catalog_id=None,
    title_id="0100ABCD12340001",
    build_id=None,
    name="60fps",
    mod_type=ModType.PERFORMANCE,
    source="github",
    version="1.0",
    state="active",
    install_path="/opt/steamzero/games/0100ABCD12340001/mods/60fps",
    emulator_id="azahar",
)

_CHEAT = InstalledCheat(
    id="cheat-1",
    game_id="0100ABCD12340001",
    title_id="0100ABCD12340001",
    build_id=None,
    name="Moedas infinitas",
    cheat_type=CheatType.GOLD,
    source="nsecm",
    version=None,
    state="active",
    install_path=None,
    emulator_id="azahar",
    code_count=2,
    enabled=True,
)


def test_role_default_is_steamzero_supplied_when_manifest_silent() -> None:
    assert resolve_provider_role({}, EnhancementKind.CHEAT) is ProviderRole.STEAMZERO_SUPPLIED
    assert resolve_provider_role(None, EnhancementKind.MOD) is ProviderRole.STEAMZERO_SUPPLIED


def test_role_emulator_supplied_when_declared_for_kind() -> None:
    manifest = {"enhancements": {"supplied": ["cheat"], "formats": ["yaml"]}}
    assert resolve_provider_role(manifest, EnhancementKind.CHEAT) is ProviderRole.EMULATOR_SUPPLIED
    assert resolve_provider_role(manifest, EnhancementKind.MOD) is ProviderRole.STEAMZERO_SUPPLIED


@pytest.mark.parametrize(
    ("category", "allowed"),
    [
        ("quality-of-life", True),
        ("display-only", True),
        ("performance", True),
        ("compatibility", True),
        ("graphics", True),
        ("audio", True),
        ("gameplay", False),
        ("unlock", False),
        ("speedhack", False),
        ("currency", False),
        ("misterious", False),
    ],
)
def test_policy_default_deny_except_technical_whitelist(category: str, allowed: bool) -> None:
    decision = policy_decision(
        EnhancementKind.MOD,
        category,
        role=ProviderRole.STEAMZERO_SUPPLIED,
        source="github",
    )
    assert decision.allowed is allowed
    if not allowed:
        assert decision.reason is not None


def test_policy_denies_without_provenance() -> None:
    decision = policy_decision(
        EnhancementKind.MOD,
        "graphics",
        role=ProviderRole.STEAMZERO_SUPPLIED,
        source=None,
    )
    assert decision == EnhancementDecision(False, "proveniência obrigatória ausente")
    assert decision.allowed is False


def test_policy_emulator_supplied_is_informative_only() -> None:
    decision = policy_decision(
        EnhancementKind.CHEAT,
        "gameplay",
        role=ProviderRole.EMULATOR_SUPPLIED,
        source="super-zsnes",
    )
    assert decision.allowed is True


def test_list_enhancements_unifies_mods_and_cheats_of_same_game() -> None:
    manager = _manager(
        mod_store=_FakeModStore(rows=[_MOD]),
        cheat_store=_FakeCheatStore(rows=[_CHEAT]),
    )
    rows = manager.list_enhancements(P1, emulator_id="azahar")
    assert [row.kind for row in rows] == [EnhancementKind.MOD, EnhancementKind.CHEAT]
    by_kind = {row.kind: row for row in rows}
    assert by_kind[EnhancementKind.MOD].category == "performance"
    assert by_kind[EnhancementKind.CHEAT].category == "gold"
    assert all(row.game_id == "0100ABCD12340001" for row in rows)
    assert all(row.role is ProviderRole.STEAMZERO_SUPPLIED for row in rows)


def test_list_enhancements_filters_by_emulator() -> None:
    other = InstalledMod(
        id="mod-2",
        game_id="0100ABCD12340001",
        catalog_id=None,
        title_id="0100ABCD12340001",
        build_id=None,
        name="shaders",
        mod_type=ModType.GRAPHICS,
        source="semd",
        version=None,
        state="inactive",
        install_path=None,
        emulator_id="yuzu",
    )
    manager = _manager(mod_store=_FakeModStore(rows=[_MOD, other]))
    names = [row.name for row in manager.list_enhancements(P1, emulator_id="azahar")]
    assert names == ["60fps"]


def test_list_enhancements_empty_for_unknown_game() -> None:
    manager = _manager(mod_store=_FakeModStore(rows=[_MOD]))
    other = GameIdentity.switch("0100EFEF0000FACE")
    assert manager.list_enhancements(other) == []


def test_candidates_mod_and_cheat_kinds() -> None:
    mod_candidate = _FakeModCatalog(
        by_title=[
            ModCandidate(
                title_id="0100ABCD12340001",
                build_id=None,
                identity=ModIdentity(
                    name="60fps",
                    mod_type="performance",
                    source="github",
                    source_url="https://example.invalid/mods/60fps",
                ),
            )
        ]
    )
    cheat_candidate = _FakeCheatCatalog(
        by_title=[
            CheatCandidate(
                title_id="0100ABCD12340001",
                build_id=None,
                identity=CheatIdentity(
                    name="Moedas infinitas",
                    cheat_type="gold",
                    source="nsecm",
                    source_url="https://example.invalid/cheats/gold",
                ),
            )
        ]
    )
    manager = _manager(mod_catalog=mod_candidate, cheat_catalog=cheat_candidate)
    mods = manager.list_candidates(P1, EnhancementKind.MOD)
    cheats = manager.list_candidates(P1, EnhancementKind.CHEAT)
    assert [c.category for c in mods] == ["performance"]
    assert [c.name for c in cheats] == ["Moedas infinitas"]
    assert mods[0].match_confidence == 1.0


def test_candidates_prefer_build_id_when_given() -> None:
    mod_candidate = _FakeModCatalog(
        by_build=[
            ModCandidate(
                title_id="0100ABCD12340001",
                build_id="ABCDEF0123456789",
                identity=ModIdentity(
                    name="fix-beta",
                    mod_type="patch",
                    source="github",
                    source_url="https://example.invalid/patch",
                ),
            )
        ]
    )
    manager = _manager(mod_catalog=mod_candidate)
    rows = manager.list_candidates(P1, EnhancementKind.MOD, build_id="ABCDEF0123456789")
    assert [c.identity for c in rows] == ["fix-beta"]


def test_assert_allowed_raises_on_gameplay_or_unknown() -> None:
    manager = _manager()
    with pytest.raises(SteamZeroError) as exc:
        manager.assert_allowed(
            EnhancementKind.CHEAT,
            "unlock",
            role=ProviderRole.STEAMZERO_SUPPLIED,
            source="nsecm",
        )
    assert exc.value.code == "E-ENHANCEMENT-DENIED"
    with pytest.raises(SteamZeroError):
        manager.assert_allowed(
            EnhancementKind.MOD,
            "graphics",
            role=ProviderRole.STEAMZERO_SUPPLIED,
            source=None,
        )


def test_assert_allowed_passes_technical_with_provenance() -> None:
    manager = _manager()
    manager.assert_allowed(
        EnhancementKind.MOD,
        "graphics",
        role=ProviderRole.STEAMZERO_SUPPLIED,
        source="github",
    )
