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
- o plano v2 (envelope executor-independente) persiste executor, adapter,
  fingerprint da fonte e o plano delegado de cada executor, permitindo
  ``plan`` e ``apply`` em processos diferentes; planos Flatpak v1 continuam
  aplicáveis durante a transição;
- falha de um adapter é agregada em ``unavailable`` com motivo — um componente
  degradado não derruba ``component list`` nem o workspace inteiro.

O que NÃO muda: cada executor mantém suas garantias. Portátil continua exigindo
sha256; Flatpak continua exigindo commit fixado. Fonte sem a garantia da sua
família falha fechado, aqui como antes.
"""

from __future__ import annotations

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

from steamzero.adapters.engine import AdapterEngine, HttpsArtifactPort, PreparedComponent
from steamzero.adapters.flatpak import FlatpakCLI, FlatpakExecutor
from steamzero.adapters.registry import AdapterManifest, AdapterRegistry, AdapterSource
from steamzero.api import contracts
from steamzero.core import fs, ids, journal, paths, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore

#: Famílias de fonte com executor real. Fonte fora daqui não tem lifecycle e
#: precisa falhar fechado — habilitar ação para ela produziria botão que termina
#: em stub.
PORTABLE_SOURCES = frozenset({"appimage", "native"})
FLATPAK_SOURCES = frozenset({"flatpak"})

_PLAN_SCHEMA_V2 = "component-plan-v2.schema.json"
_PLAN_SCHEMA_V1 = "component-plan-v1.schema.json"
_DEFAULT_TTL_S = 3600

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

    return LifecycleRoute(
        manifest.id,
        source.type,
        "none",
        False,
        f"não há executor para fonte do tipo '{source.type}'",
    )


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
    """Envelope executor-independente de plano de componente (schema v2, G27).

    O executor e o fingerprint da fonte ficam no envelope; o plano delegado
    continua sendo o documento autoritativo de cada executor (plano Flatpak v1
    ou plano transacional do engine), referenciado por id. O ``confirmToken``
    do envelope é o MESMO do plano delegado: aplicar o envelope revalida o
    token contra o executor, em qualquer processo.
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
    schema_version: int = 2

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
    ) -> None:
        self._store = store
        self._registry = registry
        self._artifacts = artifacts if artifacts is not None else HttpsArtifactPort()
        self._flatpak_factory = flatpak_factory
        self._which = which
        self._spawn = spawn
        self._now = now or (lambda: datetime.now(UTC))

    # ------------------------------------------------------------------ status
    def status(self, adapter_id: str) -> dict[str, Any]:
        """Status normalizado do componente, roteado pela família da fonte."""
        manifest = self._registry.get(adapter_id)
        route = route_for(manifest)
        try:
            if route.executor == "flatpak":
                return normalize_status(self._flatpak().status(adapter_id), route)
            if route.executor == "engine":
                return normalize_status(self._engine().status(adapter_id), route)
            if route.end_of_life and route.source_type in FLATPAK_SOURCES:
                # EOL não é ausência: o executor ainda observa o deployment.
                # Consultá-lo preserva versão/origem/existência instalada.
                return normalize_status(self._flatpak().status(adapter_id), route)
            if route.end_of_life and route.source_type in PORTABLE_SOURCES:
                return normalize_status(self._engine().status(adapter_id), route)
            return unavailable_status(route)
        except Exception as exc:
            return failed_status(route, exc)

    def status_all(self) -> list[dict[str, Any]]:
        """Status de todos os adapters, com falha agregada por componente.

        Um adapter cujo executor falhou vira uma linha ``unavailable`` com
        motivo — nunca derruba a lista nem o workspace inteiro (G27).
        """
        rows: list[dict[str, Any]] = []
        for manifest in self._registry.list():
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
        route = route_for(manifest)
        if not route.installable:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail=route.reason or "componente sem executor de lifecycle",
            )
        if action not in {"install", "update", "uninstall"}:
            raise SteamZeroError("E-API-SCHEMA", detail="ação de componente não permitida")
        if route.executor == "flatpak":
            if action == "uninstall":
                raise SteamZeroError(
                    "E-API-SCHEMA",
                    detail="desinstalação Flatpak ainda não é oferecida; o deployment é preservado",
                )
            delegated_plan = self._flatpak().plan_install(adapter_id)
            effective = str(delegated_plan.action)
            delegated: dict[str, Any] = {"flatpakPlanId": delegated_plan.plan_id}
            fingerprint = self._source_fingerprint(manifest, route)
            preview = delegated_plan.preview
            rollback_guarantee = delegated_plan.rollback_guarantee
            confirm_token = delegated_plan.confirm_token
        else:
            engine = self._engine()
            current = engine.status(adapter_id)
            if action == "uninstall":
                prepared = engine.plan_uninstall(adapter_id)
                effective = "uninstall"
            else:
                prepared = engine.plan_install(adapter_id)
                if current["state"] == "installed":
                    effective = "noop" if not prepared.plan.actions else "update"
                else:
                    effective = "install"
            delegated = {"transactionPlanId": prepared.plan.plan_id}
            fingerprint = self._source_fingerprint(manifest, route)
            preview = prepared.plan.preview
            rollback_guarantee = prepared.plan.rollback_guarantee
            confirm_token = prepared.plan.confirm_token
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
        try:
            contracts.validate(raw, _PLAN_SCHEMA_V2)
        except ValidationError as exc:
            raise SteamZeroError(
                "E-STATE-INTEGRITY", detail=f"plano de componente v2 inválido: {exc}"
            ) from exc
        envelope = ComponentPlan.from_dict(raw)
        self._validate_pending(envelope, confirm_token)
        manifest = self._registry.get(envelope.adapter_id)
        route = route_for(manifest)
        if route.executor != envelope.executor:
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail="executor do componente mudou após o plano"
            )
        fingerprint = self._source_fingerprint(manifest, route)
        if fingerprint != envelope.source_fingerprint:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="manifesto mudou após o plano")
        if envelope.executor == "flatpak":
            delegated_id = str(envelope.delegated["flatpakPlanId"])
            result = self._flatpak().apply(delegated_id, confirm_token)
            self._mark_applied(envelope)
            return {
                "status": result.status,
                "operationId": result.operation_id,
                "adapterId": result.adapter_id,
                "executor": "flatpak",
                "planVersion": 2,
            }
        engine = self._engine()
        source = manifest.preferred_source(route.source_type, allow_eol=False)
        plan = transaction.load_plan(str(envelope.delegated["transactionPlanId"]))
        prepared = PreparedComponent(manifest, source, plan)

        def smoke() -> None:
            self._engine_smoke(engine, manifest)

        applied = engine.apply(
            prepared,
            confirm_token,
            smoke=None if envelope.action == "uninstall" else smoke,
        )
        self._mark_applied(envelope)
        return {
            "status": applied.status,
            "operationId": applied.operation_id,
            "adapterId": envelope.adapter_id,
            "executor": "engine",
            "planVersion": 2,
        }

    # --------------------------------------------------------------- rollback
    def rollback(self, operation_id: str) -> dict[str, Any]:
        """Reverte operação Flatpak (arquivo próprio) ou transacional do engine."""
        operation_path = paths.component_operation_path(operation_id)
        if operation_path.is_file() and not operation_path.is_symlink():
            flatpak_result = self._flatpak().rollback(operation_id)
            return {
                "status": flatpak_result.status,
                "operationId": flatpak_result.operation_id,
                "adapterId": flatpak_result.adapter_id,
                "executor": "flatpak",
            }
        rolled = transaction.rollback(operation_id, reason="component-manual")
        adapter_id = self._engine_operation_adapter(operation_id)
        if adapter_id is not None:
            # O rollback já restaurou os arquivos; a persistência no banco
            # é apenas o espelho — falha aqui não invalida a operação.
            with suppress(Exception):
                self._engine().persist_status(adapter_id)
        return {
            "status": rolled.status,
            "operationId": rolled.operation_id,
            "executor": "engine",
            "restored": list(rolled.restored),
            "adapterId": adapter_id,
        }

    # ---------------------------------------------------------- launch / stop
    def launch(self, adapter_id: str) -> dict[str, Any]:
        """Inicia o componente instalado, roteado pela família da fonte."""
        manifest = self._registry.get(adapter_id)
        route = route_for(manifest)
        current = self.status(adapter_id)
        if current["state"] != "installed":
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
            pid = self._spawn((executable, "run", "--user", source.ref))
        else:
            pid = self._spawn([str(self._engine().payload_path(adapter_id))])
        return {"status": "started", "componentId": adapter_id, "pid": pid}

    def stop(self, adapter_id: str) -> dict[str, Any]:
        """Encerra os grupos de processo do componente portátil (SIGTERM)."""
        route = route_for(self._registry.get(adapter_id))
        if route.executor == "flatpak":
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
        """Recupera operações Flatpak interrompidas (delegação ao executor)."""
        return [
            {
                "status": result.status,
                "operationId": result.operation_id,
                "adapterId": result.adapter_id,
                "executor": "flatpak",
            }
            for result in self._flatpak().recover()
        ]

    # ------------------------------------------------------------- internals
    def _engine(self) -> AdapterEngine:
        return AdapterEngine(self._store, self._registry, self._artifacts)

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

    def _validate_pending(self, envelope: ComponentPlan, confirm_token: str) -> None:
        if envelope.status != "pending":
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail=f"plano não está pendente ({envelope.status})"
            )
        if not secrets.compare_digest(confirm_token, envelope.confirm_token):
            raise SteamZeroError("E-TX-CONFIRM-REQUIRED", detail="confirmToken incorreto")
        try:
            expires_at = datetime.fromisoformat(envelope.expires_at)
        except ValueError as exc:
            raise SteamZeroError("E-STATE-INTEGRITY", detail="expiração do plano inválida") from exc
        if self._utc_now() > expires_at:
            raise SteamZeroError("E-TX-CONFIRM-REQUIRED", detail="confirmToken expirado")

    def _save_plan(self, envelope: ComponentPlan) -> None:
        data = envelope.to_dict()
        try:
            contracts.validate(data, _PLAN_SCHEMA_V2)
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
        if data.get("schemaVersion") not in {1, 2}:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano não é de componente")
        return data

    @staticmethod
    def _engine_operation_adapter(operation_id: str) -> str | None:
        """Deriva o adapter de uma operação transacional a partir do journal.

        Best-effort: falha em derivar devolve ``None`` e o rollback continua
        válido (o status real é relido do disco na próxima consulta).
        """
        try:
            records = journal.read_records(operation_id)
            begin = next(record for record in records if record.get("type") == "operation.begin")
            plan = transaction.load_plan(str(begin["planId"]))
            if not plan.kind.startswith("component."):
                return None
            root = Path(plan.root)
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
