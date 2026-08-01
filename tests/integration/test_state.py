# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes do State Store: migração, integridade, jobs, eventos, export, RT-14."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from steamzero.core import state
from steamzero.core.errors import SteamZeroError
from steamzero.core.migrations import (
    MIGRATIONS,
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
    assert store.user_version == state.LATEST == 15
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
    media_columns = {
        str(row[1])
        for row in store._conn.execute("PRAGMA table_info(switch_game_media)").fetchall()
    }
    assert "errors_json" in media_columns
    store.close()


def test_migrate_idempotent(db_path: Path) -> None:
    store = state.open_state(db_path)
    assert store.migrate() == 15  # 2ª vez: no-op
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
    assert store.user_version == 15
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
    assert store.user_version == 15
    assert store.get_profile("steam-runtime:game:10") is not None
    assert store.latest_game_session("10") is None
    store.close()


def test_migration_v12_backfills_legacy_session_duration(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True)
    connection = sqlite3.connect(db_path)
    for version, migration in MIGRATIONS:
        if version > 12:
            break
        migration(connection)
        connection.execute(f"PRAGMA user_version={version}")
    connection.execute(
        """
        INSERT INTO game_session (
          id,game_id,state,owner,started_at,updated_at,finished_at
        ) VALUES (?,?,?,?,?,?,?)
        """,
        (
            "legacy-session",
            "10",
            "closed",
            "steamzero-game-session",
            "2026-07-23T10:00:00+00:00",
            "2026-07-23T10:30:00+00:00",
            "2026-07-23T10:30:00+00:00",
        ),
    )
    connection.commit()
    connection.close()

    store = state.open_state(db_path)
    session = store.latest_game_session("10")
    assert store.user_version == 15
    assert session is not None
    assert 1799 <= session["played_seconds"] <= 1800
    assert session["duration_source"] == "legacy-wall-clock"
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


def test_jobs_and_operations_use_bounded_keyset_pages(db_path: Path) -> None:
    store = state.open_state(db_path)
    for identifier in (
        "01J0000000000000000000000A",
        "01J0000000000000000000000B",
        "01J0000000000000000000000C",
    ):
        store.save_job(
            {
                "id": identifier,
                "type": "t",
                "priority": "background",
                "state": "queued",
            }
        )
        store.save_operation(identifier, state="committed")

    jobs, jobs_more = store.list_jobs_page(limit=2)
    operations, operations_more = store.list_operations_page(limit=2)
    assert [row["id"] for row in jobs] == [
        "01J0000000000000000000000C",
        "01J0000000000000000000000B",
    ]
    assert [row["id"] for row in operations] == [
        "01J0000000000000000000000C",
        "01J0000000000000000000000B",
    ]
    assert jobs_more is operations_more is True

    remaining_jobs, jobs_more = store.list_jobs_page(
        limit=2, before_id="01J0000000000000000000000B"
    )
    remaining_operations, operations_more = store.list_operations_page(
        limit=2, before_id="01J0000000000000000000000B"
    )
    assert [row["id"] for row in remaining_jobs] == ["01J0000000000000000000000A"]
    assert [row["id"] for row in remaining_operations] == ["01J0000000000000000000000A"]
    assert jobs_more is operations_more is False
    with pytest.raises(ValueError, match="entre 1 e 256"):
        store.list_jobs_page(limit=257)
    store.close()


def test_event_log(db_path: Path) -> None:
    store = state.open_state(db_path)
    s1 = store.append_event("job.state", entity="J1", payload={"state": "running"})
    s2 = store.append_event("entity.changed", entity="comp:x")
    assert s2 > s1
    since = store.events_since(s1)
    assert [e["kind"] for e in since] == ["entity.changed"]
    store.close()


def test_event_pages_are_filtered_bounded_and_reconnect_by_sequence(db_path: Path) -> None:
    store = state.open_state(db_path)
    first = store.append_event("job.state", entity="job:J1", payload={"state": "queued"})
    store.append_event("job.state", entity="job:J2", payload={"state": "queued"})
    third = store.append_event(
        "job.progress",
        entity="job:J1",
        payload={"stage": "scan", "current": 1, "total": 2, "unit": "items"},
    )

    page, has_more = store.events_page(
        after_seq=0,
        limit=1,
        kinds=["job.state", "job.progress"],
        entities=["job:J1"],
    )
    assert [row["seq"] for row in page] == [first]
    assert has_more is True
    resumed, has_more = store.events_page(
        after_seq=first,
        limit=2,
        kinds=["job.state", "job.progress"],
        entities=["job:J1"],
    )
    assert [row["seq"] for row in resumed] == [third]
    assert has_more is False
    assert store.latest_event_seq() == third
    store.close()


def test_operation_state_event_is_atomic_and_deduplicated(db_path: Path) -> None:
    store = state.open_state(db_path)
    store.save_operation("OP1", state="applying")
    store.save_operation("OP1", state="applying")
    store.save_operation("OP1", state="committed")

    events = [row for row in store.events_since(0) if row["kind"] == "operation.state"]
    assert [json.loads(row["payload_json"])["state"] for row in events] == [
        "applying",
        "committed",
    ]
    assert all(row["entity"] == "operation:OP1" for row in events)
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

    resume_seq = store.record_session_resume(42.125)
    resume = [row for row in store.events_since(resume_seq - 1) if row["kind"] == "session.resume"]
    assert len(resume) == 1
    assert json.loads(resume[0]["payload_json"]) == {"suspendedSeconds": 42.125}
    store.close()


def test_export_json(db_path: Path) -> None:
    store = state.open_state(db_path)
    store.save_job({"id": "J1", "type": "t", "priority": "background", "state": "queued"})
    export = store.export_json()
    assert export["schemaVersion"] == 15
    assert "job" in export["tables"]
    assert export["tables"]["job"][0]["id"] == "J1"
    store.close()


def test_close_is_idempotent_and_finalizer_closes_abandoned_connection(
    db_path: Path,
) -> None:
    store = state.open_state(db_path)
    connection = store.adapter_connection()
    store.close()
    store.close()
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")

    abandoned = state.open_state(db_path)
    abandoned_connection = abandoned.adapter_connection()
    del abandoned
    with pytest.raises(sqlite3.ProgrammingError):
        abandoned_connection.execute("SELECT 1")


def test_migration_failure_restores_backup(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # RT-14 (conceito): migração falha => backup restaurado, versão anterior operante
    store = state.open_state(db_path)  # versão atual
    store.save_job({"id": "J1", "type": "t", "priority": "background", "state": "queued"})
    store.close()

    def bad(conn: object) -> None:
        conn.execute("CREATE TABLE t_novo (x)")  # type: ignore[attr-defined]
        raise RuntimeError("migração v16 quebrada")

    monkeypatch.setattr(state, "MIGRATIONS", [*state.MIGRATIONS, (16, bad)])
    monkeypatch.setattr(state, "LATEST", 16)

    store2 = state.StateStore(db_path)
    with pytest.raises(SteamZeroError) as ei:
        store2.migrate()
    assert ei.value.code == "E-STATE-MIGRATION"
    assert store2.user_version == 15  # não avançou além da v15 atual
    tables = {
        r["name"]
        for r in store2._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "t_novo" not in tables  # migração revertida
    assert store2.get_job("J1") is not None  # dados preservados
    store2.close()
