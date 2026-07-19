# SPDX-License-Identifier: GPL-3.0-or-later
"""Launch Options Steam: patch preservador, conta ativa e rollback."""

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.adapters.steam_launch_options import (
    SteamLaunchOptionsManager,
    patch_launch_options,
)
from steamzero.core import transaction
from steamzero.core.errors import SteamZeroError


def _localconfig(apps: bytes) -> bytes:
    return (
        b'"UserLocalConfigStore"\n{\n'
        b'\t"Software"\n\t{\n\t\t"Valve"\n\t\t{\n\t\t\t"Steam"\n\t\t\t{\n'
        b'\t\t\t\t"apps"\n\t\t\t\t{\n' + apps + b"\t\t\t\t}\n\t\t\t}\n\t\t}\n\t}\n}\n"
    )


def _app(app_id: str, launch_options: str | None = None) -> bytes:
    leaf = (
        b""
        if launch_options is None
        else b'\t\t\t\t\t\t"LaunchOptions"\t\t"' + launch_options.encode() + b'"\n'
    )
    return (
        b'\t\t\t\t\t"'
        + app_id.encode()
        + b'"\n\t\t\t\t\t{\n'
        + b'\t\t\t\t\t\t"LastPlayed"\t\t"42"\n'
        + leaf
        + b"\t\t\t\t\t}\n"
    )


@pytest.fixture(autouse=True)
def isolated_transaction_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))


def _account(root: Path, account_id: str, data: bytes) -> Path:
    target = root / "userdata" / account_id / "config/localconfig.vdf"
    target.parent.mkdir(parents=True)
    target.write_bytes(data)
    return target


def test_patch_replaces_only_existing_launch_options_bytes() -> None:
    original = _localconfig(_app("10", "gamemoderun %command%"))
    desired = "steamzero-launch --appid 10 -- %command%"

    patched = patch_launch_options(original, "10", desired)

    assert patched.previous_present is True
    assert patched.previous_state == "foreign"
    expected = original.replace(b'"gamemoderun %command%"', b'"' + desired.encode() + b'"')
    assert patched.content == expected


def test_patch_inserts_leaf_without_reserializing_app() -> None:
    original = _localconfig(_app("10"))
    patched = patch_launch_options(original, "10", "steamzero-launch --appid 10 -- %command%")
    assert patched.previous_present is False
    assert patched.content.count(b'"LastPlayed"') == 1
    assert patched.content.count(b'"LaunchOptions"') == 1
    assert (
        patched.content.replace(
            b'\t\t\t\t\t\t"LaunchOptions"\t\t"steamzero-launch --appid 10 -- %command%"\n',
            b"",
        )
        == original
    )


def test_patch_inserts_missing_app_and_preserves_other_apps() -> None:
    original = _localconfig(_app("20", "foreign %command%"))
    patched = patch_launch_options(original, "10", "steamzero-launch --appid 10 -- %command%")
    assert b'"20"' in patched.content
    assert b'"foreign %command%"' in patched.content
    assert b'"10"' in patched.content
    assert (
        patch_launch_options(
            patched.content, "10", "steamzero-launch --appid 10 -- %command%"
        ).previous_state
        == "managed"
    )


@pytest.mark.parametrize(
    "payload",
    [
        b'"UserLocalConfigStore" { "Software" {',
        _localconfig(_app("10", "one") + _app("10", "two")),
        _localconfig(
            b'\t\t\t\t\t"10"\n\t\t\t\t\t{\n'
            b'\t\t\t\t\t\t"LaunchOptions" "one"\n'
            b'\t\t\t\t\t\t"LaunchOptions" "two"\n\t\t\t\t\t}\n'
        ),
        _localconfig(b'\t\t\t\t\t"10"\t\t"not-a-block"\n'),
        _localconfig(
            b'\t\t\t\t\t"10"\n\t\t\t\t\t{\n'
            b'\t\t\t\t\t\t"LaunchOptions"\n\t\t\t\t\t\t{\n\t\t\t\t\t\t}\n'
            b"\t\t\t\t\t}\n"
        ),
    ],
)
def test_patch_rejects_malformed_or_ambiguous_vdf(payload: bytes) -> None:
    with pytest.raises(SteamZeroError) as error:
        patch_launch_options(payload, "10", "steamzero-launch --appid 10 -- %command%")
    assert error.value.code == "E-STATE-INTEGRITY"


