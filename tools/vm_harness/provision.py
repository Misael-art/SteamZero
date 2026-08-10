#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Provisiona e certifica uma VM Arch descartável para o M10.

O módulo é deliberadamente separado do driver puro. ``--plan`` só imprime o
que seria feito; ``--execute --confirm EXECUTAR-VM-M10`` é a única forma de
criar disco, VM ou relatório. Isso não substitui a autorização explícita do
operador exigida por AGENTS.md: é uma segunda trava técnica para evitar que uma
revisão de plano vire mutação por acidente.

Uma execução autorizada cria uma overlay qcow2 sobre uma imagem cloud Arch
fornecida pelo operador, gera cloud-init (Python, SDDM, Flatpak, SSH e btrfs),
arranca a VM com virt-install, copia a árvore do commit exato por ``git
archive`` e chama ``component`` por SSH. Antes dos ciclos, ela prova console
serial e SSH, coleta baseline e cria snapshot Btrfs. Depois do relatório M10,
configura esse snapshot como default, reinicia a VM e confirma que os três
Flatpaks voltaram ao baseline. A VM e a overlay são removidas no fim; em falha,
os artefatos de evidência ficam no diretório de trabalho para inspeção.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
TOOLS_ROOT = ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from vm_harness.driver import (  # noqa: E402 - sys.path precisa incluir tools no entry point direto
    FLATHUB_RETRY_DELAYS,
    M10_FLATPAK_EMULATORS,
    ComponentClient,
    certify_emulator,
    certify_emulator_minimal,
    m10_pinned_commits,
    render_evidence_report,
)

_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{2,62}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40,64}$")
_KEY_PREFIXES = ("ssh-ed25519 ", "ssh-rsa ", "ecdsa-sha2-", "sk-ssh-ed25519@")
_SNAPSHOT_ROOT = "/var/lib/steamzero-m10-snapshots"
_GUEST_SOURCE = "/home/steamzero/steamzero-src"
_GUEST_USER = "steamzero"
_CONFIRM = "EXECUTAR-VM-M10"
_FLATHUB_URL = "https://dl.flathub.org/repo/flathub.flatpakrepo"
_GUEST_PACKAGES: tuple[str, ...] = (
    "python",
    "python-jsonschema",
    "flatpak",
    # SDDM exige um provedor de ttf-font. Torná-lo alvo explícito impede que o
    # pacman pergunte interativamente qual dos provedores deve usar.
    "noto-fonts",
    "sddm",
    "openssh",
    "btrfs-progs",
    "git",
)
_GUEST_PACKAGE_ARGS = " ".join(_GUEST_PACKAGES)
_PACMAN_RETRY_DELAYS: tuple[int, ...] = (5, 10, 20)
_PACMAN_ATTEMPT_TIMEOUT_SECONDS = 600
_PACMAN_KILL_AFTER_SECONDS = 30
_CLOUD_INIT_TIMEOUT_SECONDS = 2_600

REQUIRED_BINARIES: tuple[str, ...] = (
    "virt-install",
    "virsh",
    "qemu-img",
    "ssh",
    "git",
)
SEED_BUILDERS: tuple[str, ...] = ("cloud-localds", "xorriso", "genisoimage")


@dataclass(frozen=True)
class VmConfig:
    """Entradas validadas para uma execução destrutiva e descartável."""

    source_commit: str
    vm_name: str
    base_image: Path
    ssh_public_key: Path
    work_dir: Path
    ssh_private_key: Path | None = None
    disk_size_gb: int = 40
    memory_mib: int = 4096
    cpus: int = 4

    def validate(self, *, executing: bool) -> None:
        if not _COMMIT_RE.fullmatch(self.source_commit):
            raise ValueError("--source-commit exige SHA completo de 40 ou 64 hexadecimais")
        if not _NAME_RE.fullmatch(self.vm_name):
            raise ValueError("--vm-name deve ter 3-63 caracteres [a-z0-9-]")
        if min(self.disk_size_gb, self.memory_mib, self.cpus) <= 0:
            raise ValueError("disco, memória e CPUs devem ser positivos")
        if executing and not self.base_image.is_file():
            raise ValueError("--base-image deve apontar para uma imagem cloud Arch regular")
        if executing and not self.ssh_public_key.is_file():
            raise ValueError("--ssh-public-key deve apontar para uma chave pública regular")
        if executing and (self.ssh_private_key is None or not self.ssh_private_key.is_file()):
            raise ValueError("--ssh-private-key deve apontar para a chave privada correspondente")

    @property
    def run_dir(self) -> Path:
        return self.work_dir / self.vm_name


