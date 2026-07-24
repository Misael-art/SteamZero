# SPDX-License-Identifier: GPL-3.0-or-later
"""Contrato, resolução e transação dos perfis de input retro (F6)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from steamzero.core import fs, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.domain.input_profiles import (
    InputProfileManager,
    InputProfileRegistry,
    load_input_profile,
    resolve_bindings,
)
from steamzero.domain.platforms import PlatformRegistry

PROFILES = Path("src/steamzero/input_profiles")


def _raw(name: str = "01-standard-gamepad.input.json") -> dict[str, Any]:
    value = json.loads((PROFILES / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


@pytest.fixture
def manager(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> InputProfileManager:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return InputProfileManager(tmp_path / "config" / "steamzero" / "input-profiles")


def test_registry_covers_every_profile_referenced_by_platform_manifests() -> None:
    profiles = InputProfileRegistry.bundled()
    profile_ids = {profile.id for profile in profiles.list()}
    referenced = {
        str(profile_id)
        for platform in PlatformRegistry.bundled().list()
        for profile_id in platform.controls["profiles"]
    }

    assert profile_ids == referenced
    assert profiles.get("standard-gamepad").revision == 1
    with pytest.raises(SteamZeroError, match="perfil de input desconhecido"):
        profiles.get("missing")


def test_profile_limits_fit_each_platform(manager: InputProfileManager) -> None:
    for platform in PlatformRegistry.bundled().list():
        profiles = manager.list_for_platform(platform.id)
        assert profiles
        assert all(profile["maxPlayers"] <= platform.controls["maxPlayers"] for profile in profiles)


def test_rotation_resolves_directional_bindings_without_mutating_profile() -> None:
    profile = InputProfileRegistry.bundled().get("standard-gamepad")

    landscape = {row["action"]: row["input"] for row in resolve_bindings(profile)}
    left = {row["action"]: row["input"] for row in resolve_bindings(profile, "portrait-left")}
    right = {row["action"]: row["input"] for row in resolve_bindings(profile, "portrait-right")}

    assert landscape["game.up"] == "hat.up"
    assert left["game.up"] == "hat.right"
    assert right["game.up"] == "hat.left"
    assert {row["action"]: row["input"] for row in profile.bindings} == landscape
    with pytest.raises(SteamZeroError, match="não é permitida"):
        resolve_bindings(profile, "upside-down")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: data["bindings"].append(copy.deepcopy(data["bindings"][0])),
        lambda data: data["rotation"].update({"defaultOrientation": "portrait-left"}),
        lambda data: data["bindings"].pop(0),
        lambda data: data.update({"unexpected": True}),
    ],
)
def test_semantic_and_schema_violations_are_typed(
    mutate: Any,
) -> None:
    data = _raw()
    mutate(data)
    if data["rotation"]["defaultOrientation"] == "portrait-left":
        data["rotation"]["allowedOrientations"] = ["landscape"]
    with pytest.raises(SteamZeroError) as raised:
        load_input_profile(data)
    assert raised.value.code == "E-API-SCHEMA"


def test_directional_rotation_requires_complete_hat() -> None:
    data = _raw()
    data["bindings"] = [binding for binding in data["bindings"] if binding["input"] != "hat.left"]

    with pytest.raises(SteamZeroError, match="direcional completo"):
        load_input_profile(data)


def test_activation_is_confirmed_verified_noop_and_rollback_safe(
    manager: InputProfileManager,
) -> None:
    target = manager._root / "active/switch/platform-default.json"  # type: ignore[attr-defined]
    first = manager.plan_activate(
        platform_id="switch",
        profile_id="standard-gamepad",
        orientation="portrait-left",
    )
    assert not target.exists()
    with pytest.raises(SteamZeroError) as wrong:
        manager.apply(first.plan_id, "wrong")
    assert wrong.value.code == "E-TX-CONFIRM-REQUIRED"
    assert not target.exists()

    first_result = manager.apply(first.plan_id, first.confirm_token)
    first_bytes = target.read_bytes()
    status = manager.status("switch")
    assert first_result.status == "ok"
    assert status["active"] == {
        "id": "standard-gamepad",
        "revision": 1,
        "orientation": "portrait-left",
        "scope": "platform",
        "scopeId": None,
    }

    second = manager.plan_activate(platform_id="switch", profile_id="joycon-pair")
    second_result = manager.apply(second.plan_id, second.confirm_token)
    assert manager.status("switch")["active"]["id"] == "joycon-pair"
    rollback = manager.rollback(second_result.operation_id)
    assert rollback.status == "rolled-back"
    assert target.read_bytes() == first_bytes
    assert manager.rollback(second_result.operation_id).status == "rolled-back"

    noop = manager.plan_activate(
        platform_id="switch",
        profile_id="standard-gamepad",
        orientation="portrait-left",
    )
    assert noop.actions == []
    assert len(noop.preconditions) == 1
    assert manager.apply(noop.plan_id, noop.confirm_token).status == "ok"
    stale_noop = manager.plan_activate(
        platform_id="switch",
        profile_id="standard-gamepad",
        orientation="portrait-left",
    )
    fs.write_atomic_text(target, "{}")
    with pytest.raises(SteamZeroError) as changed:
        manager.apply(stale_noop.plan_id, stale_noop.confirm_token)
    assert changed.value.code == "E-TX-STALE-PLAN"


def test_stale_plan_and_corrupt_activation_degrade_honestly(
    manager: InputProfileManager,
) -> None:
    initial = manager.plan_activate(platform_id="switch", profile_id="standard-gamepad")
    manager.apply(initial.plan_id, initial.confirm_token)
    stale = manager.plan_activate(platform_id="switch", profile_id="joycon-pair")
    target = manager._root / "active/switch/platform-default.json"  # type: ignore[attr-defined]
    fs.write_atomic_text(target, "{}")

    with pytest.raises(SteamZeroError) as raised:
        manager.apply(stale.plan_id, stale.confirm_token)
    assert raised.value.code == "E-TX-STALE-PLAN"
    assert manager.status("switch")["state"] == "degraded"


def test_activation_rejects_symlink_and_oversized_existing_file(
    manager: InputProfileManager, tmp_path: Path
) -> None:
    target = manager._root / "active/switch/platform-default.json"  # type: ignore[attr-defined]
    target.parent.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    target.symlink_to(outside)

    assert manager.status("switch")["state"] == "degraded"
    with pytest.raises(SteamZeroError) as symlink:
        manager.plan_activate(platform_id="switch", profile_id="standard-gamepad")
    assert symlink.value.code == "E-TX-STALE-PLAN"
    target.unlink()
    target.write_bytes(b"x" * (256 * 1024 + 1))
    with pytest.raises(SteamZeroError, match="excede 256 KiB"):
        manager.plan_activate(platform_id="switch", profile_id="standard-gamepad")


def test_rollback_rejects_foreign_operation(manager: InputProfileManager, tmp_path: Path) -> None:
    root = tmp_path / "foreign"
    root.mkdir()
    plan = transaction.plan_write_files(
        {root / "value.json": b"{}"}, root=root, kind="foreign.config"
    )
    result = transaction.apply(plan.plan_id, plan.confirm_token)

    with pytest.raises(SteamZeroError, match="não pertence"):
        manager.rollback(result.operation_id)
    with pytest.raises(SteamZeroError, match="operationId"):
        manager.rollback("not-an-operation")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"platform_id": "switch", "profile_id": "arcade-standard"}, "não pertence"),
        (
            {
                "platform_id": "switch",
                "profile_id": "standard-gamepad",
                "scope": "game",
            },
            "scopeId",
        ),
        (
            {
                "platform_id": "switch",
                "profile_id": "standard-gamepad",
                "scope": "game",
                "scope_id": "../escape",
            },
            "scopeId",
        ),
        (
            {
                "platform_id": "geforce-now",
                "profile_id": "cloud-standard-gamepad",
                "orientation": "portrait-left",
            },
            "não é permitida",
        ),
    ],
)
def test_activation_rejects_cross_platform_scope_and_orientation(
    manager: InputProfileManager,
    kwargs: dict[str, Any],
    message: str,
) -> None:
    with pytest.raises(SteamZeroError, match=message):
        manager.plan_activate(**kwargs)


@settings(max_examples=50, deadline=None)
@given(st.dictionaries(st.text(max_size=16), st.recursive(st.none(), st.lists, max_leaves=8)))
def test_profile_parser_fuzz_only_returns_profile_or_typed_error(data: dict[str, Any]) -> None:
    try:
        profile = load_input_profile(data)
    except SteamZeroError as exc:
        assert exc.code == "E-API-SCHEMA"
    else:
        assert profile.schema_version == 1
