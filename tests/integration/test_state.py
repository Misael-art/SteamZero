# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes do State Store: migração, integridade, jobs, eventos, export, RT-14."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from steamzero.core import state
from steamzero.core.errors import SteamZeroError
from steamzero.core.migrations import m0001_baseline


@pytest.fixture
def db_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    return tmp_path / "state" / "steamzero" / "state.db"


def test_migrate_fresh_to_latest(db_path: Path) -> None:
    store = state.open_state(db_path)
    assert store.user_version == state.LATEST == 3
    tables = {
        r["name"]
        for r in store._conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    for expected in ("job", "operation", "event_log", "game", "save_entry", "component"):
        assert expected in tables
    store.close()


def test_migrate_idempotent(db_path: Path) -> None:
    store = state.open_state(db_path)
    assert store.migrate() == 3  # 2ª vez: no-op
    store.close()


def test_migrate_v1_profile_to_desktop_capable_v2(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True)
    connection = sqlite3.connect(db_path)
    m0001_baseline.up(connection)
    connection.execute("PRAGMA user_version=1")
    connection.execute(
        "INSERT INTO profile (id,scope,kind,payload_json,priority) VALUES (?,?,?,?,?)",
        ("legacy-profile", "mode", "display", "{}", 0),
    )
    connection.commit()
    connection.close()

    store = state.open_state(db_path)
    assert store.user_version == 3
    assert store.get_profile("legacy-profile") is not None
    store.save_profile(
        {
            "id": "desktop-current",
            "scope": "desktop-experience",
            "kind": "desktop-current",
            "payload_json": "{}",
            "priority": 0,
        }
    )
    store.close()


def test_migration_v3_accepts_gameplay_scopes_and_runtime(db_path: Path) -> None:
    store = state.open_state(db_path)
    for scope in ("global", "portable", "dock"):
        store.save_profile(
            {
                "id": f"steam-gameplay:{scope}:default",
                "scope": scope,
                "kind": "performance",
                "payload_json": "{}",
            }
        )
    store.save_profile(
        {
            "id": "steam-runtime:game:10",
            "scope": "game",
            "kind": "performance-runtime",
            "payload_json": '{"state":"active"}',
        }
    )
    assert store.get_profile("steam-runtime:game:10") is not None
    store.close()


def test_integrity_ok(db_path: Path) -> None:
    store = state.open_state(db_path)
    assert store.integrity_ok()
    store.check_integrity()  # não levanta
    store.close()


def test_save_profiles_rolls_back_the_whole_group_on_failure(db_path: Path) -> None:
    store = state.open_state(db_path)
    base = {
        "scope": "game",
        "payload_json": "{}",
        "priority": 100,
        "profile_owner": "steamzero",
    }

    with pytest.raises(sqlite3.IntegrityError):
        store.save_profiles(
            [
                {**base, "id": "performance", "kind": "performance"},
                {**base, "id": "invalid", "kind": "not-allowlisted"},
            ]
        )

    assert store.get_profile("performance") is None
    store.close()


def test_job_crud_and_upsert(db_path: Path) -> None:
    store = state.open_state(db_path)
    store.save_job(
        {"id": "J1", "type": "component.update", "priority": "interactive", "state": "queued"}
    )
    got = store.get_job("J1")
    assert got is not None
    assert got["type"] == "component.update"
    assert got["state"] == "queued"
    # upsert: muda estado
    store.save_job(
        {"id": "J1", "type": "component.update", "priority": "interactive", "state": "running"}
    )
    assert store.get_job("J1")["state"] == "running"
    assert store.get_job("desconhecido") is None
    store.close()


def test_list_jobs_by_state(db_path: Path) -> None:
    store = state.open_state(db_path)
    store.save_job({"id": "A", "type": "t", "priority": "background", "state": "queued"})
    store.save_job({"id": "B", "type": "t", "priority": "background", "state": "running"})
    store.save_job({"id": "C", "type": "t", "priority": "background", "state": "queued"})
    queued = {j["id"] for j in store.list_jobs(states=["queued"])}
    assert queued == {"A", "C"}
    assert len(store.list_jobs()) == 3
    store.close()


def test_event_log(db_path: Path) -> None:
    store = state.open_state(db_path)
    s1 = store.append_event("job.state", entity="J1", payload={"state": "running"})
    s2 = store.append_event("entity.changed", entity="comp:x")
    assert s2 > s1
    since = store.events_since(s1)
    assert [e["kind"] for e in since] == ["entity.changed"]
    store.close()


def test_export_json(db_path: Path) -> None:
    store = state.open_state(db_path)
    store.save_job({"id": "J1", "type": "t", "priority": "background", "state": "queued"})
    export = store.export_json()
    assert export["schemaVersion"] == 3
    assert "job" in export["tables"]
    assert export["tables"]["job"][0]["id"] == "J1"
    store.close()


def test_migration_failure_restores_backup(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # RT-14 (conceito): migração falha => backup restaurado, versão anterior operante
    store = state.open_state(db_path)  # versão atual
    store.save_job({"id": "J1", "type": "t", "priority": "background", "state": "queued"})
    store.close()

    def bad(conn: object) -> None:
        conn.execute("CREATE TABLE t_novo (x)")  # type: ignore[attr-defined]
        raise RuntimeError("migração v2 quebrada")

    monkeypatch.setattr(state, "MIGRATIONS", [*state.MIGRATIONS, (4, bad)])
    monkeypatch.setattr(state, "LATEST", 4)

    store2 = state.StateStore(db_path)
    with pytest.raises(SteamZeroError) as ei:
        store2.migrate()
    assert ei.value.code == "E-STATE-MIGRATION"
    assert store2.user_version == 3  # não avançou
    tables = {
        r["name"]
        for r in store2._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "t_novo" not in tables  # migração revertida
    assert store2.get_job("J1") is not None  # dados preservados
    store2.close()
