# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Porta única de lifecycle de componentes, roteada pelo tipo de fonte fixado.

O projeto tem dois executores especializados e ambos funcionam:

- ``AdapterEngine`` — fontes portáteis (AppImage, nativo), com digest obrigatório
  e transação sobre o payload;
- ``FlatpakExecutor`` — fontes Flatpak, com remote/ref/commit fixados e rollback
  do deployment.

O que faltava era a porta comum. ``AdapterEngine.plan_install`` recusava fonte
Flatpak com "executor Flatpak ainda não está habilitado" — apesar de o executor
existir, testado, ao lado. O efeito prático: oito dos treze emuladores declarados
usam Flatpak e nenhum podia ser instalado, mesmo com adapter, manifesto e fonte
fixada corretos.

Esta fachada não reimplementa nada. Ela lê a fonte preferida do manifesto e
entrega a operação ao executor que sabe conduzi-la, normalizando o formato de
status para que a UI não precise saber de qual executor a resposta veio.

``ComponentLifecycle`` (G27) é a porta usada por CLI, dashboard e central de
emulação para ``status``/``plan``/``apply``/``rollback``/``launch``/``stop``:

- o executor é decidido pela família da fonte (``route_for``), nunca pelo
  chamador;
- os estados ``missing``/``installed``/``degraded``/``unavailable`` são
  publicados sem colapso — degradado preserva versão, origem e motivo do drift
  e nunca vira "não instalado";
- o plano v3 metadata-only persiste executor, adapter e fingerprint da fonte;
  aquisição e plano delegado nascem somente após confirmação. Envelopes v2 e
  planos Flatpak v1 continuam aplicáveis durante a transição;
- falha de um adapter é agregada em ``unavailable`` com motivo — um componente
  degradado não derruba ``component list`` nem o workspace inteiro.

O que NÃO muda: cada executor mantém suas garantias. Portátil continua exigindo
sha256; Flatpak continua exigindo commit fixado. Fonte sem a garantia da sua
família falha fechado, aqui como antes.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import signal
import subprocess
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from jsonschema import ValidationError

from steamzero.adapters import input_devices
from steamzero.adapters.engine import AdapterEngine, HttpsArtifactPort, PreparedComponent
from steamzero.adapters.flatpak import FlatpakCLI, FlatpakExecutor
from steamzero.adapters.libretro_cores import (
    ArchiveReader,
    LibretroCoreExecutor,
    PreparedLibretroCore,
)
from steamzero.adapters.registry import AdapterManifest, AdapterRegistry, AdapterSource
from steamzero.api import contracts
from steamzero.core import fs, ids, journal, paths, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.core.lock import ResourceLock
from steamzero.core.log import get_logger
from steamzero.core.state import StateStore

#: Famílias de fonte com executor real. Fonte fora daqui não tem lifecycle e
#: precisa falhar fechado — habilitar ação para ela produziria botão que termina
#: em stub.
PORTABLE_SOURCES = frozenset({"appimage", "native"})
FLATPAK_SOURCES = frozenset({"flatpak"})

_PLAN_SCHEMA_V2 = "component-plan-v2.schema.json"
_PLAN_SCHEMA_V3 = "component-plan-v3.schema.json"
_PLAN_SCHEMA_V1 = "component-plan-v1.schema.json"
_DEFAULT_TTL_S = 3600

#: Marcadores de estado do arquivo de operação de reparo (schemaVersion 2).
#: v1 é consumido pelo executor Flatpak no mesmo diretório; o v2 só existe no
#: caminho de reparo do lifecycle.
_REPAIR_OP_SCHEMA = 2
_REPAIR_ACTION = "repair"
_REPAIR_OP_APPLYING = "applying"
_REPAIR_OP_COMMITTED = "committed"
_REPAIR_OP_ROLLED_BACK = "rolled-back"
_REPAIR_OP_RECOVERY_REQUIRED = "recovery-required"
_REPAIR_OP_STATES = frozenset(
    {
        _REPAIR_OP_APPLYING,
        _REPAIR_OP_COMMITTED,
        _REPAIR_OP_ROLLED_BACK,
        _REPAIR_OP_RECOVERY_REQUIRED,
    }
)

Spawn = Callable[[Sequence[str]], int | None]


def spawn_detached(argv: Sequence[str]) -> int | None:
    """Inicia um processo sem shell, em grupo próprio, sem herdar stdio."""
    if not argv:
        return None
    process = subprocess.Popen(  # noqa: S603
        list(argv),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env={**os.environ, "APPIMAGELAUNCHER_DISABLE": "true"},
    )
    return process.pid


@dataclass(frozen=True)
class LifecycleRoute:
    """Para onde uma operação deste adapter deve ir, e por quê."""

    adapter_id: str
    source_type: str
    executor: str
    installable: bool
    reason: str | None = None
    target_version: str | None = None
    end_of_life: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapterId": self.adapter_id,
            "sourceType": self.source_type,
            "executor": self.executor,
            "installable": self.installable,
            "reason": self.reason,
            "targetVersion": self.target_version,
        }


def _preferred(manifest: AdapterManifest, *, allow_eol: bool) -> AdapterSource | None:
    try:
        return manifest.preferred_source(None, allow_eol=allow_eol)
    except SteamZeroError:
        return None


def route_for(manifest: AdapterManifest) -> LifecycleRoute:
    """Decide o executor a partir da fonte fixada, sem executar nada.

    Read-only de propósito: a UI precisa saber se uma ação é aplicável antes de
    oferecê-la, e descobrir isso tentando instalar seria tarde demais.
    """
    source = _preferred(manifest, allow_eol=False)
    if source is None:
        eol = _preferred(manifest, allow_eol=True)
        if eol is not None:
            # Fonte existe mas está marcada como fim de vida: recusar é o
            # comportamento correto, e o motivo precisa ser dizível na UI.
            return LifecycleRoute(
                manifest.id,
                eol.type,
                "none",
                False,
                "a fonte fixada deste componente está marcada como fim de vida",
                end_of_life=True,
            )
        return LifecycleRoute(
            manifest.id, "", "none", False, "o componente não declara fonte instalável"
        )

    if source.type in FLATPAK_SOURCES:
        if not source.ref or not source.remote:
            return LifecycleRoute(
                manifest.id, source.type, "none", False, "fonte Flatpak sem ref ou remote fixados"
            )
        return LifecycleRoute(
            manifest.id, source.type, "flatpak", True, target_version=source.version
        )

    if source.type in PORTABLE_SOURCES:
        if not source.sha256:
            return LifecycleRoute(
                manifest.id, source.type, "none", False, "fonte portátil sem sha256"
            )
        return LifecycleRoute(
            manifest.id, source.type, "engine", True, target_version=source.version
        )

    if source.type == "archive" and manifest.kind == "core" and manifest.core is not None:
        if source.sha256 is None:
            return LifecycleRoute(
                manifest.id, source.type, "none", False, "arquivo de core sem sha256"
            )
        return LifecycleRoute(
            manifest.id, source.type, "libretro", True, target_version=source.version
        )

    return LifecycleRoute(
        manifest.id,
        source.type,
        "none",
        False,
        f"não há executor para fonte do tipo '{source.type}'",
    )


#: Vocabulário público de estado do componente (migração m0017).
#:
#: ``missing`` não instalado, mas instalável · ``installed`` íntegro na fonte
#: fixada · ``outdated`` íntegro, porém a fonte fixada avançou · ``degraded``
#: artefato ou metadados não conferem · ``repairing`` reparo em curso ·
#: ``unavailable`` sem executor ou probe falhou, com motivo · ``retired``
#: adapter fora do conjunto suportado por decisão registrada.
LIFECYCLE_STATES = frozenset(
    {
        "missing",
        "installed",
        "outdated",
        "degraded",
        "repairing",
        "unavailable",
        "retired",
    }
)

#: Só faz sentido reparar o que a observação já reprovou.
_REPAIRABLE_STATES = frozenset({"degraded", "outdated"})


def routes_for(registry: AdapterRegistry) -> dict[str, LifecycleRoute]:
    """Rota de cada adapter declarado, para o read model publicar aplicabilidade."""
    return {manifest.id: route_for(manifest) for manifest in registry.list()}


