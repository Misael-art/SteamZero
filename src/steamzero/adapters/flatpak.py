# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Executor Flatpak user-scoped, pinado e recuperável para o M10.

Nenhum comando usa shell. O plano congela o deployment anterior e o commit
alvo; apply revalida o contexto, registra intent durável antes do primeiro
efeito, verifica o commit e executa smoke. Falha antes do commit lógico restaura
o deployment anterior. Dados da aplicação nunca são apagados no rollback.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from jsonschema import ValidationError

from steamzero.adapters.registry import AdapterManifest, AdapterRegistry, AdapterSource
from steamzero.api import contracts
from steamzero.core import fs, ids, paths
from steamzero.core.errors import SteamZeroError
from steamzero.core.lock import ResourceLock
from steamzero.core.state import StateStore
from steamzero.jobs.manager import JobCancelled

_COMMIT_RE = re.compile(r"^[a-f0-9]{64}$")
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,254}$")
# O primeiro `flatpak run --user` de um app-runtime cria a árvore .var/app
# (config, dbus-proxy) e pode levar ~23 s em VM recém-provisionada (medido
# 2026-08-10; o segundo run cai para ~10 s, o terceiro ~0,4 s). 90 s dá
# margem de ~3x sobre o pior caso frio sem deixar de detectar app que abre
# UI e pendura esperando entrada.
_SMOKE_TIMEOUT = 90.0
# `flatpak list`/`info` são locais, mas rodam logo após install/deploy
# (I/O pesado no guest; um list estourou 10 s no rollback do r38 em
# 2026-08-11). 60 s dá margem sem mascarar repo quebrado (erro real vira
# rc != 0, não timeout).
_STATUS_TIMEOUT = 60.0
_REMOTE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_PLAN_SCHEMA = "component-plan-v1.schema.json"
_DEFAULT_TTL_S = 3600


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str = ""


Runner = Callable[[Sequence[str], float], CommandResult]
StageProgress = Callable[[str, int, int], None]
CancelCheck = Callable[[], None]


@dataclass(frozen=True)
class _FlatpakOperationObserver:
    progress: StageProgress
    cancel_check: CancelCheck


_FLATPAK_OPERATION_OBSERVER: ContextVar[_FlatpakOperationObserver | None] = ContextVar(
    "steamzero_flatpak_operation_observer", default=None
)


@contextmanager
def flatpak_operation_observer(
    *, progress: StageProgress, cancel_check: CancelCheck
) -> Iterator[None]:
    """Liga etapas e cancelamento do job à operação Flatpak desta thread."""
    token = _FLATPAK_OPERATION_OBSERVER.set(_FlatpakOperationObserver(progress, cancel_check))
    try:
        yield
    finally:
        _FLATPAK_OPERATION_OBSERVER.reset(token)


def report_flatpak_stage(stage: str, *, current: int, total: int) -> None:
    observer = _FLATPAK_OPERATION_OBSERVER.get()
    if observer is None:
        return
    observer.cancel_check()
    observer.progress(stage, current, total)


def _stop_flatpak_process(process: subprocess.Popen[str]) -> tuple[str, str]:
    process.terminate()
    try:
        return process.communicate(timeout=2.0)
    except subprocess.TimeoutExpired:
        process.kill()
        return process.communicate()


