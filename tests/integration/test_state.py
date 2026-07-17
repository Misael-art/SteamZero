# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes do State Store: migração, integridade, jobs, eventos, export, RT-14."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from steamzero.core import state
from steamzero.core.errors import SteamZeroError
from steamzero.core.migrations import (
    m0001_baseline,
    m0002_desktop_experience,
    m0003_gameplay_runtime,
)


@pytest.fixture
def db_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    return tmp_path / "state" / "steamzero" / "state.db"


def test_migrate_fresh_to_latest(db_path: Path) -> None:
    store = state.open_state(db_path)
    assert store.user_version == state.LATEST == 5
    tables = {
        r["name"]
        for r in store._conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    for expected in (
        "job",
        "operation",
        "event_log",
        "game",
        "game_session",
        "session_environment",
        "save_entry",
        "component",
    ):
        assert expected in tables
    store.close()


def test_migrate_idempotent(db_path: Path) -> None:
    store = state.open_state(db_path)
    assert store.migrate() == 5  # 2ª vez: no-op
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
    assert store.user_version == 5
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


def test_migration_v3_to_v4_preserves_legacy_runtime(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True)
    connection = sqlite3.connect(db_path)
    m0001_baseline.up(connection)
    m0002_desktop_experience.up(connection)
    m0003_gameplay_runtime.up(connection)
    connection.execute("PRAGMA user_version=3")
    connection.execute(
        "INSERT INTO profile (id,scope,kind,payload_json,profile_owner) VALUES (?,?,?,?,?)",
        (
            "steam-runtime:game:10",
            "game",
            "performance-runtime",
            '{"state":"active","pid":42}',
            "steamzero-launcher",
        ),
    )
    connection.commit()
    connection.close()

    store = state.open_state(db_path)
    assert store.user_version == 5
    assert store.get_profile("steam-runtime:game:10") is not None
    assert store.latest_game_session("10") is None
    store.close()


def test_game_session_is_exclusive_and_transitions_are_persisted(db_path: Path) -> None:
    store = state.open_state(db_path)
    store.create_game_session(
        {"id": "S1", "game_id": "10", "state": "launching", "owner": "launcher"}
    )
    with pytest.raises(sqlite3.IntegrityError):
        store.create_game_session(
            {"id": "S2", "game_id": "20", "state": "launching", "owner": "launcher"}
        )
    running = store.transition_game_session("S1", "running", pid=42)
    assert running["pid"] == 42
    assert store.active_game_session("launcher") == running
    closed = store.transition_game_session("S1", "closed", pid=None, exit_code=0)
    assert closed["state"] == "closed"
    assert store.active_game_session("launcher") is None
    assert store.latest_game_session("10") == closed
    events = store.events_since(0)
    assert [event["kind"] for event in events] == [
        "session.state",
        "session.state",
        "session.state",
    ]
    store.close()


def test_game_session_rejects_invalid_transition_and_unknown_fields(db_path: Path) -> None:
    store = state.open_state(db_path)
    store.create_game_session(
        {"id": "S1", "game_id": "10", "state": "launching", "owner": "launcher"}
    )
    with pytest.raises(SteamZeroError, match="transição"):
        store.transition_game_session("S1", "closed")
    with pytest.raises(SteamZeroError, match="campo"):
        store.transition_game_session("S1", "running", command="secret")
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


def test_session_environment_snapshot_and_event_are_atomic(db_path: Path) -> None:
    store = state.open_state(db_path)
    payload = {"observedAt": "2026-07-17T00:00:00+00:00", "readOnly": True}
    store.save_session_environment(payload, "a" * 64, changes=["initial"])
    current = store.get_session_environment()
    assert current is not None
    assert current["digest"] == "a" * 64
    assert '"readOnly":true' in current["payload_json"]
    event = store.events_since(0)[-1]
    assert event["kind"] == "session.environment"
    assert '"changes": ["initial"]' in event["payload_json"]
    store.close()


def test_export_json(db_path: Path) -> None:
    store = state.open_state(db_path)
    store.save_job({"id": "J1", "type": "t", "priority": "background", "state": "queued"})
    export = store.export_json()
    assert export["schemaVersion"] == 5
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

    monkeypatch.setattr(state, "MIGRATIONS", [*state.MIGRATIONS, (6, bad)])
    monkeypatch.setattr(state, "LATEST", 6)

    store2 = state.StateStore(db_path)
    with pytest.raises(SteamZeroError) as ei:
        store2.migrate()
    assert ei.value.code == "E-STATE-MIGRATION"
    assert store2.user_version == 5  # não avançou
    tables = {
        r["name"]
        for r in store2._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "t_novo" not in tables  # migração revertida
    assert store2.get_job("J1") is not None  # dados preservados
    store2.close()
