# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Concrete RetroArch session peripherals behind the canonical control port."""

from __future__ import annotations

import socket
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from steamzero.core import fs, paths
from steamzero.core.errors import SteamZeroError

MAX_SLOT = 31
DEFAULT_COMMAND_PORT = 55355
SESSION_CONFIG_NAME = "session-peripherals.cfg"
BEZEL_CONFIG_NAME = "aura-bezel-overlay.cfg"
BEZEL_ASSET_NAME = "aura-bezel.svg"


class SessionPeripheralRecord(Protocol):
    state: str


class SessionPeripheralControl(Protocol):
    def list_save_states(self) -> Mapping[str, Any]: ...

    def save_state(self, slot: int) -> SessionPeripheralRecord: ...

    def load_state(self, slot: int) -> SessionPeripheralRecord: ...

    def list_discs(self) -> Mapping[str, Any]: ...

    def swap_disc(self, disc_id: str) -> SessionPeripheralRecord: ...


SendCommand = Callable[[str], None]


def prepare_retroarch_session_config() -> Path:
    """Publish bounded session controls and the managed AURA bezel overlay."""

    state_root = paths.saves_dir() / "states"
    config_root = paths.config_home() / "retroarch"
    config_path = config_root / SESSION_CONFIG_NAME
    bezel_source = Path(__file__).resolve().parents[1] / "ui" / "assets" / BEZEL_ASSET_NAME
    if bezel_source.is_symlink() or not bezel_source.is_file():
        raise SteamZeroError(
            "E-COMPONENT-DEGRADED", detail=f"asset de bezel AURA ausente: {BEZEL_ASSET_NAME}"
        )
    bezel_asset = config_root / BEZEL_ASSET_NAME
    fs.copy_file_atomic(bezel_source, bezel_asset)
    bezel_config = config_root / BEZEL_CONFIG_NAME
    fs.write_atomic_text(
        bezel_config,
        "\n".join(
            (
                "# SteamZero-Session-Managed: true",
                f'overlay0_overlay = "{bezel_asset}"',
                'overlay0_full_screen = "true"',
                'overlay0_normalized = "true"',
                'overlay0_descs = "0"',
                'overlay0_rect = "0.0,0.0,1.0,1.0"',
                'overlay0_alpha = "1.0"',
                "",
            )
        ),
    )
    fs.write_atomic_text(
        config_path,
        "\n".join(
            (
                "# SteamZero-Session-Managed: true",
                'network_cmd_enable = "true"',
                f'network_cmd_port = "{DEFAULT_COMMAND_PORT}"',
                f'savestate_directory = "{state_root}"',
                f'input_overlay = "{bezel_config}"',
                'input_overlay_enable = "true"',
                'config_save_on_exit = "false"',
                "",
            )
        ),
    )
    return config_path


def _send_udp(command: str, *, host: str, port: int, timeout: float) -> None:
    payload = command.encode("utf-8")
    if len(payload) > 512:
        raise ValueError("comando RetroArch excede o limite")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
        connection.settimeout(timeout)
        connection.sendto(payload, (host, port))


