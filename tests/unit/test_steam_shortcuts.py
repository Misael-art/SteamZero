# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
from pathlib import Path

import pytest

from steamzero.adapters.steam_shortcuts import (
    SteamShortcutManager,
    decode_shortcuts,
    encode_shortcuts,
    shortcut_app_id,
    shortcut_long_id,
)
from steamzero.core import transaction
from steamzero.core.errors import SteamZeroError


def _steam_root(tmp_path: Path) -> Path:
    root = tmp_path / "Steam"
    config = root / "userdata" / "123" / "config"
    config.mkdir(parents=True)
    (config / "localconfig.vdf").write_bytes(b'"UserLocalConfigStore"\n{\n}\n')
    return root


def test_codec_roundtrip_and_id_formula() -> None:
    rows = [
        {
            "appid": 0x80000001,
            "AppName": "Foreign game",
            "tags": {"0": "Local"},
        }
    ]
    assert decode_shortcuts(encode_shortcuts(rows)) == rows
    app_id = shortcut_app_id("/usr/local/bin/steamzero", "Example")
    assert app_id & 0x80000000
    assert shortcut_long_id(app_id) == (app_id << 32) | 0x02000000


def test_sync_preserves_foreign_entries_and_removes_only_managed(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    root = _steam_root(tmp_path)
    target = root / "userdata/123/config/shortcuts.vdf"
    foreign = {"appid": 42, "AppName": "Foreign", "ShortcutPath": ""}
    target.write_bytes(encode_shortcuts([foreign]))
    manager = SteamShortcutManager(roots=[root], running_probe=lambda: False)

    first = manager.plan([{"id": "game-1", "name": "Owned game"}])
    manager.apply(first.plan_id, first.confirm_token)
    rows = decode_shortcuts(target.read_bytes())
    assert rows[0] == foreign
    assert rows[1]["ShortcutPath"] == "steamzero://switch/game-1"
    assert manager.managed_game_ids() == {"game-1"}

    second = manager.plan([])
    manager.apply(second.plan_id, second.confirm_token)
    assert decode_shortcuts(target.read_bytes()) == [foreign]


def test_sync_fails_closed_for_running_steam_and_malformed_file(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    root = _steam_root(tmp_path)
    running = SteamShortcutManager(roots=[root], running_probe=lambda: True)
    with pytest.raises(SteamZeroError, match="feche completamente"):
        running.plan([])

    target = root / "userdata/123/config/shortcuts.vdf"
    target.write_bytes(b"corrupt")
    stopped = SteamShortcutManager(roots=[root], running_probe=lambda: False)
    with pytest.raises(SteamZeroError, match="inválido"):
        stopped.plan([])


def test_cloud_sync_preserves_switch_and_foreign_entries_and_rolls_back(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    root = _steam_root(tmp_path)
    target = root / "userdata/123/config/shortcuts.vdf"
    foreign = {"appid": 42, "AppName": "Foreign", "ShortcutPath": ""}
    target.write_bytes(encode_shortcuts([foreign]))
    manager = SteamShortcutManager(roots=[root], running_probe=lambda: False)

    switch_plan = manager.plan([{"id": "game-1", "name": "Owned game"}])
    manager.apply(switch_plan.plan_id, switch_plan.confirm_token)
    cloud_plan = manager.plan_cloud(
        [
            {"id": "xbox-cloud-gaming", "name": "Xbox Cloud Gaming"},
            {"id": "amazon-luna", "name": "Amazon Luna"},
        ]
    )
    manager.apply_cloud(cloud_plan.plan_id, cloud_plan.confirm_token)

    rows = decode_shortcuts(target.read_bytes())
    assert rows[0] == foreign
    assert any(row.get("ShortcutPath") == "steamzero://switch/game-1" for row in rows)
    assert manager.managed_game_ids() == {"game-1"}
    assert manager.managed_cloud_platform_ids() == {
        "amazon-luna",
        "xbox-cloud-gaming",
    }
    xbox = next(
        row for row in rows if row.get("ShortcutPath") == "steamzero://cloud/xbox-cloud-gaming"
    )
    assert xbox["LaunchOptions"] == "cloud launch --platform xbox-cloud-gaming"
    assert xbox["tags"] == {"0": "SteamZero", "1": "Cloud Gaming"}

    clear = manager.plan_cloud([])
    cleared = manager.apply_cloud(clear.plan_id, clear.confirm_token)
    assert manager.managed_cloud_platform_ids() == set()
    assert manager.managed_game_ids() == {"game-1"}

    transaction.rollback(cleared.operation_id, reason="test")
    assert manager.managed_cloud_platform_ids() == {
        "amazon-luna",
        "xbox-cloud-gaming",
    }
    assert manager.managed_game_ids() == {"game-1"}


def test_cloud_sync_rejects_invalid_ids_and_wrong_plan_kind(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    root = _steam_root(tmp_path)
    manager = SteamShortcutManager(roots=[root], running_probe=lambda: False)

    with pytest.raises(SteamZeroError, match="plataforma"):
        manager.plan_cloud([{"id": "../escape", "name": "Invalid"}])
    switch_plan = manager.plan([])
    with pytest.raises(SteamZeroError, match="não pertence"):
        manager.apply_cloud(switch_plan.plan_id, switch_plan.confirm_token)


def test_second_plan_after_convergence_is_noop_and_creates_no_backup(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    root = _steam_root(tmp_path)
    target = root / "userdata/123/config/shortcuts.vdf"
    foreign = {"appid": 42, "AppName": "Foreign", "ShortcutPath": ""}
    target.write_bytes(encode_shortcuts([foreign]))
    manager = SteamShortcutManager(roots=[root], running_probe=lambda: False)
    games = [{"id": "game-1", "name": "Owned game"}]

    first = manager.plan(games)
    assert len(first.actions) == 1
    manager.apply(first.plan_id, first.confirm_token)
    bytes_after_first = target.read_bytes()

    second = manager.plan(games)
    assert second.actions == []
    noop = manager.apply(second.plan_id, second.confirm_token)

    assert target.read_bytes() == bytes_after_first
    noop_backup = tmp_path / "state/steamzero/backups" / noop.operation_id
    manifest = json.loads((noop_backup / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["entries"] == []
    assert list(noop_backup.iterdir()) == [noop_backup / "manifest.json"]


def test_plan_rejects_app_id_collision_with_foreign_entry(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    root = _steam_root(tmp_path)
    target = root / "userdata/123/config/shortcuts.vdf"
    foreign_app_id = shortcut_app_id('"/usr/local/bin/steamzero"', "Taken")
    target.write_bytes(encode_shortcuts([{"appid": foreign_app_id}]))
    manager = SteamShortcutManager(roots=[root], running_probe=lambda: False)
    with pytest.raises(SteamZeroError, match="não gerenciado"):
        manager.plan([{"id": "game-1", "name": "Taken"}])


def test_plan_rejects_two_managed_games_with_same_app_id(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    root = _steam_root(tmp_path)
    manager = SteamShortcutManager(roots=[root], running_probe=lambda: False)
    with pytest.raises(SteamZeroError, match="mesmo AppID"):
        manager.plan([{"id": "game-a", "name": "Same"}, {"id": "game-b", "name": "Same"}])


def test_plan_rejects_item_without_id_or_name(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    root = _steam_root(tmp_path)
    manager = SteamShortcutManager(roots=[root], running_probe=lambda: False)
    with pytest.raises(SteamZeroError, match="sem id ou nome"):
        manager.plan([{"id": "game-1"}])


def test_foreign_entry_unknown_fields_survive_sync(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    root = _steam_root(tmp_path)
    target = root / "userdata/123/config/shortcuts.vdf"
    foreign = {
        "appid": 42,
        "AppName": "Foreign",
        "ShortcutPath": "",
        "UnknownUint": 99,
        "UnknownNested": {"0": "keep", "1": 7, "2": ""},
    }
    target.write_bytes(encode_shortcuts([foreign]))
    manager = SteamShortcutManager(roots=[root], running_probe=lambda: False)
    plan = manager.plan([{"id": "game-1", "name": "Owned game"}])
    manager.apply(plan.plan_id, plan.confirm_token)
    rows = decode_shortcuts(target.read_bytes())
    assert rows[0] == foreign
    assert rows[1]["ShortcutPath"] == "steamzero://switch/game-1"


def test_apply_rejects_stale_plan_when_file_changed(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    root = _steam_root(tmp_path)
    target = root / "userdata/123/config/shortcuts.vdf"
    target.write_bytes(encode_shortcuts([{"appid": 42, "AppName": "Foreign"}]))
    manager = SteamShortcutManager(roots=[root], running_probe=lambda: False)
    plan = manager.plan([{"id": "game-1", "name": "Owned game"}])
    target.write_bytes(encode_shortcuts([{"appid": 43, "AppName": "Changed"}]))
    with pytest.raises(SteamZeroError, match="STALE"):
        manager.apply(plan.plan_id, plan.confirm_token)


def test_rollback_rejects_tampered_backup(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    root = _steam_root(tmp_path)
    target = root / "userdata/123/config/shortcuts.vdf"
    target.write_bytes(encode_shortcuts([{"appid": 42, "AppName": "Foreign"}]))
    manager = SteamShortcutManager(roots=[root], running_probe=lambda: False)
    plan = manager.plan([{"id": "game-1", "name": "Owned game"}])
    applied = manager.apply(plan.plan_id, plan.confirm_token)
    backup_dir = tmp_path / "state/steamzero/backups" / applied.operation_id
    manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
    entry = backup_dir / manifest["entries"][0]["relpath"]
    entry.write_bytes(entry.read_bytes() + b"tampered")
    with pytest.raises(SteamZeroError, match="adulterado"):
        transaction.rollback(applied.operation_id, reason="test")


class TestLaunchingSteamZeroItselfFromSteam:
    """O atalho que faltava: abrir a INTERFACE, e nao um destino.

    Os dois tipos anteriores publicam destinos — um jogo (`emulation launch`) e
    um servico de nuvem (`cloud launch`). Dava para lancar cada jogo pela Steam
    e nao dava para lancar o SteamZero. E a entrada pelo Big Picture que faz a
    experiencia ser equivalente a de um ES-DE, LaunchBox ou RetroFE.
    """

    @staticmethod
    def _manager(monkeypatch, tmp_path: Path) -> tuple[SteamShortcutManager, Path]:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        root = _steam_root(tmp_path)
        target = root / "userdata/123/config/shortcuts.vdf"
        return SteamShortcutManager(roots=[root], running_probe=lambda: False), target

    def test_the_shortcut_opens_the_interface(self, monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        manager, target = self._manager(monkeypatch, tmp_path)
        plan = manager.plan_frontend([{"id": "central", "name": "SteamZero"}])
        manager.apply_frontend(plan.plan_id, plan.confirm_token)

        row = decode_shortcuts(target.read_bytes())[0]
        assert row["LaunchOptions"] == "desktop ui"
        assert row["ShortcutPath"] == "steamzero://frontend/central"
        assert manager.managed_frontend_mode_ids() == {"central"}

    def test_foreign_and_game_shortcuts_survive(self, monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        """O contrato do M11 vale para o tipo novo tambem.

        Conferir so que o atalho da interface aparece passaria mesmo se ele
        varresse os outros — que e o defeito que mais dói, porque leva embora a
        biblioteca inteira de alguem.
        """
        manager, target = self._manager(monkeypatch, tmp_path)
        foreign = {"appid": 42, "AppName": "Foreign", "ShortcutPath": ""}
        target.write_bytes(encode_shortcuts([foreign]))

        game = manager.plan([{"id": "game-1", "name": "Owned game"}])
        manager.apply(game.plan_id, game.confirm_token)
        front = manager.plan_frontend([{"id": "central", "name": "SteamZero"}])
        manager.apply_frontend(front.plan_id, front.confirm_token)

        rows = decode_shortcuts(target.read_bytes())
        assert foreign in rows, "atalho de terceiro nao pode ser removido"
        assert manager.managed_game_ids() == {"game-1"}, "atalho de jogo nao pode ser removido"
        assert manager.managed_frontend_mode_ids() == {"central"}

    def test_reapplying_converges_without_duplicating(self, monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        manager, target = self._manager(monkeypatch, tmp_path)
        first = manager.plan_frontend([{"id": "central", "name": "SteamZero"}])
        manager.apply_frontend(first.plan_id, first.confirm_token)
        before = target.read_bytes()

        second = manager.plan_frontend([{"id": "central", "name": "SteamZero"}])
        manager.apply_frontend(second.plan_id, second.confirm_token)

        assert target.read_bytes() == before
        assert len(decode_shortcuts(target.read_bytes())) == 1

    def test_an_unknown_mode_is_refused(self, monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        """O modo vem da UI; interpolá-lo daria argumento arbitrário ao binário.

        A tabela fechada e o que separa "escolher um modo" de "escolher o que o
        SteamZero instalado executa".
        """
        manager, _target = self._manager(monkeypatch, tmp_path)
        with pytest.raises(SteamZeroError, match="modo de interface desconhecido"):
            manager.plan_frontend([{"id": "modo-inventado", "name": "X"}])

    def test_a_plan_of_another_kind_is_refused(self, monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        manager, _target = self._manager(monkeypatch, tmp_path)
        plan = manager.plan_frontend([{"id": "central", "name": "SteamZero"}])
        with pytest.raises(SteamZeroError, match="não pertence"):
            manager.apply(plan.plan_id, plan.confirm_token)

    def test_removing_the_entry_leaves_the_rest_intact(self, monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        manager, target = self._manager(monkeypatch, tmp_path)
        foreign = {"appid": 42, "AppName": "Foreign", "ShortcutPath": ""}
        target.write_bytes(encode_shortcuts([foreign]))
        first = manager.plan_frontend([{"id": "central", "name": "SteamZero"}])
        manager.apply_frontend(first.plan_id, first.confirm_token)

        empty = manager.plan_frontend([])
        manager.apply_frontend(empty.plan_id, empty.confirm_token)

        assert decode_shortcuts(target.read_bytes()) == [foreign]
        assert manager.managed_frontend_mode_ids() == set()
