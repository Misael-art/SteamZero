# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Configuração de emuladores: perfis conhecidos bons e diff/preview (WI-3).

Aplica presets declarativos por Title ID via escrita transacional (nunca muta o
alvo sem plano+preview+confirmação+rollback). O catálogo pode nascer vazio; sem
entrada para o jogo, não há mudança. A serialização INI é determinística
(seções/keys ordenadas) para que o diff seja estável e revisável.

O modelo de settings é seccionado (``{secao: {chave: valor}}``), cobrindo o INI
usado pelos emuladores de Switch. Formatos específicos de cada emulador (ex.:
Qt .ini com tipagem) são consumidos por um writer dedicado no adapter — aqui o
domínio permanece agnóstico e testável.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from steamzero.api import contracts
from steamzero.core import transaction
from steamzero.core.errors import SteamZeroError

Settings = dict[str, dict[str, Any]]


class KnownGoodProfileCatalog:
    """Catálogo validado de perfis conhecidos bons; pode estar vazio."""

    def __init__(self, data: dict[str, Any]) -> None:
        contracts.validate(data, "known-good-profile-v1.schema.json")
        self.platform: str = data["platform"]
        self._entries: list[dict[str, Any]] = data["entries"]

    @classmethod
    def empty(cls, platform: str) -> KnownGoodProfileCatalog:
        return cls({"schemaVersion": 1, "platform": platform, "entries": []})

    def lookup(self, title_id: str, *, emulator: str | None = None) -> Settings | None:
        """Melhor perfil para o jogo: específico do emulador tem prioridade."""
        title_id = title_id.upper()
        specific: Settings | None = None
        generic: Settings | None = None
        for entry in self._entries:
            if entry["titleId"].upper() != title_id:
                continue
            if entry.get("emulator") is None:
                generic = entry["settings"]
            elif emulator is not None and entry["emulator"] == emulator:
                specific = entry["settings"]
        return specific or generic


@dataclass(frozen=True)
class SettingsDiff:
    added: dict[str, dict[str, Any]]
    changed: dict[str, dict[str, tuple[Any, Any]]]  # secao -> chave -> (antes, depois)
    unchanged: int

    @property
    def is_empty(self) -> bool:
        return not self.added and not self.changed

    def to_dict(self) -> dict[str, Any]:
        return {
            "added": self.added,
            "changed": {
                section: {
                    key: {"from": before, "to": after} for key, (before, after) in keys.items()
                }
                for section, keys in self.changed.items()
            },
            "unchanged": self.unchanged,
            "isEmpty": self.is_empty,
        }


def diff_settings(current: Settings, desired: Settings) -> SettingsDiff:
    """Diff seccionado entre config atual e desejada (só o que muda)."""
    added: dict[str, dict[str, Any]] = {}
    changed: dict[str, dict[str, tuple[Any, Any]]] = {}
    unchanged = 0
    for section, keys in desired.items():
        current_section = current.get(section, {})
        for key, new_value in keys.items():
            if key not in current_section:
                added.setdefault(section, {})[key] = new_value
            elif current_section[key] != new_value:
                changed.setdefault(section, {})[key] = (current_section[key], new_value)
            else:
                unchanged += 1
    return SettingsDiff(added, changed, unchanged)


def merge_settings(current: Settings, desired: Settings) -> Settings:
    """Mescla desejado sobre atual sem descartar chaves não tocadas."""
    merged: Settings = {section: dict(keys) for section, keys in current.items()}
    for section, keys in desired.items():
        merged.setdefault(section, {}).update(keys)
    return merged


def render_ini(settings: Settings) -> bytes:
    """Serializa settings em INI determinístico (seções e chaves ordenadas)."""
    _validate_ini_settings(settings)
    lines: list[str] = []
    for section in sorted(settings):
        lines.append(f"[{section}]")
        for key in sorted(settings[section]):
            lines.append(f"{key}={_render_value(settings[section][key])}")
        lines.append("")
    return ("\n".join(lines).rstrip("\n") + "\n").encode("utf-8")


def _render_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _validate_ini_settings(settings: Settings) -> None:
    """Recusa nomes/valores que alterariam a estrutura do documento INI."""
    for section, values in settings.items():
        _validate_ini_token(section, kind="seção")
        if not isinstance(values, dict) or not values:
            raise SteamZeroError("E-API-SCHEMA", detail=f"seção INI vazia: {section!r}")
        for key, value in values.items():
            _validate_ini_token(key, kind="chave")
            if isinstance(value, str):
                if len(value) > 4096 or any(char in value for char in "[]\r\n\x00="):
                    raise SteamZeroError(
                        "E-API-SCHEMA", detail=f"valor INI inseguro para {section}.{key}"
                    )
            elif isinstance(value, bool | int):
                continue
            elif isinstance(value, float):
                if not math.isfinite(value):
                    raise SteamZeroError(
                        "E-API-SCHEMA", detail=f"número INI inválido para {section}.{key}"
                    )
            else:
                raise SteamZeroError(
                    "E-API-SCHEMA", detail=f"tipo INI inválido para {section}.{key}"
                )


def _validate_ini_token(value: Any, *, kind: str) -> None:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 120
        or any(char in value for char in "[]\r\n\x00=")
    ):
        raise SteamZeroError("E-API-SCHEMA", detail=f"{kind} INI insegura: {value!r}")


class EmulatorConfigurator:
    """Aplica perfis conhecidos bons com plano/preview/rollback."""

    def __init__(self, catalog: KnownGoodProfileCatalog) -> None:
        self._catalog = catalog

    def preview(
        self, title_id: str, current: Settings, *, emulator: str | None = None
    ) -> SettingsDiff:
        desired = self._catalog.lookup(title_id, emulator=emulator)
        if desired is None:
            return SettingsDiff({}, {}, sum(len(v) for v in current.values()))
        return diff_settings(current, desired)

    def plan_apply(
        self,
        title_id: str,
        current: Settings,
        *,
        config_path: Path,
        root: Path,
        emulator: str | None = None,
    ) -> transaction.Plan:
        desired = self._catalog.lookup(title_id, emulator=emulator)
        if desired is None:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail=f"nenhum perfil conhecido bom para {title_id}",
            )
        merged = merge_settings(current, desired)
        content = render_ini(merged)
        return transaction.plan_write_files(
            {config_path: content}, root=root, kind="emulator.config"
        )

    @staticmethod
    def apply(plan_id: str, confirm_token: str) -> transaction.ApplyResult:
        return transaction.apply(plan_id, confirm_token)

    @staticmethod
    def rollback(operation_id: str) -> transaction.RollbackResult:
        return transaction.rollback(operation_id, reason="emulator-config")
