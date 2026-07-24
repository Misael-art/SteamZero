from __future__ import annotations

import json
from pathlib import Path

import pytest

from steamzero.cli import main as cli
from steamzero.core import paths, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.domain.collections import CollectionManager
from steamzero.domain.operation_history import OperationHistory


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))


def _apply(manager: CollectionManager, action: dict[str, object]) -> dict[str, object]:
    plan = manager.plan(action)
    return manager.apply(str(plan["planId"]), str(plan["confirmToken"]))


def test_tags_favorites_and_smart_collections_are_projected_and_reversible() -> None:
    manager = CollectionManager()
    _apply(
        manager,
        {"actionId": "tag.upsert", "tagId": "coop", "name": "Co-op", "color": "#13BDF2"},
    )
    _apply(
        manager,
        {"actionId": "favorite.set", "gameRef": "steam:10", "value": True},
    )
    _apply(
        manager,
        {
            "actionId": "game-tag.set",
            "gameRef": "steam:10",
            "tagId": "coop",
            "value": True,
        },
    )
    result = _apply(
        manager,
        {
            "actionId": "collection.upsert",
            "collectionId": "steam-coop",
            "name": "Steam cooperativo",
            "rule": {
                "match": "all",
                "predicates": [
                    {"field": "source", "value": "steam"},
                    {"field": "tag", "value": "coop"},
                    {"field": "favorite", "value": True},
                ],
            },
        },
    )
    state = manager.state(
        [
            {"gameRef": "steam:10", "source": "steam", "platformId": "steam"},
            {
                "gameRef": "emulation:abc",
                "source": "emulation",
                "platformId": "switch",
            },
        ]
    )
    assert state["collections"][0]["members"] == ["steam:10"]
    assert state["favorites"] == ["steam:10"]

    preview = OperationHistory().plan_rollback(str(result["operationId"]))
    OperationHistory().apply_rollback(preview["plan"]["planId"], preview["plan"]["confirmToken"])
    assert manager.state()["collections"] == []


def test_delete_tag_cascades_assignments_and_dependent_smart_collections() -> None:
    manager = CollectionManager()
    _apply(
        manager,
        {"actionId": "tag.upsert", "tagId": "arcade", "name": "Arcade", "color": "#FF9F1A"},
    )
    _apply(
        manager,
        {
            "actionId": "game-tag.set",
            "gameRef": "emulation:mame-1",
            "tagId": "arcade",
            "value": True,
        },
    )
    _apply(
        manager,
        {
            "actionId": "collection.upsert",
            "collectionId": "arcade-only",
            "name": "Arcade",
            "rule": {
                "match": "any",
                "predicates": [{"field": "tag", "value": "arcade"}],
            },
        },
    )
    _apply(manager, {"actionId": "tag.delete", "tagId": "arcade"})
    state = manager.state()
    assert state["tags"] == []
    assert state["assignments"] == []
    assert state["collections"] == []


def test_collection_validation_and_plan_ownership_fail_closed(tmp_path: Path) -> None:
    manager = CollectionManager()
    with pytest.raises(SteamZeroError, match="E-API-SCHEMA"):
        manager.plan({"actionId": "favorite.set", "gameRef": "../../etc", "value": True})
    with pytest.raises(SteamZeroError, match="E-API-SCHEMA"):
        manager.plan(
            {
                "actionId": "collection.upsert",
                "collectionId": "bad",
                "name": "Bad",
                "rule": {"match": "all", "predicates": []},
            }
        )

    target = tmp_path / "other.json"
    unrelated = transaction.plan_write_files({target: b"{}"}, root=tmp_path, kind="config.write")
    with pytest.raises(SteamZeroError, match="E-TX-STALE-PLAN"):
        manager.apply(unrelated.plan_id, unrelated.confirm_token)

    paths.collection_config_path().parent.mkdir(parents=True, exist_ok=True)
    paths.collection_config_path().write_text("{broken", encoding="utf-8")
    with pytest.raises(SteamZeroError, match="E-STATE-INTEGRITY"):
        manager.state()


def test_cli_plan_apply_and_list(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("STEAMZERO_NO_DAEMON", "1")
    action = {
        "actionId": "favorite.set",
        "gameRef": "steam:10",
        "value": True,
    }
    assert (
        cli.main(["collections", "plan", "--action-json", json.dumps(action), "--json"])
        == cli.EXIT_OK
    )
    plan = json.loads(capsys.readouterr().out)["data"]
    assert (
        cli.main(
            [
                "collections",
                "apply",
                "--plan-id",
                plan["planId"],
                "--confirm",
                plan["confirmToken"],
                "--json",
            ]
        )
        == cli.EXIT_OK
    )
    capsys.readouterr()
    assert cli.main(["collections", "list", "--json"]) == cli.EXIT_OK
    state = json.loads(capsys.readouterr().out)["data"]
    assert state["favorites"] == ["steam:10"]


def test_unset_and_delete_actions_are_bounded_and_idempotent() -> None:
    manager = CollectionManager()
    _apply(
        manager,
        {"actionId": "favorite.set", "gameRef": "steam:20", "value": True},
    )
    _apply(
        manager,
        {"actionId": "favorite.set", "gameRef": "steam:20", "value": False},
    )
    _apply(
        manager,
        {"actionId": "tag.upsert", "tagId": "retro", "name": "Retro", "color": "#59D35D"},
    )
    _apply(
        manager,
        {
            "actionId": "game-tag.set",
            "gameRef": "emulation:nes-1",
            "tagId": "retro",
            "value": True,
        },
    )
    _apply(
        manager,
        {
            "actionId": "game-tag.set",
            "gameRef": "emulation:nes-1",
            "tagId": "retro",
            "value": False,
        },
    )
    _apply(
        manager,
        {
            "actionId": "collection.upsert",
            "collectionId": "emulated",
            "name": "Emulados",
            "rule": {
                "match": "any",
                "predicates": [{"field": "source", "value": "emulation"}],
            },
        },
    )
    assert manager.state(
        [{"gameRef": "emulation:nes-1", "source": "emulation", "platformId": "nes"}]
    )["collections"][0]["members"] == ["emulation:nes-1"]
    _apply(
        manager,
        {"actionId": "collection.delete", "collectionId": "emulated"},
    )
    state = manager.state()
    assert state["favorites"] == []
    assert state["assignments"] == []
    assert state["collections"] == []

    with pytest.raises(SteamZeroError, match="E-API-SCHEMA"):
        manager.plan(
            {
                "actionId": "game-tag.set",
                "gameRef": "steam:20",
                "tagId": "missing",
                "value": True,
            }
        )
    with pytest.raises(SteamZeroError, match="E-API-SCHEMA"):
        manager.plan({"actionId": "unknown"})
