# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes do módulo de mods para emuladores Switch.

Cobre: modelos de domínio, SwitchModManager, adapters e migração.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from steamzero.adapters.mods.build_id_scanner import BuildIdScanner
from steamzero.adapters.mods.composite_catalog import CompositeModCatalog
from steamzero.adapters.mods.github_mod_source import GithubModSource
from steamzero.adapters.mods.mod_installer import (
    FilesystemModInstaller,
)
from steamzero.adapters.mods.state_store_mods import StateStoreModsAdapter
from steamzero.core.errors import SteamZeroError
from steamzero.core.migrations.m0008_switch_mods import up as m0008_up
from steamzero.domain.switch_mods import (
    GameBuildId,
    InstalledMod,
    ModDatabasePort,
    ModEntry,
    ModType,
    SwitchModManager,
)
from steamzero.ports import (
    BuildIdProviderPort,
    InstalledModView,
    ModCandidate,
    ModCatalogPort,
    ModIdentity,
    ModInstallerPort,
)

# =============================================================================
# Domain models
# =============================================================================


class TestModType:
    def test_performance_enum(self) -> None:
        assert ModType.PERFORMANCE.value == "performance"

    def test_from_valid_string(self) -> None:
        assert ModType("graphics") == ModType.GRAPHICS
        assert ModType("ultrawide") == ModType.ULTRAWIDE

    def test_from_invalid_string_falls_back_to_other(self) -> None:
        assert ModType("invalid_type").value == "other"

    def test_all_values_are_strings(self) -> None:
        for mt in ModType:
            assert isinstance(mt.value, str)


class TestModEntry:
    def test_minimal(self) -> None:
        entry = ModEntry(
            id="mod-1",
            title_id="0100000000010000",
            build_id=None,
            name="60 FPS Mod",
            mod_type=ModType.PERFORMANCE,
            source="github:stevensnd",
            source_url="https://github.com/StevensND/switch-port-mods",
            version="1.0",
            description="Unlocks 60 FPS",
            author="StevensND",
            requirements="prod keys",
        )
        assert entry.title_id == "0100000000010000"
        assert entry.mod_type == ModType.PERFORMANCE

    def test_defaults(self) -> None:
        entry = ModEntry(
            id="mod-2",
            title_id="0100000000020000",
            build_id=None,
            name="Some Mod",
            mod_type=ModType.OTHER,
            source="semdb",
            source_url="",
            version=None,
            description=None,
            author=None,
            requirements=None,
        )
        assert entry.version is None
        assert entry.author is None


class TestInstalledMod:
    def test_fields(self) -> None:
        mod = InstalledMod(
            id="inst-1",
            game_id="game-1",
            catalog_id="cat-1",
            title_id="0100000000010000",
            build_id="ABCDEF1234567890ABCDEF1234567890",
            name="60 FPS Mod",
            mod_type=ModType.PERFORMANCE,
            source="github:stevensnd",
            version="1.0",
            state="active",
            install_path="/some/path",
            emulator_id="eden",
        )
        assert mod.state == "active"
        assert mod.emulator_id == "eden"

    def test_no_optional_fields(self) -> None:
        mod = InstalledMod(
            id="inst-2",
            game_id="game-2",
            catalog_id=None,
            title_id="0100000000020000",
            build_id=None,
            name="Mod",
            mod_type=ModType.OTHER,
            source="local",
            version=None,
            state="installed",
            install_path=None,
            emulator_id=None,
        )
        assert mod.catalog_id is None
        assert mod.install_path is None


class TestGameBuildId:
    def test_creation(self) -> None:
        entry = GameBuildId(
            game_id="game-1",
            title_id="0100000000010000",
            build_id="ABCDEF1234567890ABCDEF1234567890",
            detected_from="rom",
            detected_at="2026-07-20T12:00:00",
        )
        assert entry.build_id == "ABCDEF1234567890ABCDEF1234567890"
        assert entry.detected_from == "rom"


# =============================================================================
# DTOs (ports)
# =============================================================================


class TestModIdentity:
    def test_frozen(self) -> None:
        ident = ModIdentity(name="test", mod_type="performance", source="test", source_url="")
        assert ident.name == "test"

    def test_with_all_fields(self) -> None:
        ident = ModIdentity(
            name="60 FPS",
            mod_type="performance",
            source="github:stevensnd",
            source_url="https://example.com",
            version="1.0",
            description="desc",
            author="author",
            requirements="keys",
        )
        assert ident.version == "1.0"
        assert ident.author == "author"