@dataclass(frozen=True)
class CommandResult:
    """Saída de processo injetável, sempre binária para archive e SSH."""

    returncode: int
    stdout: bytes = b""
    stderr: bytes = b""


Runner = Callable[[Sequence[str], bytes | None, float], CommandResult]


class RequiredCommandError(RuntimeError):
    """Falha de subprocesso com seus bytes preservados para a evidência."""

    def __init__(self, label: str, result: CommandResult) -> None:
        self.label = label
        self.result = result
        detail = (
            result.stderr.decode("utf-8", errors="replace").strip()
            or result.stdout.decode("utf-8", errors="replace").strip()
            or "sem diagnóstico"
        )
        super().__init__(f"{label} falhou: {detail}")


class GuestComponentError(RuntimeError):
    """Envelope JSON reprovado da CLI do guest, sem perder payload."""

    def __init__(self, action: str, envelope: dict[str, Any]) -> None:
        self.action = action
        self.envelope = envelope
        detail = envelope.get("error") or envelope.get("data") or envelope
        super().__init__(f"component {action} falhou: {json.dumps(detail, sort_keys=True)}")


class GuestReadinessError(RuntimeError):
    """Readiness esgotado, com a última causa observada no guest."""

    def __init__(self, last_issue: dict[str, Any]) -> None:
        self.last_issue = last_issue
        super().__init__("VM não obteve IPv4/SSH antes do prazo")


class FlathubSetupError(RuntimeError):
    """Configuração do remote falhou; guarda cada tentativa para evidência."""

    def __init__(self, attempts: list[dict[str, Any]]) -> None:
        self.attempts = attempts
        super().__init__("não foi possível configurar o remote Flathub na VM")


def _run(argv: Sequence[str], input_data: bytes | None, timeout: float) -> CommandResult:
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "check": False,
        "timeout": timeout,
    }
    if input_data is None:
        kwargs["stdin"] = subprocess.DEVNULL
    else:
        kwargs["input"] = input_data
    completed = subprocess.run(list(argv), **kwargs)
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def _required(value: CommandResult, label: str) -> bytes:
    if value.returncode != 0:
        raise RequiredCommandError(label, value)
    return value.stdout


def _preflight() -> None:
    missing = [name for name in REQUIRED_BINARIES if shutil.which(name) is None]
    if missing:
        raise RuntimeError("lab KVM/libvirt incompleto; faltam: " + ", ".join(missing))
    if not any(shutil.which(name) is not None for name in SEED_BUILDERS):
        raise RuntimeError(
            "lab KVM/libvirt incompleto; falta cloud-localds, xorriso ou genisoimage"
        )


def _seed_argv(seed: Path, user_data: Path, meta_data: Path) -> tuple[str, ...]:
    """Cria uma ISO ``cidata`` com ferramenta presente, sem instalar no host."""
    if shutil.which("cloud-localds") is not None:
        return ("cloud-localds", str(seed), str(user_data), str(meta_data))
    if shutil.which("xorriso") is not None:
        return (
            "xorriso",
            "-as",
            "mkisofs",
            "-output",
            str(seed),
            "-volid",
            "cidata",
            "-joliet",
            "-rock",
            str(user_data),
            str(meta_data),
        )
    if shutil.which("genisoimage") is not None:
        return (
            "genisoimage",
            "-output",
            str(seed),
            "-volid",
            "cidata",
            "-joliet",
            "-rock",
            str(user_data),
            str(meta_data),
        )
    raise RuntimeError("não há gerador de ISO cloud-init disponível")


def _public_key(path: Path) -> str:
    key = path.read_text(encoding="utf-8").strip()
    if "\n" in key or not key.startswith(_KEY_PREFIXES):
        raise ValueError("--ssh-public-key não contém uma chave OpenSSH de linha única")
    return key


