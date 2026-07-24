from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from steamzero.api import contracts
from steamzero.cli import main as cli
from steamzero.core import fs, ids, paths, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore
from steamzero.domain.operation_history import OperationHistory


@pytest.fixture
def history_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path / "state"
    data = tmp_path / "data"
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    return tmp_path / "managed"


def _committed(root: Path) -> tuple[str, Path]:
    target = root / "private-game.cfg"
    fs.write_atomic(target, b"before")
    plan = transaction.plan_write_files(
        {target: b"after"},
        root=root,
        kind="emulator.config",
    )
    result = transaction.apply(plan.plan_id, plan.confirm_token)
    return result.operation_id, target


def test_history_preview_confirm_apply_and_verify_rollback(history_home: Path) -> None:
    operation_id, target = _committed(history_home)
    history = OperationHistory()

    listed = history.list(limit=20)
    contracts.validate(listed, "feat-operation-history-v1.schema.json")
    assert listed["items"][0]["operationId"] == operation_id
    assert listed["items"][0]["target"].startswith("arquivo:")
    assert str(history_home) not in json.dumps(listed)
    assert listed["items"][0]["rollback"] == {
        "available": True,
        "guarantee": "G-FULL",
        "route": "transaction",
        "reason": "",
    }
    assert history.page(page=2, page_size=20)["items"] == []

    preview = history.plan_rollback(operation_id)
    assert target.read_bytes() == b"after"
    with pytest.raises(SteamZeroError, match="E-TX-CONFIRM-REQUIRED"):
        history.apply_rollback(preview["plan"]["planId"], "wrong-token")
    result = history.apply_rollback(
        preview["plan"]["planId"],
        preview["plan"]["confirmToken"],
    )
    assert result["result"] == {
        "operationId": operation_id,
        "status": "rolled-back",
        "restoredCount": 1,
        "verified": True,
    }
    assert target.read_bytes() == b"before"
    assert history.get(operation_id)["operation"]["rollback"]["available"] is False


