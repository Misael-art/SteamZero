# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Perfis de input retro declarativos, resolvíveis e reversíveis (WI-F6)."""

from __future__ import annotations

import importlib.resources
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import ValidationError

from steamzero.api import contracts
from steamzero.core import ids, journal, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.domain import retropad as retropad_mod
from steamzero.domain.platforms import PlatformRegistry

_SCHEMA = "retro-input-profile-v1.schema.json"
_MAX_ACTIVATION_BYTES = 256 * 1024
_ORIENTATIONS = frozenset({"landscape", "portrait-left", "portrait-right"})
_DIRECTION_INPUTS = {
    "portrait-left": {
        "hat.up": "hat.right",
        "hat.right": "hat.down",
        "hat.down": "hat.left",
        "hat.left": "hat.up",
    },
    "portrait-right": {
        "hat.up": "hat.left",
        "hat.left": "hat.down",
        "hat.down": "hat.right",
        "hat.right": "hat.up",
    },
}


@dataclass(frozen=True)
class RetroInputProfile:
    schema_version: int
    id: str
    revision: int
    label: str
    platforms: tuple[str, ...]
    source: dict[str, str]
    layout: str
    max_players: int
    bindings: tuple[dict[str, Any], ...]
    rotation: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "id": self.id,
            "revision": self.revision,
            "label": self.label,
            "platforms": list(self.platforms),
            "source": dict(self.source),
            "layout": self.layout,
            "maxPlayers": self.max_players,
            "bindings": [dict(binding) for binding in self.bindings],
            "rotation": {
                **self.rotation,
                "allowedOrientations": list(self.rotation["allowedOrientations"]),
            },
        }


def load_input_profile(data: dict[str, Any]) -> RetroInputProfile:
    """Valida um perfil sem executar strings ou aceitar campos laterais."""
    try:
        contracts.validate(data, _SCHEMA)
    except (ValidationError, KeyError, TypeError, ValueError) as exc:
        raise SteamZeroError("E-API-SCHEMA", detail=f"perfil de input inválido: {exc}") from exc

    actions = [str(binding["action"]) for binding in data["bindings"]]
    if len(actions) != len(set(actions)):
        raise SteamZeroError(
            "E-API-SCHEMA", detail=f"perfil {data['id']} possui actions duplicadas"
        )
    rotation = data["rotation"]
    if rotation["defaultOrientation"] not in rotation["allowedOrientations"]:
        raise SteamZeroError(
            "E-API-SCHEMA",
            detail=f"perfil {data['id']} possui orientação default não permitida",
        )
    if rotation["directionalRemap"] == "rotate-with-display" and not {
        "hat.up",
        "hat.right",
        "hat.down",
        "hat.left",
    } <= {str(binding["input"]) for binding in data["bindings"]}:
        raise SteamZeroError(
            "E-API-SCHEMA",
            detail=f"perfil {data['id']} não possui direcional completo para rotação",
        )
    return RetroInputProfile(
        schema_version=int(data["schemaVersion"]),
        id=str(data["id"]),
        revision=int(data["revision"]),
        label=str(data["label"]),
        platforms=tuple(str(item) for item in data["platforms"]),
        source={str(key): str(value) for key, value in data["source"].items()},
        layout=str(data["layout"]),
        max_players=int(data["maxPlayers"]),
        bindings=tuple(dict(item) for item in data["bindings"]),
        rotation={
            "allowedOrientations": tuple(rotation["allowedOrientations"]),
            "defaultOrientation": str(rotation["defaultOrientation"]),
            "directionalRemap": str(rotation["directionalRemap"]),
        },
    )