def run_flatpak_command(argv: Sequence[str], timeout: float) -> CommandResult:
    """Executa Flatpak pinado, fora do mount namespace endurecido do daemon.

    Flatpak cria um sandbox Bubblewrap que monta uma ``procfs`` própria. A unit
    do core deliberadamente protege subárvores de ``/proc``; o kernel então
    recusa a procfs aninhada. Quando chamado pelo daemon, ``systemd-run`` pede
    ao user manager um serviço transitório limpo, mantendo o daemon endurecido
    e sem aceitar comando ou propriedade arbitrários.
    """
    if not argv or argv[0] != "flatpak":
        return CommandResult(127, "", "comando Flatpak inválido")
    executable = shutil.which("flatpak")
    if executable is None:
        return CommandResult(127, "", "flatpak não encontrado")
    observer = _FLATPAK_OPERATION_OBSERVER.get()
    if observer is not None:
        observer.cancel_check()
    command: list[str] = [executable, *argv[1:]]
    if os.environ.get("STEAMZERO_CLASS") == "daemon":
        # Fora do mount namespace endurecido do daemon: o sandbox Bubblewrap do
        # Flatpak monta uma procfs própria que o kernel recusa sob a unit
        # protegida. O serviço transitório do user manager executa limpo.
        systemd_run = shutil.which("systemd-run")
        if systemd_run is None:
            return CommandResult(127, "", "systemd-run não encontrado para Flatpak do daemon")
        command = [
            systemd_run,
            "--user",
            "--wait",
            "--pipe",
            "--collect",
            "--quiet",
            "--service-type=exec",
            "--",
            *command,
        ]
    try:
        process = subprocess.Popen(  # noqa: S603
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
    except OSError as exc:
        return CommandResult(127, "", str(exc))
    deadline = time.monotonic() + timeout
    while True:
        if observer is not None:
            try:
                observer.cancel_check()
            except Exception:
                _stop_flatpak_process(process)
                raise
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            stdout, stderr = _stop_flatpak_process(process)
            return CommandResult(124, stdout or "", stderr or "timeout")
        try:
            stdout, stderr = process.communicate(timeout=min(0.25, remaining))
        except subprocess.TimeoutExpired:
            continue
        return CommandResult(process.returncode, stdout, stderr)


@dataclass(frozen=True)
class FlatpakState:
    installed: bool
    ref: str
    origin: str | None = None
    commit: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "installed": self.installed,
            "ref": self.ref,
            "origin": self.origin,
            "commit": self.commit,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FlatpakState:
        installed = data.get("installed")
        ref = data.get("ref")
        origin = data.get("origin")
        commit = data.get("commit")
        if type(installed) is not bool:
            raise ValueError("installed deve ser booleano")
        if not isinstance(ref, str) or not _REF_RE.fullmatch(ref):
            raise ValueError("ref Flatpak inválido")
        if installed:
            if not isinstance(origin, str) or not _REMOTE_RE.fullmatch(origin):
                raise ValueError("origin Flatpak inválido")
            if not isinstance(commit, str) or not _COMMIT_RE.fullmatch(commit):
                raise ValueError("commit Flatpak inválido")
        elif origin is not None or commit is not None:
            raise ValueError("deployment ausente não pode declarar origin/commit")
        return cls(installed=installed, ref=ref, origin=origin, commit=commit)


class FlatpakPort(Protocol):
    def status(self, ref: str) -> FlatpakState: ...

    def resolve(self, remote: str, ref: str, commit: str) -> str: ...

    def install(self, remote: str, ref: str) -> None: ...

    def deploy(self, ref: str, commit: str) -> None: ...

    def uninstall(self, ref: str) -> None: ...

    def smoke(
        self,
        ref: str,
        arguments: Sequence[str],
        environment: Sequence[tuple[str, str]] = (),
        exit_codes: Sequence[int] = (0,),
        match: str | None = None,
        mode: str = "application",
    ) -> None: ...


class FlatpakCLI:
    """Porta real para a instalação Flatpak do usuário atual."""

    def __init__(self, *, runner: Runner = run_flatpak_command) -> None:
        self._runner = runner

    def status(self, ref: str) -> FlatpakState:
        _require_ref(ref)
        result = self._runner(
            ("flatpak", "list", "--user", "--app", "--columns=application,origin"),
            _STATUS_TIMEOUT,
        )
        _require_command(result, "listar instalações Flatpak")
        for line in result.stdout.splitlines():
            columns = line.split("\t")
            if len(columns) >= 2 and columns[0].strip() == ref:
                origin = columns[1].strip()
                info = self._runner(
                    ("flatpak", "info", "--user", "--show-commit", ref),
                    _STATUS_TIMEOUT,
                )
                _require_command(info, f"ler commit Flatpak de {ref}")
                commit = info.stdout.strip()
                if not _COMMIT_RE.fullmatch(commit) or not _REMOTE_RE.fullmatch(origin):
                    raise SteamZeroError(
                        "E-COMPONENT-DEGRADED",
                        detail=f"estado Flatpak inválido para {ref}",
                    )
                return FlatpakState(True, ref, origin, commit)
        return FlatpakState(False, ref)

    def resolve(self, remote: str, ref: str, commit: str) -> str:
        _require_remote(remote)
        _require_ref(ref)
        _require_commit(commit)
        result = self._runner(
            (
                "flatpak",
                "remote-info",
                "--user",
                "--app",
                "--show-commit",
                f"--commit={commit}",
                remote,
                ref,
            ),
            30.0,
        )
        if result.returncode != 0:
            current = self._runner(
                (
                    "flatpak",
                    "remote-info",
                    "--user",
                    "--app",
                    "--show-commit",
                    remote,
                    ref,
                ),
                30.0,
            )
            current_commit = current.stdout.strip()
            current_detail = (
                f"; commit atual do remoto: {current_commit}"
                if current.returncode == 0 and _COMMIT_RE.fullmatch(current_commit)
                else ""
            )
            raise SteamZeroError(
                "E-SUPPLY-REMOTE-FAILED",
                detail=(
                    f"commit pinado indisponível para {ref}: {_detail(result)}{current_detail}"
                ),
            )
        resolved = result.stdout.strip()
        if resolved != commit:
            raise SteamZeroError(
                "E-SUPPLY-UPSTREAM-GONE",
                detail=f"remote não confirmou o commit pinado de {ref}",
            )
        return resolved

    def install(self, remote: str, ref: str) -> None:
        _require_remote(remote)
        _require_ref(ref)
        result = self._runner(
            (
                "flatpak",
                "install",
                "--user",
                "--app",
                "--noninteractive",
                "--assumeyes",
                "--no-related",
                remote,
                ref,
            ),
            1800.0,
        )
        _require_command(result, f"instalar {ref}")

    def deploy(self, ref: str, commit: str) -> None:
        _require_ref(ref)
        _require_commit(commit)
        result = self._runner(
            (
                "flatpak",
                "update",
                "--user",
                "--app",
                "--noninteractive",
                "--assumeyes",
                "--no-related",
                f"--commit={commit}",
                ref,
            ),
            1800.0,
        )
        _require_command(result, f"implantar commit de {ref}")

    def uninstall(self, ref: str) -> None:
        _require_ref(ref)
        result = self._runner(
            (
                "flatpak",
                "uninstall",
                "--user",
                "--app",
                "--noninteractive",
                "--assumeyes",
                "--no-related",
                ref,
            ),
            1800.0,
        )
        _require_command(result, f"remover deployment de {ref}")

    def smoke(
        self,
        ref: str,
        arguments: Sequence[str],
        environment: Sequence[tuple[str, str]] = (),
        exit_codes: Sequence[int] = (0,),
        match: str | None = None,
        mode: str = "application",
    ) -> None:
        _require_ref(ref)
        if not arguments or any("\x00" in item or len(item) > 256 for item in arguments):
            raise SteamZeroError("E-API-SCHEMA", detail="smoke test Flatpak inválido")
        if any("\x00" in key or "\x00" in value for key, value in environment):
            raise SteamZeroError("E-API-SCHEMA", detail="ambiente de smoke Flatpak inválido")
        if not exit_codes:
            raise SteamZeroError("E-API-SCHEMA", detail="smoke Flatpak sem códigos de saída")
        argv: tuple[str, ...]
        if mode == "flatpak-info":
            if tuple(arguments) != ("--show-commit",) or environment:
                raise SteamZeroError(
                    "E-API-SCHEMA",
                    detail="smoke flatpak-info exige somente --show-commit e sem ambiente",
                )
            argv = ("flatpak", "info", "--user", "--show-commit", ref)
        elif mode == "application":
            argv = (
                "flatpak",
                "run",
                "--user",
                "--die-with-parent",
                *(f"--env={key}={value}" for key, value in environment),
                ref,
                *arguments,
            )
        else:
            raise SteamZeroError("E-API-SCHEMA", detail=f"modo de smoke Flatpak inválido: {mode}")
        result = self._runner(argv, _SMOKE_TIMEOUT)
        codes_ok = result.returncode in exit_codes
        match_ok = match is None or re.search(match, f"{result.stdout}\n{result.stderr}", re.M)
        if not codes_ok or not match_ok:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail=_smoke_failure_detail(
                    ref, argv, result, pattern=None if not codes_ok else match
                ),
            )


