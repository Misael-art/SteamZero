# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes do módulo de cheats para emuladores Switch.

Cobre: modelos de domínio, SwitchCheatManager, adapters e migração.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from steamzero.adapters.cheats.cheat_installer import FsCheatInstaller
from steamzero.adapters.cheats.nsecm_source import (
    _guess_cheat_type,
    _parse_cheat_text,
)
from steamzero.adapters.cheats.state_store_cheats import StateStoreCheatsAdapter
from steamzero.core.errors import SteamZeroError
from steamzero.core.migrations.m0009_switch_cheats import up as m0009_up
from steamzero.domain.switch_cheats import (
    CheatDatabasePort,
    CheatEntry,
    CheatType,
    InstalledCheat,
    SwitchCheatManager,
    validate_cheat_codes,
)
from steamzero.ports import (
    CheatCandidate,
    CheatCatalogPort,
    CheatIdentity,
    CheatInstallerPort,
    InstalledCheatView,
)

# =============================================================================
# Domain models
# =============================================================================


class TestCheatType:
    def test_values(self) -> None:
        assert CheatType.GOLD.value == "gold"
        assert CheatType.INFINITE.value == "infinite"
        assert CheatType.SPEED.value == "speed"

    def test_from_string(self) -> None:
        assert CheatType("gold") == CheatType.GOLD
        assert CheatType("items") == CheatType.ITEMS

    def test_invalid_falls_back(self) -> None:
        assert CheatType("invalid").value == "other"


class TestCheatEntry:
    def test_minimal(self) -> None:
        entry = CheatEntry(
            id="c1",
            title_id="0100000000010000",
            build_id="BID1",
            name="Infinite Health",
            cheat_type=CheatType.INFINITE,
            source="nsecm:tomad",
            source_url="https://example.com",
            codes=("580F0000 00000000", "780F0000 00000001"),
            description="Infinite health cheat",
            author="tomad",
            version="1.0",
        )
        assert entry.title_id == "0100000000010000"
        assert len(entry.codes) == 2

    def test_no_optional_fields(self) -> None:
        entry = CheatEntry(
            id="c2",
            title_id="0100000000020000",
            build_id=None,
            name="Cheat",
            cheat_type=CheatType.OTHER,
            source="local",
            source_url="",
            codes=(),
            description=None,
            author=None,
            version=None,
        )
        assert entry.build_id is None
        assert entry.codes == ()


class TestInstalledCheat:
    def test_fields(self) -> None:
        cheat = InstalledCheat(
            id="ic1",
            game_id="g1",
            title_id="0100000000010000",
            build_id="BID1",
            name="Max Gold",
            cheat_type=CheatType.GOLD,
            source="nsecm:tomad",
            version="1.0",
            state="active",
            install_path="/path/cheats/BID1.txt",
            emulator_id="eden",
            code_count=1,
            enabled=True,
            codes=("580F0000 00000000",),
        )
        assert cheat.state == "active"
        assert cheat.enabled is True
        assert cheat.code_count == 1

    def test_disabled(self) -> None:
        cheat = InstalledCheat(
            id="ic2",
            game_id="g2",
            title_id="0100000000020000",
            build_id="BID2",
            name="Speed",
            cheat_type=CheatType.SPEED,
            source="local",
            version=None,
            state="inactive",
            install_path=None,
            emulator_id=None,
            code_count=0,
            enabled=False,
        )
        assert cheat.enabled is False
        assert cheat.install_path is None


# =============================================================================
# Validation
# =============================================================================


class TestValidateCheatCodes:
    def test_valid_atmosphere_codes(self) -> None:
        codes = ("580F0000 00000000", "780F0000 00000001", "04010000 00000000")
        assert validate_cheat_codes(codes) is True

    def test_invalid_format(self) -> None:
        codes = ("invalid", "also bad")
        assert validate_cheat_codes(codes) is False

    def test_mixed_valid_and_invalid(self) -> None:
        codes = ("580F0000 00000000", "badcode")
        assert validate_cheat_codes(codes) is False

    def test_empty_is_valid(self) -> None:
        assert validate_cheat_codes(()) is True

    def test_comment_lines_are_ignored(self) -> None:
        codes = ("// Infinite Health by tomad", "580F0000 00000000")
        assert validate_cheat_codes(codes) is True


