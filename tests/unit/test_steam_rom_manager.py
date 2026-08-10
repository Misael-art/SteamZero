# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from steamzero.adapters.steam_rom_manager import SteamRomManager
from steamzero.core import transaction
from steamzero.core.errors import SteamZeroError

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "frontends"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manager(manifest_dir: Path) -> SteamRomManager:
    return SteamRomManager(roots=[manifest_dir])


def _collection(slug: str, ids: tuple[str, ...]) -> dict[str, object]:
    return {"slug": slug, "games": [{"id": game_id, "title": f"Game {game_id}"} for game_id in ids]}


def _target(manifest_dir: Path, slug: str) -> Path:
    return manifest_dir / f"steamzero-manifest-{slug}.json"


def _apply(
    manager: SteamRomManager, collections: list[dict[str, object]]
) -> transaction.ApplyResult:
    plan = manager.plan(collections)
    return manager.apply(plan.plan_id, plan.confirm_token)


def test_plan_apply_verify_rollback_byte_identical(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    manifest_dir = tmp_path / "srm" / "userData" / "manifests"
    manifest_dir.mkdir(parents=True)
    foreign = FIXTURES / "srm-foreign-manifest.json"
    (manifest_dir / "foreign-list.json").write_bytes(foreign.read_bytes())
    foreign_hash = _sha256(manifest_dir / "foreign-list.json")
    manager = _manager(manifest_dir)

    plan = manager.plan([_collection("switch", ("game-1",))])
    assert plan.actions != []
    applied = manager.apply(plan.plan_id, plan.confirm_token)
    assert applied.status == "ok"

    target = _target(manifest_dir, "switch")
    assert target.is_file()
    entries = json.loads(target.read_bytes())
    assert entries[0]["title"] == "Game game-1"
    assert entries[0]["steamzero"] == {"collection": "switch", "id": "game-1"}
    assert entries[0]["target"] == "/usr/local/bin/steamzero"
    assert entries[0]["startIn"] == "/usr/local/bin"
    assert entries[0]["launchOptions"] == "emulation launch --game-id game-1"
    assert entries[0]["appendArgsToExecutable"] is True
    assert _sha256(manifest_dir / "foreign-list.json") == foreign_hash

    second = manager.plan([_collection("switch", ("game-1",))])
    assert second.actions == []
    assert manager.verify([_collection("switch", ("game-1",))])["converged"] is True

    result = transaction.rollback(applied.operation_id, reason="test")
    assert result.status == "rolled-back"
    assert not target.exists()
    assert _sha256(manifest_dir / "foreign-list.json") == foreign_hash


def test_reapply_is_noop_and_does_not_duplicate(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    manifest_dir = tmp_path / "srm" / "userData" / "manifests"
    manifest_dir.mkdir(parents=True)
    manager = _manager(manifest_dir)
    collections = [_collection("switch", ("game-1", "game-2"))]

    _apply(manager, collections)
    first = _target(manifest_dir, "switch").read_bytes()

    plan = manager.plan(collections)
    assert plan.actions == []
    manager.apply(plan.plan_id, plan.confirm_token)
    assert _target(manifest_dir, "switch").read_bytes() == first
    assert len(json.loads(first)) == 2


def test_deterministic_output_regardless_of_input_order(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    dir_a = tmp_path / "a" / "userData" / "manifests"
    dir_b = tmp_path / "b" / "userData" / "manifests"
    dir_a.mkdir(parents=True)
    dir_b.mkdir(parents=True)
    _apply(_manager(dir_a), [_collection("switch", ("game-1", "game-2"))])
    _apply(_manager(dir_b), [_collection("switch", ("game-2", "game-1"))])
    assert _target(dir_a, "switch").read_bytes() == _target(dir_b, "switch").read_bytes()


def test_preserves_foreign_files_and_removes_only_marked_ones(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    manifest_dir = tmp_path / "srm" / "userData" / "manifests"
    manifest_dir.mkdir(parents=True)
    foreign = FIXTURES / "srm-foreign-manifest.json"
    (manifest_dir / "foreign-list.json").write_bytes(foreign.read_bytes())
    manager = _manager(manifest_dir)

    _apply(manager, [_collection("switch", ("game-1",))])
    _apply(manager, [])
    assert (manifest_dir / "foreign-list.json").read_bytes() == foreign.read_bytes()
    assert not _target(manifest_dir, "switch").exists()


def test_empty_collection_removes_existing_marked_file(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    manifest_dir = tmp_path / "srm" / "userData" / "manifests"
    manifest_dir.mkdir(parents=True)
    manager = _manager(manifest_dir)
    _apply(manager, [_collection("switch", ("game-1",))])
    assert _target(manifest_dir, "switch").exists()
    result = _apply(manager, [_collection("switch", ())])
    assert result.status == "ok"
    assert not _target(manifest_dir, "switch").exists()


def test_plan_rejects_invalid_slug_and_game_id(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    manifest_dir = tmp_path / "srm" / "userData" / "manifests"
    manifest_dir.mkdir(parents=True)
    manager = _manager(manifest_dir)
    with pytest.raises(SteamZeroError, match="inválida"):
        manager.plan([{"slug": "../escape", "games": []}])
    with pytest.raises(SteamZeroError, match="jogo SRM com id"):
        manager.plan([_collection("switch", ("a b",))])
    with pytest.raises(SteamZeroError, match="jogo SRM com id"):
        manager.plan([_collection("switch", ("../evil",))])
    with pytest.raises(SteamZeroError, match="título"):
        manager.plan([{"slug": "switch", "games": [{"id": "ok-1", "title": ""}]}])
    with pytest.raises(SteamZeroError, match="duplicado"):
        manager.plan(
            [
                _collection("switch", ("game-1",)),
                _collection("retro", ("game-1",)),
            ]
        )


def test_plan_rejects_invalid_or_oversized_or_symlink_managed_file(  # type: ignore[no-untyped-def]
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    manifest_dir = tmp_path / "srm" / "userData" / "manifests"
    manifest_dir.mkdir(parents=True)
    manager = _manager(manifest_dir)
    (manifest_dir / "steamzero-manifest-broken.json").write_text("{nope", encoding="utf-8")
    with pytest.raises(SteamZeroError, match="JSON"):
        manager.plan([_collection("switch", ("game-1",))])
    (manifest_dir / "steamzero-manifest-broken.json").unlink()

    outside = tmp_path / "outside.json"
    outside.write_text("[]", encoding="utf-8")
    (manifest_dir / "steamzero-manifest-symlink.json").symlink_to(outside)
    with pytest.raises(SteamZeroError, match="symlink"):
        manager.plan([_collection("switch", ("game-1",))])
    (manifest_dir / "steamzero-manifest-symlink.json").unlink()

    (manifest_dir / "steamzero-manifest-big.json").write_bytes(
        b"[" + b" " * (2 * 1024 * 1024) + b"]"
    )
    with pytest.raises(SteamZeroError, match="2 MiB"):
        manager.plan([_collection("switch", ("game-1",))])


def test_plan_rejects_managed_file_without_marker(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    manifest_dir = tmp_path / "srm" / "userData" / "manifests"
    manifest_dir.mkdir(parents=True)
    foreign_markerless = manifest_dir / "steamzero-manifest-notours.json"
    foreign_markerless.write_text('[{"title": "x", "target": "/bin/true"}]', encoding="utf-8")
    manager = _manager(manifest_dir)
    with pytest.raises(SteamZeroError, match="sem marcador"):
        manager.plan([_collection("switch", ("game-1",))])
    assert foreign_markerless.exists()


def test_smoke_failure_triggers_auto_rollback(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    manifest_dir = tmp_path / "srm" / "userData" / "manifests"
    manifest_dir.mkdir(parents=True)
    manager = _manager(manifest_dir)
    plan = manager.plan([_collection("switch", ("game-1",))])
    target = _target(manifest_dir, "switch")
    assert not target.exists()

    def poisoned_smoke() -> None:
        raise SteamZeroError("E-STATE-INTEGRITY", detail="smoke simulada")

    with pytest.raises(SteamZeroError, match="smoke simulada"):
        manager.apply(plan.plan_id, plan.confirm_token, smoke=poisoned_smoke)
    assert not target.exists()


def test_status_missing_configured_degraded_permission_denied(  # type: ignore[no-untyped-def]
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    manifest_dir = tmp_path / "srm" / "userData" / "manifests"
    manager = _manager(manifest_dir)

    assert manager.status()["status"] == "missing"
    manifest_dir.mkdir(parents=True)

    _apply(manager, [_collection("switch", ("game-1",))])
    assert manager.status()["status"] == "configured"

    (manifest_dir / "steamzero-manifest-broken.json").write_text("{nope", encoding="utf-8")
    assert manager.status()["status"] == "degraded"
    (manifest_dir / "steamzero-manifest-broken.json").unlink()

    manifest_dir.chmod(0o000)
    try:
        assert manager.status()["status"] == "permissionDenied"
    finally:
        manifest_dir.chmod(0o700)


def test_foreign_malformed_file_is_not_parsed(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    manifest_dir = tmp_path / "srm" / "userData" / "manifests"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "user-broken.json").write_text("{oops", encoding="utf-8")
    manager = _manager(manifest_dir)

    plan = manager.plan([_collection("switch", ("game-1",))])
    manager.apply(plan.plan_id, plan.confirm_token)
    assert (manifest_dir / "user-broken.json").read_text(encoding="utf-8") == "{oops"


def test_managed_collections_and_noop_after_convergence(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    manifest_dir = tmp_path / "srm" / "userData" / "manifests"
    manifest_dir.mkdir(parents=True)
    manager = _manager(manifest_dir)

    assert manager.managed_collections() == set()
    _apply(manager, [_collection("switch", ("game-1",))])
    assert manager.managed_collections() == {"switch"}

    targets = list(manifest_dir.glob("steamzero-manifest-*.json"))
    assert len(targets) == 1
    second = manager.plan([_collection("switch", ("game-1",))])
    assert second.actions == []
    manager.apply(second.plan_id, second.confirm_token)
    assert list(manifest_dir.glob("steamzero-manifest-*.json")) == targets
    assert manager.managed_collections() == {"switch"}

    _apply(manager, [])
    assert manager.managed_collections() == set()
    assert list(manifest_dir.glob("steamzero-manifest-*.json")) == []


def test_apply_rejects_stale_or_alien_plan(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    manifest_dir = tmp_path / "srm" / "userData" / "manifests"
    manifest_dir.mkdir(parents=True)
    manager = _manager(manifest_dir)

    plan = manager.plan([_collection("switch", ("game-1",))])
    target = _target(manifest_dir, "switch")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("[]", encoding="utf-8")
    with pytest.raises(SteamZeroError, match="E-TX-STALE-PLAN"):
        manager.apply(plan.plan_id, plan.confirm_token)

    alien = transaction.plan_write_files(
        {target: b'[{"title": "alien", "target": "/bin/false"}]'},
        root=manifest_dir.parent,
        kind="frontend.outro.sync",
    )
    with pytest.raises(SteamZeroError, match="não pertence"):
        manager.apply(alien.plan_id, alien.confirm_token)