class RetroArchSessionPeripheral:
    """Use only RetroArch's documented UDP commands and its state files.

    The adapter tracks RetroArch's current state slot from the session start and
    moves it with the documented ``STATE_SLOT_PLUS``/``STATE_SLOT_MINUS``
    commands before saving. Loading uses the documented ``LOAD_STATE_SLOT``
    command, so the gallery can operate on every bounded slot it lists.
    """

    def __init__(
        self,
        content_path: Path,
        state_root: Path,
        *,
        command_port: int = DEFAULT_COMMAND_PORT,
        send_command: SendCommand | None = None,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._content_path = Path(content_path)
        self._state_root = Path(state_root)
        if not 1 <= command_port <= 65535:
            raise ValueError("porta RetroArch inválida")
        self._command_port = command_port
        self._send = send_command or (
            lambda command: _send_udp(command, host="127.0.0.1", port=command_port, timeout=1.0)
        )
        self._sleep = sleep
        self._now = now
        self._active_disc = 0
        self._state_slot = 0
        self._discs = self._read_m3u()

    def list_save_states(self) -> Mapping[str, Any]:
        entries: list[dict[str, Any]] = []
        for slot in range(MAX_SLOT + 1):
            path = self._state_path(slot)
            try:
                stat = path.stat()
            except OSError:
                continue
            if path.is_symlink() or not path.is_file() or stat.st_size <= 0:
                continue
            entries.append(
                {
                    "slot": slot,
                    "timestamp": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                    "playtimeSeconds": 0,
                    "thumbnailUrl": "",
                    "compatibility": "native",
                    "available": True,
                    "backupAvailable": self._backup_path(slot).is_file(),
                }
            )
        return {
            "state": "ready" if entries else "empty",
            "entries": entries,
            "reason": "" if entries else "Nenhum save-state foi criado para esta sessão.",
        }

    def save_state(self, slot: int) -> SessionPeripheralRecord:
        self._require_slot(slot)
        self._select_state_slot(slot)
        fs.ensure_dir(self._state_root, mode=0o700)
        current = self._state_path(slot)
        if current.is_file() and not current.is_symlink() and current.stat().st_size > 0:
            fs.copy_file_atomic(current, self._backup_path(slot))
        self._send("SAVE_STATE")
        self._wait_for_state(slot)
        return self._record()

    def load_state(self, slot: int) -> SessionPeripheralRecord:
        self._require_slot(slot)
        if not self._state_path(slot).is_file():
            raise RuntimeError("o slot de save-state ainda não existe")
        self._send(f"LOAD_STATE_SLOT {slot}")
        self._state_slot = slot
        return self._record()

    def list_discs(self) -> Mapping[str, Any]:
        if len(self._discs) < 2:
            return {
                "state": "unavailable",
                "discs": [],
                "reason": "O jogo não declara um conjunto multi-disc.",
            }
        return {
            "state": "ready",
            "activeDisc": self._active_disc,
            "discs": [
                {
                    "id": f"disc-{index}",
                    "label": path.name,
                    "available": True,
                    "compatible": True,
                    "inserted": index == self._active_disc,
                }
                for index, path in enumerate(self._discs)
            ],
        }

    def swap_disc(self, disc_id: str) -> SessionPeripheralRecord:
        if len(self._discs) < 2:
            raise RuntimeError("o jogo não oferece troca de disco")
        if not isinstance(disc_id, str) or not disc_id.startswith("disc-"):
            raise ValueError("identificador de disco inválido")
        try:
            target = int(disc_id[5:])
        except ValueError as exc:
            raise ValueError("identificador de disco inválido") from exc
        if not 0 <= target < len(self._discs):
            raise ValueError("disco fora do conjunto declarado")
        if target == self._active_disc:
            return self._record()
        self._send("DISK_EJECT_TOGGLE")
        step = "DISK_NEXT" if target > self._active_disc else "DISK_PREV"
        for _ in range(abs(target - self._active_disc)):
            self._send(step)
        self._send("DISK_EJECT_TOGGLE")
        self._active_disc = target
        return self._record()

    def _state_path(self, slot: int) -> Path:
        stem = self._content_path.name.rsplit(".", 1)[0]
        suffix = ".state" if slot == 0 else f".state{slot}"
        return self._state_root / f"{stem}{suffix}"

    def _backup_path(self, slot: int) -> Path:
        stem = self._content_path.name.rsplit(".", 1)[0]
        return self._state_root / ".backups" / f"{stem}.slot{slot}.state"

    def _wait_for_state(self, slot: int) -> None:
        for _ in range(10):
            path = self._state_path(slot)
            if path.is_file() and not path.is_symlink() and path.stat().st_size > 0:
                return
            self._sleep(0.1)
        raise RuntimeError("RetroArch não publicou o save-state no diretório gerenciado")

    def _read_m3u(self) -> tuple[Path, ...]:
        if self._content_path.suffix.casefold() != ".m3u":
            return ()
        try:
            if self._content_path.is_symlink() or not self._content_path.is_file():
                return ()
            lines = self._content_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return ()
        discs: list[Path] = []
        for line in lines:
            value = line.strip()
            if not value or value.startswith("#"):
                continue
            raw_candidate = self._content_path.parent / value
            if raw_candidate.is_symlink() or not raw_candidate.is_file():
                continue
            candidate = raw_candidate.resolve()
            if candidate.is_file():
                discs.append(candidate)
        return tuple(discs[:16])

    def _select_state_slot(self, slot: int) -> None:
        step = "STATE_SLOT_PLUS" if slot > self._state_slot else "STATE_SLOT_MINUS"
        for _ in range(abs(slot - self._state_slot)):
            self._send(step)
        self._state_slot = slot

    @staticmethod
    def _require_slot(slot: int) -> None:
        if isinstance(slot, bool) or not isinstance(slot, int) or not 0 <= slot <= MAX_SLOT:
            raise ValueError(f"slot de save-state fora do limite 0..{MAX_SLOT}")

    def _record(self) -> SessionPeripheralRecord:
        class Record:
            state = "running"

        return Record()


__all__ = [
    "BEZEL_ASSET_NAME",
    "BEZEL_CONFIG_NAME",
    "DEFAULT_COMMAND_PORT",
    "SESSION_CONFIG_NAME",
    "RetroArchSessionPeripheral",
    "SessionPeripheralControl",
    "prepare_retroarch_session_config",
]