class TestModCandidate:
    def test_default_confidence(self) -> None:
        ident = ModIdentity(name="test", mod_type="performance", source="test", source_url="")
        cand = ModCandidate(title_id="0100", build_id=None, identity=ident)
        assert cand.match_confidence == 1.0

    def test_lower_confidence(self) -> None:
        ident = ModIdentity(name="test", mod_type="performance", source="test", source_url="")
        cand = ModCandidate(title_id="0100", build_id=None, identity=ident, match_confidence=0.5)
        assert cand.match_confidence == 0.5


class TestInstalledModView:
    def test_all_fields(self) -> None:
        view = InstalledModView(
            mod_id="m1",
            game_id="g1",
            title_id="0100",
            build_id="b1",
            name="Mod",
            mod_type="performance",
            state="active",
            emulator_id="eden",
            install_path="/path",
            source="test",
            version="1.0",
        )
        assert view.mod_id == "m1"
        assert view.state == "active"


# =============================================================================
# StateStoreModsAdapter (with real SQLite)
# =============================================================================


class TestStateStoreModsAdapter:
    @pytest.fixture
    def conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(":memory:")
        c.row_factory = sqlite3.Row
        m0008_up(c)
        c.execute("PRAGMA user_version=8")
        yield c
        c.close()

    def test_save_and_list_installed(self, conn: sqlite3.Connection, tmp_path: Path) -> None:
        adapter = StateStoreModsAdapter(conn)
        mod = InstalledMod(
            id="m1",
            game_id="g1",
            catalog_id="cat-1",
            title_id="0100000000010000",
            build_id="BID1",
            name="Test Mod",
            mod_type=ModType.PERFORMANCE,
            source="github:test",
            version="1.0",
            state="installed",
            install_path=str(tmp_path / "mod"),
            emulator_id="eden",
        )
        adapter.save_installed_mod(mod)
        lst = adapter.list_installed("g1")
        assert len(lst) == 1
        assert lst[0].id == "m1"
        assert lst[0].state == "installed"

    def test_remove_installed(self, conn: sqlite3.Connection) -> None:
        adapter = StateStoreModsAdapter(conn)
        mod = InstalledMod(
            id="m2",
            game_id="g1",
            catalog_id=None,
            title_id="0100000000010000",
            build_id=None,
            name="Remove Me",
            mod_type=ModType.OTHER,
            source="test",
            version=None,
            state="downloaded",
            install_path=None,
            emulator_id=None,
        )
        adapter.save_installed_mod(mod)
        assert adapter.remove_installed_mod("m2") is True
        assert adapter.remove_installed_mod("nonexistent") is False
        assert len(adapter.list_installed("g1")) == 0

    def test_update_state(self, conn: sqlite3.Connection, tmp_path: Path) -> None:
        adapter = StateStoreModsAdapter(conn)
        mod = InstalledMod(
            id="m3",
            game_id="g2",
            catalog_id=None,
            title_id="0100000000020000",
            build_id=None,
            name="Activate Me",
            mod_type=ModType.GRAPHICS,
            source="test",
            version=None,
            state="installed",
            install_path=str(tmp_path / "mod"),
            emulator_id="citron",
        )
        adapter.save_installed_mod(mod)
        adapter.update_state("m3", "active")
        retrieved = adapter.get_by_id("m3")
        assert retrieved is not None
        assert retrieved.state == "active"
        assert retrieved.emulator_id == "citron"

    def test_get_by_id_returns_none(self, conn: sqlite3.Connection) -> None:
        adapter = StateStoreModsAdapter(conn)
        assert adapter.get_by_id("nonexistent") is None

    def test_build_id_lifecycle(self, conn: sqlite3.Connection) -> None:
        adapter = StateStoreModsAdapter(conn)
        entry = GameBuildId(
            game_id="g1",
            title_id="0100000000010000",
            build_id="BID_123456789012345678901234567890",
            detected_from="rom",
            detected_at="2026-07-20T12:00:00",
        )
        adapter.save_build_id(entry)
        lst = adapter.list_build_ids("g1")
        assert len(lst) == 1
        assert lst[0].build_id == "BID_123456789012345678901234567890"

    def test_save_and_list_game_build_ids_filters_by_game(self, conn: sqlite3.Connection) -> None:
        adapter = StateStoreModsAdapter(conn)
        adapter.save_build_id(GameBuildId("g1", "0100", "BID1", "rom", "2026-07-20T12:00:00"))
        adapter.save_build_id(GameBuildId("g2", "0200", "BID2", "rom", "2026-07-20T12:00:00"))
        assert len(adapter.list_build_ids("g1")) == 1
        assert len(adapter.list_build_ids("g2")) == 1
        assert len(adapter.list_build_ids("g3")) == 0


