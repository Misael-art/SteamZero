from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from steamzero.adapters.preservation import PreservationService, PreservationTarget
from steamzero.core import fs, paths, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.domain.switch_content import SwitchContentManager

_GAME = "switch-game"
_TITLE = "0100ABCDEF123000"


def _service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    targets: list[PreservationTarget],
    *,
    progress: list[tuple[int, int]] | None = None,
) -> tuple[PreservationService, SwitchContentManager]:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    content = SwitchContentManager(tmp_path / "content")
    callback = (
        (lambda current, total: progress.append((current, total))) if progress is not None else None
    )
    return PreservationService(content, targets=targets, progress=callback), content


def _target(kind: str, root: Path, *, fingerprint: str = "") -> PreservationTarget:
    return PreservationTarget(
        kind=kind,
        game_id=_GAME,
        title_id=_TITLE,
        emulator_id="citron",
        root=root,
        emulator_version="1.2.3",
        compatibility_fingerprint=fingerprint,
    )


def test_save_backup_restore_and_rollback_are_byte_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    active = tmp_path / "emulator" / "save" / _TITLE
    fs.write_atomic(active / "slot" / "main.bin", b"version-one")
    fs.write_atomic(active / "settings.dat", b"settings-one")
    progress: list[tuple[int, int]] = []
    service, content = _service(tmp_path, monkeypatch, [_target("save", active)], progress=progress)

    status = service.target_status(_GAME, _TITLE, "citron", "save")
    assert status["confirmed"] is True
    assert status["destination"] == str(active)
    assert status["emulatorVersion"] == "1.2.3"
    assert status["size"] == len(b"version-onesettings-one")

    backup = service.plan_backup(_GAME, _TITLE, "citron", "save")
    content.apply_import(backup.plan.plan_id, backup.plan.confirm_token)
    service.cleanup(backup.staging_root)
    backups = service.backups(_TITLE, "citron", "save")
    assert len(backups) == 1
    assert backups[0]["integrity"] == "verified"
    assert backups[0]["createdAt"]
    assert progress[-1] == (2, 2)

    fs.write_atomic(active / "slot" / "main.bin", b"version-two")
    fs.write_atomic(active / "new.bin", b"new-current-file")
    restore = service.plan_restore(
        _GAME,
        _TITLE,
        "citron",
        "save",
        str(backups[0]["recordKey"]),
    )
    applied = transaction.apply(restore.plan.plan_id, restore.plan.confirm_token)
    assert (active / "slot" / "main.bin").read_bytes() == b"version-one"
    assert (active / "settings.dat").read_bytes() == b"settings-one"
    assert not (active / "new.bin").exists()

    transaction.rollback(applied.operation_id)
    assert (active / "slot" / "main.bin").read_bytes() == b"version-two"
    assert (active / "new.bin").read_bytes() == b"new-current-file"
    service.cleanup(restore.staging_root)


def test_restore_failure_rolls_back_active_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    active = tmp_path / "emulator" / "save" / _TITLE
    fs.write_atomic(active / "save.bin", b"backup-version")
    service, content = _service(tmp_path, monkeypatch, [_target("save", active)])
    backup = service.plan_backup(_GAME, _TITLE, "citron", "save")
    content.apply_import(backup.plan.plan_id, backup.plan.confirm_token)
    record_key = str(service.backups(_TITLE, "citron", "save")[0]["recordKey"])
    fs.write_atomic(active / "save.bin", b"active-version")
    restore = service.plan_restore(_GAME, _TITLE, "citron", "save", record_key)

    with pytest.raises(SteamZeroError) as error:
        transaction.apply(
            restore.plan.plan_id,
            restore.plan.confirm_token,
            smoke=lambda: (_ for _ in ()).throw(RuntimeError("emulator rejected save")),
        )
    assert error.value.code == "E-TX-VERIFY-FAILED"
    assert (active / "save.bin").read_bytes() == b"active-version"