@dataclass(frozen=True)
class FlatpakPlan:
    plan_id: str
    confirm_token: str
    adapter_id: str
    ref: str
    remote: str
    target_commit: str
    before: FlatpakState
    action: str
    status: str
    created_at: str
    expires_at: str
    preview: str
    schema_version: int = 1
    rollback_guarantee: str = "G-DEPLOYMENT"

    def to_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": self.schema_version,
            "planId": self.plan_id,
            "confirmToken": self.confirm_token,
            "adapterId": self.adapter_id,
            "ref": self.ref,
            "remote": self.remote,
            "targetCommit": self.target_commit,
            "before": self.before.to_dict(),
            "action": self.action,
            "status": self.status,
            "createdAt": self.created_at,
            "expiresAt": self.expires_at,
            "rollbackGuarantee": self.rollback_guarantee,
            "preview": self.preview,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FlatpakPlan:
        return cls(
            plan_id=str(data["planId"]),
            confirm_token=str(data["confirmToken"]),
            adapter_id=str(data["adapterId"]),
            ref=str(data["ref"]),
            remote=str(data["remote"]),
            target_commit=str(data["targetCommit"]),
            before=FlatpakState.from_dict(data["before"]),
            action=str(data["action"]),
            status=str(data["status"]),
            created_at=str(data["createdAt"]),
            expires_at=str(data["expiresAt"]),
            rollback_guarantee=str(data["rollbackGuarantee"]),
            preview=str(data["preview"]),
            schema_version=int(data["schemaVersion"]),
        )


@dataclass(frozen=True)
class FlatpakApplyResult:
    operation_id: str
    status: str
    adapter_id: str
    commit: str | None

    def to_dict(self) -> dict[str, object | None]:
        return {
            "operationId": self.operation_id,
            "status": self.status,
            "adapterId": self.adapter_id,
            "commit": self.commit,
        }


