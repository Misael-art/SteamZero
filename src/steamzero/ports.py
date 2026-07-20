# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Portas de capacidade (contratos) — camada neutra de inversão de dependência.

Protocols + DTOs que ``domain.*`` consome e ``adapters.*`` implementa. Vive aqui
(não em domain) para que os adapters NÃO importem domain (MODULE-BOUNDARIES:
"adapters dependem de core.*, nunca de domain.* nem api.*"). Depende apenas de
stdlib. A composição (steamzero.runtime) injeta as implementações concretas.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


# --- Device (DMI) ----------------------------------------------------------
class DevicePort(Protocol):
    """Leitura de identificação de hardware (DMI/sysfs)."""

    def read_dmi(self) -> dict[str, str]:
        """Campos DMI: product_name, sys_vendor, board_name (valores crus)."""
        ...


# --- Display ---------------------------------------------------------------
@dataclass(frozen=True)
class DisplayProfile:
    label: str  # degrau da cadeia (target, no-hdr, ..., internal)
    output: str  # internal | external
    width: int
    height: int
    refresh_hz: int
    hdr: bool
    vrr: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "output": self.output,
            "width": self.width,
            "height": self.height,
            "refreshHz": self.refresh_hz,
            "hdr": self.hdr,
            "vrr": self.vrr,
        }


class DisplayPort(Protocol):
    """Aplica um perfil de display e confirma sinal válido."""

    def apply(self, profile: DisplayProfile) -> bool: ...


# --- Storage ---------------------------------------------------------------
@dataclass(frozen=True)
class VolumeInfo:
    uuid: str
    label: str | None
    fstype: str | None
    role: str  # internal | microsd | usb
    mountpoint: str | None  # None = não montado
    capacity: int | None = None
    free: int | None = None


class StoragePort(Protocol):
    """Enumeração de volumes por UUID (/dev/disk/by-uuid + /proc/mounts)."""

    def list_volumes(self) -> list[VolumeInfo]: ...


# --- Session ---------------------------------------------------------------
class SessionPort(Protocol):
    """Controle do processo/emulador em execução."""

    def launch(self, game_id: str) -> bool: ...
    def is_alive(self) -> bool: ...
    def flush_save(self) -> bool: ...
    def signal_close(self) -> None: ...
    def terminate(self) -> None: ...
    def kill(self) -> None: ...


# --- Cloud sync ------------------------------------------------------------
class CloudPort(Protocol):
    """Sincronização remota (fila/rate limit aplicados pela porta)."""

    def available(self) -> bool: ...
    def upload(self, digest: str, data: bytes) -> str: ...
    def fetch_divergent(self, game_id: str, local_digest: str) -> bytes | None: ...


# --- Conversão -------------------------------------------------------------
class ConversionTimeout(Exception):
    """A ferramenta de conversão excedeu o tempo limite."""


class ConverterPort(Protocol):
    """Ferramenta de conversão. Escreve ``dst``; True=ok; pode levantar ConversionTimeout."""

    def convert(self, src: Path, dst: Path, target_format: str) -> bool: ...