# =============================================================================
# Cheat catalog parsing
# =============================================================================


class TestParseCheatText:
    def test_parses_codes_and_name(self) -> None:
        text = "// Infinite Health\n580F0000 00000000\n780F0000 00000001\n"
        codes, name, _build_id = _parse_cheat_text(text)
        assert name == "Infinite Health"
        assert len(codes) == 2

    def test_parses_build_id_from_comment(self) -> None:
        text = "// BuildID: ABCDEF0123456789ABCDEF0123456789\n580F0000 00000000\n"
        _codes, _name, build_id = _parse_cheat_text(text)
        assert build_id == "ABCDEF0123456789ABCDEF0123456789"

    def test_empty_text(self) -> None:
        codes, _name, build_id = _parse_cheat_text("")
        assert codes == ()
        assert build_id is None

    def test_no_codes_returns_empty(self) -> None:
        codes, _name, _bid = _parse_cheat_text("// just a comment\n")
        assert codes == ()


class TestGuessCheatType:
    def test_gold(self) -> None:
        assert _guess_cheat_type("Max Gold") == "gold"
        assert _guess_cheat_type("Infinite Money") == "gold"
        assert _guess_cheat_type("999 Rupees") == "gold"

    def test_infinite(self) -> None:
        assert _guess_cheat_type("Infinite Health") == "infinite"
        assert _guess_cheat_type("Moon Jump") == "infinite"
        assert _guess_cheat_type("Inf HP") == "infinite"

    def test_speed(self) -> None:
        assert _guess_cheat_type("Speed Hack") == "speed"
        assert _guess_cheat_type("Move Speed") == "speed"

    def test_items(self) -> None:
        assert _guess_cheat_type("All Items") == "items"
        assert _guess_cheat_type("Max Inventory") == "items"
        assert _guess_cheat_type("Materials x999") == "items"

    def test_unlock(self) -> None:
        assert _guess_cheat_type("Unlock All") == "unlock"

    def test_stats(self) -> None:
        assert _guess_cheat_type("Max Stats") == "stats"
        assert _guess_cheat_type("999 EXP") == "stats"
        assert _guess_cheat_type("Max Level") == "stats"

    def test_fallback(self) -> None:
        assert _guess_cheat_type("Random Mod") == "other"


# =============================================================================
# StateStoreCheatsAdapter
# =============================================================================


class TestStateStoreCheatsAdapter:
    @pytest.fixture
    def conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(":memory:")
        c.row_factory = sqlite3.Row
        m0009_up(c)
        c.execute("PRAGMA user_version=9")
        yield c
        c.close()

    def test_save_and_list(self, conn: sqlite3.Connection) -> None:
        adapter = StateStoreCheatsAdapter(conn)
        cheat = InstalledCheat(
            id="c1",
            game_id="g1",
            title_id="0100000000010000",
            build_id="BID1",
            name="Infinite Health",
            cheat_type=CheatType.INFINITE,
            source="nsecm:tomad",
            version="1.0",
            state="installed",
            install_path="/cheats/BID1.txt",
            emulator_id="eden",
            code_count=2,
            enabled=False,
        )
        adapter.save_installed_cheat(cheat)
        lst = adapter.list_installed("g1")
        assert len(lst) == 1
        assert lst[0].id == "c1"
        assert lst[0].enabled is False

    def test_remove(self, conn: sqlite3.Connection) -> None:
        adapter = StateStoreCheatsAdapter(conn)
        cheat = InstalledCheat(
            id="c2",
            game_id="g1",
            title_id="0100000000010000",
            build_id="BID1",
            name="Remove Me",
            cheat_type=CheatType.OTHER,
            source="test",
            version=None,
            state="downloaded",
            install_path=None,
            emulator_id=None,
            code_count=0,
            enabled=False,
        )
        adapter.save_installed_cheat(cheat)
        assert adapter.remove_installed_cheat("c2") is True
        assert len(adapter.list_installed("g1")) == 0

    def test_update_state_and_enabled(self, conn: sqlite3.Connection) -> None:
        adapter = StateStoreCheatsAdapter(conn)
        cheat = InstalledCheat(
            id="c3",
            game_id="g2",
            title_id="0100000000020000",
            build_id="BID2",
            name="Gold",
            cheat_type=CheatType.GOLD,
            source="test",
            version=None,
            state="installed",
            install_path="/cheats/BID2.txt",
            emulator_id="citron",
            code_count=1,
            enabled=False,
        )
        adapter.save_installed_cheat(cheat)
        adapter.update_state("c3", "active")
        adapter.update_enabled("c3", True)
        retrieved = adapter.get_by_id("c3")
        assert retrieved is not None
        assert retrieved.state == "active"
        assert retrieved.enabled is True

    def test_get_by_id_none(self, conn: sqlite3.Connection) -> None:
        adapter = StateStoreCheatsAdapter(conn)
        assert adapter.get_by_id("nonexistent") is None