def test_plan_apply_verify_and_rollback_are_byte_identical(tmp_path: Path) -> None:
    root = tmp_path / "Steam"
    original = _localconfig(_app("10", "foreign %command%"))
    target = _account(root, "123", original)
    manager = SteamLaunchOptionsManager(roots=(root,), running_probe=lambda: False)

    assert manager.status("10")["state"] == "foreign"
    plan = manager.plan("10")
    assert plan["rollbackGuarantee"] == "G-FULL"
    assert plan["replacesExisting"] is True
    with pytest.raises(SteamZeroError) as wrong:
        manager.apply(str(plan["planId"]), "wrong", "10")
    assert wrong.value.code == "E-TX-CONFIRM-REQUIRED"
    assert target.read_bytes() == original

    applied = manager.apply(str(plan["planId"]), str(plan["confirmToken"]), "10")
    assert manager.status("10")["state"] == "managed"
    manager.rollback(str(applied["operationId"]))
    assert target.read_bytes() == original


def test_running_steam_blocks_plan_and_apply(tmp_path: Path) -> None:
    root = tmp_path / "Steam"
    _account(root, "123", _localconfig(_app("10")))
    running = True
    manager = SteamLaunchOptionsManager(roots=(root,), running_probe=lambda: running)
    assert manager.status("10")["state"] == "steam-running"
    with pytest.raises(SteamZeroError, match="feche completamente"):
        manager.plan("10")


def test_loginusers_selects_one_account_without_touching_the_other(tmp_path: Path) -> None:
    root = tmp_path / "Steam"
    first = _account(root, "123", _localconfig(_app("10")))
    second_original = _localconfig(_app("10", "keep %command%"))
    second = _account(root, "456", second_original)
    loginusers = root / "config/loginusers.vdf"
    loginusers.parent.mkdir(parents=True)
    loginusers.write_bytes(
        b'"users"\n{\n'
        b'\t"76561197960265851"\n\t{\n\t\t"MostRecent" "1"\n\t}\n'
        b'\t"76561197960266184"\n\t{\n\t\t"MostRecent" "0"\n\t}\n}\n'
    )
    manager = SteamLaunchOptionsManager(roots=(root,), running_probe=lambda: False)
    plan = manager.plan("10")
    manager.apply(str(plan["planId"]), str(plan["confirmToken"]), "10")
    assert b"steamzero-launch" in first.read_bytes()
    assert second.read_bytes() == second_original


def test_apply_rejects_plan_from_another_subsystem(tmp_path: Path) -> None:
    root = tmp_path / "Steam"
    _account(root, "123", _localconfig(_app("10")))
    manager = SteamLaunchOptionsManager(roots=(root,), running_probe=lambda: False)
    unrelated = transaction.plan_write_files(
        {tmp_path / "other/file": b"x"}, root=tmp_path / "other", kind="other.install"
    )
    with pytest.raises(SteamZeroError) as error:
        manager.apply(unrelated.plan_id, unrelated.confirm_token, "10")
    assert error.value.code == "E-TX-STALE-PLAN"
    assert not (tmp_path / "other/file").exists()


def test_apply_rejects_same_kind_plan_for_sibling_file(tmp_path: Path) -> None:
    root = tmp_path / "Steam"
    target = _account(root, "123", _localconfig(_app("10")))
    manager = SteamLaunchOptionsManager(roots=(root,), running_probe=lambda: False)
    sibling = target.with_name("sharedconfig.vdf")
    unrelated = transaction.plan_write_files(
        {sibling: b'"unrelated" "content"\n'},
        root=target.parents[1],
        kind="steam.launch-options.configure:10",
    )
    with pytest.raises(SteamZeroError) as error:
        manager.apply(unrelated.plan_id, unrelated.confirm_token, "10")
    assert error.value.code == "E-TX-STALE-PLAN"
    assert not sibling.exists()


def test_apply_binds_plan_to_exact_appid(tmp_path: Path) -> None:
    root = tmp_path / "Steam"
    target = _account(root, "123", _localconfig(_app("10") + _app("20")))
    original = target.read_bytes()
    manager = SteamLaunchOptionsManager(roots=(root,), running_probe=lambda: False)
    plan = manager.plan("10")
    with pytest.raises(SteamZeroError) as error:
        manager.apply(str(plan["planId"]), str(plan["confirmToken"]), "20")
    assert error.value.code == "E-TX-STALE-PLAN"
    assert target.read_bytes() == original


def test_symlinked_account_config_is_not_followed(tmp_path: Path) -> None:
    root = tmp_path / "Steam"
    account = root / "userdata/123"
    account.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "localconfig.vdf").write_bytes(_localconfig(_app("10")))
    (account / "config").symlink_to(outside, target_is_directory=True)
    manager = SteamLaunchOptionsManager(roots=(root,), running_probe=lambda: False)
    status = manager.status("10")
    assert status["state"] == "unavailable"
    assert b"steamzero-launch" not in (outside / "localconfig.vdf").read_bytes()
