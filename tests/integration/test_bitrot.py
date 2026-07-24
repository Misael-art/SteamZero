# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from steamzero.api import contracts
from steamzero.cli import main as cli
from steamzero.core.errors import SteamZeroError
from steamzero.domain.bitrot import BitrotManager, BitrotTarget


def _target(path: Path, asset_id: str = "emulation:game-1") -> BitrotTarget:
    return BitrotTarget(
        asset_id=asset_id,
        title=path.stem,
        platform_id="switch",
        path=path,
        size=path.stat().st_size if path.exists() else 128,
    )


def test_baseline_rehash_and_suspect_never_modify_rom(tmp_path: Path) -> None:
    rom = tmp_path / "Game.nsp"
    rom.write_bytes(b"A" * 2048)
    state = tmp_path / "bitrot.json"
    manager = BitrotManager(state)
    target = _target(rom)

    first = manager.verify_sample([target], max_files=1, max_bytes=4096, max_seconds=5)
    original_state = state.read_text(encoding="utf-8")
    assert first == {
        "checked": 1,
        "bytesRead": 2048,
        "suspect": 0,
        "limited": False,
        "finishedAt": first["finishedAt"],
    }
    assert manager.status([target])["state"] == "healthy"
    assert str(rom) not in original_state

    rom.write_bytes(b"B" * 2048)
    second = manager.verify_sample([_target(rom)], max_files=1, max_bytes=4096)
    health = manager.status([_target(rom)])
    assert second["suspect"] == 1
    assert health["state"] == "suspect"
    assert health["items"][0]["state"] == "suspect"
    assert rom.read_bytes() == b"B" * 2048
    persisted = json.loads(state.read_text(encoding="utf-8"))["items"][target.asset_id]
    assert persisted["expectedSha256"] != persisted["observedSha256"]


def test_sampling_is_deterministic_and_strictly_bounded(tmp_path: Path) -> None:
    first = tmp_path / "A.nsp"
    second = tmp_path / "B.nsp"
    first.write_bytes(b"A" * 700)
    second.write_bytes(b"B" * 700)
    manager = BitrotManager(tmp_path / "state.json")

    result = manager.verify_sample(
        [_target(second, "emulation:b"), _target(first, "emulation:a")],
        max_files=1,
        max_bytes=1024,
        max_seconds=5,
    )

    assert result["checked"] == 1
    assert result["bytesRead"] == 700
    assert result["limited"] is True
    status = manager.status([_target(second, "emulation:b"), _target(first, "emulation:a")])
    assert status["counts"]["verified"] == 1
    assert status["counts"]["unchecked"] == 1
    contracts.validate(status, "feat-bitrot-v1.schema.json")


def test_missing_symlink_deadline_and_corrupt_state_degrade_safely(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.nsp"
    manager = BitrotManager(tmp_path / "missing-state.json")
    result = manager.verify_sample([_target(missing)], max_files=1, max_bytes=1024, max_seconds=5)
    assert result["suspect"] == 1
    assert manager.status([_target(missing)])["items"][0]["state"] == "missing"

    real = tmp_path / "real.nsp"
    real.write_bytes(b"x" * 1024)
    link = tmp_path / "link.nsp"
    link.symlink_to(real)
    unsafe = BitrotManager(tmp_path / "unsafe-state.json")
    link_target = BitrotTarget(
        asset_id="emulation:link",
        title="Link",
        platform_id="switch",
        path=link,
        size=1024,
    )
    unsafe.verify_sample(
        [link_target],
        max_files=1,
        max_bytes=1024,
    )
    assert unsafe.status([link_target])["items"][0]["state"] == "error"

    ticks = iter((0.0, 0.0, 1.0))
    deadline = BitrotManager(tmp_path / "deadline-state.json", monotonic=lambda: next(ticks))
    timed = deadline.verify_sample([_target(real)], max_files=1, max_bytes=1024, max_seconds=0.1)
    assert timed["checked"] == 0
    assert timed["bytesRead"] == 0

    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{", encoding="utf-8")
    with pytest.raises(SteamZeroError, match="corrompido"):
        BitrotManager(corrupt).status()


def test_limits_and_target_validation(tmp_path: Path) -> None:
    rom = tmp_path / "Game.nsp"
    rom.write_bytes(b"x" * 1024)
    manager = BitrotManager(tmp_path / "state.json")
    for kwargs in (
        {"max_files": 0, "max_bytes": 1024, "max_seconds": 1},
        {"max_files": 1, "max_bytes": 100, "max_seconds": 1},
        {"max_files": 1, "max_bytes": 1024, "max_seconds": 121},
    ):
        with pytest.raises(SteamZeroError):
            manager.verify_sample([_target(rom)], **kwargs)
    with pytest.raises(ValueError):
        BitrotTarget("", "Game", "switch", rom, 1)


def test_cli_status_plan_apply_roundtrip(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("STEAMZERO_NO_DAEMON", "1")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    rom = tmp_path / "Game.nsp"
    rom.write_bytes(b"synthetic" * 256)
    cache = tmp_path / "data" / "steamzero" / "emulation-library-cache-v1.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "unidentified": 0,
                "games": [
                    {
                        "id": "game-1",
                        "name": "Game",
                        "state": "ready",
                        "path": str(rom),
                        "size": rom.stat().st_size,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert cli.main(["health", "status", "--json"]) == cli.EXIT_OK
    status = json.loads(capsys.readouterr().out)
    assert status["data"]["counts"]["unchecked"] == 1
    assert cli.main(["health", "plan", "--json"]) == cli.EXIT_OK
    plan = json.loads(capsys.readouterr().out)["data"]
    assert (
        cli.main(
            [
                "health",
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
    applied = json.loads(capsys.readouterr().out)["data"]
    assert applied["job"]["rawState"] == "completed"
    assert applied["health"]["state"] == "healthy"


@settings(
    max_examples=64,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(raw=st.binary(max_size=2048))
def test_state_parser_fuzz_fails_closed(tmp_path: Path, raw: bytes) -> None:
    state = tmp_path / "fuzz-state.json"
    state.write_bytes(raw)
    try:
        payload = BitrotManager(state).status()
    except SteamZeroError:
        return
    contracts.validate(payload, "feat-bitrot-v1.schema.json")