# =============================================================================
# Migration v9
# =============================================================================


class TestMigrationV9:
    @pytest.fixture
    def conn(self) -> sqlite3.Connection:
        value = sqlite3.connect(":memory:")
        value.row_factory = sqlite3.Row
        yield value
        value.close()

    def test_creates_expected_tables(self, conn: sqlite3.Connection) -> None:
        m0009_up(conn)
        tables = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        for expected in ("switch_cheat", "switch_cheat_catalog"):
            assert expected in tables

    def test_creates_indexes(self, conn: sqlite3.Connection) -> None:
        m0009_up(conn)
        idxs = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        }
        for expected in (
            "idx_switch_cheat_game",
            "idx_switch_cheat_title",
            "idx_cheat_catalog_title",
            "idx_cheat_catalog_source",
        ):
            assert expected in idxs

    def test_switch_cheat_constraints(self, conn: sqlite3.Connection) -> None:
        m0009_up(conn)
        conn.execute(
            "INSERT INTO switch_cheat (id,game_id,title_id,name,cheat_type,"
            "source,state,installed_at) "
            "VALUES ('c1','g1','0100','Gold','gold','test','active','2026-01-01')"
        )
        row = conn.execute("SELECT cheat_type FROM switch_cheat WHERE id='c1'").fetchone()
        assert row[0] == "gold"

    def test_invalid_cheat_type_rejected(self, conn: sqlite3.Connection) -> None:
        m0009_up(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO switch_cheat (id,game_id,title_id,name,cheat_type,"
                "source,state,installed_at) "
                "VALUES ('c1','g1','0100','Cheat','invalid','test','installed','2026-01-01')"
            )

    def test_idempotent(self, conn: sqlite3.Connection) -> None:
        m0009_up(conn)
        m0009_up(conn)
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "switch_cheat" in tables

    def test_enabled_defaults_to_false(self, conn: sqlite3.Connection) -> None:
        m0009_up(conn)
        conn.execute(
            "INSERT INTO switch_cheat (id,game_id,title_id,name,cheat_type,"
            "source,state,installed_at) "
            "VALUES ('c1','g1','0100','Cheat','gold','test','installed','2026-01-01')"
        )
        row = conn.execute("SELECT enabled FROM switch_cheat WHERE id='c1'").fetchone()
        assert row["enabled"] == 0


class TestMigrationRegistration:
    def test_m0009_is_registered(self) -> None:
        from steamzero.core.migrations import MIGRATIONS

        versions = [v for v, _ in MIGRATIONS]
        assert 9 in versions

    def test_latest_is_9(self) -> None:
        from steamzero.core.migrations import LATEST

        assert LATEST >= 9


# =============================================================================
# SwitchCheatManager
# =============================================================================


class _FakeCheatCatalog(CheatCatalogPort):
    def __init__(self, candidates: list[CheatCandidate] | None = None) -> None:
        self._candidates = candidates or []
        self.refresh_count = 0

    def search_by_title_id(self, title_id: str) -> list[CheatCandidate]:
        return [c for c in self._candidates if c.title_id == title_id]

    def search_by_build_id(self, title_id: str, build_id: str) -> list[CheatCandidate]:
        return [c for c in self._candidates if c.title_id == title_id and c.build_id == build_id]

    def refresh_catalog(self) -> int:
        self.refresh_count += 1
        return len(self._candidates)


class _FakeCheatInstaller(CheatInstallerPort):
    def __init__(self) -> None:
        self.installed: list[tuple[str, str, str]] = []
        self.removed: list[str] = []
        self.enabled_list: list[str] = []
        self.disabled_list: list[str] = []
        self.edited: list[str] = []

    def install(
        self,
        title_id: str,
        build_id: str | None,
        name: str,
        codes: tuple[str, ...],
        emulator_id: str,
    ) -> Path:
        bid = build_id or "default"
        self.installed.append((title_id, bid, emulator_id))
        return Path(f"/cheats/{title_id}/{bid}.txt")

    def remove(self, title_id: str, build_id: str, emulator_id: str) -> bool:
        self.removed.append(f"{title_id}/{build_id}")
        return True

    def enable(self, title_id: str, build_id: str, emulator_id: str) -> bool:
        self.enabled_list.append(f"{title_id}/{build_id}")
        return True

    def disable(self, title_id: str, build_id: str, emulator_id: str) -> bool:
        self.disabled_list.append(f"{title_id}/{build_id}")
        return True

    def list_installed(self, title_id: str, emulator_id: str) -> list[InstalledCheatView]:
        return []

    def edit_codes(
        self,
        title_id: str,
        build_id: str,
        emulator_id: str,
        codes: tuple[str, ...],
    ) -> bool:
        self.edited.append(f"{title_id}/{build_id}")
        return True


class _FakeCheatDb(CheatDatabasePort):
    def __init__(self) -> None:
        self._cheats: dict[str, InstalledCheat] = {}

    def save_installed_cheat(self, cheat: InstalledCheat) -> None:
        self._cheats[cheat.id] = cheat

    def remove_installed_cheat(self, cheat_id: str) -> bool:
        return self._cheats.pop(cheat_id, None) is not None

    def list_installed(self, game_id: str) -> list[InstalledCheat]:
        return [c for c in self._cheats.values() if c.game_id == game_id]

    def update_state(self, cheat_id: str, new_state: str) -> None:
        if cheat_id in self._cheats:
            old = self._cheats[cheat_id]
            self._cheats[cheat_id] = InstalledCheat(
                id=old.id,
                game_id=old.game_id,
                title_id=old.title_id,
                build_id=old.build_id,
                name=old.name,
                cheat_type=old.cheat_type,
                source=old.source,
                version=old.version,
                state=new_state,
                install_path=old.install_path,
                emulator_id=old.emulator_id,
                code_count=old.code_count,
                enabled=old.enabled,
                codes=old.codes,
            )

    def update_enabled(self, cheat_id: str, enabled: bool) -> None:
        if cheat_id in self._cheats:
            old = self._cheats[cheat_id]
            self._cheats[cheat_id] = InstalledCheat(
                id=old.id,
                game_id=old.game_id,
                title_id=old.title_id,
                build_id=old.build_id,
                name=old.name,
                cheat_type=old.cheat_type,
                source=old.source,
                version=old.version,
                state=old.state,
                install_path=old.install_path,
                emulator_id=old.emulator_id,
                code_count=old.code_count,
                enabled=enabled,
                codes=old.codes,
            )

    def get_by_id(self, cheat_id: str) -> InstalledCheat | None:
        return self._cheats.get(cheat_id)


class TestSwitchCheatManager:
    @pytest.fixture
    def manager(self) -> SwitchCheatManager:
        ident = CheatIdentity(
            name="Infinite Health",
            cheat_type="infinite",
            source="nsecm:tomad",
            source_url="https://example.com",
        )
        candidates = [
            CheatCandidate(
                title_id="0100000000010000",
                build_id=None,
                identity=ident,
                codes=("580F0000 00000000", "780F0000 00000001"),
            ),
            CheatCandidate(
                title_id="0100000000010000",
                build_id="BID_MATCH",
                identity=ident,
                codes=("580F0000 11111111",),
            ),
        ]
        catalog = _FakeCheatCatalog(candidates)
        installer = _FakeCheatInstaller()
        db = _FakeCheatDb()
        return SwitchCheatManager(catalog, installer, db)

    def test_list_candidates_by_title_id(self, manager: SwitchCheatManager) -> None:
        candidates = manager.list_candidates("0100000000010000")
        assert len(candidates) == 2

    def test_list_candidates_by_build_id(self, manager: SwitchCheatManager) -> None:
        candidates = manager.list_candidates("0100000000010000", build_id="BID_MATCH")
        assert len(candidates) == 1

    def test_list_candidates_no_match(self, manager: SwitchCheatManager) -> None:
        candidates = manager.list_candidates("0100000000999999")
        assert len(candidates) == 0

    def test_refresh_catalog(self, manager: SwitchCheatManager) -> None:
        n = manager.refresh_catalog()
        assert n == 2

    def test_download_and_install(self, manager: SwitchCheatManager) -> None:
        candidates = manager.list_candidates("0100000000010000")
        assert len(candidates) >= 1
        cheat = manager.download_and_install(candidates[0], "eden", "g1")
        assert cheat.state == "installed"
        assert cheat.emulator_id == "eden"
        assert cheat.code_count == 2
        installed = manager.list_installed("g1")
        assert len(installed) == 1

    def test_enable_and_disable(self, manager: SwitchCheatManager) -> None:
        # Usa candidato com build_id para enable/disable funcionarem
        candidates = [c for c in manager.list_candidates("0100000000010000") if c.build_id]
        assert len(candidates) >= 1
        cheat = manager.download_and_install(candidates[0], "eden", "g1")
        assert manager.enable(cheat.id) is True
        db_cheat = manager._db.get_by_id(cheat.id)
        assert db_cheat is not None
        assert db_cheat.enabled is True
        assert db_cheat.state == "active"

        assert manager.disable(cheat.id) is True
        db_cheat = manager._db.get_by_id(cheat.id)
        assert db_cheat is not None
        assert db_cheat.enabled is False
        assert db_cheat.state == "inactive"

    def test_enable_nonexistent(self, manager: SwitchCheatManager) -> None:
        assert manager.enable("nonexistent") is False

    def test_disable_nonexistent(self, manager: SwitchCheatManager) -> None:
        assert manager.disable("nonexistent") is False

    def test_remove(self, manager: SwitchCheatManager) -> None:
        candidates = [c for c in manager.list_candidates("0100000000010000") if c.build_id]
        assert len(candidates) >= 1
        cheat = manager.download_and_install(candidates[0], "eden", "g1")
        assert manager.remove(cheat.id) is True
        assert manager._db.get_by_id(cheat.id) is None

    def test_remove_nonexistent(self, manager: SwitchCheatManager) -> None:
        assert manager.remove("nonexistent") is False

    def test_edit_codes(self, manager: SwitchCheatManager) -> None:
        candidates = [c for c in manager.list_candidates("0100000000010000") if c.build_id]
        assert len(candidates) >= 1
        cheat = manager.download_and_install(candidates[0], "eden", "g1")
        new_codes = ("580F0000 99999999", "780F0000 88888888")
        assert manager.edit_codes(cheat.id, new_codes) is True
        db_cheat = manager._db.get_by_id(cheat.id)
        assert db_cheat is not None
        assert db_cheat.code_count == 2

    def test_edit_codes_invalid(self, manager: SwitchCheatManager) -> None:
        candidates = [c for c in manager.list_candidates("0100000000010000") if c.build_id]
        assert len(candidates) >= 1
        cheat = manager.download_and_install(candidates[0], "eden", "g1")
        assert manager.edit_codes(cheat.id, ("invalid",)) is False

    def test_to_dict(self, manager: SwitchCheatManager) -> None:
        candidate = manager.list_candidates("0100000000010000")[0]
        cheat = manager.download_and_install(candidate, "eden", "g1")
        d = manager.to_dict(cheat)
        assert d["gameId"] == "g1"
        assert d["codeCount"] == 2
        assert d["enabled"] is False

    def test_list_installed_filters_by_game(self, manager: SwitchCheatManager) -> None:
        c1 = manager.list_candidates("0100000000010000")[0]
        manager.download_and_install(c1, "eden", "g1")
        assert len(manager.list_installed("g1")) == 1
        assert len(manager.list_installed("g2")) == 0


# =============================================================================
# FsCheatInstaller
# =============================================================================


class TestFsCheatInstaller:
    @pytest.fixture
    def installer(self, tmp_path: Path) -> FsCheatInstaller:
        return FsCheatInstaller(tmp_path)

    def test_install_creates_cheat_file(self, installer: FsCheatInstaller, tmp_path: Path) -> None:
        path = installer.install(
            "0100000000010000",
            "BID12345",
            "Infinite Health",
            ("580F0000 00000000", "780F0000 00000001"),
            "eden",
        )
        assert path.exists()
        text = path.read_text("utf-8")
        assert "Infinite Health" in text
        assert "580F0000 00000000" in text

    def test_install_without_build_id(self, installer: FsCheatInstaller, tmp_path: Path) -> None:
        path = installer.install(
            "0100000000010000",
            None,
            "Default",
            ("580F0000 00000000",),
            "eden",
        )
        assert path.name == "default.txt"
        assert path.exists()

    def test_install_unknown_emulator_raises(self, installer: FsCheatInstaller) -> None:
        with pytest.raises(SteamZeroError, match="E-CHEAT-EMULATOR-NOT-FOUND"):
            installer.install("0100", "BID1", "Cheat", (), "nonexistent")

    def test_remove_existing(self, installer: FsCheatInstaller) -> None:
        installer.install("0100", "BID1", "Cheat", ("580F0000 00000000",), "eden")
        assert installer.remove("0100", "BID1", "eden") is True

    def test_remove_nonexistent(self, installer: FsCheatInstaller) -> None:
        assert installer.remove("0100", "NONEXISTENT", "eden") is False

    def test_enable_and_disable(self, installer: FsCheatInstaller) -> None:
        installer.install("0100", "BID1", "Cheat", ("580F0000 00000000",), "eden")
        assert installer.disable("0100", "BID1", "eden") is True
        disabled = installer.list_installed("0100", "eden")
        assert len(disabled) == 1
        assert disabled[0].enabled is False
        assert installer.enable("0100", "BID1", "eden") is True
        assert installer.list_installed("0100", "eden")[0].enabled is True

    def test_list_installed(self, installer: FsCheatInstaller) -> None:
        installer.install("0100", "BID1", "Cheat 1", ("580F0000 00000000",), "eden")
        installer.install("0100", "BID2", "Cheat 2", ("780F0000 00000001",), "eden")
        views = installer.list_installed("0100", "eden")
        assert len(views) == 2

    def test_list_installed_no_title(self, installer: FsCheatInstaller) -> None:
        assert installer.list_installed("0100", "eden") == []

    def test_edit_codes(self, installer: FsCheatInstaller) -> None:
        installer.install("0100", "BID1", "Test", ("580F0000 00000000",), "eden")
        new_codes = ("580F0000 FFFFFFFF",)
        assert installer.edit_codes("0100", "BID1", "eden", new_codes) is True
        cheat_file = installer._cheats_dir("eden", "0100") / "BID1.txt"
        text = cheat_file.read_text("utf-8")
        assert "FFFFFFFF" in text