def normalize_status(raw: dict[str, Any], route: LifecycleRoute) -> dict[str, Any]:
    """Formato único de status, venha do engine ou do executor Flatpak.

    Os dois publicam ``id`` e ``state``; o resto diverge (``version``/``sha256``
    de um lado, ``commit``/``remote`` do outro). A UI consome esta forma e não
    precisa saber quem respondeu. O formato normalizado (G27) tem: ``state``,
    ``installed``, ``installable``, ``executor``, ``sourceType``, ``version``,
    ``targetVersion``, ``origin``, ``detail`` e ``endOfLife`` — sem colapso de
    ``degraded`` em ``missing`` (versão e origem do drift são preservadas).
    """
    state = str(raw.get("state", "unknown"))
    installed = state == "installed"
    version = raw.get("version") or raw.get("commit")
    target = raw.get("targetVersion") or raw.get("targetCommit") or route.target_version
    detail = raw.get("detail") or route.reason
    return {
        "id": route.adapter_id,
        "state": state,
        "installed": installed,
        "installable": route.installable,
        "executor": route.executor,
        "sourceType": route.source_type,
        "version": str(version) if version else None,
        "targetVersion": str(target) if target else None,
        "origin": raw.get("origin"),
        "detail": detail,
        "endOfLife": bool(raw.get("endOfLife", route.end_of_life)),
    }


def unavailable_status(route: LifecycleRoute) -> dict[str, Any]:
    """Status de componente sem executor: declarado, não instalável, com motivo.

    Publicar ``unverified`` sem motivo é como a central passou a mostrar linhas
    mortas — o usuário vê uma plataforma listada e nenhuma explicação de por que
    nada acontece ao clicar.
    """
    return {
        "id": route.adapter_id,
        "state": "unavailable",
        "installed": False,
        "installable": False,
        "executor": route.executor,
        "sourceType": route.source_type,
        "version": None,
        "targetVersion": route.target_version,
        "origin": None,
        "detail": route.reason,
        "endOfLife": route.end_of_life,
    }


def failed_status(route: LifecycleRoute, error: Exception) -> dict[str, Any]:
    """Status de componente cujo executor falhou ao responder.

    A falha vira ``unavailable`` com motivo dizível, em vez de derrubar a lista
    inteira ou o workspace — agregação de falha por adapter (G27).
    """
    detail = str(error).strip()[:500] or route.reason or "falha ao consultar o componente"
    return {
        "id": route.adapter_id,
        "state": "unavailable",
        "installed": False,
        "installable": route.installable,
        "executor": route.executor,
        "sourceType": route.source_type,
        "version": None,
        "targetVersion": route.target_version,
        "origin": None,
        "detail": detail,
        "endOfLife": route.end_of_life,
    }


@dataclass(frozen=True)
class ComponentPlan:
    """Envelope executor-independente de plano de componente (schemas v2/v3).

    No v3, o executor e o fingerprint ficam no envelope e ``delegated`` vazio
    prova que nenhuma aquisição foi materializada. O v2 legado referencia um
    plano Flatpak v1 ou transacional e permanece legível para atualização sem
    invalidar confirmações já emitidas.
    """

    plan_id: str
    confirm_token: str
    adapter_id: str
    executor: str
    action: str
    source_fingerprint: dict[str, Any]
    delegated: dict[str, Any]
    status: str
    created_at: str
    expires_at: str
    preview: str
    rollback_guarantee: str
    schema_version: int = 3

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "planId": self.plan_id,
            "confirmToken": self.confirm_token,
            "adapterId": self.adapter_id,
            "executor": self.executor,
            "action": self.action,
            "sourceFingerprint": self.source_fingerprint,
            "delegated": self.delegated,
            "status": self.status,
            "createdAt": self.created_at,
            "expiresAt": self.expires_at,
            "rollbackGuarantee": self.rollback_guarantee,
            "preview": self.preview,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ComponentPlan:
        return cls(
            plan_id=str(data["planId"]),
            confirm_token=str(data["confirmToken"]),
            adapter_id=str(data["adapterId"]),
            executor=str(data["executor"]),
            action=str(data["action"]),
            source_fingerprint=dict(data["sourceFingerprint"]),
            delegated=dict(data["delegated"]),
            status=str(data["status"]),
            created_at=str(data["createdAt"]),
            expires_at=str(data["expiresAt"]),
            rollback_guarantee=str(data["rollbackGuarantee"]),
            preview=str(data["preview"]),
            schema_version=int(data["schemaVersion"]),
        )


@dataclass(frozen=True)
class RepairOperation:
    """Operação de reparo durável (schemaVersion 2, Etapa 1).

    Nasce em ``applying`` ANTES de qualquer efeito no deployment e é o que
    permite distinguir reparo interrompido de corrupção nova. ``previous_state``
    preserva o estado observado antes da mutação para restauração no rollback.
    """

    operation_id: str
    plan_id: str
    adapter_id: str
    action: str
    state: str
    manifest_hash: str
    previous_state: str
    started_at: str
    error: str | None = None
    schema_version: int = _REPAIR_OP_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "operationId": self.operation_id,
            "planId": self.plan_id,
            "adapterId": self.adapter_id,
            "action": self.action,
            "state": self.state,
            "manifestHash": self.manifest_hash,
            "previousState": self.previous_state,
            "startedAt": self.started_at,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RepairOperation:
        return cls(
            operation_id=str(data["operationId"]),
            plan_id=str(data["planId"]),
            adapter_id=str(data["adapterId"]),
            action=str(data["action"]),
            state=str(data["state"]),
            manifest_hash=str(data["manifestHash"]),
            previous_state=str(data["previousState"]),
            started_at=str(data["startedAt"]),
            error=str(data["error"]) if data.get("error") is not None else None,
            schema_version=int(data["schemaVersion"]),
        )


