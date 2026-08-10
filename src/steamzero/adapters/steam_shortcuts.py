# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Publicação transacional de jogos locais na biblioteca da Steam.

O formato ``shortcuts.vdf`` é binário. Este adapter aceita somente os tipos
usados por atalhos locais (objeto, string e uint32), rejeita documentos
ambíguos e preserva entradas não gerenciadas semanticamente. A Steam precisa
estar encerrada durante plan/apply para impedir lost updates.
"""

from __future__ import annotations

import re
import struct
import zlib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, TypeAlias

from steamzero.adapters.steam_launch_options import (
    SteamLaunchOptionsManager,
    _default_roots,
    _steam_running,
)
from steamzero.core import transaction
from steamzero.core.errors import SteamZeroError

_MAX_BYTES = 16 * 1024 * 1024
_SWITCH_MARKER_PREFIX = "steamzero://switch/"
_CLOUD_MARKER_PREFIX = "steamzero://cloud/"
_TARGET = "/usr/local/bin/steamzero"
_QUOTED_TARGET = f'"{_TARGET}"'

BinaryValue: TypeAlias = str | int | dict[str, "BinaryValue"]


def _invalid(detail: str) -> SteamZeroError:
    return SteamZeroError("E-STATE-INTEGRITY", detail=f"shortcuts.vdf inválido: {detail}")


def _cstring(data: bytes, offset: int, *, allow_empty: bool = False) -> tuple[str, int]:
    end = data.find(b"\0", offset)
    if end < 0:
        raise _invalid("string sem terminador")
    try:
        value = data[offset:end].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _invalid("string não UTF-8") from exc
    if not value and not allow_empty:
        raise _invalid("chave vazia")
    return value, end + 1


def decode_shortcuts(data: bytes) -> list[dict[str, BinaryValue]]:
    """Decodifica o objeto raiz e retorna os atalhos em sua ordem original."""

    if len(data) > _MAX_BYTES:
        raise _invalid("arquivo excede 16 MiB")
    if not data:
        return []

    def parse_object(offset: int) -> tuple[dict[str, BinaryValue], int]:
        result: dict[str, BinaryValue] = {}
        while offset < len(data):
            value_type = data[offset]
            offset += 1
            if value_type == 0x08:
                return result, offset
            key, offset = _cstring(data, offset)
            if key in result:
                raise _invalid(f"chave duplicada: {key}")
            value: BinaryValue
            if value_type == 0x00:
                value, offset = parse_object(offset)
            elif value_type == 0x01:
                value, offset = _cstring(data, offset, allow_empty=True)
            elif value_type == 0x02:
                if offset + 4 > len(data):
                    raise _invalid("uint32 truncado")
                value = struct.unpack_from("<I", data, offset)[0]
                offset += 4
            else:
                raise _invalid(f"tipo não suportado: 0x{value_type:02x}")
            result[key] = value
        raise _invalid("objeto sem fechamento")

    if data[0] != 0x00:
        raise _invalid("objeto raiz ausente")
    root_key, position = _cstring(data, 1)
    if root_key.casefold() != "shortcuts":
        raise _invalid("raiz shortcuts ausente")
    root, position = parse_object(position)
    if position != len(data):
        raise _invalid("bytes após o documento")
    rows: list[dict[str, BinaryValue]] = []
    for index, (key, value) in enumerate(root.items()):
        if key != str(index) or not isinstance(value, dict):
            raise _invalid("índices não contíguos")
        rows.append(value)
    return rows


def _encode_cstring(value: str, *, allow_empty: bool = False) -> bytes:
    if (not value and not allow_empty) or "\0" in value:
        raise SteamZeroError("E-API-SCHEMA", detail="string inválida para shortcuts.vdf")
    return value.encode("utf-8") + b"\0"


def encode_shortcuts(rows: Sequence[Mapping[str, BinaryValue]]) -> bytes:
    """Serializa somente os tipos allowlisted pelo decoder."""

    def encode_object(values: Mapping[str, BinaryValue]) -> bytes:
        output = bytearray()
        for key, value in values.items():
            if isinstance(value, bool):
                value = int(value)
            if isinstance(value, str):
                output.extend(
                    b"\x01" + _encode_cstring(key) + _encode_cstring(value, allow_empty=True)
                )
            elif isinstance(value, int):
                if value < 0 or value > 0xFFFFFFFF:
                    raise SteamZeroError("E-API-SCHEMA", detail="uint32 fora dos limites")
                output.extend(b"\x02" + _encode_cstring(key) + struct.pack("<I", value))
            elif isinstance(value, dict):
                output.extend(b"\x00" + _encode_cstring(key) + encode_object(value))
            else:
                raise SteamZeroError("E-API-SCHEMA", detail="tipo VDF não permitido")
        output.append(0x08)
        return bytes(output)

    root = {str(index): dict(row) for index, row in enumerate(rows)}
    encoded = b"\x00shortcuts\x00" + encode_object(root)
    if len(encoded) > _MAX_BYTES:
        raise SteamZeroError("E-STATE-INTEGRITY", detail="shortcuts.vdf excederia 16 MiB")
    return encoded


def shortcut_app_id(executable: str, name: str) -> int:
    return zlib.crc32((executable + name).encode("utf-8")) | 0x80000000


def shortcut_long_id(app_id: int) -> int:
    return (app_id << 32) | 0x02000000


def _managed_id(row: Mapping[str, BinaryValue], prefix: str) -> str | None:
    marker = row.get("ShortcutPath")
    if not isinstance(marker, str) or not marker.startswith(prefix):
        return None
    item_id = marker.removeprefix(prefix)
    return item_id if item_id and len(item_id) <= 128 else None


def _managed_game_id(row: Mapping[str, BinaryValue]) -> str | None:
    return _managed_id(row, _SWITCH_MARKER_PREFIX)


def _managed_cloud_id(row: Mapping[str, BinaryValue]) -> str | None:
    return _managed_id(row, _CLOUD_MARKER_PREFIX)


class SteamShortcutManager:
    """Sincroniza apenas os atalhos marcados como pertencentes ao SteamZero."""

    def __init__(
        self,
        *,
        roots: Sequence[Path] | None = None,
        running_probe: Callable[[], bool] = _steam_running,
    ) -> None:
        self._roots = tuple(roots) if roots is not None else _default_roots()
        self._running_probe = running_probe

    def managed_game_ids(self) -> set[str]:
        try:
            return {
                game_id
                for row in self._read_rows(self._target())
                if (game_id := _managed_game_id(row)) is not None
            }
        except SteamZeroError:
            return set()

    def managed_cloud_platform_ids(self) -> set[str]:
        try:
            return {
                platform_id
                for row in self._read_rows(self._target())
                if (platform_id := _managed_cloud_id(row)) is not None
            }
        except SteamZeroError:
            return set()

    def resolve_app_id(self, game_id: str) -> int | None:
        try:
            for row in self._read_rows(self._target()):
                marker = row.get("ShortcutPath")
                if isinstance(marker, str) and marker == f"{_SWITCH_MARKER_PREFIX}{game_id}":
                    app_id = row.get("appid")
                    if isinstance(app_id, int):
                        return app_id
            return None
        except SteamZeroError:
            return None

    def media_grid_dir(self, account_id: str) -> Path:
        """Resolve o grid real de uma conta local sem aceitar path arbitrário."""
        if not account_id.isdigit() or len(account_id) > 32:
            raise SteamZeroError("E-API-SCHEMA", detail="accountId Steam inválido")
        matches: list[Path] = []
        for root in self._roots:
            account = root / "userdata" / account_id
            config = account / "config"
            localconfig = config / "localconfig.vdf"
            try:
                resolved_account = account.resolve(strict=True)
                resolved_config = config.resolve(strict=True)
                resolved_localconfig = localconfig.resolve(strict=True)
            except OSError:
                continue
            if (
                account.is_symlink()
                or config.is_symlink()
                or localconfig.is_symlink()
                or not resolved_config.is_relative_to(resolved_account)
                or not resolved_localconfig.is_relative_to(resolved_account)
            ):
                continue
            matches.append(resolved_config / "grid")
        unique = list(dict.fromkeys(matches))
        if len(unique) != 1:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail="conta Steam local ausente ou ambígua",
            )
        return unique[0]

    def plan(self, games: Sequence[Mapping[str, Any]]) -> transaction.Plan:
        return self._plan_rows(
            games,
            marker_prefix=_SWITCH_MARKER_PREFIX,
            kind="steam.shortcuts.sync",
            row_factory=self._row,
            noun="jogo",
            id_pattern=None,
        )

    def plan_cloud(self, platforms: Sequence[Mapping[str, Any]]) -> transaction.Plan:
        return self._plan_rows(
            platforms,
            marker_prefix=_CLOUD_MARKER_PREFIX,
            kind="steam.cloud-shortcuts.sync",
            row_factory=self._cloud_row,
            noun="plataforma",
            id_pattern=r"[a-z][a-z0-9-]{0,127}",
        )

    def _plan_rows(
        self,
        items: Sequence[Mapping[str, Any]],
        *,
        marker_prefix: str,
        kind: str,
        row_factory: Callable[[str, str, int], dict[str, BinaryValue]],
        noun: str,
        id_pattern: str | None,
    ) -> transaction.Plan:
        if self._running_probe():
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED", detail="feche completamente a Steam antes de publicar"
            )
        target = self._target()
        existing = self._read_rows(target)
        foreign = [row for row in existing if _managed_id(row, marker_prefix) is None]
        foreign_app_ids: set[int] = set()
        for row in foreign:
            app_id = row.get("appid")
            if isinstance(app_id, int):
                foreign_app_ids.add(app_id)
        managed: list[dict[str, BinaryValue]] = []
        managed_app_ids: set[int] = set()
        seen_ids: set[str] = set()
        for item in items:
            if item.get("id") is None or item.get("name") is None:
                raise SteamZeroError("E-API-SCHEMA", detail=f"{noun} sem id ou nome")
        for item in sorted(items, key=lambda value: str(value["name"]).casefold()):
            item_id = str(item["id"])
            name = str(item["name"])
            valid_id = bool(item_id) and len(item_id) <= 128
            if id_pattern is not None:
                valid_id = valid_id and re.fullmatch(id_pattern, item_id) is not None
            if item_id in seen_ids or not valid_id:
                raise SteamZeroError("E-API-SCHEMA", detail=f"{noun} duplicado(a) ou inválido(a)")
            seen_ids.add(item_id)
            app_id = shortcut_app_id(_QUOTED_TARGET, name)
            if app_id in foreign_app_ids:
                raise SteamZeroError(
                    "E-STATE-INTEGRITY",
                    detail=f"colisão de AppID com atalho não gerenciado: {name}",
                )
            if app_id in managed_app_ids:
                raise SteamZeroError(
                    "E-STATE-INTEGRITY",
                    detail=f"dois {noun}s gerenciados geram o mesmo AppID: {name}",
                )
            managed_app_ids.add(app_id)
            managed.append(row_factory(item_id, name, app_id))
        content = encode_shortcuts([*foreign, *managed])
        return transaction.plan_write_files(
            {target: content}, root=target.parents[1], kind=kind, skip_unchanged=True
        )

    def apply(self, plan_id: str, confirm_token: str) -> transaction.ApplyResult:
        return self._apply_kind(plan_id, confirm_token, kind="steam.shortcuts.sync")

    def apply_cloud(self, plan_id: str, confirm_token: str) -> transaction.ApplyResult:
        return self._apply_kind(plan_id, confirm_token, kind="steam.cloud-shortcuts.sync")

    def _apply_kind(
        self, plan_id: str, confirm_token: str, *, kind: str
    ) -> transaction.ApplyResult:
        if self._running_probe():
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED", detail="a Steam foi aberta; feche-a e revise novamente"
            )
        plan = transaction.load_plan(plan_id)
        target = self._target()
        valid_actions = len(plan.actions) == 0 or (
            len(plan.actions) == 1
            and plan.actions[0].target == str(target)
            and plan.actions[0].kind == "write"
        )
        if plan.kind != kind or Path(plan.root) != target.parents[1] or not valid_actions:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano não pertence aos atalhos Steam")

        def smoke() -> None:
            decode_shortcuts(target.read_bytes())

        return transaction.apply(plan_id, confirm_token, smoke=smoke)

    def _target(self) -> Path:
        locator = SteamLaunchOptionsManager(roots=self._roots, running_probe=self._running_probe)
        return locator._active_localconfig().parent / "shortcuts.vdf"

    @staticmethod
    def _read_rows(target: Path) -> list[dict[str, BinaryValue]]:
        if not target.exists():
            return []
        if target.is_symlink() or not target.is_file() or target.stat().st_size > _MAX_BYTES:
            raise _invalid("alvo ausente, symlink ou grande demais")
        return decode_shortcuts(target.read_bytes())

    @staticmethod
    def _row(game_id: str, name: str, app_id: int) -> dict[str, BinaryValue]:
        return {
            "appid": app_id,
            "AppName": name,
            "Exe": _QUOTED_TARGET,
            "StartDir": '"/usr/local/bin"',
            "icon": "",
            "ShortcutPath": f"{_SWITCH_MARKER_PREFIX}{game_id}",
            "LaunchOptions": f"emulation launch --game-id {game_id}",
            "IsHidden": 0,
            "AllowDesktopConfig": 1,
            "AllowOverlay": 1,
            "OpenVR": 0,
            "Devkit": 0,
            "DevkitGameID": "",
            "DevkitOverrideAppID": 0,
            "LastPlayTime": 0,
            "FlatpakAppID": "",
            "tags": {"0": "SteamZero", "1": "Nintendo Switch"},
        }

    @staticmethod
    def _cloud_row(platform_id: str, name: str, app_id: int) -> dict[str, BinaryValue]:
        return {
            "appid": app_id,
            "AppName": name,
            "Exe": _QUOTED_TARGET,
            "StartDir": '"/usr/local/bin"',
            "icon": "",
            "ShortcutPath": f"{_CLOUD_MARKER_PREFIX}{platform_id}",
            "LaunchOptions": f"cloud launch --platform {platform_id}",
            "IsHidden": 0,
            "AllowDesktopConfig": 1,
            "AllowOverlay": 1,
            "OpenVR": 0,
            "Devkit": 0,
            "DevkitGameID": "",
            "DevkitOverrideAppID": 0,
            "LastPlayTime": 0,
            "FlatpakAppID": "",
            "tags": {"0": "SteamZero", "1": "Cloud Gaming"},
        }