def test_ambiguous_symlink_and_oversized_save_targets_are_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "one" / _TITLE
    second = tmp_path / "two" / _TITLE
    fs.write_atomic(first / "save.bin", b"one")
    fs.write_atomic(second / "save.bin", b"two")
    ambiguous, _content = _service(
        tmp_path,
        monkeypatch,
        [_target("save", first), _target("save", second)],
    )
    status = ambiguous.target_status(_GAME, _TITLE, "citron", "save")
    assert status == {
        "confirmed": False,
        "reason": "mais de um destino compatível foi detectado",
        "ambiguous": True,
    }
    with pytest.raises(SteamZeroError) as error:
        ambiguous.plan_backup(_GAME, _TITLE, "citron", "save")
    assert error.value.code == "E-CONTENT-UNSAFE-PATH"

    unsafe = tmp_path / "unsafe" / _TITLE
    unsafe.mkdir(parents=True)
    (unsafe / "escape").symlink_to(first / "save.bin")
    symlinked, _content = _service(tmp_path, monkeypatch, [_target("save", unsafe)])
    with pytest.raises(SteamZeroError) as error:
        symlinked.target_status(_GAME, _TITLE, "citron", "save")
    assert error.value.code == "E-CONTENT-UNSAFE-PATH"

    huge = tmp_path / "huge" / _TITLE
    huge.mkdir(parents=True)
    with (huge / "save.bin").open("wb") as stream:
        stream.truncate(64 * 1024 * 1024 + 1)
    oversized, _content = _service(tmp_path, monkeypatch, [_target("save", huge)])
    with pytest.raises(SteamZeroError) as error:
        oversized.plan_backup(_GAME, _TITLE, "citron", "save")
    assert error.value.code == "E-CONTENT-LIMIT"


def test_shader_fingerprint_restore_and_reversible_invalidation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "emulator" / "shader" / _TITLE
    fs.write_atomic(cache / "pipeline.bin", b"driver-a-cache")
    service, content = _service(
        tmp_path,
        monkeypatch,
        [_target("shader-cache", cache, fingerprint="driver-a-emu-1")],
    )
    backup = service.plan_backup(_GAME, _TITLE, "citron", "shader-cache")
    content.apply_import(backup.plan.plan_id, backup.plan.confirm_token)
    record_key = str(service.backups(_TITLE, "citron", "shader-cache")[0]["recordKey"])

    incompatible = PreservationService(
        content,
        targets=[_target("shader-cache", cache, fingerprint="driver-b-emu-1")],
    )
    with pytest.raises(SteamZeroError) as error:
        incompatible.plan_restore(_GAME, _TITLE, "citron", "shader-cache", record_key)
    assert error.value.code == "E-CONTENT-UNSUPPORTED"
    assert "driver-a-emu-1" in str(error.value.detail)
    assert "driver-b-emu-1" in str(error.value.detail)

    invalidation = service.plan_shader_invalidation(_GAME, _TITLE, "citron")
    applied = transaction.apply(invalidation.plan_id, invalidation.confirm_token)
    moved = cache / ".invalidated" / _TITLE / "driver-a-emu-1" / "pipeline.bin"
    assert moved.read_bytes() == b"driver-a-cache"
    assert not (cache / "pipeline.bin").exists()
    transaction.rollback(applied.operation_id)
    assert (cache / "pipeline.bin").read_bytes() == b"driver-a-cache"


def test_restore_blocks_archive_traversal_and_cleans_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    active = tmp_path / "emulator" / "save" / _TITLE
    fs.write_atomic(active / "save.bin", b"active")
    service, content = _service(tmp_path, monkeypatch, [_target("save", active)])
    malicious = tmp_path / "malicious.zip"
    with zipfile.ZipFile(malicious, "w") as archive:
        archive.writestr("../escape.bin", b"escaped")
        archive.writestr(
            "STEAMZERO-MANIFEST.json",
            json.dumps(
                {
                    "schemaVersion": 1,
                    "files": [
                        {
                            "path": "../escape.bin",
                            "sha256": fs.hash_bytes(b"escaped"),
                            "size": 7,
                        }
                    ],
                }
            ),
        )
    decision = content.plan_import(
        malicious,
        kind="save",
        title_id=_TITLE,
        emulator_id="citron",
        version='backup:{"createdAt":"now","fingerprint":"","schemaVersion":1}',
    )
    assert decision.plan is not None
    content.apply_import(decision.plan.plan_id, decision.plan.confirm_token)
    record_key = str(service.backups(_TITLE, "citron", "save")[0]["recordKey"])

    with pytest.raises(SteamZeroError) as error:
        service.plan_restore(_GAME, _TITLE, "citron", "save", record_key)
    assert error.value.code == "E-CONTENT-UNSAFE-PATH"
    assert not (tmp_path / "escape.bin").exists()
    staging = paths.staging_dir() / "preservation"
    assert not staging.exists() or not any(staging.iterdir())