class ComponentLifecycle:
    """Fachada de lifecycle usada por CLI, dashboard e central de emulação.

    Nenhum chamador escolhe executor: a família da fonte fixada no manifesto
    decide. Falhas de um adapter viram ``unavailable`` com motivo, sem derrubar
    os demais. Planos v2 sobrevivem a processos diferentes; planos Flatpak v1
    continuam aplicáveis durante a transição.
    """

    def __init__(
        self,
        store: StateStore,
        registry: AdapterRegistry,
        *,
        artifacts: Any = None,
        flatpak_factory: Callable[[], FlatpakCLI] = FlatpakCLI,
        which: Callable[[str], str | None] = shutil.which,
        spawn: Spawn = spawn_detached,
        now: Callable[[], datetime] | None = None,
        libretro_core_root: Path | None = None,
        libretro_archive_reader: ArchiveReader | None = None,
        retroarch_config: input_devices.ManagedRetroArchConfig | None = None,
    ) -> None:
        # Preguiçoso: resolver o config gerenciado lê o `retroarch.cfg` do
        # usuário, e construir um lifecycle não pode custar isso.
        self._retroarch_config_override = retroarch_config
        self._retroarch_config_cache: input_devices.ManagedRetroArchConfig | None = None
        self._store = store
        self._registry = registry
        self._artifacts = artifacts if artifacts is not None else HttpsArtifactPort()
        self._flatpak_factory = flatpak_factory
        self._which = which
        self._spawn = spawn
        self._now = now or (lambda: datetime.now(UTC))
        self._libretro_core_root = libretro_core_root
        self._libretro_archive_reader = libretro_archive_reader

    # ------------------------------------------------------------------ status
    def status(self, adapter_id: str) -> dict[str, Any]:
        """Status normalizado do componente, roteado pela família da fonte.

        Depois de observar o deployment real, o marcador ``repairing`` é
        reconciliado: só é exposto enquanto existir operação de reparo válida em
        curso; um marcador órfão volta ao estado observado com diagnóstico.
        """
        observed = self._observe_state(adapter_id)
        tombstone = self._registry.retired(adapter_id)
        if tombstone is not None:
            return {
                **observed,
                "state": "retired",
                "installable": False,
                "detail": tombstone.reason,
                "retiredAt": tombstone.retired_at,
                "replacementAdapterId": tombstone.replacement_adapter_id,
                "deploymentPolicy": tombstone.deployment_policy,
                "dataPolicy": tombstone.data_policy,
                "deploymentState": observed["state"],
            }
        return self._reconcile_repairing(adapter_id, observed)

    def _observe_state(self, adapter_id: str) -> dict[str, Any]:
        """Estado observado pelo executor, sem leitura/escrita de marcadores."""
        manifest = self._registry.get(adapter_id)
        route = route_for(manifest)
        try:
            if route.executor == "flatpak":
                return normalize_status(self._flatpak().status(adapter_id), route)
            if route.executor == "engine":
                return normalize_status(self._engine().status(adapter_id), route)
            if route.executor == "libretro":
                return normalize_status(self._libretro().status(adapter_id), route)
            if route.end_of_life and route.source_type in FLATPAK_SOURCES:
                # EOL não é ausência: o executor ainda observa o deployment.
                # Consultá-lo preserva versão/origem/existência instalada.
                return normalize_status(self._flatpak().status(adapter_id), route)
            if route.end_of_life and route.source_type in PORTABLE_SOURCES:
                return normalize_status(self._engine().status(adapter_id), route)
            return unavailable_status(route)
        except Exception as exc:
            return failed_status(route, exc)

    def _reconcile_repairing(self, adapter_id: str, observed: dict[str, Any]) -> dict[str, Any]:
        """Expõe ``repairing`` só com operação válida ativa; órfão reconcilia.

        Um marcador ``repairing`` sem arquivo de operação válido em ``applying``
        é órfão (operação vencida, apagada ou decreto de crash antes da
        persistência). Nada além do marcador existe para corrigi-lo: o estado
        verdadeiro é o que o executor observa no deployment. Reconcilia e emite
        diagnóstico auditável (evento + log estruturado).
        """
        try:
            row = self._store.get_component(adapter_id)
        except Exception:
            return observed
        if row is None or str(row.get("state")) != "repairing":
            return observed
        operation_id = row.get("operation_id")
        active: RepairOperation | None = None
        if isinstance(operation_id, str):
            active = self._try_load_repair_operation(operation_id)
        if active is not None and active.state == _REPAIR_OP_APPLYING:
            repairing = dict(observed)
            repairing["state"] = "repairing"
            repairing["installed"] = False
            repairing.setdefault("detail", "reparo em curso")
            return repairing
        reason = (
            "componente marcado repairing sem operation_id"
            if not isinstance(operation_id, str)
            else (
                "arquivo de operação de reparo ausente"
                if active is None
                else f"operação de reparo não está em applying ({active.state})"
            )
        )
        manifest = self._registry.get(adapter_id)
        # Reconciliar um marcador não pode derrubar uma leitura de status: a
        # persistência e o evento são best-effort (o estado real vem do proxy).
        with suppress(Exception):
            self._store.save_component(
                {
                    "id": adapter_id,
                    "adapter_id": adapter_id,
                    "kind": manifest.kind,
                    "version": observed.get("version"),
                    "origin": observed.get("origin"),
                    "state": str(observed["state"]),
                    "manifest_hash": manifest.manifest_hash,
                    "operation_id": None,
                }
            )
            self._store.append_event(
                "component.state",
                entity=f"component:{adapter_id}",
                payload={
                    "from": "repairing",
                    "to": observed["state"],
                    "reconciled": True,
                    "reason": reason,
                },
            )
        with suppress(Exception):
            get_logger().warning(
                "component.repair.reconciled",
                componentId=adapter_id,
                operationId=operation_id,
                reason=reason,
                observedState=observed["state"],
            )
        return observed

    def _mark_repairing(
        self, manifest: AdapterManifest, observed: dict[str, Any], plan_id: str
    ) -> str:
        """Registra o reparo durável ANTES de qualquer efeito no deployment.

        O arquivo de operação (schemaVersion 2) nasce em ``applying`` no mesmo
        diretório das operações Flatpak e é quem permite ao recovery distinguir
        reparo interrompido de corrupção nova. Falha de persistência AQUI aborta
        o apply com ``E-STATE-INTEGRITY`` — reparar sem intent durável não começa.
        Se já houver uma operação de reparo em ``applying`` para o mesmo adapter
        (restart/reaplicação de plano), reusa-a mantendo a idempotência.
        """
        existing = self._active_repair_operation(manifest.id)
        if existing is not None:
            return existing.operation_id
        operation_id = ids.new_ulid()
        operation = RepairOperation(
            operation_id=operation_id,
            plan_id=plan_id,
            adapter_id=manifest.id,
            action=_REPAIR_ACTION,
            state=_REPAIR_OP_APPLYING,
            manifest_hash=manifest.manifest_hash,
            previous_state=str(observed["state"]),
            started_at=self._utc_now().isoformat(),
        )
        try:
            self._save_repair_operation(operation)
            self._store.save_component(
                {
                    "id": manifest.id,
                    "adapter_id": manifest.id,
                    "kind": manifest.kind,
                    "version": observed.get("version"),
                    "origin": observed.get("origin"),
                    "state": "repairing",
                    "manifest_hash": manifest.manifest_hash,
                    "operation_id": operation_id,
                }
            )
        except Exception as exc:
            raise SteamZeroError(
                "E-STATE-INTEGRITY",
                detail=f"falha ao registrar reparo de {manifest.id}: {exc}",
            ) from exc
        return operation_id

    def verify(self, adapter_id: str) -> dict[str, Any]:
        """Confere o deployment contra a fonte fixada. Não muta nada.

        Deliberadamente **fora** do fluxo plan/apply: verificação não muda
        estado, e exigir token de confirmação para uma leitura treinaria o
        operador a confirmar sem ler — o que corrói o valor da confirmação
        justamente onde ela importa, que é no reparo e na desinstalação.

        A conferência é a que cada executor já sabe fazer: o engine reidrata o
        SHA-256 do payload em disco, o Flatpak compara o commit implantado com
        o pinado. ``verified`` é verdadeiro somente em ``installed`` — nem
        ``outdated`` conta, porque o artefato não é o que o manifesto fixa.
        """
        status = self.status(adapter_id)
        state = str(status["state"])
        status["verified"] = state == "installed"
        status["repairable"] = state in _REPAIRABLE_STATES
        if status["verified"]:
            status.setdefault("detail", None)
        elif not status.get("detail"):
            status["detail"] = f"componente em '{state}'"
        return status

    def status_all(self) -> list[dict[str, Any]]:
        """Status de todos os adapters, com falha agregada por componente.

        Um adapter cujo executor falhou vira uma linha ``unavailable`` com
        motivo — nunca derruba a lista nem o workspace inteiro (G27).
        """
        rows: list[dict[str, Any]] = []
        for manifest in self._registry.list_including_retired():
            try:
                rows.append(self.status(manifest.id))
            except Exception as exc:
                rows.append(
                    {
                        "id": manifest.id,
                        "state": "unavailable",
                        "installed": False,
                        "installable": False,
                        "executor": "none",
                        "sourceType": "",
                        "version": None,
                        "targetVersion": None,
                        "origin": None,
                        "detail": f"falha ao consultar o componente: {exc}"[:500],
                        "endOfLife": False,
                    }
                )
        return rows

    # ------------------------------------------------------------------- plan
    def plan(self, adapter_id: str, action: str = "install") -> ComponentPlan:
        """Planeja install/update/uninstall pelo executor da fonte, persistido.

        O envelope v2 é gravado em ``state/plans/<planId>.json``; o plano
        delegado do executor fica referenciado por id. Um processo novo pode
        aplicar o envelope pelo ``planId``.
        """
        manifest = self._registry.get(adapter_id)
        tombstone = self._registry.retired(adapter_id)
        route = route_for(manifest)
        if tombstone is not None and action != "uninstall":
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail=f"{adapter_id} foi retirado: {tombstone.reason}",
            )
        if not route.installable and action != "uninstall":
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail=route.reason or "componente sem executor de lifecycle",
            )
        if action not in {"install", "update", "uninstall", "repair", "stop"}:
            raise SteamZeroError("E-API-SCHEMA", detail="ação de componente não permitida")
        if action == "stop" and route.executor != "engine":
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail="parada só é gerenciada para payload portátil do SteamZero",
            )
        if action in {"repair", "stop"}:
            # Estas duas intenções dependem do deployment observado: reparar
            # algo íntegro e parar algo ausente seriam confirmações enganosas.
            # A observação é estritamente local; resolução e aquisição remotas
            # continuam adiadas para apply.
            observed = str(self.status(adapter_id)["state"])
            allowed = _REPAIRABLE_STATES if action == "repair" else {"installed", "outdated"}
            if observed not in allowed:
                code = "E-API-SCHEMA" if action == "repair" else "E-COMPONENT-DEGRADED"
                raise SteamZeroError(
                    code,
                    detail=f"{adapter_id} está em '{observed}'; {action} exige {sorted(allowed)}",
                )

        # v3 congela somente a intenção e os metadados confiáveis do manifesto.
        # Resolver Flatpak, baixar AppImage/native/archive, extrair core e gerar
        # o plano transacional são preparo da execução: começam apenas depois
        # que o operador confirma este envelope.
        fingerprint = self._source_fingerprint(manifest, route)
        effective = (
            "noop"
            if action in {"install", "update"} and self._persisted_target_matches(manifest, route)
            else action
        )
        delegated: dict[str, Any] = {}
        target = route.target_version or "versão fixada no manifesto"
        preview = (
            f"{effective} {manifest.id}\n"
            f"fonte: {route.source_type}\n"
            f"versão alvo: {target}\n"
            "aquisição e verificação começam somente após a confirmação"
        )
        rollback_guarantee = (
            "G-NONE"
            if action == "stop"
            else "preserva dados do aplicativo e restaura o deployment anterior"
            if route.executor == "flatpak"
            else "G-FULL: restaura somente artefatos gerenciados pelo SteamZero"
        )
        confirm_token = secrets.token_urlsafe(24)
        now = self._utc_now()
        envelope = ComponentPlan(
            plan_id=ids.new_ulid(),
            confirm_token=confirm_token,
            adapter_id=manifest.id,
            executor=route.executor,
            action=effective,
            source_fingerprint=fingerprint,
            delegated=delegated,
            status="pending",
            created_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=_DEFAULT_TTL_S)).isoformat(),
            preview=preview,
            rollback_guarantee=rollback_guarantee,
        )
        self._save_plan(envelope)
        return envelope

    # ------------------------------------------------------------------ apply
    def validate_apply(self, plan_id: str, confirm_token: str) -> dict[str, str]:
        """Valida confirmação e contexto sem iniciar preparo ou efeito.

        A bridge usa esta leitura antes de enfileirar o job. A validação é
        repetida pelo worker em :meth:`apply`, sob o contexto efetivo, então
        uma mudança entre enqueue e execução continua falhando fechada.
        """
        raw = self._read_plan_file(plan_id)
        schema_version = int(raw.get("schemaVersion", 0))
        schema_name = {
            1: _PLAN_SCHEMA_V1,
            2: _PLAN_SCHEMA_V2,
            3: _PLAN_SCHEMA_V3,
        }[schema_version]
        try:
            contracts.validate(raw, schema_name)
        except ValidationError as exc:
            raise SteamZeroError(
                "E-STATE-INTEGRITY",
                detail=f"plano de componente v{schema_version} inválido: {exc}",
            ) from exc
        if schema_version == 1:
            self._validate_confirmation_fields(raw, confirm_token)
            return {
                "adapterId": str(raw["adapterId"]),
                "action": str(raw["action"]),
                "executor": "flatpak",
            }
        envelope = ComponentPlan.from_dict(raw)
        self._validate_pending(envelope, confirm_token)
        manifest = self._registry.get(envelope.adapter_id)
        tombstone = self._registry.retired(envelope.adapter_id)
        if tombstone is not None and envelope.action != "uninstall":
            raise SteamZeroError(
                "E-TX-STALE-PLAN",
                detail=f"{envelope.adapter_id} foi retirado após o plano",
            )
        route = route_for(manifest)
        if route.executor != envelope.executor:
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail="executor do componente mudou após o plano"
            )
        if self._source_fingerprint(manifest, route) != envelope.source_fingerprint:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="manifesto mudou após o plano")
        return {
            "adapterId": envelope.adapter_id,
            "action": envelope.action,
            "executor": envelope.executor,
        }

    def apply(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        """Aplica um plano v2 (ou Flatpak v1 legado) e devolve o resultado.

        O fingerprint da fonte é recalculado contra o manifesto ATUAL: fonte ou
        manifesto mudados após o plano geram ``E-TX-STALE-PLAN`` sem efeito.
        """
        raw = self._read_plan_file(plan_id)
        if raw.get("schemaVersion") == 1:
            # Transição: planos Flatpak v1 continuam aplicáveis pelo mesmo id.
            try:
                contracts.validate(raw, _PLAN_SCHEMA_V1)
            except ValidationError as exc:
                raise SteamZeroError(
                    "E-STATE-INTEGRITY", detail=f"plano de componente v1 inválido: {exc}"
                ) from exc
            result = self._flatpak().apply(plan_id, confirm_token)
            return {
                "status": result.status,
                "operationId": result.operation_id,
                "adapterId": result.adapter_id,
                "executor": "flatpak",
                "planVersion": 1,
            }
        schema_version = int(raw.get("schemaVersion", 0))
        schema_name = _PLAN_SCHEMA_V3 if schema_version == 3 else _PLAN_SCHEMA_V2
        try:
            contracts.validate(raw, schema_name)
        except ValidationError as exc:
            raise SteamZeroError(
                "E-STATE-INTEGRITY",
                detail=f"plano de componente v{schema_version} inválido: {exc}",
            ) from exc
        envelope = ComponentPlan.from_dict(raw)
        self._validate_pending(envelope, confirm_token)
        manifest = self._registry.get(envelope.adapter_id)
        tombstone = self._registry.retired(envelope.adapter_id)
        if tombstone is not None and envelope.action != "uninstall":
            raise SteamZeroError(
                "E-TX-STALE-PLAN",
                detail=f"{envelope.adapter_id} foi retirado após o plano",
            )
        route = route_for(manifest)
        if route.executor != envelope.executor:
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail="executor do componente mudou após o plano"
            )
        fingerprint = self._source_fingerprint(manifest, route)
        if fingerprint != envelope.source_fingerprint:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="manifesto mudou após o plano")
        if envelope.schema_version == 3:
            return self._apply_deferred(envelope, manifest, route)
        if envelope.action == "stop":
            if envelope.executor != "engine":
                raise SteamZeroError("E-TX-STALE-PLAN", detail="executor de parada mudou")
            self._mark_applied(envelope)
            stop_result = self.stop(envelope.adapter_id)
            return {**stop_result, "executor": "engine", "planVersion": 2}
        repair_op_id: str | None = None
        repair_observed: dict[str, Any] | None = None
        if envelope.executor == "flatpak":
            if envelope.action == "repair":
                repair_observed = self._observe_state(envelope.adapter_id)
                repair_op_id = self._mark_repairing(manifest, repair_observed, envelope.plan_id)
            delegated_id = str(envelope.delegated["flatpakPlanId"])
            try:
                result = self._flatpak().apply(delegated_id, confirm_token)
            except Exception:
                if repair_op_id is not None:
                    self._finish_failed_repair(repair_op_id, manifest, repair_observed)
                raise
            if repair_op_id is not None:
                self._commit_repair_operation(repair_op_id)
            self._mark_applied(envelope)
            return {
                "status": result.status,
                "operationId": result.operation_id,
                "adapterId": result.adapter_id,
                "executor": "flatpak",
                "planVersion": 2,
            }
        if envelope.executor == "libretro":
            cores = self._libretro()
            source = manifest.preferred_source("archive", allow_eol=False)
            plan = transaction.load_plan(str(envelope.delegated["transactionPlanId"]))
            prepared_core = PreparedLibretroCore(manifest, source, plan)
            with ResourceLock(
                f"component:libretro:{envelope.adapter_id}",
                job_id=ids.new_ulid(),
                lease_seconds=3600,
            ):
                self._revalidate_libretro_apply(envelope, cores, prepared_core)
                core_result = cores.apply(prepared_core, confirm_token)
            self._mark_applied(envelope)
            return {
                "status": core_result.status,
                "operationId": core_result.operation_id,
                "adapterId": envelope.adapter_id,
                "executor": "libretro",
                "planVersion": 2,
            }
        engine = self._engine()
        source = manifest.preferred_source(route.source_type, allow_eol=False)
        plan = transaction.load_plan(str(envelope.delegated["transactionPlanId"]))
        prepared = PreparedComponent(manifest, source, plan)

        def smoke() -> None:
            self._engine_smoke(engine, manifest)

        # Revalida plano e deployment sob lock (padrão do executor Flatpak):
        # efeito só começa com o contexto que autorizou o plano ainda verdadeiro.
        with ResourceLock(
            f"component:engine:{envelope.adapter_id}",
            job_id=ids.new_ulid(),
            lease_seconds=3600,
        ):
            self._revalidate_engine_apply(envelope, engine)
            if envelope.action == "repair":
                repair_observed = self._observe_state(envelope.adapter_id)
                repair_op_id = self._mark_repairing(manifest, repair_observed, envelope.plan_id)
            try:
                applied = engine.apply(
                    prepared,
                    confirm_token,
                    smoke=None if envelope.action == "uninstall" else smoke,
                )
            except Exception:
                if repair_op_id is not None:
                    self._finish_failed_repair(repair_op_id, manifest, repair_observed)
                raise
        if repair_op_id is not None:
            self._commit_repair_operation(repair_op_id)
        self._mark_applied(envelope)
        return {
            "status": applied.status,
            "operationId": applied.operation_id,
            "adapterId": envelope.adapter_id,
            "executor": "engine",
            "planVersion": 2,
        }

    def _apply_deferred(
        self,
        envelope: ComponentPlan,
        manifest: AdapterManifest,
        route: LifecycleRoute,
    ) -> dict[str, Any]:
        """Materializa e aplica um plano v3 somente depois da confirmação.

        O envelope já teve token, TTL, executor e fingerprint revalidados por
        :meth:`apply`. Cada executor continua dono de sua transação e de seu
        rollback; a diferença é temporal: rede, download e extração começam
        aqui, nunca em :meth:`plan`.
        """
        if envelope.action == "noop":
            verified = self.verify(envelope.adapter_id)
            if not verified["verified"]:
                raise SteamZeroError(
                    "E-TX-STALE-PLAN",
                    detail="deployment mudou após o plano idempotente",
                )
            self._mark_applied(envelope)
            return {
                "status": "noop",
                "operationId": "",
                "adapterId": envelope.adapter_id,
                "executor": route.executor,
                "planVersion": 3,
            }
        if envelope.action == "stop":
            self._mark_applied(envelope)
            return {**self.stop(envelope.adapter_id), "executor": "engine", "planVersion": 3}

        repair_op_id: str | None = None
        repair_observed: dict[str, Any] | None = None
        if envelope.action == "repair":
            repair_observed = self._observe_state(envelope.adapter_id)
            if repair_observed["state"] not in _REPAIRABLE_STATES:
                raise SteamZeroError(
                    "E-TX-STALE-PLAN",
                    detail=(
                        f"estado do componente mudou após o plano ({repair_observed['state']})"
                    ),
                )

        if route.executor == "flatpak":
            executor = self._flatpak()
            delegated = (
                executor.plan_uninstall(envelope.adapter_id)
                if envelope.action == "uninstall"
                else executor.plan_install(envelope.adapter_id)
            )
            if envelope.action == "repair":
                repair_op_id = self._mark_repairing(
                    manifest, repair_observed or {}, envelope.plan_id
                )
            try:
                flatpak_result = executor.apply(delegated.plan_id, delegated.confirm_token)
            except Exception:
                if repair_op_id is not None:
                    self._finish_failed_repair(repair_op_id, manifest, repair_observed)
                raise
            if repair_op_id is not None:
                self._commit_repair_operation(repair_op_id)
            self._mark_applied(envelope)
            return {
                "status": flatpak_result.status,
                "operationId": flatpak_result.operation_id,
                "adapterId": flatpak_result.adapter_id,
                "executor": "flatpak",
                "planVersion": 3,
            }

        if route.executor == "libretro":
            cores = self._libretro()
            prepared_core = (
                cores.plan_uninstall(envelope.adapter_id)
                if envelope.action == "uninstall"
                else cores.plan_install(
                    envelope.adapter_id,
                    force=envelope.action == "repair",
                )
            )
            with ResourceLock(
                f"component:libretro:{envelope.adapter_id}",
                job_id=ids.new_ulid(),
                lease_seconds=3600,
            ):
                if self._source_fingerprint(manifest, route) != envelope.source_fingerprint:
                    raise SteamZeroError(
                        "E-TX-STALE-PLAN", detail="manifesto do core mudou após o preparo"
                    )
                cores.validate_plan(prepared_core)
                core_result = cores.apply(prepared_core, prepared_core.plan.confirm_token)
            self._mark_applied(envelope)
            return {
                "status": core_result.status,
                "operationId": core_result.operation_id,
                "adapterId": envelope.adapter_id,
                "executor": "libretro",
                "planVersion": 3,
            }

        engine = self._engine()
        prepared = (
            engine.plan_uninstall(envelope.adapter_id)
            if envelope.action == "uninstall"
            else engine.plan_install(
                envelope.adapter_id,
                force=envelope.action == "repair",
            )
        )

        def smoke() -> None:
            self._engine_smoke(engine, manifest)

        with ResourceLock(
            f"component:engine:{envelope.adapter_id}",
            job_id=ids.new_ulid(),
            lease_seconds=3600,
        ):
            if self._source_fingerprint(manifest, route) != envelope.source_fingerprint:
                raise SteamZeroError(
                    "E-TX-STALE-PLAN", detail="manifesto do componente mudou após o preparo"
                )
            if envelope.action == "repair":
                repair_op_id = self._mark_repairing(
                    manifest, repair_observed or {}, envelope.plan_id
                )
            try:
                engine_result = engine.apply(
                    prepared,
                    prepared.plan.confirm_token,
                    smoke=None if envelope.action == "uninstall" else smoke,
                )
            except Exception:
                if repair_op_id is not None:
                    self._finish_failed_repair(repair_op_id, manifest, repair_observed)
                raise
        if repair_op_id is not None:
            self._commit_repair_operation(repair_op_id)
        self._mark_applied(envelope)
        return {
            "status": engine_result.status,
            "operationId": engine_result.operation_id,
            "adapterId": envelope.adapter_id,
            "executor": "engine",
            "planVersion": 3,
        }

    def _persisted_target_matches(self, manifest: AdapterManifest, route: LifecycleRoute) -> bool:
        """Indica noop por metadados duráveis, sem sondagem ou rede.

        O apply ainda observa e verifica o deployment real. Assim o preview é
        rápido e idempotente, mas um registro obsoleto nunca autoriza sucesso
        falso nem impede que o usuário gere um novo plano após o erro stale.
        """
        persisted = self._store.get_component(manifest.id)
        return bool(
            persisted
            and persisted.get("state") == "installed"
            and persisted.get("version") == route.target_version
            and persisted.get("manifest_hash") == manifest.manifest_hash
        )

    # --------------------------------------------------------------- rollback
    def rollback(self, operation_id: str) -> dict[str, Any]:
        """Reverte operação Flatpak (arquivo próprio), transacional do engine
        ou, no caso de reparo em curso, reconcilia o marcador para o estado
        observado."""
        operation_path = paths.component_operation_path(operation_id)
        if operation_path.is_file() and not operation_path.is_symlink():
            repair = self._repair_operation_from_file(operation_path)
            if repair is not None:
                if repair.state != _REPAIR_OP_APPLYING:
                    raise SteamZeroError(
                        "E-TX-STALE-PLAN",
                        detail=f"operação de reparo não está em applying ({repair.state})",
                    )
                observed = self._observe_state(repair.adapter_id)
                manifest = self._registry.get(repair.adapter_id)
                self._finish_failed_repair(operation_id, manifest, observed)
                return {
                    "status": "rolled-back",
                    "operationId": operation_id,
                    "adapterId": repair.adapter_id,
                    "executor": "repair",
                    "observedState": observed["state"],
                }
            flatpak_result = self._flatpak().rollback(operation_id)
            return {
                "status": flatpak_result.status,
                "operationId": flatpak_result.operation_id,
                "adapterId": flatpak_result.adapter_id,
                "executor": "flatpak",
            }
        rolled = transaction.rollback(operation_id, reason="component-manual")
        adapter_id = self._transaction_operation_adapter(operation_id)
        if adapter_id is not None:
            # O rollback já restaurou os arquivos; a persistência no banco
            # é apenas o espelho — falha aqui não invalida a operação.
            with suppress(Exception):
                route = route_for(self._registry.get(adapter_id))
                if route.executor == "libretro":
                    self._libretro().persist_status(adapter_id)
                else:
                    self._engine().persist_status(adapter_id)
        executor = "engine"
        if (
            adapter_id is not None
            and route_for(self._registry.get(adapter_id)).executor == "libretro"
        ):
            executor = "libretro"
        return {
            "status": rolled.status,
            "operationId": rolled.operation_id,
            "executor": executor,
            "restored": list(rolled.restored),
            "adapterId": adapter_id,
        }

    def _operation_adapter_id(self, operation_id: str) -> str | None:
        """Retorna o dono verificável de uma operação de componente.

        A bridge usa este fato antes de gerar um plano de rollback.  Assim um
        ``operationId`` copiado de outro componente nunca atravessa a fronteira
        de autorização apenas por ser um ULID válido.
        """
        if not ids.is_ulid(operation_id):
            raise SteamZeroError("E-API-SCHEMA", detail="operationId inválido")
        operation_path = paths.component_operation_path(operation_id)
        if operation_path.is_file() and not operation_path.is_symlink():
            repair = self._repair_operation_from_file(operation_path)
            if repair is not None:
                return repair.adapter_id
            try:
                raw = json.loads(operation_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise SteamZeroError(
                    "E-STATE-INTEGRITY", detail="operação de componente corrompida"
                ) from exc
            adapter_id = raw.get("adapterId") if isinstance(raw, dict) else None
            if not isinstance(adapter_id, str):
                raise SteamZeroError("E-STATE-INTEGRITY", detail="operação sem componente")
            self._registry.get(adapter_id)
            return adapter_id
        return self._transaction_operation_adapter(operation_id)

    # ---------------------------------------------------------- launch / stop
    def launch(self, adapter_id: str) -> dict[str, Any]:
        """Inicia o componente instalado, roteado pela família da fonte."""
        manifest = self._registry.get(adapter_id)
        route = route_for(manifest)
        if route.executor == "libretro":
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail="core Libretro é carregado pelo RetroArch e não possui launch próprio",
            )
        current = self.status(adapter_id)
        if current["state"] not in {"installed", "outdated"}:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail=current.get("detail") or f"{adapter_id} não está instalado",
            )
        if route.executor == "flatpak" or (
            route.end_of_life and route.source_type in FLATPAK_SOURCES
        ):
            source = manifest.preferred_source("flatpak", allow_eol=True)
            executable = self._which("flatpak")
            if executable is None or source.ref is None:
                raise SteamZeroError("E-COMPONENT-DEGRADED", detail="runtime Flatpak indisponível")
            pid = self._spawn(
                (executable, "run", "--user", source.ref, *self._launch_extras(source.ref))
            )
        else:
            pid = self._spawn([str(self._engine().payload_path(adapter_id))])
        return {"status": "started", "componentId": adapter_id, "pid": pid}

    def _retroarch_config(self) -> input_devices.ManagedRetroArchConfig:
        if self._retroarch_config_override is not None:
            return self._retroarch_config_override
        if self._retroarch_config_cache is None:
            self._retroarch_config_cache = input_devices.managed_config()
        return self._retroarch_config_cache

    def _launch_extras(self, flatpak_ref: str | None) -> tuple[str, ...]:
        """Delegado ao ponto compartilhado (ver `input_devices`)."""
        return input_devices.retroarch_launch_arguments(flatpak_ref, self._retroarch_config())

    def open_config(self, adapter_id: str) -> dict[str, Any]:
        """Abre a configuração nativa do emulador, com argv allowlisted.

        Emuladores não compartilham uma forma de "abrir configuração": alguns
        têm flag própria, outros só o menu da GUI. Adivinhar um argv produziria
        um botão que abre a coisa errada — ou nada — e o usuário não teria como
        saber qual dos dois aconteceu.

        Por isso o argv vem do manifesto (``openConfig.arguments``). Adapter que
        não declara recebe recusa com motivo dizível, e a bridge publica a ação
        como não aplicável em vez de oferecer um botão que termina em stub.
        """
        manifest = self._registry.get(adapter_id)
        route = route_for(manifest)
        if route.executor == "libretro":
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail="core Libretro não possui configuração executável própria",
            )
        arguments = self._open_config_arguments(manifest)
        if arguments is None:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail=f"{adapter_id} não declara como abrir a configuração nativa",
            )
        current = self.status(adapter_id)
        if current["state"] not in {"installed", "outdated"}:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail=current.get("detail") or f"{adapter_id} não está instalado",
            )
        if route.executor == "flatpak" or (
            route.end_of_life and route.source_type in FLATPAK_SOURCES
        ):
            source = manifest.preferred_source("flatpak", allow_eol=True)
            executable = self._which("flatpak")
            if executable is None or source.ref is None:
                raise SteamZeroError("E-COMPONENT-DEGRADED", detail="runtime Flatpak indisponível")
            argv = [executable, "run", "--user", source.ref, *arguments]
        else:
            argv = [str(self._engine().payload_path(adapter_id)), *arguments]
        pid = self._spawn(argv)
        # ``argv`` é detalhe de execução, não contrato público: ele pode
        # carregar paths de payload ou referências de runtime. A chamada
        # continua sem shell e com argumentos allowlisted, mas só publica o
        # resultado mínimo necessário para a UI/CLI.
        return {"status": "started", "componentId": adapter_id, "pid": pid}

    @staticmethod
    def _open_config_arguments(manifest: AdapterManifest) -> list[str] | None:
        """Argumentos declarados para abrir a configuração, validados.

        Cada item é atômico: nada de string única que o shell fatiaria, e nada
        de NUL ou tamanho absurdo chegando a um ``Popen``.
        """
        raw = manifest.raw.get("openConfig")
        if not isinstance(raw, dict):
            return None
        arguments = raw.get("arguments")
        if not isinstance(arguments, list) or not arguments:
            return None
        validated: list[str] = []
        for item in arguments:
            if not isinstance(item, str) or not item or "\x00" in item or len(item) > 256:
                raise SteamZeroError(
                    "E-API-SCHEMA", detail=f"argumento de openConfig inválido em {manifest.id}"
                )
            validated.append(item)
        return validated

    def stop(self, adapter_id: str) -> dict[str, Any]:
        """Encerra os grupos de processo do componente portátil (SIGTERM)."""
        tombstone = self._registry.retired(adapter_id)
        if tombstone is not None:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail=f"{adapter_id} foi retirado: {tombstone.reason}",
            )
        route = route_for(self._registry.get(adapter_id))
        if route.executor == "libretro":
            return {
                "status": "not-supported",
                "componentId": adapter_id,
                "detail": "core Libretro é encerrado junto do RetroArch",
            }
        if route.executor == "flatpak" or (
            route.end_of_life and route.source_type in FLATPAK_SOURCES
        ):
            return {
                "status": "not-supported",
                "componentId": adapter_id,
                "detail": "parada de processos Flatpak não é gerenciada pelo SteamZero",
            }
        current = self.status(adapter_id)
        if current["state"] != "installed":
            return {"status": "not-running", "componentId": adapter_id}
        payload = self._engine().payload_path(adapter_id)
        groups = self._managed_process_groups(payload)
        for process_group in groups:
            try:
                os.killpg(process_group, signal.SIGTERM)
            except ProcessLookupError:
                continue
        return {
            "status": "stopping" if groups else "not-running",
            "componentId": adapter_id,
            "processGroups": len(groups),
        }

    def recover(self) -> list[dict[str, Any]]:
        """Recupera operações interrompidas (Flatpak delegado + reparos).

        Operações de reparo em ``applying`` viram fatos observados: se o
        deployment já está íntegro, o reparo terminou antes do crash e a
        operação é ``committed``; senão, o marcador ``repairing`` volta ao
        estado real do executor com a operação ``rolled-back``. Idempotente:
        uma operação já encerrada não é processada de novo.
        """
        recovered: list[dict[str, Any]] = [
            {
                "status": result.status,
                "operationId": result.operation_id,
                "adapterId": result.adapter_id,
                "executor": "flatpak",
            }
            for result in self._flatpak().recover()
        ]
        fs.ensure_dir(paths.component_operations_dir())
        for entry in sorted(paths.component_operations_dir().glob("*.json")):
            if entry.is_symlink() or not entry.is_file():
                continue
            operation = self._repair_operation_from_file(entry)
            if operation is None:
                continue
            if operation.state not in {_REPAIR_OP_APPLYING, _REPAIR_OP_RECOVERY_REQUIRED}:
                continue
            try:
                obs = self._observe_state(operation.adapter_id)
                final = (
                    _REPAIR_OP_COMMITTED if obs["state"] == "installed" else _REPAIR_OP_ROLLED_BACK
                )
                manifest = self._registry.get(operation.adapter_id)
                self._store.save_component(
                    {
                        "id": operation.adapter_id,
                        "adapter_id": operation.adapter_id,
                        "kind": manifest.kind,
                        "version": obs.get("version"),
                        "origin": obs.get("origin"),
                        "state": obs["state"],
                        "manifest_hash": manifest.manifest_hash,
                        "operation_id": None,
                    }
                )
                self._save_repair_operation(replace(operation, state=final))
                recovered.append(
                    {
                        "status": "reconciled",
                        "operationId": operation.operation_id,
                        "adapterId": operation.adapter_id,
                        "executor": "repair",
                        "state": final,
                        "observedState": obs["state"],
                    }
                )
            except Exception as exc:
                self._save_repair_operation(replace(operation, state=_REPAIR_OP_RECOVERY_REQUIRED))
                raise SteamZeroError(
                    "E-TX-STALE-PLAN",
                    operation_id=operation.operation_id,
                    detail=f"recuperação de reparo órfão falhou: {exc}",
                ) from exc
        return recovered

    def recovery_inspect(self) -> list[dict[str, Any]]:
        """Lista recovery pendente sem chamar executor ou modificar estado."""
        pending: list[dict[str, Any]] = []
        fs.ensure_dir(paths.component_operations_dir())
        for entry in sorted(paths.component_operations_dir().glob("*.json")):
            if entry.is_symlink() or not entry.is_file():
                continue
            try:
                raw = json.loads(entry.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            if not isinstance(raw, dict):
                continue
            operation_id = raw.get("operationId")
            adapter_id = raw.get("adapterId")
            status = raw.get("status", raw.get("state"))
            if (
                not isinstance(operation_id, str)
                or not isinstance(adapter_id, str)
                or status not in {"applying", "rolling-back", "recovery-required"}
            ):
                continue
            pending.append(
                {
                    "operationId": operation_id,
                    "adapterId": adapter_id,
                    "executor": "repair"
                    if raw.get("schemaVersion") == _REPAIR_OP_SCHEMA
                    else "flatpak",
                    "state": status,
                }
            )
        return pending

    def plan_recovery(self) -> dict[str, Any]:
        plan = transaction.plan_write_files(
            {},
            root=paths.state_home(),
            kind="component.recovery",
            requirements_extra={"recoveryFingerprint": self._recovery_fingerprint()},
        )
        return plan.to_dict()

    def apply_recovery(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        plan = transaction.load_plan(plan_id)
        expected = plan.requirements.get("recoveryFingerprint")
        if (
            plan.kind != "component.recovery"
            or Path(plan.root) != paths.state_home()
            or not isinstance(expected, str)
        ):
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail="plano não pertence à recuperação de componentes"
            )
        if expected != self._recovery_fingerprint():
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail="operações pendentes mudaram desde o plano"
            )
        applied = transaction.apply(plan_id, confirm_token)
        recovered = self.recover()
        return {
            "status": applied.status,
            "operationId": applied.operation_id,
            "operations": recovered,
        }

    def _recovery_fingerprint(self) -> str:
        """Congela a seleção sanitizada que o recovery poderá reconciliar."""
        encoded = json.dumps(
            self.recovery_inspect(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    # ------------------------------------------------------------- internals
    def _engine(self) -> AdapterEngine:
        return AdapterEngine(self._store, self._registry, self._artifacts)

    def _libretro(self) -> LibretroCoreExecutor:
        return LibretroCoreExecutor(
            self._store,
            self._registry,
            self._artifacts,
            core_root=self._libretro_core_root,
            archive_reader=self._libretro_archive_reader,
        )

    def _flatpak(self) -> FlatpakExecutor:
        return FlatpakExecutor(self._store, self._registry, self._flatpak_factory())

    @staticmethod
    def _source_fingerprint(manifest: AdapterManifest, route: LifecycleRoute) -> dict[str, Any]:
        """Fingerprint da fonte no momento do plano; revalidado no apply."""
        try:
            if route.executor == "flatpak":
                source = manifest.preferred_source("flatpak", allow_eol=False)
                return {
                    "type": "flatpak",
                    "ref": source.ref,
                    "remote": source.remote,
                    "targetCommit": source.version,
                }
            if route.executor == "libretro":
                source = manifest.preferred_source("archive", allow_eol=False)
                if manifest.core is None:
                    raise SteamZeroError("E-API-SCHEMA", detail="core sem declaração de conteúdo")
                return {
                    "type": "libretro-archive",
                    "version": source.version,
                    "archiveSha256": source.sha256,
                    "coreId": manifest.core.id,
                    "coreSha256": manifest.core.sha256,
                    "manifestHash": manifest.manifest_hash,
                }
            source = manifest.preferred_source(route.source_type, allow_eol=False)
            return {
                "type": "portable",
                "version": source.version,
                "sha256": source.sha256,
                "manifestHash": manifest.manifest_hash,
            }
        except SteamZeroError as exc:
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail=f"fonte do componente mudou após o plano: {exc}"
            ) from exc

    def _engine_smoke(self, engine: AdapterEngine, manifest: AdapterManifest) -> None:
        """Smoke test do payload portátil, igual ao caminho da central."""
        command = [str(engine.payload_path(manifest.id))]
        command.extend(manifest.verify_smoke_test)
        try:
            result = subprocess.run(  # noqa: S603
                command,
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env={**os.environ, "APPIMAGELAUNCHER_DISABLE": "1"},
                timeout=20,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED", detail=f"smoke test falhou: {exc}"
            ) from exc
        if result.returncode != 0:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail=f"smoke test retornou código {result.returncode}",
            )

    def _revalidate_engine_apply(self, envelope: ComponentPlan, engine: AdapterEngine) -> None:
        """Revalida plano e deployment sob lock, como o executor Flatpak faz.

        Copia o padrão de flatpak.py: o plano é carregado DE NOVO sob o lock, o
        fingerprint da fonte é recalculado contra o manifesto ATUAL e o estado
        do deployment é conferido contra a ação do envelope. Qualquer divergência
        aborta com ``E-TX-STALE-PLAN`` antes de efeito.
        """
        plan = transaction.load_plan(str(envelope.delegated["transactionPlanId"]))
        if plan.status != "pending":
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail="plano transacional não está mais pendente"
            )
        manifest = self._registry.get(envelope.adapter_id)
        route = route_for(manifest)
        if route.executor != envelope.executor:
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail="executor do componente mudou após o plano"
            )
        if self._source_fingerprint(manifest, route) != envelope.source_fingerprint:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="manifesto mudou após o plano")
        current = engine.status(envelope.adapter_id)
        if envelope.action == "uninstall" and current["state"] == "missing":
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail="deployment já foi removido após o plano"
            )
        if envelope.action == "repair" and current["state"] not in _REPAIRABLE_STATES:
            raise SteamZeroError(
                "E-TX-STALE-PLAN",
                detail=f"estado do componente mudou após o plano ({current['state']})",
            )

    def _revalidate_libretro_apply(
        self,
        envelope: ComponentPlan,
        cores: LibretroCoreExecutor,
        prepared: PreparedLibretroCore,
    ) -> None:
        """Equivalente ao preflight Engine para o plano de extração de core."""
        manifest = self._registry.get(envelope.adapter_id)
        route = route_for(manifest)
        if route.executor != "libretro" or route.executor != envelope.executor:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="executor do core mudou após o plano")
        if self._source_fingerprint(manifest, route) != envelope.source_fingerprint:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="manifesto do core mudou após o plano")
        cores.validate_plan(prepared)
        observed = cores.status(envelope.adapter_id)
        if envelope.action == "uninstall" and observed["state"] == "missing":
            raise SteamZeroError("E-TX-STALE-PLAN", detail="core já foi removido após o plano")
        if envelope.action == "repair" and observed["state"] not in _REPAIRABLE_STATES:
            raise SteamZeroError(
                "E-TX-STALE-PLAN",
                detail=f"estado do core mudou após o plano ({observed['state']})",
            )

    def _finish_failed_repair(
        self,
        operation_id: str,
        manifest: AdapterManifest,
        observed: dict[str, Any] | None,
    ) -> None:
        """Encerra um reparo que falhou: restaura o estado observado.

        O deployment já voltou ao que o executor observa (rollback do próprio
        executor ou transação que não chegou a vigorar). Aqui apenas o marcador
        ``repairing`` e a operação são encerrados, preservando versão/origem
        observados. Falha na restauração vira ``recovery-required`` (o recovery
        fará a reconciliação depois).
        """
        try:
            if observed is not None:
                self._store.save_component(
                    {
                        "id": manifest.id,
                        "adapter_id": manifest.id,
                        "kind": manifest.kind,
                        "version": observed.get("version"),
                        "origin": observed.get("origin"),
                        "state": str(observed["state"]),
                        "manifest_hash": manifest.manifest_hash,
                        "operation_id": None,
                    }
                )
        except Exception as exc:
            self._mark_repair_recovery(operation_id, f"estado não restaurado: {exc}")
            raise SteamZeroError(
                "E-TX-ROLLBACK-FAILED",
                operation_id=operation_id,
                detail=f"reparo falhou e o estado não pôde ser restaurado: {exc}",
            ) from exc
        self._mark_repair_rolled_back(operation_id)

    def _commit_repair_operation(self, operation_id: str) -> None:
        self._save_repair_operation(
            replace(self._load_repair_operation(operation_id), state=_REPAIR_OP_COMMITTED)
        )

    def _mark_repair_rolled_back(self, operation_id: str) -> None:
        self._save_repair_operation(
            replace(self._load_repair_operation(operation_id), state=_REPAIR_OP_ROLLED_BACK)
        )

    def _mark_repair_recovery(self, operation_id: str, error: str) -> None:
        try:
            operation = self._load_repair_operation(operation_id)
        except SteamZeroError:
            return
        self._save_repair_operation(
            replace(operation, state=_REPAIR_OP_RECOVERY_REQUIRED, error=error)
        )

    def _save_repair_operation(self, operation: RepairOperation) -> None:
        fs.ensure_dir(paths.component_operations_dir())
        fs.write_atomic_text(
            paths.component_operation_path(operation.operation_id),
            json.dumps(operation.to_dict(), ensure_ascii=False, sort_keys=True),
        )
        self._store.save_operation(
            operation.operation_id,
            journal_path=str(paths.component_operation_path(operation.operation_id)),
            state=operation.state,
        )

    def _try_load_repair_operation(self, operation_id: str) -> RepairOperation | None:
        if not ids.is_ulid(operation_id):
            return None
        return self._repair_operation_from_file(paths.component_operation_path(operation_id))

    def _load_repair_operation(self, operation_id: str) -> RepairOperation:
        operation = self._try_load_repair_operation(operation_id)
        if operation is None:
            raise SteamZeroError(
                "E-STATE-INTEGRITY", detail=f"operação de reparo não encontrada: {operation_id}"
            )
        return operation

    def _active_repair_operation(self, adapter_id: str) -> RepairOperation | None:
        """Operação de reparo em curso para o adapter, se houver (idempotência).

        Permite reaplicar um plano sobre um reparo já registrado sem criar uma
        operação nova: o restart encontra o arquivo em ``applying`` e segue.
        """
        try:
            row = self._store.get_component(adapter_id)
        except Exception:
            return None
        if row is None or row.get("state") != "repairing":
            return None
        operation_id = row.get("operation_id")
        if not isinstance(operation_id, str) or not operation_id:
            return None
        operation = self._try_load_repair_operation(operation_id)
        if operation is None or operation.state != _REPAIR_OP_APPLYING:
            return None
        return operation

    @staticmethod
    def _repair_operation_from_file(path: Path) -> RepairOperation | None:
        if path.is_symlink() or not path.is_file():
            return None
        try:
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        try:
            operation = RepairOperation.from_dict(data)
        except (KeyError, TypeError, ValueError):
            return None
        if (
            operation.schema_version != _REPAIR_OP_SCHEMA
            or operation.action != _REPAIR_ACTION
            or operation.operation_id != path.stem
            or not ids.is_ulid(operation.operation_id)
        ):
            return None
        if operation.state not in _REPAIR_OP_STATES:
            return None
        return operation

    def _validate_pending(self, envelope: ComponentPlan, confirm_token: str) -> None:
        if envelope.status != "pending":
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail=f"plano não está pendente ({envelope.status})"
            )
        if not all(ord(char) < 128 for char in confirm_token + envelope.confirm_token):
            raise SteamZeroError("E-STATE-INTEGRITY", detail="confirmToken deve ser ASCII")
        if not secrets.compare_digest(confirm_token, envelope.confirm_token):
            raise SteamZeroError("E-TX-CONFIRM-REQUIRED", detail="confirmToken incorreto")
        try:
            expires_at = datetime.fromisoformat(envelope.expires_at)
        except ValueError as exc:
            raise SteamZeroError("E-STATE-INTEGRITY", detail="expiração do plano inválida") from exc
        if expires_at.tzinfo is None:
            raise SteamZeroError("E-STATE-INTEGRITY", detail="expiração do plano sem timezone")
        if self._utc_now() > expires_at:
            raise SteamZeroError("E-TX-CONFIRM-REQUIRED", detail="confirmToken expirado")

    def _validate_confirmation_fields(self, raw: dict[str, Any], confirm_token: str) -> None:
        """Valida os campos de confirmação comuns ao plano Flatpak v1."""
        expected = str(raw["confirmToken"])
        if str(raw["status"]) != "pending":
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail=f"plano não está pendente ({raw['status']})"
            )
        if not all(ord(char) < 128 for char in confirm_token + expected):
            raise SteamZeroError("E-STATE-INTEGRITY", detail="confirmToken deve ser ASCII")
        if not secrets.compare_digest(confirm_token, expected):
            raise SteamZeroError("E-TX-CONFIRM-REQUIRED", detail="confirmToken incorreto")
        expires_at = datetime.fromisoformat(str(raw["expiresAt"]))
        if expires_at.tzinfo is None:
            raise SteamZeroError("E-STATE-INTEGRITY", detail="expiração do plano sem timezone")
        if self._utc_now() > expires_at:
            raise SteamZeroError("E-TX-CONFIRM-REQUIRED", detail="confirmToken expirado")

    def _save_plan(self, envelope: ComponentPlan) -> None:
        data = envelope.to_dict()
        schema_name = _PLAN_SCHEMA_V3 if envelope.schema_version == 3 else _PLAN_SCHEMA_V2
        try:
            contracts.validate(data, schema_name)
        except ValidationError as exc:
            raise SteamZeroError(
                "E-STATE-INTEGRITY", detail=f"plano de componente inválido: {exc}"
            ) from exc
        fs.ensure_dir(paths.plans_dir())
        fs.write_atomic_text(
            paths.plan_path(envelope.plan_id),
            json.dumps(data, ensure_ascii=False, sort_keys=True),
        )

    def _mark_applied(self, envelope: ComponentPlan) -> None:
        self._save_plan(replace(envelope, status="applied"))

    def _read_plan_file(self, plan_id: str) -> dict[str, Any]:
        if not ids.is_ulid(plan_id):
            raise SteamZeroError("E-TX-STALE-PLAN", detail="planId inválido")
        path = paths.plan_path(plan_id)
        try:
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano não encontrado") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise SteamZeroError(
                "E-STATE-INTEGRITY", detail=f"plano de componente corrompido: {exc}"
            ) from exc
        if not isinstance(data, dict):
            raise SteamZeroError(
                "E-STATE-INTEGRITY", detail="plano de componente corrompido: raiz não é objeto JSON"
            )
        if data.get("schemaVersion") not in {1, 2, 3}:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano não é de componente")
        return data

    def _transaction_operation_adapter(self, operation_id: str) -> str | None:
        """Deriva o adapter de uma operação transacional a partir do journal.

        Best-effort: falha em derivar devolve ``None`` e o rollback continua
        válido (o status real é relido do disco na próxima consulta).
        """
        try:
            records = journal.read_records(operation_id)
            begin = next(record for record in records if record.get("type") == "operation.begin")
            plan = transaction.load_plan(str(begin["planId"]))
            if not plan.kind.startswith(("component.", "libretro.")):
                return None
            root = Path(plan.root)
            if plan.kind.startswith("libretro."):
                for manifest in self._registry.list():
                    if manifest.kind != "core" or manifest.core is None:
                        continue
                    target = root / f"{manifest.core.id}_libretro.so"
                    if any(Path(action.target) == target for action in plan.actions):
                        return manifest.id
                return None
            for action in plan.actions:
                try:
                    relative = Path(action.target).relative_to(root)
                except ValueError:
                    continue
                if relative.parts:
                    return relative.parts[0]
        except (SteamZeroError, KeyError, StopIteration, OSError, ValueError, json.JSONDecodeError):
            return None
        return None

    @staticmethod
    def _managed_process_groups(payload: Path) -> set[int]:
        """Grupos do usuário cujo argv contém o payload exato (read-only)."""
        expected = os.fsencode(str(payload))
        groups: set[int] = set()
        try:
            entries = tuple(Path("/proc").iterdir())
        except OSError:
            return groups
        for entry in entries:
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            try:
                if entry.stat().st_uid != os.getuid():
                    continue
                argv = (entry / "cmdline").read_bytes().split(b"\0")
                if expected not in argv:
                    continue
                process_group = os.getpgid(pid)
                if process_group > 1:
                    groups.add(process_group)
            except (OSError, ProcessLookupError):
                continue
        return groups

    def _utc_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
