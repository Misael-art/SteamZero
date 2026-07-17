# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Protocolo e allowlist do helper privilegiado (PRIVILEGE-BOUNDARIES).

Allowlist FECHADA (enum). Cada ação tem um validador explícito de parâmetros
(sem eval, sem dispatch por string do chamador). O helper NUNCA aceita paths
arbitrários, strings de shell, scripts ou conteúdo de arquivo — conteúdos
privilegiados (udev rules, units) são identificados por enum e embutidos no
próprio helper.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

#: Versão do protocolo helper↔client. Mismatch => recusa (E-PRIV-PROTO-MISMATCH).
PROTOCOL_VERSION = 1

# Faixa absoluta de TDP (o chamador pode restringir mais por modelo — device.quirks).
_TDP_MIN, _TDP_MAX = 3, 30

# Tabelas embutidas (conteúdo/alvo privilegiado vem daqui, nunca do chamador).
GPU_CLOCK_MHZ = frozenset({200, 400, 800, 1000, 1200, 1600})
ALLOWED_SYSCTL: dict[str, tuple[int, int]] = {
    "vm.swappiness": (0, 200),
    "vm.compaction_proactiveness": (0, 100),
}
ALLOWED_UDEV_RULES = frozenset({"steam-controller", "deck-microsd-automount"})
ALLOWED_SYSTEM_UNITS = frozenset({"steamzero-mount.service"})

# UUID de partição: FAT (1234-ABCD) ou formato ext/label hex-dash. Sem '/', '..'.
_UUID_RE = re.compile(
    r"^(?:[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})$"
)


class ParamError(ValueError):
    """Parâmetro inválido para uma ação da allowlist."""


def _require_int(params: dict[str, Any], key: str) -> int:
    value = params.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ParamError(f"{key} deve ser inteiro")
    return value


def _v_set_tdp(params: dict[str, Any]) -> None:
    watts = _require_int(params, "watts")
    if not _TDP_MIN <= watts <= _TDP_MAX:
        raise ParamError(f"watts fora da faixa {_TDP_MIN}..{_TDP_MAX}")


def _v_set_gpu_clock(params: dict[str, Any]) -> None:
    mhz = _require_int(params, "mhz")
    if mhz not in GPU_CLOCK_MHZ:
        raise ParamError("mhz fora da tabela embutida")


def _v_write_sysctl(params: dict[str, Any]) -> None:
    key = params.get("key")
    if key not in ALLOWED_SYSCTL:
        raise ParamError("key de sysctl não permitida")
    lo, hi = ALLOWED_SYSCTL[key]
    value = _require_int(params, "value")
    if not lo <= value <= hi:
        raise ParamError(f"value fora da faixa {lo}..{hi}")


def _v_install_udev_rule(params: dict[str, Any]) -> None:
    if params.get("ruleId") not in ALLOWED_UDEV_RULES:
        raise ParamError("ruleId não é uma regra embutida")


def _v_enable_system_unit(params: dict[str, Any]) -> None:
    if params.get("unitId") not in ALLOWED_SYSTEM_UNITS:
        raise ParamError("unitId não é uma unit embutida")


def _v_mount_removable(params: dict[str, Any]) -> None:
    uuid = params.get("uuid")
    if not isinstance(uuid, str) or not _UUID_RE.match(uuid):
        raise ParamError("uuid inválido (formato)")
    if params.get("mode") not in ("ro", "rw"):
        raise ParamError("mode deve ser ro|rw")


def _v_health(params: dict[str, Any]) -> None:
    if params:
        raise ParamError("health não aceita parâmetros")


@dataclass(frozen=True)
class ActionSpec:
    name: str
    validate: Callable[[dict[str, Any]], None]
    #: chaves de parâmetro aceitas (rejeita extras — defesa contra injeção).
    allowed_keys: frozenset[str] = field(default_factory=frozenset)


ACTIONS: dict[str, ActionSpec] = {
    "health": ActionSpec("health", _v_health),
    "set-tdp": ActionSpec("set-tdp", _v_set_tdp, frozenset({"watts"})),
    "set-gpu-clock": ActionSpec("set-gpu-clock", _v_set_gpu_clock, frozenset({"mhz"})),
    "write-sysctl": ActionSpec("write-sysctl", _v_write_sysctl, frozenset({"key", "value"})),
    "install-udev-rule": ActionSpec(
        "install-udev-rule", _v_install_udev_rule, frozenset({"ruleId"})
    ),
    "enable-system-unit": ActionSpec(
        "enable-system-unit", _v_enable_system_unit, frozenset({"unitId"})
    ),
    "mount-removable": ActionSpec(
        "mount-removable", _v_mount_removable, frozenset({"uuid", "mode"})
    ),
}


@dataclass(frozen=True)
class Request:
    action: str
    params: dict[str, Any]
    protocol_version: int = PROTOCOL_VERSION
    caller: str = "steamzero-core"


@dataclass(frozen=True)
class Response:
    ok: bool
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