class InputProfileRegistry:
    """Registry fechado de templates; IDs nunca são paths nem código."""

    def __init__(self, profiles: list[RetroInputProfile]) -> None:
        self._items: dict[str, RetroInputProfile] = {}
        for profile in profiles:
            if profile.id in self._items:
                raise SteamZeroError(
                    "E-API-SCHEMA", detail=f"perfil de input duplicado: {profile.id}"
                )
            self._items[profile.id] = profile

    @classmethod
    def bundled(cls) -> InputProfileRegistry:
        directory = importlib.resources.files("steamzero.input_profiles")
        profiles: list[RetroInputProfile] = []
        for entry in sorted(directory.iterdir(), key=lambda item: item.name):
            if entry.name.endswith(".input.json"):
                value = json.loads(entry.read_text(encoding="utf-8"))
                if not isinstance(value, dict):
                    raise SteamZeroError(
                        "E-API-SCHEMA", detail=f"{entry.name} precisa conter objeto JSON"
                    )
                profiles.append(load_input_profile(value))
        return cls(profiles)

    def get(self, profile_id: str) -> RetroInputProfile:
        try:
            return self._items[profile_id]
        except KeyError as exc:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail=f"perfil de input desconhecido: {profile_id}",
            ) from exc

    def list(self) -> list[RetroInputProfile]:
        return list(self._items.values())


def resolve_bindings(
    profile: RetroInputProfile, orientation: str | None = None
) -> list[dict[str, Any]]:
    """Resolve a rotação de direcionais sem inventar mapeamento de adapter."""
    selected = orientation or str(profile.rotation["defaultOrientation"])
    if selected not in _ORIENTATIONS or selected not in profile.rotation["allowedOrientations"]:
        raise SteamZeroError(
            "E-API-SCHEMA",
            detail=f"orientação {selected!r} não é permitida pelo perfil {profile.id}",
        )
    remap: dict[str, str] = {}
    if selected != "landscape" and profile.rotation["directionalRemap"] == "rotate-with-display":
        remap = _DIRECTION_INPUTS[selected]
    return [
        {**binding, "input": remap.get(str(binding["input"]), binding["input"])}
        for binding in profile.bindings
    ]