@dataclass(frozen=True)
class FlatpakOperation:
    operation_id: str
    plan_id: str
    adapter_id: str
    ref: str
    remote: str
    target_commit: str
    before: FlatpakState
    status: str
    started_at: str
    error: str | None = None
    schema_version: int = 1

    def to_dict(self) -> dict[str, object | None]:
        return {
            "schemaVersion": self.schema_version,
            "operationId": self.operation_id,
            "planId": self.plan_id,
            "adapterId": self.adapter_id,
            "ref": self.ref,
            "remote": self.remote,
            "targetCommit": self.target_commit,
            "before": self.before.to_dict(),
            "status": self.status,
            "startedAt": self.started_at,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FlatpakOperation:
        return cls(
            operation_id=str(data["operationId"]),
            plan_id=str(data["planId"]),
            adapter_id=str(data["adapterId"]),
            ref=str(data["ref"]),
            remote=str(data["remote"]),
            target_commit=str(data["targetCommit"]),
            before=FlatpakState.from_dict(data["before"]),
            status=str(data["status"]),
            started_at=str(data["startedAt"]),
            error=str(data["error"]) if data.get("error") is not None else None,
            schema_version=int(data["schemaVersion"]),
        )


class FlatpakExecutor:
    """Orquestra lifecycle Flatpak com rollback do deployment e recovery."""

    def __init__(
        self,
        store: StateStore,
        registry: AdapterRegistry,
        flatpak: FlatpakPort,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._flatpak = flatpak
        self._now = now or (lambda: datetime.now(UTC))

    def status(self, adapter_id: str) -> dict[str, object | None]:
        manifest, source = self._flatpak_source(adapter_id, allow_eol=True)
        state = self._flatpak.status(_source_ref(source))
        data: dict[str, object | None] = {
            "id": adapter_id,
            "kind": manifest.kind,
            "state": "installed" if state.installed else "missing",
            "origin": "flatpak" if state.installed else None,
            "remote": state.origin,
            "commit": state.commit,
            "targetCommit": source.version,
            "pinned": state.commit == source.version,
            "endOfLife": source.end_of_life,
        }
        if state.installed and state.commit != source.version:
            data["state"] = "degraded"
        return data

    def plan_install(self, adapter_id: str, *, ttl_s: int = _DEFAULT_TTL_S) -> FlatpakPlan:
        manifest, source = self._flatpak_source(adapter_id)
        ref = _source_ref(source)
        remote = _source_remote(source)
        before = self._flatpak.status(ref)
        if before.installed and before.origin != remote:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail=f"{ref} pertence ao remote {before.origin}, não a {remote}",
            )
        action = (
            "noop"
            if before.installed and before.commit == source.version
            else "update"
            if before.installed
            else "install"
        )
        if action != "noop" and action not in manifest.capabilities:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail=f"adapter {adapter_id} não declara capability {action}",
            )
        self._require_resolvable(remote, ref, source.version)
        if before.installed and before.commit is not None and before.commit != source.version:
            self._require_resolvable(remote, ref, before.commit)
        now = self._utc_now()
        plan = FlatpakPlan(
            plan_id=ids.new_ulid(),
            confirm_token=secrets.token_urlsafe(24),
            adapter_id=manifest.id,
            ref=ref,
            remote=remote,
            target_commit=source.version,
            before=before,
            action=action,
            status="pending",
            created_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=ttl_s)).isoformat(),
            preview=(
                f"{action} {manifest.id} como Flatpak user-scoped\n"
                f"ref: {ref}\ncommit alvo: {source.version}\n"
                "rollback: restaura somente o deployment; dados da aplicação são preservados"
            ),
        )
        self._save_plan(plan)
        return plan

    def plan_uninstall(self, adapter_id: str, *, ttl_s: int = _DEFAULT_TTL_S) -> FlatpakPlan:
        """Planeja remover o deployment, preservando os dados da aplicação.

        ``flatpak uninstall`` sem ``--delete-data`` mantém ``~/.var/app/<ref>``:
        saves, configuração e estado do emulador sobrevivem. Isso é contrato, e
        não detalhe de implementação — desinstalar não pode virar um caminho
        para perder save.
        """
        manifest, source = self._flatpak_source(adapter_id)
        ref = _source_ref(source)
        remote = _source_remote(source)
        if "uninstall" not in manifest.capabilities:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail=f"adapter {adapter_id} não declara capability uninstall",
            )
        before = self._flatpak.status(ref)
        if not before.installed:
            raise SteamZeroError("E-COMPONENT-DEGRADED", detail=f"{adapter_id} não está instalado")
        now = self._utc_now()
        plan = FlatpakPlan(
            plan_id=ids.new_ulid(),
            confirm_token=secrets.token_urlsafe(24),
            adapter_id=manifest.id,
            ref=ref,
            remote=remote,
            target_commit=source.version,
            before=before,
            action="uninstall",
            status="pending",
            created_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=ttl_s)).isoformat(),
            preview=(
                f"remover {manifest.id} (Flatpak user-scoped)\n"
                f"ref: {ref}\ncommit implantado: {before.commit}\n"
                "dados da aplicação são PRESERVADOS; rollback reinstala o mesmo commit"
            ),
        )
        self._save_plan(plan)
        return plan

    def apply(
        self, plan_id: str, confirm_token: str, *, operation_id: str | None = None
    ) -> FlatpakApplyResult:
        """Aplica uma confirmação e fecha o plano em toda saída não-crash."""
        plan = self._load_plan(plan_id)
        self._validate_pending(plan, confirm_token)
        try:
            return self._apply_unterminalized(plan_id, confirm_token, operation_id=operation_id)
        except Exception:
            self._abort_plan(plan_id)
            raise

    def _apply_unterminalized(
        self, plan_id: str, confirm_token: str, *, operation_id: str | None = None
    ) -> FlatpakApplyResult:
        # A leitura externa ao lock serve apenas para resolver o recurso. Toda
        # precondição que autoriza efeito é recarregada e revalidada sob o lock.
        plan = self._load_plan(plan_id)
        self._validate_pending(plan, confirm_token)
        manifest, source = self._flatpak_source(plan.adapter_id)
        if self._source_fingerprint(source) != (plan.ref, plan.remote, plan.target_commit):
            raise SteamZeroError("E-TX-STALE-PLAN", detail="manifesto mudou após o plano")
        # O lifecycle pode reservar um operationId conhecido pelo cliente antes
        # de iniciar o trabalho. O plano Flatpak segue em seu namespace próprio,
        # portanto não há colisão entre os dois arquivos de plano.
        lock_owner = operation_id or ids.new_ulid()
        with ResourceLock(f"flatpak:user:{plan.ref}", job_id=lock_owner, lease_seconds=3600):
            plan = self._load_plan(plan_id)
            self._validate_pending(plan, confirm_token)
            manifest, source = self._flatpak_source(plan.adapter_id)
            if self._source_fingerprint(source) != (plan.ref, plan.remote, plan.target_commit):
                raise SteamZeroError("E-TX-STALE-PLAN", detail="manifesto mudou após o plano")
            current = self._flatpak.status(plan.ref)
            if current != plan.before:
                raise SteamZeroError("E-TX-STALE-PLAN", detail="deployment mudou após o plano")
            if plan.action == "noop":
                report_flatpak_stage("verifying", current=1, total=2)
                report_flatpak_stage("persisting", current=2, total=2)
                self._save_plan(replace(plan, status="applied"))
                self._persist(manifest, current)
                return FlatpakApplyResult("", "noop", plan.adapter_id, current.commit)

            operation = FlatpakOperation(
                operation_id=lock_owner,
                plan_id=plan.plan_id,
                adapter_id=plan.adapter_id,
                ref=plan.ref,
                remote=plan.remote,
                target_commit=plan.target_commit,
                before=plan.before,
                status="applying",
                started_at=self._utc_now().isoformat(),
            )
            self._save_operation(operation)
            try:
                if plan.action == "uninstall":
                    report_flatpak_stage("uninstalling", current=1, total=3)
                    self._flatpak.uninstall(plan.ref)
                    report_flatpak_stage("verifying", current=2, total=3)
                    final = self._flatpak.status(plan.ref)
                    if final.installed:
                        raise SteamZeroError(
                            "E-TX-VERIFY-FAILED",
                            detail=f"{plan.ref} continua implantado após a remoção",
                        )
                    report_flatpak_stage("persisting", current=3, total=3)
                    self._persist(manifest, final)
                    self._save_operation(replace(operation, status="committed"))
                    self._save_plan(replace(plan, status="applied"))
                    return FlatpakApplyResult(operation.operation_id, "ok", plan.adapter_id, None)
                total = 5 if not plan.before.installed else 4
                current_stage = 0
                if not plan.before.installed:
                    current_stage += 1
                    report_flatpak_stage("installing", current=current_stage, total=total)
                    self._flatpak.install(plan.remote, plan.ref)
                current_stage += 1
                report_flatpak_stage("deploying", current=current_stage, total=total)
                self._flatpak.deploy(plan.ref, plan.target_commit)
                current_stage += 1
                report_flatpak_stage("verifying", current=current_stage, total=total)
                self._verify_target(plan.ref, plan.remote, plan.target_commit)
                current_stage += 1
                report_flatpak_stage("smoke", current=current_stage, total=total)
                self._flatpak.smoke(
                    plan.ref,
                    manifest.verify_smoke_test,
                    manifest.verify_environment,
                    manifest.verify_smoke_exit_codes,
                    manifest.verify_smoke_match,
                    manifest.verify_smoke_mode,
                )
                final = self._flatpak.status(plan.ref)
                current_stage += 1
                report_flatpak_stage("persisting", current=current_stage, total=total)
                self._persist(manifest, final)
                self._save_operation(replace(operation, status="committed"))
                self._save_plan(replace(plan, status="applied"))
            except Exception as exc:
                self._rollback_failed_apply(operation, manifest, exc)
        return FlatpakApplyResult(operation.operation_id, "ok", plan.adapter_id, plan.target_commit)

    def rollback(self, operation_id: str) -> FlatpakApplyResult:
        # O primeiro load resolve o recurso; status e deployment são recarregados
        # após adquirir o lock para impedir rollback sobre mudança concorrente.
        operation = self._load_operation(operation_id)
        with ResourceLock(
            f"flatpak:user:{operation.ref}", job_id=operation.operation_id, lease_seconds=3600
        ):
            operation = self._load_operation(operation_id)
            manifest = self._registry.get(operation.adapter_id)
            if operation.status == "rolled-back":
                state = self._flatpak.status(operation.ref)
                return FlatpakApplyResult(
                    operation_id, "rolled-back", operation.adapter_id, state.commit
                )
            if operation.status != "committed":
                raise SteamZeroError(
                    "E-TX-STALE-PLAN",
                    detail=f"operação não pode sofrer rollback (status={operation.status})",
                )
            current = self._flatpak.status(operation.ref)
            expected = FlatpakState(True, operation.ref, operation.remote, operation.target_commit)
            if current != expected:
                raise SteamZeroError(
                    "E-TX-STALE-PLAN", detail="deployment mudou depois da operação"
                )
            rolling_back = replace(operation, status="rolling-back")
            self._save_operation(rolling_back)
            try:
                self._restore(rolling_back)
                final = self._flatpak.status(operation.ref)
                self._persist(manifest, final)
                self._save_operation(replace(operation, status="rolled-back"))
            except Exception as exc:
                self._save_operation(replace(operation, status="recovery-required", error=str(exc)))
                raise SteamZeroError(
                    "E-TX-ROLLBACK-FAILED",
                    operation_id=operation.operation_id,
                    detail=f"rollback Flatpak falhou: {exc}",
                ) from exc
        return FlatpakApplyResult(operation_id, "rolled-back", operation.adapter_id, final.commit)

    def recover(self) -> list[FlatpakApplyResult]:
        recovered: list[FlatpakApplyResult] = []
        fs.ensure_dir(paths.component_operations_dir())
        for entry in sorted(paths.component_operations_dir().glob("*.json")):
            if entry.is_symlink() or not entry.is_file():
                continue
            # Operações de reparo (schemaVersion 2) vivem no MESMO diretório,
            # mas são reconciliadas pelo lifecycle, não por este executor.
            try:
                raw = json.loads(entry.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if raw.get("schemaVersion") != 1:
                continue
            operation = self._load_operation_file(entry)
            if operation.status not in {"applying", "rolling-back", "recovery-required"}:
                continue
            try:
                with ResourceLock(
                    f"flatpak:user:{operation.ref}",
                    job_id=operation.operation_id,
                    lease_seconds=3600,
                ):
                    operation = self._load_operation(operation.operation_id)
                    if operation.status not in {
                        "applying",
                        "rolling-back",
                        "recovery-required",
                    }:
                        continue
                    manifest = self._registry.get(operation.adapter_id)
                    self._restore(operation)
                    final = self._flatpak.status(operation.ref)
                    self._save_operation(replace(operation, status="rolled-back", error=None))
                    self._persist(manifest, final)
                    self._abort_plan(operation.plan_id)
            except Exception as exc:
                self._save_operation(replace(operation, status="recovery-required", error=str(exc)))
                raise SteamZeroError(
                    "E-TX-ROLLBACK-FAILED",
                    operation_id=operation.operation_id,
                    detail=f"recovery Flatpak falhou: {exc}",
                ) from exc
            recovered.append(
                FlatpakApplyResult(
                    operation.operation_id,
                    "rolled-back",
                    operation.adapter_id,
                    final.commit,
                )
            )
        return recovered

    def recover_plan(self, plan_id: str) -> str:
        """Terminaliza um plano pela operação Flatpak durável que o referencia."""
        plan = self._load_plan(plan_id)
        if plan.status != "pending":
            return plan.status
        operations = self._operations_for_plan(plan_id)
        if any(
            operation.status in {"applying", "rolling-back", "recovery-required"}
            for operation in operations
        ):
            self.recover()
            operations = self._operations_for_plan(plan_id)
        terminal = (
            "applied"
            if any(operation.status == "committed" for operation in operations)
            else "aborted"
        )
        self._save_plan(replace(plan, status=terminal))
        return terminal

    def _operations_for_plan(self, plan_id: str) -> list[FlatpakOperation]:
        operations: list[FlatpakOperation] = []
        fs.ensure_dir(paths.component_operations_dir())
        for entry in sorted(paths.component_operations_dir().glob("*.json")):
            if entry.is_symlink() or not entry.is_file():
                continue
            try:
                raw = json.loads(entry.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if raw.get("schemaVersion") == 1 and raw.get("planId") == plan_id:
                operations.append(self._load_operation_file(entry))
        return operations

    def _rollback_failed_apply(
        self, operation: FlatpakOperation, manifest: AdapterManifest, cause: Exception
    ) -> None:
        try:
            self._restore(operation)
            final = self._flatpak.status(operation.ref)
            self._save_operation(replace(operation, status="rolled-back", error=str(cause)))
            self._persist(manifest, final)
        except Exception as rollback_exc:
            self._save_operation(
                replace(operation, status="recovery-required", error=str(rollback_exc))
            )
            raise SteamZeroError(
                "E-TX-ROLLBACK-FAILED",
                operation_id=operation.operation_id,
                detail=f"apply falhou ({cause}); rollback falhou ({rollback_exc})",
            ) from rollback_exc
        if isinstance(cause, JobCancelled):
            raise cause
        raise SteamZeroError(
            "E-COMPONENT-UPDATE-ROLLEDBACK",
            operation_id=operation.operation_id,
            auto_action="deployment anterior restaurado",
            detail=str(cause),
        ) from cause

    def _restore(self, operation: FlatpakOperation) -> None:
        current = self._flatpak.status(operation.ref)
        before = operation.before
        if not before.installed:
            if current.installed:
                self._flatpak.uninstall(operation.ref)
        else:
            if before.origin is None or before.commit is None:
                raise SteamZeroError("E-STATE-INTEGRITY", detail="snapshot Flatpak incompleto")
            if not current.installed:
                self._flatpak.install(before.origin, operation.ref)
            self._flatpak.deploy(operation.ref, before.commit)
        restored = self._flatpak.status(operation.ref)
        if restored != before:
            raise SteamZeroError(
                "E-TX-ROLLBACK-FAILED",
                operation_id=operation.operation_id,
                detail="deployment anterior não foi restaurado",
            )

    def _verify_target(self, ref: str, remote: str, commit: str) -> None:
        state = self._flatpak.status(ref)
        if state != FlatpakState(True, ref, remote, commit):
            raise SteamZeroError(
                "E-TX-VERIFY-FAILED",
                detail=f"deployment Flatpak de {ref} diverge do commit pinado",
            )

    def _validate_pending(self, plan: FlatpakPlan, confirm_token: str) -> None:
        if plan.status != "pending":
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail=f"plano não está pendente ({plan.status})"
            )
        if not secrets.compare_digest(confirm_token, plan.confirm_token):
            raise SteamZeroError("E-TX-CONFIRM-REQUIRED", detail="confirmToken incorreto")
        try:
            expires_at = datetime.fromisoformat(plan.expires_at)
        except ValueError as exc:
            raise SteamZeroError("E-STATE-INTEGRITY", detail="expiração do plano inválida") from exc
        if self._utc_now() > expires_at:
            self._save_plan(replace(plan, status="aborted"))
            raise SteamZeroError("E-TX-CONFIRM-REQUIRED", detail="confirmToken expirado")

    def _abort_plan(self, plan_id: str) -> None:
        plan = self._load_plan(plan_id)
        if plan.status == "pending":
            self._save_plan(replace(plan, status="aborted"))

    def _flatpak_source(
        self, adapter_id: str, *, allow_eol: bool = False
    ) -> tuple[AdapterManifest, AdapterSource]:
        manifest = self._registry.get(adapter_id)
        source = manifest.preferred_source("flatpak", allow_eol=allow_eol)
        _source_ref(source)
        _source_remote(source)
        _require_commit(source.version)
        return manifest, source

    def _require_resolvable(self, remote: str, ref: str, commit: str) -> None:
        if self._flatpak.resolve(remote, ref, commit) != commit:
            raise SteamZeroError("E-SUPPLY-UPSTREAM-GONE", detail=f"commit {commit} não confirmado")

    def _persist(self, manifest: AdapterManifest, state: FlatpakState) -> None:
        source = manifest.preferred_source("flatpak", allow_eol=True)
        lifecycle_state = (
            "missing"
            if not state.installed
            else "installed"
            if state.commit == source.version
            else "degraded"
        )
        self._store.save_component(
            {
                "id": manifest.id,
                "adapter_id": manifest.id,
                "kind": manifest.kind,
                "version": state.commit,
                "origin": "flatpak" if state.installed else None,
                "state": lifecycle_state,
                "manifest_hash": manifest.manifest_hash,
            }
        )

    def _save_plan(self, plan: FlatpakPlan) -> None:
        data = plan.to_dict()
        try:
            contracts.validate(data, _PLAN_SCHEMA)
        except ValidationError as exc:
            raise SteamZeroError(
                "E-STATE-INTEGRITY", detail=f"plano Flatpak inválido: {exc}"
            ) from exc
        fs.ensure_dir(paths.plans_dir())
        fs.write_atomic_text(
            paths.plan_path(plan.plan_id),
            json.dumps(data, ensure_ascii=False, sort_keys=True),
        )

    def _load_plan(self, plan_id: str) -> FlatpakPlan:
        if not ids.is_ulid(plan_id):
            raise SteamZeroError("E-TX-STALE-PLAN", detail="planId inválido")
        path = paths.plan_path(plan_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            contracts.validate(data, _PLAN_SCHEMA)
            return FlatpakPlan.from_dict(data)
        except FileNotFoundError as exc:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano não encontrado") from exc
        except (
            OSError,
            KeyError,
            TypeError,
            ValueError,
            ValidationError,
            json.JSONDecodeError,
        ) as exc:
            raise SteamZeroError(
                "E-STATE-INTEGRITY", detail=f"plano Flatpak corrompido: {exc}"
            ) from exc

    def _save_operation(self, operation: FlatpakOperation) -> None:
        fs.ensure_dir(paths.component_operations_dir())
        fs.write_atomic_text(
            paths.component_operation_path(operation.operation_id),
            json.dumps(operation.to_dict(), ensure_ascii=False, sort_keys=True),
        )
        self._store.save_operation(
            operation.operation_id,
            journal_path=str(paths.component_operation_path(operation.operation_id)),
            state=operation.status,
        )

    def _load_operation(self, operation_id: str) -> FlatpakOperation:
        if not ids.is_ulid(operation_id):
            raise SteamZeroError("E-TX-STALE-PLAN", detail="operationId inválido")
        path = paths.component_operation_path(operation_id)
        try:
            return self._load_operation_file(path)
        except FileNotFoundError as exc:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="operação não encontrada") from exc

    @staticmethod
    def _load_operation_file(path: Path) -> FlatpakOperation:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            operation = FlatpakOperation.from_dict(data)
        except FileNotFoundError:
            raise
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise SteamZeroError(
                "E-STATE-INTEGRITY", detail=f"operação Flatpak corrompida: {exc}"
            ) from exc
        if (
            operation.schema_version != 1
            or not ids.is_ulid(operation.operation_id)
            or not ids.is_ulid(operation.plan_id)
            or operation.before.ref != operation.ref
            or operation.status
            not in {
                "applying",
                "rolling-back",
                "committed",
                "rolled-back",
                "recovery-required",
            }
        ):
            raise SteamZeroError("E-STATE-INTEGRITY", detail="operação Flatpak inválida")
        try:
            ids.require_slug(operation.adapter_id)
            _require_ref(operation.ref)
            _require_remote(operation.remote)
            _require_commit(operation.target_commit)
            started_at = datetime.fromisoformat(operation.started_at)
            if started_at.tzinfo is None:
                raise ValueError("startedAt sem timezone")
        except (SteamZeroError, ValueError) as exc:
            raise SteamZeroError(
                "E-STATE-INTEGRITY", detail=f"operação Flatpak inválida: {exc}"
            ) from exc
        return operation

    def _utc_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _source_fingerprint(source: AdapterSource) -> tuple[str, str, str]:
        return (_source_ref(source), _source_remote(source), source.version)


def _source_ref(source: AdapterSource) -> str:
    if source.ref is None:
        raise SteamZeroError("E-API-SCHEMA", detail="fonte Flatpak sem ref")
    _require_ref(source.ref)
    return source.ref


def _source_remote(source: AdapterSource) -> str:
    if source.remote is None:
        raise SteamZeroError("E-API-SCHEMA", detail="fonte Flatpak sem remote")
    _require_remote(source.remote)
    return source.remote


def _require_ref(ref: str) -> None:
    if not _REF_RE.fullmatch(ref):
        raise SteamZeroError("E-API-SCHEMA", detail="ref Flatpak inválido")


def _require_remote(remote: str) -> None:
    if not _REMOTE_RE.fullmatch(remote):
        raise SteamZeroError("E-API-SCHEMA", detail="remote Flatpak inválido")


def _require_commit(commit: str) -> None:
    if not _COMMIT_RE.fullmatch(commit):
        raise SteamZeroError("E-SUPPLY-NO-CHECKSUM", detail="commit Flatpak não pinado")


def _detail(result: CommandResult) -> str:
    return (result.stderr or result.stdout or f"exit {result.returncode}").strip()[:500]


_SMOKE_PAYLOAD_LIMIT = 12_000


def _smoke_failure_detail(
    ref: str, argv: Sequence[str], result: CommandResult, pattern: str | None = None
) -> str:
    """Preserva o payload integral do smoke para a evidência da VM M10.

    ``_detail`` truncava o envelope a 500 caracteres e a causa real do smoke
    (retorno, stdout e stderr completos) nunca chegava à evidência — a falha do
    PCSX2 ficou indiagnosticável por esse motivo. Aqui o comando exato e o
    retorno ficam no início e a saída é preservada na cauda, onde aparecem o
    crash e o encerramento do processo. ``pattern`` registra a exigência de
    ``smokeMatch`` quando o retorno passou mas a saída não correspondeu.
    """
    head = (
        f"falha ao smoke test de {ref}\ncomando: {' '.join(argv)}\nretorno: {result.returncode}\n"
    )
    if pattern is not None:
        head += f"saída não corresponde ao padrão {pattern!r}\n"
    output = f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    if len(head) + len(output) > _SMOKE_PAYLOAD_LIMIT:
        marker = f"... saída truncada (limite {_SMOKE_PAYLOAD_LIMIT} caracteres):\n"
        budget = max(1, _SMOKE_PAYLOAD_LIMIT - len(head) - len(marker))
        output = marker + output[-budget:]
    return head + output


def _require_command(result: CommandResult, action: str) -> None:
    if result.returncode != 0:
        raise SteamZeroError("E-COMPONENT-DEGRADED", detail=f"falha ao {action}: {_detail(result)}")