# =============================================================================
# Migration v8
# =============================================================================


class TestMigrationV8:
    @pytest.fixture
    def conn(self) -> sqlite3.Connection:
        value = sqlite3.connect(":memory:")
        value.row_factory = sqlite3.Row
        yield value
        value.close()

    def test_creates_expected_tables(self, conn: sqlite3.Connection) -> None:
        m0008_up(conn)
        tables = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        for expected in ("switch_mod", "switch_mod_catalog", "switch_game_build_id"):
            assert expected in tables

    def test_creates_indexes(self, conn: sqlite3.Connection) -> None:
        m0008_up(conn)
        idxs = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        }
        for expected in (
            "idx_switch_mod_game",
            "idx_switch_mod_state",
            "idx_catalog_title_id",
            "idx_catalog_source",
            "idx_build_id_title",
        ):
            assert expected in idxs

    def test_switch_mod_constraints(self, conn: sqlite3.Connection) -> None:
        m0008_up(conn)
        conn.execute(
            "INSERT INTO switch_mod (id,game_id,title_id,name,mod_type,source,state,installed_at) "
            "VALUES ('m1','g1','0100','Mod','performance','test','active','2026-01-01')"
        )
        row = conn.execute("SELECT * FROM switch_mod WHERE id='m1'").fetchone()
        assert row["mod_type"] == "performance"

    def test_switch_mod_state_check(self, conn: sqlite3.Connection) -> None:
        m0008_up(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO switch_mod (id,game_id,title_id,name,mod_type,"
                "source,state,installed_at) "
                "VALUES ('m1','g1','0100','Mod','performance','test','invalid_state','2026-01-01')"
            )

    def test_switch_mod_type_check(self, conn: sqlite3.Connection) -> None:
        m0008_up(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO switch_mod (id,game_id,title_id,name,mod_type,"
                "source,state,installed_at) "
                "VALUES ('m1','g1','0100','Mod','invalid_type','test','installed','2026-01-01')"
            )

    def test_idempotent(self, conn: sqlite3.Connection) -> None:
        m0008_up(conn)
        m0008_up(conn)  # segunda execução não deve falhar
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "switch_mod" in tables

    def test_catalog_table(self, conn: sqlite3.Connection) -> None:
        m0008_up(conn)
        conn.execute(
            "INSERT INTO switch_mod_catalog (id,title_id,name,mod_type,source,"
            "source_url,added_at,refreshed_at) VALUES "
            "('c1','0100','60FPS','performance','stevensnd',"
            "'https://example.com','2026-01-01','2026-01-01')"
        )
        row = conn.execute("SELECT * FROM switch_mod_catalog WHERE id='c1'").fetchone()
        assert row["name"] == "60FPS"
        assert row["source"] == "stevensnd"


# =============================================================================
# Migration registration test
# =============================================================================


class TestMigrationRegistration:
    def test_m0008_is_registered(self) -> None:
        from steamzero.core.migrations import MIGRATIONS

        versions = [v for v, _ in MIGRATIONS]
        assert 8 in versions

    def test_latest_is_8(self) -> None:
        from steamzero.core.migrations import LATEST

        assert LATEST >= 8


# =============================================================================
# SwitchModManager
# =============================================================================


class _FakeModCatalog(ModCatalogPort):
    def __init__(self, candidates: list[ModCandidate] | None = None) -> None:
        self._candidates = candidates or []
        self.refresh_count = 0

    def search_by_title_id(self, title_id: str) -> list[ModCandidate]:
        return [c for c in self._candidates if c.title_id == title_id]

    def search_by_build_id(self, title_id: str, build_id: str) -> list[ModCandidate]:
        return [c for c in self._candidates if c.title_id == title_id and c.build_id == build_id]

    def refresh_catalog(self) -> int:
        self.refresh_count += 1
        return len(self._candidates)


class _FakeModInstaller(ModInstallerPort):
    def __init__(self) -> None:
        self.installed: list[tuple[str, str, str]] = []
        self.removed: list[str] = []
        self.activated: list[str] = []
        self.deactivated: list[str] = []

    def install(
        self,
        candidate: ModIdentity,
        game_title_id: str,
        emulator_id: str,
        files: list[tuple[str, bytes]],
    ) -> Path:
        self.installed.append((candidate.name, game_title_id, emulator_id))
        return Path("/fake/mods") / game_title_id / candidate.name

    def remove(self, install_path: Path) -> bool:
        self.removed.append(str(install_path))
        return True

    def activate(self, install_path: Path) -> bool:
        self.activated.append(str(install_path))
        return True

    def deactivate(self, install_path: Path) -> bool:
        self.deactivated.append(str(install_path))
        return True

    def list_installed_mods(self, title_id: str, emulator_id: str) -> list[InstalledModView]:
        return []


class _FakeBuildIdProvider(BuildIdProviderPort):
    def __init__(self, build_ids: dict[str, list[str]] | None = None) -> None:
        self._build_ids = build_ids or {}
        self.scanned: list[str] = []

    def scan_game(self, game_id: str) -> list[str]:
        self.scanned.append(game_id)
        return self._build_ids.get(game_id, [])

    def scan_rom_file(self, rom_path: Path) -> list[str]:
        return []


class _FakeModDb(ModDatabasePort):
    def __init__(self) -> None:
        self._mods: dict[str, InstalledMod] = {}
        self._build_ids: dict[str, list[GameBuildId]] = {}

    def save_installed_mod(self, mod: InstalledMod) -> None:
        self._mods[mod.id] = mod

    def remove_installed_mod(self, mod_id: str) -> bool:
        return self._mods.pop(mod_id, None) is not None

    def list_installed(self, game_id: str) -> list[InstalledMod]:
        return [m for m in self._mods.values() if m.game_id == game_id]

    def update_state(self, mod_id: str, new_state: str) -> None:
        if mod_id in self._mods:
            old = self._mods[mod_id]
            self._mods[mod_id] = InstalledMod(
                id=old.id,
                game_id=old.game_id,
                catalog_id=old.catalog_id,
                title_id=old.title_id,
                build_id=old.build_id,
                name=old.name,
                mod_type=old.mod_type,
                source=old.source,
                version=old.version,
                state=new_state,
                install_path=old.install_path,
                emulator_id=old.emulator_id,
            )

    def get_by_id(self, mod_id: str) -> InstalledMod | None:
        return self._mods.get(mod_id)

    def save_build_id(self, entry: GameBuildId) -> None:
        self._build_ids.setdefault(entry.game_id, []).append(entry)

    def list_build_ids(self, game_id: str) -> list[GameBuildId]:
        return self._build_ids.get(game_id, [])


class TestSwitchModManager:
    @pytest.fixture
    def manager(self, monkeypatch: pytest.MonkeyPatch) -> SwitchModManager:
        ident = ModIdentity(
            name="60 FPS",
            mod_type="performance",
            source="github:test",
            source_url="https://example.com/mod.zip",
        )
        candidates = [
            ModCandidate(
                title_id="0100000000010000",
                build_id=None,
                identity=ident,
            ),
            ModCandidate(
                title_id="0100000000010000",
                build_id="BID_MATCH",
                identity=ident,
            ),
        ]
        catalog = _FakeModCatalog(candidates)
        installer = _FakeModInstaller()
        bid_provider = _FakeBuildIdProvider({"g1": ["BID1", "BID2"]})
        db = _FakeModDb()

        def fake_fetch(self_obj: object, candidate: object) -> list[tuple[str, bytes]]:
            return [("mod.zip", b"fake")]

        monkeypatch.setattr(
            SwitchModManager,
            "_fetch_candidate_files",
            fake_fetch,
        )
        return SwitchModManager(catalog, installer, bid_provider, db)

    def test_list_candidates_by_title_id_only(self, manager: SwitchModManager) -> None:
        candidates = manager.list_candidates("0100000000010000")
        assert len(candidates) == 2

    def test_list_candidates_by_build_id(self, manager: SwitchModManager) -> None:
        candidates = manager.list_candidates("0100000000010000", build_id="BID_MATCH")
        assert len(candidates) == 1

    def test_list_candidates_no_match(self, manager: SwitchModManager) -> None:
        candidates = manager.list_candidates("0100000000999999")
        assert len(candidates) == 0

    def test_refresh_catalog(self, manager: SwitchModManager) -> None:
        n = manager.refresh_catalog()
        assert n == 2
        assert manager._catalog.refresh_count >= 1  # type: ignore

    def test_scan_games_for_build_ids(self, manager: SwitchModManager) -> None:
        result = manager.scan_games_for_build_ids(["g1"])
        assert "g1" in result
        assert result["g1"] == ["BID1", "BID2"]

    def test_download_and_install(self, manager: SwitchModManager) -> None:
        candidates = manager.list_candidates("0100000000010000")
        assert len(candidates) >= 1
        mod = manager.download_and_install(candidates[0], "eden", "g1")
        assert mod.state == "installed"
        assert mod.emulator_id == "eden"
        installed = manager.list_installed("g1")
        assert len(installed) == 1

    def test_activate_and_deactivate(self, manager: SwitchModManager) -> None:
        candidate = manager.list_candidates("0100000000010000")[0]
        mod = manager.download_and_install(candidate, "eden", "g1")
        assert manager.activate(mod.id) is True
        db_mod = manager._db.get_by_id(mod.id)
        assert db_mod is not None and db_mod.state == "active"

        assert manager.deactivate(mod.id) is True
        db_mod = manager._db.get_by_id(mod.id)
        assert db_mod is not None and db_mod.state == "inactive"

    def test_activate_nonexistent(self, manager: SwitchModManager) -> None:
        assert manager.activate("nonexistent") is False

    def test_remove(self, manager: SwitchModManager) -> None:
        candidate = manager.list_candidates("0100000000010000")[0]
        mod = manager.download_and_install(candidate, "eden", "g1")
        assert manager.remove(mod.id) is True
        assert manager._db.get_by_id(mod.id) is None

    def test_remove_nonexistent(self, manager: SwitchModManager) -> None:
        assert manager.remove("nonexistent") is False

    def test_list_installed(self, manager: SwitchModManager) -> None:
        assert manager.list_installed("g1") == []
        candidate = manager.list_candidates("0100000000010000")[0]
        manager.download_and_install(candidate, "eden", "g1")
        assert len(manager.list_installed("g1")) == 1
        assert len(manager.list_installed("g2")) == 0

    def test_to_dict(self, manager: SwitchModManager) -> None:
        candidate = manager.list_candidates("0100000000010000")[0]
        mod = manager.download_and_install(candidate, "eden", "g1")
        d = manager.to_dict(mod)
        assert d["gameId"] == "g1"
        assert d["state"] == "installed"
        assert d["emulatorId"] == "eden"

    def test_from_dict(self, manager: SwitchModManager) -> None:
        data = {
            "id": "m1",
            "gameId": "g1",
            "catalogId": None,
            "titleId": "0100",
            "buildId": None,
            "name": "Mod",
            "modType": "performance",
            "source": "test",
            "version": None,
            "state": "active",
            "installPath": "/path",
            "emulatorId": "eden",
        }
        mod = SwitchModManager.from_dict(data)
        assert mod.id == "m1"
        assert mod.mod_type == ModType.PERFORMANCE


# =============================================================================
# FilesystemModInstaller
# =============================================================================


class TestFilesystemModInstaller:
    @pytest.fixture
    def installer(self, tmp_path: Path) -> FilesystemModInstaller:
        return FilesystemModInstaller(tmp_path)

    def test_install_creates_directory(
        self, installer: FilesystemModInstaller, tmp_path: Path
    ) -> None:
        ident = ModIdentity(
            name="Test Mod",
            mod_type="performance",
            source="test",
            source_url="",
        )
        path = installer.install(ident, "0100000000010000", "eden", [("file.txt", b"content")])
        assert path.exists()
        assert (path / "file.txt").read_bytes() == b"content"

    def test_install_unknown_emulator_raises(self, installer: FilesystemModInstaller) -> None:
        ident = ModIdentity(name="Test", mod_type="performance", source="test", source_url="")
        with pytest.raises(SteamZeroError, match="E-MOD-EMULATOR-NOT-FOUND"):
            installer.install(ident, "0100", "nonexistent", [])

    def test_remove_existing(self, installer: FilesystemModInstaller) -> None:
        ident = ModIdentity(
            name="Remove Me",
            mod_type="performance",
            source="test",
            source_url="",
        )
        path = installer.install(ident, "0100", "eden", [("f.txt", b"d")])
        assert installer.remove(path) is True
        assert not path.exists()

    def test_remove_nonexistent(self, installer: FilesystemModInstaller) -> None:
        assert installer.remove(Path("/nonexistent/mod")) is False

    def test_activate_creates_symlink(
        self, installer: FilesystemModInstaller, tmp_path: Path
    ) -> None:
        ident = ModIdentity(
            name="Activate Mod",
            mod_type="performance",
            source="test",
            source_url="",
        )
        path = installer.install(ident, "0100000000010000", "eden", [])
        assert installer.activate(path) is True
        active_link = path.parent / f"{path.name}.active"
        assert active_link.is_symlink()

    def test_deactivate_removes_symlink(
        self, installer: FilesystemModInstaller, tmp_path: Path
    ) -> None:
        ident = ModIdentity(
            name="Deactivate Mod",
            mod_type="performance",
            source="test",
            source_url="",
        )
        path = installer.install(ident, "0100000000010000", "eden", [])
        installer.activate(path)
        assert installer.deactivate(path) is True
        active_link = path.parent / f"{path.name}.active"
        assert not active_link.exists()

    def test_list_installed_mods(self, installer: FilesystemModInstaller, tmp_path: Path) -> None:
        ident1 = ModIdentity(
            name="Mod A",
            mod_type="performance",
            source="test",
            source_url="",
        )
        ident2 = ModIdentity(
            name="Mod B",
            mod_type="graphics",
            source="test",
            source_url="",
        )
        installer.install(ident1, "0100000000010000", "eden", [])
        path2 = installer.install(ident2, "0100000000010000", "eden", [])
        installer.activate(path2)

        views = installer.list_installed_mods("0100000000010000", "eden")
        assert len(views) == 2
        by_name = {v.name: v for v in views}
        assert by_name["Mod A"].state == "installed"
        assert by_name["Mod B"].state == "active"

    def test_list_installed_mods_no_game(self, installer: FilesystemModInstaller) -> None:
        assert installer.list_installed_mods("0100000000999999", "eden") == []


# =============================================================================
# CompositeModCatalog
# =============================================================================


class TestCompositeModCatalog:
    def test_aggregates_from_multiple_sources(self) -> None:
        ident_a = ModIdentity(name="A", mod_type="performance", source="src1", source_url="")
        ident_b = ModIdentity(name="B", mod_type="graphics", source="src2", source_url="")
        source1 = _FakeModCatalog([ModCandidate(title_id="0100", build_id=None, identity=ident_a)])
        source2 = _FakeModCatalog([ModCandidate(title_id="0100", build_id=None, identity=ident_b)])
        composite = CompositeModCatalog([source1, source2])
        results = composite.search_by_title_id("0100")
        assert len(results) == 2

    def test_deduplicates(self) -> None:
        ident = ModIdentity(name="Same", mod_type="performance", source="src1", source_url="")
        source1 = _FakeModCatalog([ModCandidate(title_id="0100", build_id=None, identity=ident)])
        source2 = _FakeModCatalog([ModCandidate(title_id="0100", build_id=None, identity=ident)])
        composite = CompositeModCatalog([source1, source2])
        results = composite.search_by_title_id("0100")
        assert len(results) == 1

    def test_empty_when_no_sources_match(self) -> None:
        ident = ModIdentity(name="A", mod_type="performance", source="src1", source_url="")
        source = _FakeModCatalog([ModCandidate(title_id="0100", build_id=None, identity=ident)])
        composite = CompositeModCatalog([source])
        assert composite.search_by_title_id("0200") == []

    def test_no_sources(self) -> None:
        composite = CompositeModCatalog([])
        assert composite.search_by_title_id("0100") == []

    def test_search_by_build_id(self) -> None:
        ident_a = ModIdentity(name="A", mod_type="performance", source="src1", source_url="")
        ident_b = ModIdentity(name="B", mod_type="graphics", source="src2", source_url="")
        source1 = _FakeModCatalog(
            [
                ModCandidate(title_id="0100", build_id="BID_A", identity=ident_a),
                ModCandidate(title_id="0100", build_id="BID_B", identity=ident_b),
            ]
        )
        composite = CompositeModCatalog([source1])
        results = composite.search_by_build_id("0100", "BID_A")
        assert len(results) == 1
        assert results[0].identity.name == "A"

    def test_refresh_catalog(self) -> None:
        s1 = _FakeModCatalog(
            [
                ModCandidate(
                    title_id="0100",
                    build_id=None,
                    identity=ModIdentity(name="A", mod_type="p", source="s1", source_url=""),
                )
            ]
        )
        s2 = _FakeModCatalog(
            [
                ModCandidate(
                    title_id="0100",
                    build_id=None,
                    identity=ModIdentity(name="B", mod_type="p", source="s2", source_url=""),
                )
            ]
        )
        composite = CompositeModCatalog([s1, s2])
        assert composite.refresh_catalog() == 2
        assert s1.refresh_count == 1
        assert s2.refresh_count == 1


# =============================================================================
# GithubModSource
# =============================================================================


class TestGithubModSource:
    def test_guess_mod_type_ultrawide(self) -> None:
        from steamzero.adapters.mods.github_mod_source import _guess_mod_type

        assert _guess_mod_type("Ultrawide 21-9 Mod") == "ultrawide"
        assert _guess_mod_type("Ultrawide 32-9 Support") == "ultrawide"

    def test_guess_mod_type_performance(self) -> None:
        from steamzero.adapters.mods.github_mod_source import _guess_mod_type

        assert _guess_mod_type("60FPS Mod") == "performance"
        assert _guess_mod_type("Performance Boost") == "performance"

    def test_guess_mod_type_graphics(self) -> None:
        from steamzero.adapters.mods.github_mod_source import _guess_mod_type

        assert _guess_mod_type("Graphics Enhancement") == "graphics"
        assert _guess_mod_type("1080p Resolution") == "graphics"

    def test_guess_mod_type_fallback(self) -> None:
        from steamzero.adapters.mods.github_mod_source import _guess_mod_type

        assert _guess_mod_type("Some Random Mod") == "other"

    def test_empty_source_returns_no_candidates(self) -> None:
        source = GithubModSource(sources={})
        assert source.search_by_title_id("0100") == []


# =============================================================================
# SemdSource
# =============================================================================


class TestSemdSource:
    def test_guess_mod_type(self) -> None:
        from steamzero.adapters.mods.semd_source import _guess_mod_type_semd

        assert _guess_mod_type_semd("60fps") == "performance"
        assert _guess_mod_type_semd("visual") == "graphics"
        assert _guess_mod_type_semd("21by9") == "ultrawide"
        assert _guess_mod_type_semd("qol") == "gameplay"
        assert _guess_mod_type_semd("fix") == "patch"
        assert _guess_mod_type_semd("misc") == "other"


# =============================================================================
# BuildIdScanner
# =============================================================================


class TestBuildIdScanner:
    def test_scan_rom_file_nonexistent(self, tmp_path: Path) -> None:
        scanner = BuildIdScanner()
        assert scanner.scan_rom_file(tmp_path / "nonexistent.nsp") == []

    def test_scan_rom_file_wrong_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "game.txt"
        f.write_text("hello")
        scanner = BuildIdScanner()
        assert scanner.scan_rom_file(f) == []

    def test_scan_rom_file_finds_build_id(self, tmp_path: Path) -> None:
        bid = "ABCDEF0123456789ABCDEF0123456789"
        content = b"\x00" * 512 + bid.encode() + b"\x00" * 512
        f = tmp_path / "game.nsp"
        f.write_bytes(content)
        scanner = BuildIdScanner()
        result = scanner.scan_rom_file(f)
        assert bid.lower()[:32] in result

    def test_title_id_from_name(self) -> None:
        from steamzero.adapters.mods.build_id_scanner import _title_id_from_name

        assert _title_id_from_name("0100000000010000.nsp") == "0100000000010000"
        assert _title_id_from_name("game.nsp") == "game"
