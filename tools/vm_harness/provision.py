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
import re
import shutil
import subprocess
import sys
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
    ComponentClient,
    certify_m10,
    render_evidence_report,
)

_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{2,62}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40,64}$")
_KEY_PREFIXES = ("ssh-ed25519 ", "ssh-rsa ", "ecdsa-sha2-", "sk-ssh-ed25519@")
_SNAPSHOT_ROOT = "/var/lib/steamzero-m10-snapshots"
_GUEST_SOURCE = "/home/steamzero/steamzero-src"
_GUEST_USER = "steamzero"
_CONFIRM = "EXECUTAR-VM-M10"

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


def _run(argv: Sequence[str], input_data: bytes | None, timeout: float) -> CommandResult:
    completed = subprocess.run(
        list(argv),
        input=input_data,
        stdin=subprocess.DEVNULL if input_data is None else subprocess.PIPE,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def _required(value: CommandResult, label: str) -> bytes:
    if value.returncode != 0:
        detail = value.stderr.decode("utf-8", errors="replace").strip() or "sem diagnóstico"
        raise RuntimeError(f"{label} falhou: {detail}")
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
        package_update: true
        packages: [python, python-jsonschema, flatpak, sddm, openssh, btrfs-progs, git]
        runcmd:
          - [systemctl, enable, --now, sshd.service]
          - [runuser, -u, {_GUEST_USER}, --, flatpak, remote-add, --user, --if-not-exists, flathub, https://dl.flathub.org/repo/flathub.flatpakrepo]
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

    def __init__(self, address: str, *, runner: Runner = _run) -> None:
        self._address = str(ipaddress.ip_address(address))
        self._runner = runner

    def _ssh(self, command: Sequence[str], *, timeout: float = 1800.0) -> bytes:
        remote = " ".join(_shell_quote(part) for part in command)
        result = self._runner(
            (
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=accept-new",
                "-o",
                "ConnectTimeout=10",
                f"{_GUEST_USER}@{self._address}",
                remote,
            ),
            None,
            timeout,
        )
        return _required(result, f"SSH guest ({command[0]})")

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
            raise RuntimeError(f"component {action} falhou: {envelope.get('error')}")
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
    address: str, command: Sequence[str], *, runner: Runner, timeout: float = 1800.0
) -> bytes:
    return GuestComponentClient(address, runner=runner)._ssh(command, timeout=timeout)


def _wait_for_guest(config: VmConfig, *, runner: Runner, retries: int = 90) -> str:
    """Espera lease IPv4 e autenticação SSH; timeout não vira êxito implícito."""
    for _ in range(retries):
        lease = runner(("virsh", "domifaddr", config.vm_name, "--source", "lease"), None, 20.0)
        text = lease.stdout.decode("utf-8", errors="replace")
        for token in text.split():
            candidate = token.split("/", 1)[0]
            try:
                address = ipaddress.ip_address(candidate)
            except ValueError:
                continue
            if address.version != 4:
                continue
            probe = GuestComponentClient(str(address), runner=runner)
            try:
                probe._ssh(("true",), timeout=15.0)
            except RuntimeError:
                break
            return str(address)
        time.sleep(2)
    raise RuntimeError("VM não obteve IPv4/SSH antes do prazo")


def _copy_source(config: VmConfig, address: str, *, runner: Runner) -> None:
    archive = _required(
        runner(("git", "archive", "--format=tar", config.source_commit), None, 120.0),
        "git archive do commit de origem",
    )
    _guest_ssh(address, ("mkdir", "-p", _GUEST_SOURCE), runner=runner)
    remote = f"tar -x -C {_GUEST_SOURCE}"
    result = runner(
        (
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            f"{_GUEST_USER}@{address}",
            remote,
        ),
        archive,
        120.0,
    )
    _required(result, "cópia da árvore commitada para a VM")


def _snapshot_before(address: str, *, runner: Runner) -> int:
    """Cria snapshot Btrfs bootável e devolve seu subvolume id para restore."""
    commands = (
        ("sudo", "mkdir", "-p", _SNAPSHOT_ROOT),
        ("sudo", "btrfs", "subvolume", "snapshot", "/", f"{_SNAPSHOT_ROOT}/before-m10"),
        ("sudo", "btrfs", "subvolume", "show", f"{_SNAPSHOT_ROOT}/before-m10"),
    )
    _guest_ssh(address, commands[0], runner=runner)
    _guest_ssh(address, commands[1], runner=runner)
    show = _guest_ssh(address, commands[2], runner=runner).decode("utf-8", errors="replace")
    match = re.search(r"Subvolume ID:\s*(\d+)", show)
    if match is None:
        raise RuntimeError("não foi possível obter o ID do snapshot Btrfs")
    return int(match.group(1))


def _restore_snapshot(address: str, snapshot_id: int, *, runner: Runner) -> None:
    """Seleciona o baseline para o próximo boot; a chamada seguinte prova-o."""
    _guest_ssh(
        address,
        ("sudo", "btrfs", "subvolume", "set-default", str(snapshot_id), "/"),
        runner=runner,
    )
    # O SSH pode cair antes de systemctl devolver o status: a queda é esperada
    # aqui e o próximo _wait_for_guest é a prova de que o reboot realmente
    # voltou. Se o reboot não ocorrer, o baseline instalado faz essa prova falhar.
    with contextlib.suppress(RuntimeError):
        _guest_ssh(address, ("sudo", "systemctl", "reboot"), runner=runner, timeout=30.0)


def _destroy_vm(config: VmConfig, *, runner: Runner) -> None:
    """Remove somente a VM nomeada e o diretório com marcador próprio."""
    runner(("virsh", "destroy", config.vm_name), None, 60.0)
    runner(("virsh", "undefine", config.vm_name, "--nvram"), None, 60.0)
    marker = config.run_dir / ".steamzero-m10-managed"
    if marker.read_text(encoding="utf-8").strip() == config.source_commit:
        shutil.rmtree(config.run_dir)


def _write_evidence(source_commit: str, report: dict[str, Any], *, baseline_restored: bool) -> Path:
    date = dt.date.today().isoformat()
    target = ROOT / "docs" / "diagnostics" / f"{date}-m10-vm-evidence.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    body = render_evidence_report(report, source_commit=source_commit, date=date)
    restored = "SIM" if baseline_restored else "NÃO — execução interrompida"
    target.write_text(
        body + f"\n## Restore do baseline Btrfs\n\n- Confirmado: **{restored}**\n",
        encoding="utf-8",
    )
    return target


def provision(config: VmConfig, *, runner: Runner = _run) -> Path:
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
    report: dict[str, Any] = {"ok": False, "emulators": [], "summary": {}}
    try:
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
                    str(config.base_image),
                    str(overlay),
                    f"{config.disk_size_gb}G",
                ),
                None,
                120.0,
            ),
            "criação da overlay qcow2",
        )
        seed_argv = _seed_argv(seed, config.run_dir / "user-data", config.run_dir / "meta-data")
        _required(runner(seed_argv, None, 120.0), "criação da seed cloud-init")
        _required(
            runner(build_virt_install_argv(config, overlay, seed), None, 180.0), "virt-install"
        )
        address = _wait_for_guest(config, runner=runner)
        _required(
            runner(("virsh", "ttyconsole", config.vm_name), None, 30.0),
            "console serial independente",
        )
        _copy_source(config, address, runner=runner)
        snapshot_id = _snapshot_before(address, runner=runner)
        client = GuestComponentClient(address, runner=runner)
        report = certify_m10(client)
        if not report["ok"]:
            raise RuntimeError("certificação M10 reprovou; ver relatório de evidência")
        _restore_snapshot(address, snapshot_id, runner=runner)
        restored_address = _wait_for_guest(config, runner=runner)
        restored = GuestComponentClient(restored_address, runner=runner)
        baseline_restored = all(
            restored.status(adapter)["state"] in {"missing", "unavailable"}
            for adapter in ("retroarch", "pcsx2", "ppsspp")
        )
        if not baseline_restored:
            raise RuntimeError("snapshot Btrfs não restaurou o baseline dos emuladores")
    finally:
        evidence = _write_evidence(
            config.source_commit, report, baseline_restored=baseline_restored
        )
        _destroy_vm(config, runner=runner)
    return evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source-commit", required=True, help="SHA completo da fonte a certificar")
    parser.add_argument("--vm-name", default="steamzero-m10")
    parser.add_argument("--base-image", type=Path, default=Path("ARCH-CLOUD-IMAGE.qcow2"))
    parser.add_argument("--ssh-public-key", type=Path, default=Path("SSH-PUBLIC-KEY.pub"))
    parser.add_argument("--work-dir", type=Path, default=ROOT / ".zcode" / "vm-harness")
    parser.add_argument("--disk-size-gb", type=int, default=40)
    parser.add_argument("--memory-mib", type=int, default=4096)
    parser.add_argument("--cpus", type=int, default=4)
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
        evidence = provision(config)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    print(f"evidência: {evidence.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