class InputProfileManager:
    """Seleciona um perfil por escopo via transação de arquivo G-FULL."""

    def __init__(
        self,
        root: Path,
        *,
        registry: InputProfileRegistry | None = None,
        platforms: PlatformRegistry | None = None,
    ) -> None:
        self._root = root
        self._registry = registry or InputProfileRegistry.bundled()
        self._platforms = platforms or PlatformRegistry.bundled()

    def list_for_platform(self, platform_id: str) -> list[dict[str, Any]]:
        manifest = self._platforms.get(platform_id)
        allowed = [str(item) for item in manifest.controls["profiles"]]
        rows: list[dict[str, Any]] = []
        for profile_id in allowed:
            profile = self._registry.get(profile_id)
            if platform_id not in profile.platforms:
                raise SteamZeroError(
                    "E-API-SCHEMA",
                    detail=f"perfil {profile.id} não declara a plataforma {platform_id}",
                )
            if profile.max_players > int(manifest.controls["maxPlayers"]):
                raise SteamZeroError(
                    "E-API-SCHEMA",
                    detail=f"perfil {profile.id} excede jogadores de {platform_id}",
                )
            rows.append(profile.to_dict())
        return rows

    def plan_activate(
        self,
        *,
        platform_id: str,
        profile_id: str,
        scope: str = "platform",
        scope_id: str | None = None,
        orientation: str | None = None,
    ) -> transaction.Plan:
        manifest = self._platforms.get(platform_id)
        if profile_id not in manifest.controls["profiles"]:
            raise SteamZeroError(
                "E-API-SCHEMA",
                detail=f"perfil {profile_id} não pertence à plataforma {platform_id}",
            )
        profile = self._registry.get(profile_id)
        if platform_id not in profile.platforms:
            raise SteamZeroError(
                "E-API-SCHEMA",
                detail=f"perfil {profile_id} não declara a plataforma {platform_id}",
            )
        target = self._target(platform_id, scope, scope_id)
        selected_orientation = orientation or str(profile.rotation["defaultOrientation"])
        activation = {
            "schemaVersion": 1,
            "platformId": platform_id,
            "scope": scope,
            "scopeId": scope_id,
            "profile": profile.to_dict(),
            "orientation": selected_orientation,
            "resolvedBindings": resolve_bindings(profile, selected_orientation),
        }
        content = json.dumps(
            activation, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail="ativação de input existente não é arquivo regular"
            )
        if target.is_file() and target.stat().st_size > _MAX_ACTIVATION_BYTES:
            raise SteamZeroError("E-API-SCHEMA", detail="ativação de input excede 256 KiB")
        return transaction.plan_write_files(
            {target: content},
            root=self._root,
            kind=f"input-profile.activate:{platform_id}:{scope}",
            skip_unchanged=True,
        )

    def plan_clear(
        self,
        *,
        platform_id: str,
        scope: str,
        scope_id: str | None = None,
    ) -> transaction.Plan:
        """Remove a ativação de um escopo (ex.: perfil por jogo) para que a
        herança volte a valer. A remoção é transacional (G-FULL): backup do
        arquivo é feito e o rollback o restaura."""
        target = self._target(platform_id, scope, scope_id)
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail="ativação de input existente não é arquivo regular"
            )
        if not target.exists():
            return transaction.plan_write_files(
                {},
                root=self._root,
                kind=f"input-profile.clear:{platform_id}:{scope}",
            )
        return transaction.plan_write_files(
            {},
            root=self._root,
            kind=f"input-profile.clear:{platform_id}:{scope}",
            removals={target},
        )

    def apply(self, plan_id: str, confirm_token: str) -> transaction.ApplyResult:
        plan = transaction.load_plan(plan_id)
        if not plan.kind.startswith("input-profile."):
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano não pertence a perfil de input")

        def verify() -> None:
            targets = {Path(action.target) for action in plan.actions}
            targets.update(Path(precondition.target) for precondition in plan.preconditions)
            for target in targets:
                self._load_activation(target)

        smoke = verify if plan.kind.startswith("input-profile.activate:") else None
        return transaction.apply(plan_id, confirm_token, smoke=smoke)

    def rollback(self, operation_id: str) -> transaction.RollbackResult:
        if not ids.is_ulid(operation_id):
            raise SteamZeroError("E-API-SCHEMA", detail="operationId inválido")
        records = journal.read_records(operation_id)
        beginnings = [record for record in records if record.get("type") == "operation.begin"]
        kind = str(beginnings[0].get("kind", "")) if len(beginnings) == 1 else ""
        if not kind.startswith("input-profile."):
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail="operação não pertence a perfil de input"
            )
        return transaction.rollback(operation_id, reason="input-profile-user-request")

    def status(
        self, platform_id: str, *, scope: str = "platform", scope_id: str | None = None
    ) -> dict[str, Any]:
        target = self._target(platform_id, scope, scope_id)
        available = [
            {
                "id": profile["id"],
                "revision": profile["revision"],
                "label": profile["label"],
            }
            for profile in self.list_for_platform(platform_id)
        ]
        try:
            metadata = target.lstat()
        except FileNotFoundError:
            return {
                "state": "unverified",
                "statusLabel": "Perfil não selecionado",
                "active": None,
                "available": available,
            }
        except OSError as exc:
            return {
                "state": "degraded",
                "statusLabel": "Perfil ilegível",
                "detail": str(exc),
                "active": None,
                "available": available,
            }
        if not stat.S_ISREG(metadata.st_mode):
            return {
                "state": "degraded",
                "statusLabel": "Perfil inválido",
                "detail": "ativação de input não é arquivo regular",
                "active": None,
                "available": available,
            }
        try:
            active = self._load_activation(target)
        except (OSError, json.JSONDecodeError, SteamZeroError) as exc:
            return {
                "state": "degraded",
                "statusLabel": "Perfil inválido",
                "detail": str(exc),
                "active": None,
                "available": available,
            }
        # Os bindings existiam resolvidos em disco e ninguém os lia (G45). O
        # `status` passa a publicar a tradução RetroPad, que é a forma que um
        # emulador entende — e a lista do que NÃO traduz, para a tela poder
        # dizer o que não vai valer em vez de prometer mapeamento completo.
        bindings = active.get("resolvedBindings")
        rows = bindings if isinstance(bindings, list) else []
        try:
            retropad = retropad_mod.translate_bindings(rows)
            sem_equivalente = list(retropad_mod.untranslatable(rows))
        except SteamZeroError:
            # Perfil com binding malformado degrada a tradução, não o status:
            # a seleção continua válida e visível (AGENTS.md §8).
            retropad, sem_equivalente = {}, [str(b.get("action") or "") for b in rows]
        return {
            "state": "ready",
            "statusLabel": "Perfil selecionado",
            "active": {
                "id": active["profile"]["id"],
                "revision": active["profile"]["revision"],
                "orientation": active["orientation"],
                "scope": active["scope"],
                "scopeId": active["scopeId"],
                "retropad": retropad,
                "withoutRetropadEquivalent": sem_equivalente,
                # A tradução acima é abstrata e o sufixo dela é provisório (o
                # dispositivo é quem decide entre `_btn` e `_axis`). Quem resolve
                # o índice físico precisa dos bindings crus, então eles deixam de
                # ficar só no arquivo e passam a ser publicados.
                "resolvedBindings": [dict(row) for row in rows],
            },
            "available": available,
        }

    def _load_activation(self, target: Path) -> dict[str, Any]:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(target, flags)
        except OSError as exc:
            raise SteamZeroError(
                "E-CONTENT-UNSAFE-PATH", detail=f"ativação de input ilegível: {exc}"
            ) from exc

        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise SteamZeroError(
                    "E-CONTENT-UNSAFE-PATH",
                    detail="ativação de input não é arquivo regular",
                )
            if metadata.st_size > _MAX_ACTIVATION_BYTES:
                raise SteamZeroError("E-API-SCHEMA", detail="ativação de input excede 256 KiB")
            chunks: list[bytes] = []
            remaining = _MAX_ACTIVATION_BYTES + 1
            while remaining:
                chunk = os.read(descriptor, min(64 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
        finally:
            os.close(descriptor)

        if len(raw) > _MAX_ACTIVATION_BYTES:
            raise SteamZeroError("E-API-SCHEMA", detail="ativação de input excede 256 KiB")
        try:
            value = json.loads(raw.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise SteamZeroError(
                "E-API-SCHEMA", detail="ativação de input não contém UTF-8 válido"
            ) from exc
        if not isinstance(value, dict):
            raise SteamZeroError("E-API-SCHEMA", detail="ativação de input precisa ser objeto")
        required = {
            "schemaVersion",
            "platformId",
            "scope",
            "scopeId",
            "profile",
            "orientation",
            "resolvedBindings",
        }
        if set(value) != required or value["schemaVersion"] != 1:
            raise SteamZeroError("E-API-SCHEMA", detail="ativação de input inválida")
        if not isinstance(value["platformId"], str) or not isinstance(value["scope"], str):
            raise SteamZeroError("E-API-SCHEMA", detail="alvo de input inválido")
        if value["scopeId"] is not None and not isinstance(value["scopeId"], str):
            raise SteamZeroError("E-API-SCHEMA", detail="scopeId de input inválido")
        profile_raw = value["profile"]
        if not isinstance(profile_raw, dict):
            raise SteamZeroError("E-API-SCHEMA", detail="perfil ativo inválido")
        profile = load_input_profile(profile_raw)
        expected = resolve_bindings(profile, str(value["orientation"]))
        if value["resolvedBindings"] != expected:
            raise SteamZeroError("E-API-SCHEMA", detail="bindings resolvidos divergentes")
        if value["platformId"] not in profile.platforms:
            raise SteamZeroError("E-API-SCHEMA", detail="plataforma ativa divergente")
        expected_target = self._target(
            str(value["platformId"]),
            str(value["scope"]),
            value["scopeId"] if isinstance(value["scopeId"], str) else None,
        )
        if target != expected_target:
            raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="alvo de input divergente")
        return value

    def _target(self, platform_id: str, scope: str, scope_id: str | None) -> Path:
        self._platforms.get(platform_id)
        if scope not in {"global", "platform", "game", "device", "mode"}:
            raise SteamZeroError("E-API-SCHEMA", detail=f"escopo de input inválido: {scope}")
        if scope in {"global", "platform"}:
            if scope_id is not None:
                raise SteamZeroError(
                    "E-API-SCHEMA", detail=f"scopeId não é aceito no escopo {scope}"
                )
            subject = "default"
        else:
            if (
                not isinstance(scope_id, str)
                or not scope_id
                or len(scope_id) > 64
                or any(
                    character not in "abcdefghijklmnopqrstuvwxyz0123456789-"
                    for character in scope_id
                )
            ):
                raise SteamZeroError("E-API-SCHEMA", detail="scopeId de input inválido")
            subject = scope_id
        return self._root / "active" / platform_id / f"{scope}-{subject}.json"
