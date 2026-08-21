# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Configuração de emuladores: perfis conhecidos bons e diff/preview (WI-3).

Aplica presets declarativos por identidade de título (plataforma + esquema +
valor — Onda 1) via escrita transacional (nunca muta o alvo sem
plano+preview+confirmação+rollback). O catálogo pode nascer vazio; sem
entrada para o jogo, não há mudança. A serialização INI é determinística
(seções/keys ordenadas) para que o diff seja estável e revisável.

O modelo de settings é seccionado (``{secao: {chave: valor}}``), cobrindo o INI
usado pelos emuladores de Switch. Formatos específicos de cada emulador (ex.:
Qt .ini com tipagem) são consumidos por um writer dedicado no adapter — aqui o
domínio permanece agnóstico e testável.

O catálogo aceita v1 (titleId 16 hex, Switch) e v2 (identity tipada); dados
v1 são migrados na carga — o Switch continua sendo um esquema entre os demais.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from steamzero.api import contracts
from steamzero.core import transaction
from steamzero.core.errors import SteamZeroError
from steamzero.domain.game_identity import (
    GameIdentity,
    IdentityScheme,
    validate_identity_value,
)

Settings = dict[str, dict[str, Any]]


class KnownGoodProfileCatalog:
    """Catálogo validado de perfis conhecidos bons; pode estar vazio.

    Aceita v1 (migrado na carga) e v2. Entradas são indexadas por
    ``GameIdentity`` — a identidade de título tipada por plataforma substitui
    o regex de 16 hex do v1 sem bifurcar o schema: v1 é migrado, o Switch
    continua válido e outros esquemas (PSX/PS2/GC/Wii/PS3/WiiU) entram como
    valores do mesmo enum.
    """

    _SCHEMA_V2 = "known-good-profile-v2.schema.json"
    _SCHEMA_V1 = "known-good-profile-v1.schema.json"

    def __init__(self, data: dict[str, Any]) -> None:
        if data.get("schemaVersion") == 1:
            contracts.validate(data, self._SCHEMA_V1)
            data = self.migrate_v1(data)
        contracts.validate(data, self._SCHEMA_V2)
        self.platform: str = data["platform"]
        self._entries: list[dict[str, Any]] = data["entries"]

    @classmethod
    def empty(cls, platform: str) -> KnownGoodProfileCatalog:
        return cls({"schemaVersion": 2, "platform": platform, "entries": []})

    @staticmethod
    def migrate_v1(data: dict[str, Any]) -> dict[str, Any]:
        """Migra um catálogo v1 (titleId 16 hex) para v2 (identity tipada).

        A migração é a prova de que o Switch continua válido após o bump:
        cada ``titleId`` vira ``identity: {scheme: switch-title-id, value}``.
        """
        if data.get("schemaVersion") != 1 or not isinstance(data.get("entries"), list):
            raise SteamZeroError("E-API-SCHEMA", detail="catálogo v1 inválido para migração")
        migrated: list[dict[str, Any]] = []
        for entry in data["entries"]:
            title_id = entry.get("titleId")
            if not isinstance(title_id, str) or not validate_identity_value(
                IdentityScheme.SWITCH_TITLE_ID, title_id
            ):
                raise SteamZeroError(
                    "E-API-SCHEMA", detail=f"titleId v1 inválido para migração: {title_id!r}"
                )
            row = dict(entry)
            row["identity"] = {
                "scheme": IdentityScheme.SWITCH_TITLE_ID.value,
                "value": title_id.upper(),
            }
            row.pop("titleId", None)
            migrated.append(row)
        return {"schemaVersion": 2, "platform": data["platform"], "entries": migrated}

    def lookup(
        self, identity: GameIdentity | str, *, emulator: str | None = None
    ) -> Settings | None:
        """Melhor perfil para o jogo: específico do emulador tem prioridade.

        ``identity`` pode ser um ``GameIdentity`` (recomendado) ou a string
        legada de Title ID — neste caso é interpretada como identidade do
        Switch (catálogo platform switch), mantendo o contrato v1.
        """
        resolved = (
            identity if isinstance(identity, GameIdentity) else self._legacy_identity(identity)
        )
        if resolved is None or resolved.platform != self.platform:
            return None
        canonical = resolved.lookup_key()
        specific: Settings | None = None
        generic: Settings | None = None
        for entry in self._entries:
            entry_identity = self._entry_identity(entry)
            if entry_identity is None or entry_identity.lookup_key() != canonical:
                continue
            if entry.get("emulator") is None:
                generic = entry["settings"]
            elif emulator is not None and entry["emulator"] == emulator:
                specific = entry["settings"]
        return specific or generic

    def _legacy_identity(self, title_id: str) -> GameIdentity | None:
        if self.platform != "switch" or not validate_identity_value(
            IdentityScheme.SWITCH_TITLE_ID, title_id
        ):
            return None
        return GameIdentity.switch(title_id)

    def _entry_identity(self, entry: dict[str, Any]) -> GameIdentity | None:
        raw = entry.get("identity")
        if not isinstance(raw, dict):
            return None
        scheme = IdentityScheme(raw.get("scheme"))
        value = raw.get("value")
        if scheme is IdentityScheme.UNKNOWN or not isinstance(value, str):
            return None
        try:
            return GameIdentity(self.platform, scheme, value)
        except ValueError:
            return None


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
        self, identity: GameIdentity | str, current: Settings, *, emulator: str | None = None
    ) -> SettingsDiff:
        desired = self._catalog.lookup(identity, emulator=emulator)
        if desired is None:
            return SettingsDiff({}, {}, sum(len(v) for v in current.values()))
        return diff_settings(current, desired)

    def plan_apply(
        self,
        identity: GameIdentity | str,
        current: Settings,
        *,
        config_path: Path,
        root: Path,
        emulator: str | None = None,
    ) -> transaction.Plan:
        desired = self._catalog.lookup(identity, emulator=emulator)
        if desired is None:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail=f"nenhum perfil conhecido bom para {identity!r}",
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
