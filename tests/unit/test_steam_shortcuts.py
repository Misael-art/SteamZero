# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.adapters.steam_shortcuts import (
    SteamShortcutManager,
    decode_shortcuts,
    encode_shortcuts,
    shortcut_app_id,
    shortcut_long_id,
)
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
