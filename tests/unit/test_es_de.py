# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from steamzero.adapters.es_de import EsDe
from steamzero.core import transaction
from steamzero.core.errors import SteamZeroError

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "frontends"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _adapter(esde_dir: Path) -> EsDe:
    return EsDe(roots=[esde_dir])


def _system(
    name: str = "steamzero-switch",
    extensions: tuple[str, ...] = (".nsp", ".xci"),
) -> dict[str, object]:
    return {
        "name": name,
        "label": f"Label {name}",
        "path": "/media/games/switch",
        "extensions": extensions,
        "platform": "switch",
        "theme": "switch",
    }


def _apply(adapter: EsDe, systems: list[dict[str, object]]) -> transaction.ApplyResult:
    plan = adapter.plan(systems)
    return adapter.apply(plan.plan_id, plan.confirm_token)


def _file(esde_dir: Path) -> Path:
    return esde_dir / "es_systems.xml"


def test_plan_apply_verify_rollback_byte_identical(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    esde_dir = tmp_path / "ES-DE" / "custom_systems"
    esde_dir.mkdir(parents=True)
    foreign = FIXTURES / "esde-foreign-systems.xml"
    (_file(esde_dir)).write_bytes(foreign.read_bytes())
    baseline = _sha256(_file(esde_dir))
    adapter = _adapter(esde_dir)

    plan = adapter.plan([_system()])
    assert plan.actions != []
    applied = adapter.apply(plan.plan_id, plan.confirm_token)
    assert applied.status == "ok"

    written = _parse(_file(esde_dir))
    systems = written.findall("system")
    assert [s.findtext("name") for s in systems] == ["amiga", "steamzero-switch"]
    ours = systems[1]
    assert ours.get("steamzero") == "true"
    assert ours.findtext("fullname") == "Label steamzero-switch"
    assert ours.findtext("path") == "/media/games/switch"
    assert ours.findtext("extension") == ".nsp .xci"
    assert (
        ours.findtext("command") == "/usr/local/bin/steamzero emulation launch --game-id %BASENAME%"
    )
    assert ours.findtext("platform") == "switch"
    assert ours.findtext("theme") == "switch"
    assert b"<!--" in _file(esde_dir).read_bytes()

    second = adapter.plan([_system()])
    assert second.actions == []
    assert adapter.verify([_system()])["converged"] is True

    result = transaction.rollback(applied.operation_id, reason="test")
    assert result.status == "rolled-back"
    assert _file(esde_dir).read_bytes() == foreign.read_bytes()
    assert _sha256(_file(esde_dir)) == baseline


def _parse(path: Path) -> ET.Element:
    return ET.parse(path).getroot()  # noqa: S314 - documento gerido pelo próprio adapter


def test_foreign_semantics_preserved_with_custom_command(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    esde_dir = tmp_path / "ES-DE" / "custom_systems"
    esde_dir.mkdir(parents=True)
    (_file(esde_dir)).write_bytes((FIXTURES / "esde-foreign-systems.xml").read_bytes())
    custom = dict(_system())
    custom["command"] = "/opt/steamzero/bin/steamzero emulation launch --game-id %BASENAME%"
    adapter = _adapter(esde_dir)

    _apply(adapter, [custom])
    systems = _parse(_file(esde_dir)).findall("system")
    amiga = systems[0]
    assert amiga.findtext("name") == "amiga"
    assert amiga.findtext("command", default="").startswith("%EMULATOR_RETROARCH%")
    assert amiga.findtext("theme") == "amiga"
    ours = systems[1]
    assert ours.findtext("command") == custom["command"]

    _apply(adapter, [custom])
    systems = _parse(_file(esde_dir)).findall("system")
    assert [s.findtext("name") for s in systems] == ["amiga", "steamzero-switch"]
    _apply(adapter, [])
    systems = _parse(_file(esde_dir)).findall("system")
    assert [s.findtext("name") for s in systems] == ["amiga"]


def test_first_run_creates_file_without_foreign(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    esde_dir = tmp_path / "ES-DE" / "custom_systems"
    adapter = _adapter(esde_dir)
    assert adapter.status()["status"] == "missing"
    _apply(adapter, [_system()])
    assert _file(esde_dir).is_file()
    assert _parse(_file(esde_dir)).findtext("./system/name") == "steamzero-switch"


def test_deterministic_output_regardless_of_input_order(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    dir_a = tmp_path / "a" / "custom_systems"
    dir_b = tmp_path / "b" / "custom_systems"
    dir_a.mkdir(parents=True)
    dir_b.mkdir(parents=True)
    systems = [_system("steamzero-arcade"), _system("steamzero-wii")]
    _apply(_adapter(dir_a), systems)
    _apply(_adapter(dir_b), list(reversed(systems)))
    assert _file(dir_a).read_bytes() == _file(dir_b).read_bytes()


def test_plan_rejects_invalid_system(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    esde_dir = tmp_path / "ES-DE" / "custom_systems"
    esde_dir.mkdir(parents=True)
    adapter = _adapter(esde_dir)
    with pytest.raises(SteamZeroError, match="inválido ou duplicado"):
        adapter.plan([_system("switch")])
    with pytest.raises(SteamZeroError, match="duplicado"):
        adapter.plan([_system(), _system()])
    bad = dict(_system())
    bad["path"] = "relative/switch"
    with pytest.raises(SteamZeroError, match="path absoluto"):
        adapter.plan([bad])
    bad = dict(_system())
    bad["platform"] = "Switch!"
    with pytest.raises(SteamZeroError, match="platform"):
        adapter.plan([bad])
    bad = dict(_system())
    bad["extensions"] = []
    with pytest.raises(SteamZeroError, match="extensões"):
        adapter.plan([bad])
    bad = dict(_system())
    bad["extensions"] = ["nsp"]
    with pytest.raises(SteamZeroError, match="extensão"):
        adapter.plan([bad])
    bad = dict(_system())
    bad["label"] = ""
    with pytest.raises(SteamZeroError, match="label"):
        adapter.plan([bad])


def test_plan_rejects_conflict_with_foreign_system(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    esde_dir = tmp_path / "ES-DE" / "custom_systems"
    esde_dir.mkdir(parents=True)
    (_file(esde_dir)).write_text(
        "<systemList><system><name>steamzero-amiga</name></system></systemList>",
        encoding="utf-8",
    )
    adapter = _adapter(esde_dir)
    conflict = dict(_system("steamzero-amiga"))
    with pytest.raises(SteamZeroError, match="conflito com sistema externo"):
        adapter.plan([conflict])


def test_plan_rejects_doctype_invalid_root_oversize_symlink(  # type: ignore[no-untyped-def]
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    esde_dir = tmp_path / "ES-DE" / "custom_systems"
    esde_dir.mkdir(parents=True)
    adapter = _adapter(esde_dir)

    (_file(esde_dir)).write_text(
        "<?xml version='1.0'?><!DOCTYPE systemList [<!ENTITY x 'y'>]><systemList/",
        encoding="utf-8",
    )
    with pytest.raises(SteamZeroError, match="DOCTYPE"):
        adapter.plan([_system()])

    (_file(esde_dir)).write_text("<notSystemList/>", encoding="utf-8")
    with pytest.raises(SteamZeroError, match="systemList"):
        adapter.plan([_system()])

    (_file(esde_dir)).write_text("<systemList><broken", encoding="utf-8")
    with pytest.raises(SteamZeroError, match="malformado"):
        adapter.plan([_system()])

    (_file(esde_dir)).unlink()
    outside = tmp_path / "outside.xml"
    outside.write_text("<systemList/>", encoding="utf-8")
    (_file(esde_dir)).symlink_to(outside)
    with pytest.raises(SteamZeroError, match="symlink"):
        adapter.plan([_system()])
    (_file(esde_dir)).unlink()

    (_file(esde_dir)).write_bytes(b"<systemList>" + b" " * 4 * 1024 * 1024)
    with pytest.raises(SteamZeroError, match="4 MiB"):
        adapter.plan([_system()])


def test_smoke_failure_triggers_auto_rollback(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    esde_dir = tmp_path / "ES-DE" / "custom_systems"
    esde_dir.mkdir(parents=True)
    adapter = _adapter(esde_dir)
    plan = adapter.plan([_system()])
    assert not _file(esde_dir).exists()

    def poisoned_smoke() -> None:
        raise SteamZeroError("E-STATE-INTEGRITY", detail="smoke ES-DE simulada")

    with pytest.raises(SteamZeroError, match="smoke ES-DE simulada"):
        adapter.apply(plan.plan_id, plan.confirm_token, smoke=poisoned_smoke)
    assert not _file(esde_dir).exists()


def test_status_missing_configured_degraded_permission_denied(  # type: ignore[no-untyped-def]
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    esde_dir = tmp_path / "ES-DE" / "custom_systems"
    adapter = _adapter(esde_dir)
    assert adapter.status()["status"] == "missing"

    esde_dir.mkdir(parents=True)
    assert adapter.status()["status"] == "missing"

    _apply(adapter, [_system()])
    assert adapter.status()["status"] == "configured"

    (_file(esde_dir)).write_text("<systemList><broken", encoding="utf-8")
    assert adapter.status()["status"] == "degraded"
    (_file(esde_dir)).unlink()
    _apply(adapter, [_system()])

    (_file(esde_dir)).chmod(0o000)
    try:
        assert adapter.status()["status"] == "permissionDenied"
    finally:
        (_file(esde_dir)).chmod(0o600)


def test_apply_rejects_stale_or_alien_plan(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    esde_dir = tmp_path / "ES-DE" / "custom_systems"
    esde_dir.mkdir(parents=True)
    adapter = _adapter(esde_dir)

    plan = adapter.plan([_system()])
    (_file(esde_dir)).write_bytes((FIXTURES / "esde-foreign-systems.xml").read_bytes())
    with pytest.raises(SteamZeroError, match="E-TX-STALE-PLAN"):
        adapter.apply(plan.plan_id, plan.confirm_token)

    alien = transaction.plan_write_files(
        {_file(esde_dir): b"<systemList/>"}, root=esde_dir, kind="frontend.outro.sync"
    )
    with pytest.raises(SteamZeroError, match="não pertence"):
        adapter.apply(alien.plan_id, alien.confirm_token)


def test_managed_systems_and_noop_after_convergence(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    esde_dir = tmp_path / "ES-DE" / "custom_systems"
    esde_dir.mkdir(parents=True)
    adapter = _adapter(esde_dir)
    assert adapter.managed_systems() == set()

    _apply(adapter, [_system("steamzero-switch"), _system("steamzero-wii")])
    assert adapter.managed_systems() == {"steamzero-switch", "steamzero-wii"}

    first = _file(esde_dir).read_bytes()
    plan = adapter.plan([_system("steamzero-switch"), _system("steamzero-wii")])
    assert plan.actions == []
    adapter.apply(plan.plan_id, plan.confirm_token)
    assert _file(esde_dir).read_bytes() == first
    assert adapter.managed_systems() == {"steamzero-switch", "steamzero-wii"}

    _apply(adapter, [_system("steamzero-switch")])
    assert adapter.managed_systems() == {"steamzero-switch"}
    assert [s.findtext("name") for s in _parse(_file(esde_dir)).findall("system")] == [
        "steamzero-switch"
    ]