def _private_identity(config: VmConfig) -> Path:
    """Materializa a chave em arquivo local ``0600`` para uso exclusivo do SSH.

    O diretório de trabalho do harness pode estar em volume removível que não
    preserva permissões POSIX. OpenSSH recusa legitimamente uma chave assim; a
    cópia temporária fica no diretório seguro padrão do sistema e é removida
    pelo cleanup de :func:`provision`.
    """
    if config.ssh_private_key is None:
        raise RuntimeError("execução sem identidade SSH privada")
    descriptor, temporary_name = tempfile.mkstemp(prefix="steamzero-m10-identity-")
    identity_file = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with config.ssh_private_key.open("rb") as source, os.fdopen(descriptor, "wb") as target:
            shutil.copyfileobj(source, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.close(descriptor)
        identity_file.unlink(missing_ok=True)
        raise
    return identity_file


def render_cloud_init(config: VmConfig, public_key: str) -> tuple[str, str]:
    """Gera user-data/meta-data sem escrever no host.

    A imagem base é intencionalmente uma entrada do operador: URL e checksum de
    imagem não são inventados pela automação. O cloud-init instala apenas o que
    a VM precisa e cria um usuário de laboratório isolado.
    """
    user_data = textwrap.dedent(
        f"""\
        #cloud-config
        hostname: {config.vm_name}
        users:
          - name: {_GUEST_USER}
            groups: [wheel]
            shell: /bin/bash
            sudo: "ALL=(ALL) NOPASSWD:ALL"
            ssh_authorized_keys:
              - {public_key}
        package_update: false
        runcmd:
          - |
            set -u
            systemctl enable --now sshd.service || true
            for attempt in 1 2 3 4; do
              timeout --kill-after={_PACMAN_KILL_AFTER_SECONDS}s \\
                {_PACMAN_ATTEMPT_TIMEOUT_SECONDS}s \\
                pacman -Sy --noconfirm --needed \\
                {_GUEST_PACKAGE_ARGS} && exit 0
              status=$?
              echo "steamzero-m10: pacman bootstrap attempt $attempt failed (status=$status)" >&2
              pkill -9 -x pacman 2>/dev/null || true
              sleep 2
              if ! pgrep -x pacman >/dev/null 2>&1; then
                rm -f /var/lib/pacman/db.lck
                echo "steamzero-m10: lock órfão do pacman removido" >&2
              fi
              case "$attempt" in
                1) sleep {_PACMAN_RETRY_DELAYS[0]} ;;
                2) sleep {_PACMAN_RETRY_DELAYS[1]} ;;
                3) sleep {_PACMAN_RETRY_DELAYS[2]} ;;
                *) exit "$status" ;;
              esac
            done
          - [systemctl, enable, --now, sshd.service]
        """
    )
    meta_data = (
        f"instance-id: {config.vm_name}-{config.source_commit[:12]}\n"
        f"local-hostname: {config.vm_name}\n"
    )
    return user_data, meta_data


def build_virt_install_argv(config: VmConfig, overlay: Path, seed: Path) -> list[str]:
    """Monta o argv fixo de virt-install; nenhum valor vira shell."""
    return [
        "virt-install",
        "--connect",
        "qemu:///system",
        "--name",
        config.vm_name,
        "--memory",
        str(config.memory_mib),
        "--vcpus",
        str(config.cpus),
        "--import",
        "--os-variant",
        "archlinux",
        "--disk",
        f"path={overlay},format=qcow2,bus=virtio",
        "--disk",
        f"path={seed},device=cdrom,readonly=on",
        "--network",
        "network=default,model=virtio",
        "--graphics",
        "none",
        "--console",
        "pty,target_type=serial",
        "--noautoconsole",
    ]


def _emit_plan(config: VmConfig) -> str:
    return textwrap.dedent(
        f"""\
        Plano de provisionamento da VM descartável M10:

          nome:       {config.vm_name}
          commit:     {config.source_commit}
          base image: {config.base_image}
          disco:      {config.disk_size_gb} GB qcow2 overlay descartável
          memória:    {config.memory_mib} MiB
          cpus:       {config.cpus}
          guest:      Arch cloud-init + Python + SDDM + Flatpak + SSH + Btrfs

        Execução autorizada: valida o commit, cria cloud-init e overlay, inicia
        virt-install, prova console serial/SSH, cria snapshot Btrfs, copia a
        árvore por git archive, certifica RetroArch/PCSX2/PPSSPP e restaura o
        baseline pelo snapshot antes de destruir a VM. O relatório vincula o
        commit e os pins Flatpak observados em docs/diagnostics/.
        """
    )


class GuestComponentClient(ComponentClient):
    """Cliente da CLI real dentro da VM; normaliza envelopes JSON v2."""

    def __init__(
        self,
        address: str,
        *,
        identity_file: Path | None = None,
        runner: Runner = _run,
    ) -> None:
        self._address = str(ipaddress.ip_address(address))
        self._identity_file = identity_file
        self._runner = runner

    def _ssh(self, command: Sequence[str], *, timeout: float = 1800.0) -> bytes:
        return _required(self._ssh_result(command, timeout=timeout), f"SSH guest ({command[0]})")

    def _ssh_result(self, command: Sequence[str], *, timeout: float = 1800.0) -> CommandResult:
        remote = " ".join(_shell_quote(part) for part in command)
        argv = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "GlobalKnownHostsFile=/dev/null",
            "-o",
            "ConnectTimeout=10",
        ]
        if self._identity_file is not None:
            argv.extend(("-i", str(self._identity_file), "-o", "IdentitiesOnly=yes"))
        argv.extend((f"{_GUEST_USER}@{self._address}", remote))
        return self._runner(tuple(argv), None, timeout)

    def _component(self, action: str, *args: str) -> dict[str, Any]:
        command = (
            "env",
            f"PYTHONPATH={_GUEST_SOURCE}/src",
            "python",
            "-m",
            "steamzero.cli.main",
            "component",
            action,
            *args,
            "--json",
        )
        stdout = self._ssh(command)
        try:
            envelope = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("CLI da VM não devolveu JSON") from exc
        if envelope.get("ok") is False:
            raise GuestComponentError(action, envelope)
        data = envelope.get("data")
        if not isinstance(data, dict):
            raise RuntimeError(f"component {action} devolveu data inválido")
        return data

    def status(self, adapter_id: str) -> dict[str, Any]:
        return self._component("status", "--id", adapter_id)

    def plan(self, adapter_id: str, action: str = "install") -> dict[str, Any]:
        data = self._component("plan", "--id", adapter_id, "--action", action)
        plan = data.get("plan")
        if not isinstance(plan, dict):
            raise RuntimeError("component plan não devolveu plan")
        return plan

    def apply(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        return self._component("apply", "--plan-id", plan_id, "--confirm", confirm_token)

    def rollback(self, operation_id: str) -> dict[str, Any]:
        return self._component("rollback", "--operation-id", operation_id)

    def verify(self, adapter_id: str) -> dict[str, Any]:
        return self._component("verify", "--id", adapter_id)


def _shell_quote(value: str) -> str:
    """Quote mínimo para o único argumento remoto de SSH."""
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _guest_ssh(
    address: str,
    command: Sequence[str],
    *,
    identity_file: Path,
    runner: Runner,
    timeout: float = 1800.0,
) -> bytes:
    return GuestComponentClient(address, identity_file=identity_file, runner=runner)._ssh(
        command, timeout=timeout
    )


def _diagnostic_ssh_result(
    client: GuestComponentClient, command: Sequence[str], *, timeout: float
) -> CommandResult:
    """Coleta diagnóstico sem deixar um segundo timeout ocultar a falha raiz."""
    try:
        return client._ssh_result(command, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if exc.stdout else ""
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        return CommandResult(124, stdout.encode(), (stderr or "timeout de diagnóstico").encode())


def _wait_for_guest(
    config: VmConfig,
    *,
    identity_file: Path | None = None,
    runner: Runner,
    retries: int = 90,
) -> str:
    """Espera lease IPv4 e autenticação SSH; timeout não vira êxito implícito.

    ``provision`` sempre fornece a cópia temporária segura. O fallback mantém o
    helper diretamente exercitável pelas provas unitárias do loop de readiness.
    """
    last_issue: dict[str, Any] = {"phase": "lease", "detail": "nenhuma tentativa executada"}
    for _ in range(retries):
        try:
            lease = runner(
                (
                    "virsh",
                    "--connect",
                    "qemu:///system",
                    "domifaddr",
                    config.vm_name,
                    "--source",
                    "lease",
                ),
                None,
                20.0,
            )
        except subprocess.TimeoutExpired:
            last_issue = {
                "phase": "lease",
                "exception": {"type": "TimeoutExpired", "message": "domifaddr excedeu 20s"},
            }
            time.sleep(2)
            continue
        text = lease.stdout.decode("utf-8", errors="replace")
        for token in text.split():
            candidate = token.split("/", 1)[0]
            try:
                address = ipaddress.ip_address(candidate)
            except ValueError:
                continue
            if address.version != 4:
                continue
            if identity_file is None:
                if config.ssh_private_key is None:
                    raise RuntimeError("execução sem identidade SSH privada")
                selected_identity = config.ssh_private_key
            else:
                selected_identity = identity_file
            probe = GuestComponentClient(
                str(address), identity_file=selected_identity, runner=runner
            )
            try:
                probe._ssh(("true",), timeout=15.0)
            except (RuntimeError, subprocess.TimeoutExpired) as exc:
                last_issue = _readiness_issue("ssh", str(address), exc)
                break
            try:
                probe._ssh(("cloud-init", "status", "--wait"), timeout=_CLOUD_INIT_TIMEOUT_SECONDS)
            except (RuntimeError, subprocess.TimeoutExpired) as exc:
                last_issue = _readiness_issue("cloud-init", str(address), exc)
                diagnostic = _diagnostic_ssh_result(
                    probe, ("cloud-init", "status", "--long"), timeout=30.0
                )
                last_issue["cloudInitStatusLong"] = {
                    "returncode": diagnostic.returncode,
                    "stdout": diagnostic.stdout.decode("utf-8", errors="replace"),
                    "stderr": diagnostic.stderr.decode("utf-8", errors="replace"),
                }
                output_log = _diagnostic_ssh_result(
                    probe,
                    ("sudo", "tail", "-n", "400", "/var/log/cloud-init-output.log"),
                    timeout=30.0,
                )
                last_issue["cloudInitOutputLog"] = {
                    "returncode": output_log.returncode,
                    "stdout": output_log.stdout.decode("utf-8", errors="replace"),
                    "stderr": output_log.stderr.decode("utf-8", errors="replace"),
                }
                break
            return str(address)
        else:
            last_issue = {
                "phase": "lease",
                "returncode": lease.returncode,
                "stdout": text,
                "detail": "nenhum IPv4 foi encontrado no lease",
            }
        time.sleep(2)
    raise GuestReadinessError(last_issue)


def _configure_flathub(address: str, *, identity_file: Path, runner: Runner) -> None:
    """Cria o remote após cloud-init; repete somente indisponibilidade DNS."""
    client = GuestComponentClient(address, identity_file=identity_file, runner=runner)
    command = ("flatpak", "remote-add", "--user", "--if-not-exists", "flathub", _FLATHUB_URL)
    attempts: list[dict[str, Any]] = []
    for index, delay in enumerate((*FLATHUB_RETRY_DELAYS, 0.0), start=1):
        result = client._ssh_result(command, timeout=180.0)
        attempt = {
            "attempt": index,
            "returncode": result.returncode,
            "stdout": result.stdout.decode("utf-8", errors="replace"),
            "stderr": result.stderr.decode("utf-8", errors="replace"),
        }
        attempts.append(attempt)
        if result.returncode == 0:
            return
        combined = f"{attempt['stdout']}\n{attempt['stderr']}".lower()
        if "could not resolve hostname" not in combined or delay == 0.0:
            raise FlathubSetupError(attempts)
        time.sleep(delay)
    raise AssertionError("loop de retry Flathub deveria ter terminado")


def _copy_source(config: VmConfig, address: str, *, runner: Runner) -> None:
    identity_file = _private_identity(config)
    archive = _required(
        runner(("git", "archive", "--format=tar", config.source_commit), None, 120.0),
        "git archive do commit de origem",
    )
    _guest_ssh(
        address,
        ("mkdir", "-p", _GUEST_SOURCE),
        identity_file=identity_file,
        runner=runner,
    )
    remote = f"tar -x -C {_GUEST_SOURCE}"
    result = runner(
        (
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "GlobalKnownHostsFile=/dev/null",
            "-i",
            str(identity_file),
            "-o",
            "IdentitiesOnly=yes",
            f"{_GUEST_USER}@{address}",
            remote,
        ),
        archive,
        120.0,
    )
    _required(result, "cópia da árvore commitada para a VM")


def _snapshot_before(address: str, *, identity_file: Path, runner: Runner) -> int:
    """Cria snapshot Btrfs bootável e devolve seu subvolume id para restore."""
    commands = (
        ("sudo", "mkdir", "-p", _SNAPSHOT_ROOT),
        ("sudo", "btrfs", "subvolume", "snapshot", "/", f"{_SNAPSHOT_ROOT}/before-m10"),
        ("sudo", "btrfs", "subvolume", "show", f"{_SNAPSHOT_ROOT}/before-m10"),
    )
    _guest_ssh(address, commands[0], identity_file=identity_file, runner=runner)
    _guest_ssh(address, commands[1], identity_file=identity_file, runner=runner)
    show = _guest_ssh(address, commands[2], identity_file=identity_file, runner=runner).decode(
        "utf-8", errors="replace"
    )
    match = re.search(r"Subvolume ID:\s*(\d+)", show)
    if match is None:
        raise RuntimeError("não foi possível obter o ID do snapshot Btrfs")
    return int(match.group(1))


def _restore_snapshot(
    address: str, snapshot_id: int, *, identity_file: Path, runner: Runner
) -> None:
    """Seleciona o baseline para o próximo boot; a chamada seguinte prova-o."""
    _guest_ssh(
        address,
        ("sudo", "btrfs", "subvolume", "set-default", str(snapshot_id), "/"),
        identity_file=identity_file,
        runner=runner,
    )
    # O SSH pode cair antes de systemctl devolver o status: a queda é esperada
    # aqui e o próximo _wait_for_guest é a prova de que o reboot realmente
    # voltou. Se o reboot não ocorrer, o baseline instalado faz essa prova falhar.
    with contextlib.suppress(RuntimeError):
        _guest_ssh(
            address,
            ("sudo", "systemctl", "reboot"),
            identity_file=identity_file,
            runner=runner,
            timeout=30.0,
        )


def _destroy_vm(config: VmConfig, *, runner: Runner, remove_run_dir: bool) -> None:
    """Remove o domínio nomeado; só limpa artefatos depois de certificação completa."""
    runner(("virsh", "--connect", "qemu:///system", "destroy", config.vm_name), None, 60.0)
    runner(
        ("virsh", "--connect", "qemu:///system", "undefine", config.vm_name, "--nvram"),
        None,
        60.0,
    )
    if not remove_run_dir:
        return
    marker = config.run_dir / ".steamzero-m10-managed"
    if marker.is_file() and marker.read_text(encoding="utf-8").strip() == config.source_commit:
        shutil.rmtree(config.run_dir)


def _failure_payload(stage: str, exc: BaseException) -> dict[str, Any]:
    """Normaliza a causa sem descartar os dados que a VM devolveu."""
    payload: dict[str, Any] = {
        "stage": stage,
        "exception": {"type": type(exc).__name__, "message": str(exc)},
    }
    if isinstance(exc, GuestComponentError):
        payload["component"] = {"action": exc.action, "envelope": exc.envelope}
    if isinstance(exc, RequiredCommandError):
        payload["command"] = {
            "label": exc.label,
            "returncode": exc.result.returncode,
            "stdout": exc.result.stdout.decode("utf-8", errors="replace"),
            "stderr": exc.result.stderr.decode("utf-8", errors="replace"),
        }
    if isinstance(exc, GuestReadinessError):
        payload["readiness"] = exc.last_issue
    if isinstance(exc, FlathubSetupError):
        payload["flathubAttempts"] = exc.attempts
    return payload


def _readiness_issue(phase: str, address: str, exc: BaseException) -> dict[str, Any]:
    """Devolve o mesmo payload serializável que irá para a evidência final."""
    payload = _failure_payload(f"readiness: {phase}", exc)
    payload["phase"] = phase
    payload["address"] = address
    return payload


def _write_evidence(
    source_commit: str,
    report: dict[str, Any],
    *,
    baseline_restored: bool,
    failure: dict[str, Any] | None = None,
) -> Path:
    date = dt.date.today().isoformat()
    target = ROOT / "docs" / "diagnostics" / f"{date}-m10-vm-evidence.md"
    if target.exists():
        stamp = dt.datetime.now().strftime("%H%M%S")
        target = target.with_name(f"{date}-m10-vm-evidence-{stamp}.md")
    target.parent.mkdir(parents=True, exist_ok=True)
    body = render_evidence_report(report, source_commit=source_commit, date=date)
    restored = "SIM" if baseline_restored else "NÃO — execução interrompida"
    if failure is not None:
        body += "\n## Falha da execução\n\n```json\n"
        body += json.dumps(failure, indent=2, ensure_ascii=False, sort_keys=True)
        body += "\n```\n"
    body += f"\n## Restore do baseline Btrfs\n\n- Confirmado: **{restored}**\n"
    target.write_text(body, encoding="utf-8")
    return target


def _selected_certification(
    client: ComponentClient, *, adapter_id: str, protocol: str
) -> dict[str, Any]:
    if adapter_id not in M10_FLATPAK_EMULATORS:
        raise ValueError(f"--adapter não pertence ao M10: {adapter_id}")
    expected_commit = m10_pinned_commits()[adapter_id]
    if protocol == "minimal":
        result = certify_emulator_minimal(
            client=client, emulator=adapter_id, expected_commit=expected_commit
        )
    elif protocol == "full":
        result = certify_emulator(
            client=client, emulator=adapter_id, expected_commit=expected_commit
        )
    else:
        raise ValueError(f"protocolo M10 desconhecido: {protocol}")
    return {
        "ok": result.ok,
        "pins": {adapter_id: expected_commit},
        "emulators": [result.to_dict()],
        "summary": {adapter_id: "ok" if result.ok else "fail"},
        "protocol": protocol,
    }


def provision(
    config: VmConfig,
    *,
    runner: Runner = _run,
    adapter_id: str,
    protocol: str = "full",
) -> Path:
    """Executa a certificação autorizada; qualquer falha mantém evidência e falha."""
    config.validate(executing=True)
    _preflight()
    resolved = (
        _required(
            runner(
                ("git", "rev-parse", "--verify", f"{config.source_commit}^{{commit}}"), None, 30.0
            ),
            "validação do commit de origem",
        )
        .decode()
        .strip()
    )
    if resolved != config.source_commit:
        raise RuntimeError("--source-commit não resolve exatamente para o commit solicitado")
    public_key = _public_key(config.ssh_public_key)
    user_data, meta_data = render_cloud_init(config, public_key)
    config.run_dir.mkdir(parents=True, exist_ok=False)
    (config.run_dir / ".steamzero-m10-managed").write_text(config.source_commit, encoding="utf-8")
    (config.run_dir / "user-data").write_text(user_data, encoding="utf-8")
    (config.run_dir / "meta-data").write_text(meta_data, encoding="utf-8")
    overlay = config.run_dir / "disk.qcow2"
    seed = config.run_dir / "seed.iso"
    baseline_restored = False
    report: dict[str, Any] = {
        "ok": False,
        "emulators": [],
        "summary": {},
        "protocol": protocol,
    }
    failure: dict[str, Any] | None = None
    evidence: Path | None = None
    identity_file: Path | None = None
    stage = "preparação da overlay"
    try:
        identity_file = _private_identity(config)
        _required(
            runner(
                (
                    "qemu-img",
                    "create",
                    "-f",
                    "qcow2",
                    "-F",
                    "qcow2",
                    "-b",
                    str(config.base_image.resolve()),
                    str(overlay),
                    f"{config.disk_size_gb}G",
                ),
                None,
                120.0,
            ),
            "criação da overlay qcow2",
        )
        stage = "criação da seed cloud-init"
        seed_argv = _seed_argv(seed, config.run_dir / "user-data", config.run_dir / "meta-data")
        _required(runner(seed_argv, None, 120.0), "criação da seed cloud-init")
        stage = "virt-install"
        _required(
            runner(build_virt_install_argv(config, overlay, seed), None, 180.0), "virt-install"
        )
        stage = "readiness da VM"
        address = _wait_for_guest(config, identity_file=identity_file, runner=runner)
        stage = "console serial independente"
        _required(
            runner(
                ("virsh", "--connect", "qemu:///system", "ttyconsole", config.vm_name),
                None,
                30.0,
            ),
            "console serial independente",
        )
        stage = "configuração do remote Flathub"
        _configure_flathub(address, identity_file=identity_file, runner=runner)
        stage = "cópia da árvore do commit"
        _copy_source(config, address, runner=runner)
        stage = "snapshot Btrfs inicial"
        snapshot_id = _snapshot_before(address, identity_file=identity_file, runner=runner)
        client = GuestComponentClient(address, identity_file=identity_file, runner=runner)
        stage = f"certificação {adapter_id} ({protocol})"
        report = _selected_certification(client, adapter_id=adapter_id, protocol=protocol)
        if not report["ok"]:
            failure = {"stage": stage, "report": report}
            raise RuntimeError("certificação M10 reprovou; ver relatório de evidência")
        stage = "seleção do snapshot Btrfs"
        _restore_snapshot(address, snapshot_id, identity_file=identity_file, runner=runner)
        stage = "readiness após restore Btrfs"
        restored_address = _wait_for_guest(config, identity_file=identity_file, runner=runner)
        restored = GuestComponentClient(
            restored_address, identity_file=identity_file, runner=runner
        )
        baseline_restored = all(
            restored.status(adapter)["state"] in {"missing", "unavailable"}
            for adapter in (adapter_id,)
        )
        if not baseline_restored:
            raise RuntimeError("snapshot Btrfs não restaurou o baseline dos emuladores")
    except BaseException as exc:
        if failure is None:
            failure = _failure_payload(stage, exc)
            with contextlib.suppress(Exception):
                failure["expectedPins"] = m10_pinned_commits()
        raise
    finally:
        evidence_written = False
        try:
            evidence = _write_evidence(
                config.source_commit,
                report,
                baseline_restored=baseline_restored,
                failure=failure,
            )
            evidence_written = True
        finally:
            try:
                _destroy_vm(
                    config,
                    runner=runner,
                    remove_run_dir=baseline_restored and evidence_written,
                )
            finally:
                if identity_file is not None:
                    identity_file.unlink(missing_ok=True)
    if evidence is None:
        raise RuntimeError("a execução não produziu relatório de evidência")
    return evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source-commit", required=True, help="SHA completo da fonte a certificar")
    parser.add_argument("--vm-name", default="steamzero-m10")
    parser.add_argument("--base-image", type=Path, default=Path("ARCH-CLOUD-IMAGE.qcow2"))
    parser.add_argument("--ssh-public-key", type=Path, default=Path("SSH-PUBLIC-KEY.pub"))
    parser.add_argument("--ssh-private-key", type=Path)
    parser.add_argument("--work-dir", type=Path, default=ROOT / ".zcode" / "vm-harness")
    parser.add_argument("--disk-size-gb", type=int, default=40)
    parser.add_argument("--memory-mib", type=int, default=4096)
    parser.add_argument("--cpus", type=int, default=4)
    parser.add_argument("--adapter", choices=M10_FLATPAK_EMULATORS)
    parser.add_argument(
        "--protocol",
        choices=("minimal", "full"),
        default="full",
        help="minimal roda install→verify→rollback em um único adapter",
    )
    parser.add_argument(
        "--plan", action="store_true", help="somente imprime o plano; não toca o host"
    )
    parser.add_argument("--execute", action="store_true", help="executa a VM (exige confirmação)")
    parser.add_argument("--confirm", help=f"frase exata {_CONFIRM}")
    args = parser.parse_args(argv)
    config = VmConfig(
        source_commit=args.source_commit,
        vm_name=args.vm_name,
        base_image=args.base_image,
        ssh_public_key=args.ssh_public_key,
        work_dir=args.work_dir,
        ssh_private_key=args.ssh_private_key,
        disk_size_gb=args.disk_size_gb,
        memory_mib=args.memory_mib,
        cpus=args.cpus,
    )
    try:
        config.validate(executing=False)
        print(_emit_plan(config))
        if args.plan and not args.execute:
            return 0
        if not args.execute:
            raise ValueError("recusa mutar: use --plan ou --execute --confirm EXECUTAR-VM-M10")
        if args.confirm != _CONFIRM:
            raise ValueError("confirmação incorreta para execução da VM M10")
        if args.adapter is None:
            raise ValueError("execução exige --adapter; um emulador por VM")
        evidence = provision(config, adapter_id=args.adapter, protocol=args.protocol)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    print(f"evidência: {evidence.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