def test_rollback_refuses_changed_or_tampered_evidence(history_home: Path) -> None:
    operation_id, target = _committed(history_home)
    history = OperationHistory()
    preview = history.plan_rollback(operation_id)
    journal_path = paths.journal_path(operation_id)
    journal_path.write_text(journal_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(SteamZeroError, match="E-TX-STALE-PLAN"):
        history.apply_rollback(
            preview["plan"]["planId"],
            preview["plan"]["confirmToken"],
        )
    assert target.read_bytes() == b"after"

    records = [
        json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines() if line
    ]
    intent = next(item for item in records if item["type"] == "action.intent")
    intent["undo"]["target"] = str(history_home.parent / "outside")
    journal_path.write_text(
        "\n".join(json.dumps(item, sort_keys=True) for item in records) + "\n",
        encoding="utf-8",
    )
    item = history.get(operation_id)["operation"]
    assert item["state"] == "committed"
    with pytest.raises(SteamZeroError, match="E-STATE-INTEGRITY"):
        history.plan_rollback(operation_id)


def test_rollback_refuses_target_changed_after_preview(history_home: Path) -> None:
    operation_id, target = _committed(history_home)
    history = OperationHistory()
    preview = history.plan_rollback(operation_id)
    fs.write_atomic(target, b"user-change-after-preview")

    with pytest.raises(SteamZeroError, match="E-TX-STALE-PLAN"):
        history.apply_rollback(
            preview["plan"]["planId"],
            preview["plan"]["confirmToken"],
        )
    assert target.read_bytes() == b"user-change-after-preview"


def test_corrupt_or_symlink_journal_is_visible_but_not_actionable(
    history_home: Path,
) -> None:
    operation_id, _target = _committed(history_home)
    path = paths.journal_path(operation_id)
    original = path.read_bytes()
    path.unlink()
    outside = history_home.parent / "forged.jsonl"
    fs.write_atomic(outside, original)
    path.symlink_to(outside)

    item = OperationHistory().get(operation_id)["operation"]
    assert item["state"] == "invalid"
    assert item["rollback"]["available"] is False
    assert item["rollback"]["route"] == "unavailable"


def test_component_history_uses_contextual_executor(history_home: Path) -> None:
    del history_home
    operation_id = ids.new_ulid()
    operation_path = paths.component_operation_path(operation_id)
    operation = {
        "operationId": operation_id,
        "adapterId": "retroarch",
        "ref": "org.libretro.RetroArch",
        "status": "committed",
        "startedAt": datetime.now(UTC).isoformat(),
    }
    fs.ensure_dir(operation_path.parent)
    fs.write_atomic_text(operation_path, json.dumps(operation))
    with StateStore() as store:
        store.migrate()
        store.save_operation(
            operation_id,
            journal_path=str(operation_path),
            state="committed",
        )

    def rollback(target_id: str) -> dict[str, str]:
        assert target_id == operation_id
        operation["status"] = "rolled-back"
        fs.write_atomic_text(operation_path, json.dumps(operation))
        with StateStore() as store:
            store.migrate()
            store.save_operation(
                operation_id,
                journal_path=str(operation_path),
                state="rolled-back",
            )
        return {"status": "rolled-back"}

    history = OperationHistory(component_rollback=rollback)
    preview = history.plan_rollback(operation_id)
    result = history.apply_rollback(
        preview["plan"]["planId"],
        preview["plan"]["confirmToken"],
    )
    assert result["result"]["verified"] is True
    assert history.get(operation_id)["operation"]["state"] == "rolled-back"


def test_cli_exposes_detail_preview_and_confirmed_rollback(
    history_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("STEAMZERO_NO_DAEMON", "1")
    operation_id, target = _committed(history_home)

    assert cli.main(["operations", "show", "--operation-id", operation_id, "--json"]) == cli.EXIT_OK
    detail = json.loads(capsys.readouterr().out)["data"]
    assert detail["operation"]["operationId"] == operation_id

    assert (
        cli.main(
            [
                "operations",
                "rollback-plan",
                "--operation-id",
                operation_id,
                "--json",
            ]
        )
        == cli.EXIT_OK
    )
    plan = json.loads(capsys.readouterr().out)["data"]["plan"]
    assert target.read_bytes() == b"after"

    assert (
        cli.main(
            [
                "operations",
                "rollback-apply",
                "--plan-id",
                plan["planId"],
                "--confirm",
                plan["confirmToken"],
                "--json",
            ]
        )
        == cli.EXIT_OK
    )
    applied = json.loads(capsys.readouterr().out)["data"]["result"]
    assert applied["verified"] is True
    assert target.read_bytes() == b"before"


def test_validation_missing_evidence_and_unknown_operations_fail_closed(
    history_home: Path,
) -> None:
    history = OperationHistory()
    with pytest.raises(SteamZeroError, match="E-API-SCHEMA"):
        history.list(limit=0)
    with pytest.raises(SteamZeroError, match="E-API-SCHEMA"):
        history.list(cursor="not-an-ulid")
    with pytest.raises(SteamZeroError, match="E-API-SCHEMA"):
        history.page(page=0)
    with pytest.raises(SteamZeroError, match="E-API-SCHEMA"):
        history.get("not-an-ulid")
    with pytest.raises(SteamZeroError, match="E-API-SCHEMA"):
        history.get(ids.new_ulid())

    operation_id = ids.new_ulid()
    with StateStore() as store:
        store.migrate()
        store.save_operation(
            operation_id,
            journal_path=str(paths.journal_path(operation_id)),
            state="committed",
        )
    item = history.get(operation_id)["operation"]
    assert item["state"] == "invalid"
    assert item["rollback"]["available"] is False
    with pytest.raises(SteamZeroError, match="E-TX-STALE-PLAN"):
        history.plan_rollback(operation_id)
    del history_home


def test_rollback_plan_expires_and_is_single_use(history_home: Path) -> None:
    operation_id, target = _committed(history_home)
    history = OperationHistory()
    expired = history.plan_rollback(operation_id)
    expired_path = paths.plan_path(expired["plan"]["planId"])
    stored = json.loads(expired_path.read_text(encoding="utf-8"))
    stored["expiresAt"] = "2000-01-01T00:00:00+00:00"
    fs.write_atomic_text(expired_path, json.dumps(stored))
    with pytest.raises(SteamZeroError, match="E-TX-CONFIRM-REQUIRED"):
        history.apply_rollback(
            expired["plan"]["planId"],
            expired["plan"]["confirmToken"],
        )

    fresh = history.plan_rollback(operation_id)
    history.apply_rollback(fresh["plan"]["planId"], fresh["plan"]["confirmToken"])
    with pytest.raises(SteamZeroError, match="E-TX-STALE-PLAN"):
        history.apply_rollback(fresh["plan"]["planId"], fresh["plan"]["confirmToken"])
    assert target.read_bytes() == b"before"


def test_legacy_journal_is_boundedly_indexed_into_empty_store(
    history_home: Path,
    tmp_path: Path,
) -> None:
    operation_id, _target = _committed(history_home)
    legacy_db = tmp_path / "legacy-state.db"
    history = OperationHistory(lambda: StateStore(legacy_db))
    listed = history.list()
    assert [item["operationId"] for item in listed["items"]] == [operation_id]
    with StateStore(legacy_db) as store:
        store.migrate()
        assert store.count_operations() == 1


def test_committed_component_is_informational_without_contextual_executor(
    history_home: Path,
) -> None:
    del history_home
    operation_id = ids.new_ulid()
    operation_path = paths.component_operation_path(operation_id)
    fs.ensure_dir(operation_path.parent)
    fs.write_atomic_text(
        operation_path,
        json.dumps(
            {
                "operationId": operation_id,
                "adapterId": "retroarch",
                "ref": "org.libretro.RetroArch",
                "status": "committed",
                "startedAt": datetime.now(UTC).isoformat(),
            }
        ),
    )
    with StateStore() as store:
        store.migrate()
        store.save_operation(
            operation_id,
            journal_path=str(operation_path),
            state="committed",
        )
    item = OperationHistory().get(operation_id)["operation"]
    assert item["rollback"]["route"] == "component-flatpak"
    assert item["rollback"]["available"] is False


def test_zero_change_transaction_can_be_closed_with_verified_rollback(
    history_home: Path,
) -> None:
    plan = transaction.plan_write_files({}, root=history_home, kind="emulation.audit")
    applied = transaction.apply(plan.plan_id, plan.confirm_token)
    history = OperationHistory()
    preview = history.plan_rollback(applied.operation_id)
    result = history.apply_rollback(
        preview["plan"]["planId"],
        preview["plan"]["confirmToken"],
    )
    assert result["result"]["restoredCount"] == 0


def test_delete_move_and_symlink_rollbacks_revalidate_their_effective_state(
    history_home: Path,
) -> None:
    history = OperationHistory()

    deleted = history_home / "deleted.cfg"
    fs.write_atomic(deleted, b"preserve-me")
    delete_plan = transaction.plan_write_files(
        {},
        root=history_home,
        kind="media.prune",
        removals={deleted},
    )
    delete_operation = transaction.apply(
        delete_plan.plan_id, delete_plan.confirm_token
    ).operation_id
    assert not deleted.exists()
    delete_preview = history.plan_rollback(delete_operation)
    history.apply_rollback(
        delete_preview["plan"]["planId"],
        delete_preview["plan"]["confirmToken"],
    )
    assert deleted.read_bytes() == b"preserve-me"

    source = history_home / "source.rom"
    destination = history_home / "organized" / "destination.rom"
    fs.write_atomic(source, b"move-me")
    move_plan = transaction.plan_move_files(
        {source: destination},
        root=history_home,
        kind="library.organize",
    )
    move_operation = transaction.apply(move_plan.plan_id, move_plan.confirm_token).operation_id
    move_preview = history.plan_rollback(move_operation)
    history.apply_rollback(
        move_preview["plan"]["planId"],
        move_preview["plan"]["confirmToken"],
    )
    assert source.read_bytes() == b"move-me"
    assert not destination.exists()

    link_source = history_home / "canonical" / "bios.bin"
    link_target = history_home / "consumer" / "bios.bin"
    fs.write_atomic(link_source, b"bios")
    link_plan = transaction.plan_symlink_files(
        {link_source: link_target},
        root=history_home / "consumer",
        kind="bios.link",
    )
    link_operation = transaction.apply(link_plan.plan_id, link_plan.confirm_token).operation_id
    assert link_target.is_symlink()
    link_preview = history.plan_rollback(link_operation)
    history.apply_rollback(
        link_preview["plan"]["planId"],
        link_preview["plan"]["confirmToken"],
    )
    assert not link_target.exists()


def test_corrupt_journal_and_rollback_plan_are_rejected(history_home: Path) -> None:
    operation_id, target = _committed(history_home)
    history = OperationHistory()
    preview = history.plan_rollback(operation_id)
    plan_path = paths.plan_path(preview["plan"]["planId"])
    fs.write_atomic_text(plan_path, "{}")
    with pytest.raises(SteamZeroError, match="E-STATE-INTEGRITY"):
        history.apply_rollback(
            preview["plan"]["planId"],
            preview["plan"]["confirmToken"],
        )
    with pytest.raises(SteamZeroError, match="E-TX-STALE-PLAN"):
        history.apply_rollback("invalid-plan", "token")

    fs.write_atomic_text(paths.journal_path(operation_id), "{not-json}\n")
    item = history.get(operation_id)["operation"]
    assert item["state"] == "invalid"
    assert target.read_bytes() == b"after"
