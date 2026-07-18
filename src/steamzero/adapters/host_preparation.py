# SPDX-License-Identifier: GPL-3.0-or-later
"""Prontidão e preparação explícita do laboratório de validação do host.

VMs cobrem instalação/upgrade/rollback em sistemas descartáveis. Recursos que
dependem do Steam Deck (AMDGPU, TDP, KScreen, dock e suspend) permanecem no
protocolo físico com snapshot e recuperação; virtio-gpu não é aceito como prova
equivalente do hardware Valve.
"""

from __future__ import annotations

import argparse
import grp
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from steamzero.core.errors import SteamZeroError
from steamzero.domain.device import classify

Which = Callable[[str], str | None]
Runner = Callable[..., subprocess.CompletedProcess[str]]

_USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
_PACKAGE_SETS: Mapping[str, tuple[str, ...]] = {
    "pacman": (
        "qemu-desktop",
        "libvirt",
        "virt-install",
        "edk2-ovmf",
        "swtpm",
        "dnsmasq",
        "iptables-nft",
    ),
    "apt-get": (
        "qemu-system-x86",
        "libvirt-daemon-system",
        "virtinst",
        "ovmf",
        "swtpm",
        "dnsmasq-base",
    ),
    "dnf": (
        "qemu-kvm",
        "libvirt",
        "virt-install",
        "edk2-ovmf",
        "swtpm",
        "dnsmasq",
    ),
}


def _os_release(path: Path = Path("/etc/os-release")) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    result: dict[str, str] = {}
    for line in lines:
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        result[key] = value.strip().strip('"')
    return result


def _manager(which: Which) -> tuple[str | None, str | None]:
    for name in ("pacman", "apt-get", "dnf"):
        executable = which(name)
        if executable:
            return name, executable
    return None, None


def _device_kind(dmi_root: Path) -> str:
    values: dict[str, str] = {}
    for name in ("product_name", "sys_vendor", "board_name"):
        try:
            values[name] = (dmi_root / name).read_text(encoding="utf-8").strip()
        except OSError:
            values[name] = ""
    return classify(values)


def snapshot(
    device_kind: str | None = None,
    *,
    which: Which = shutil.which,
    kvm: Path = Path("/dev/kvm"),
    os_release: Path = Path("/etc/os-release"),
    dmi_root: Path = Path("/sys/devices/virtual/dmi/id"),
) -> dict[str, Any]:
    distro = _os_release(os_release)
    manager, _executable = _manager(which)
    commands = {
        "qemu": bool(which("qemu-system-x86_64")),
        "libvirt": bool(which("virsh")),
        "virtInstall": bool(which("virt-install")),
        "swtpm": bool(which("swtpm")),
    }
    kvm_ready = kvm.exists() and os.access(kvm, os.R_OK | os.W_OK)
    virtualization_ready = kvm_ready and all(commands.values())
    observed_device = device_kind or _device_kind(dmi_root)
    official_deck = observed_device in {"deck-lcd", "deck-oled"}
    return {
        "state": "ready" if virtualization_ready else "attention",
        "statusLabel": (
            "Laboratório KVM/libvirt pronto"
            if virtualization_ready
            else "Preparação de virtualização necessária"
        ),
        "distro": {
            "id": distro.get("ID", "unknown"),
            "name": distro.get("PRETTY_NAME", distro.get("NAME", "Linux")),
            "packageManager": manager,
            "supported": manager in _PACKAGE_SETS,
        },
        "kvm": {"available": kvm.exists(), "accessible": kvm_ready},
        "components": commands,
        "packages": list(_PACKAGE_SETS.get(manager or "", ())),
        "officialDeck": official_deck,
        "hardwareLab": {
            "state": "ready" if official_deck else "compatible-host",
            "scope": ["amdgpu", "tdp", "gpu-clock", "kscreen", "dock", "suspend"],
            "virtualGpuEquivalent": False,
            "reason": (
                "Steam Deck oficial: mutações de hardware seguem snapshot e recuperação."
                if official_deck
                else "Recursos Valve só são habilitados quando o hardware é observado."
            ),
        },
        "virtualLab": {
            "state": "ready" if virtualization_ready else "attention",
            "scope": ["clean-install", "update", "rollback", "packaging", "ui-smoke"],
            "gpu": "virtio",
        },
        "action": {
            "kind": "system-prepare",
            "label": "Preparar host" if not virtualization_ready else "Verificar ambiente",
            "enabled": manager in _PACKAGE_SETS and not virtualization_ready,
            "confirmPhrase": "PREPARAR-VIRTUALIZACAO",
        },
    }


def plan(*, which: Which = shutil.which) -> dict[str, Any]:
    manager, executable = _manager(which)
    if manager is None or executable is None or manager not in _PACKAGE_SETS:
        raise SteamZeroError("E-COMPONENT-DEGRADED", detail="gerenciador de pacotes não suportado")
    packages = _PACKAGE_SETS[manager]
    if manager == "pacman":
        commands = [[executable, "-S", "--needed", "--noconfirm", *packages]]
    elif manager == "apt-get":
        commands = [
            [executable, "update"],
            [executable, "install", "-y", "--no-install-recommends", *packages],
        ]
    else:
        commands = [[executable, "install", "-y", *packages]]
    return {
        "profile": "validation-vm",
        "packageManager": manager,
        "packages": list(packages),
        "commands": commands,
        "services": ["libvirtd.service"],
        "confirmPhrase": "PREPARAR-VIRTUALIZACAO",
        "scope": "VM descartável; não simula AMDGPU/TDP do Steam Deck",
    }


def _validate_user(username: str) -> pwd.struct_passwd:
    if not _USER_RE.fullmatch(username):
        raise SteamZeroError("E-API-SCHEMA", detail="usuário inválido")
    try:
        record = pwd.getpwnam(username)
    except KeyError as exc:
        raise SteamZeroError("E-API-SCHEMA", detail="usuário inexistente") from exc
    if record.pw_uid < 1000 or record.pw_uid == 65534:
        raise SteamZeroError("E-API-SCHEMA", detail="usuário não interativo")
    return record


def _run(argv: Sequence[str], *, runner: Runner) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["LC_ALL"] = "C"
    return runner(
        list(argv),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        text=True,
        timeout=1800,
        env=environment,
    )


def apply(
    username: str,
    confirm_phrase: str,
    *,
    which: Which = shutil.which,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    if os.geteuid() != 0:
        raise PermissionError("execute com bigsudo")
    if confirm_phrase != "PREPARAR-VIRTUALIZACAO":
        raise SteamZeroError("E-TX-CONFIRM-REQUIRED", detail="frase de confirmação incorreta")
    user = _validate_user(username)
    operation = plan(which=which)
    for command in operation["commands"]:
        _run(command, runner=runner)
    systemctl = which("systemctl")
    if systemctl:
        _run([systemctl, "enable", "--now", "libvirtd.service"], runner=runner)
    virsh = which("virsh")
    if virsh:
        connection = [virsh, "--connect", "qemu:///system"]
        network_info = runner(
            [*connection, "net-info", "default"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
            timeout=60,
            env={**os.environ, "LC_ALL": "C"},
        )
        default_network = Path("/usr/share/libvirt/networks/default.xml")
        if network_info.returncode != 0 and default_network.is_file():
            _run([*connection, "net-define", str(default_network)], runner=runner)
            network_info = runner(
                [*connection, "net-info", "default"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                text=True,
                timeout=60,
                env={**os.environ, "LC_ALL": "C"},
            )
        if "Active: yes" not in network_info.stdout:
            _run([*connection, "net-start", "default"], runner=runner)
        _run([*connection, "net-autostart", "default"], runner=runner)
    try:
        libvirt_group = grp.getgrnam("libvirt")
    except KeyError:
        libvirt_group = None
    if libvirt_group is not None and username not in libvirt_group.gr_mem:
        usermod = which("usermod")
        if usermod:
            _run([usermod, "-aG", "libvirt", username], runner=runner)
    result = snapshot(which=which)
    return {
        "state": "prepared",
        "user": user.pw_name,
        "packageManager": operation["packageManager"],
        "packages": operation["packages"],
        "reloginRequired": libvirt_group is not None and username not in libvirt_group.gr_mem,
        "observed": result,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepara laboratório KVM/libvirt do SteamZero")
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("status")
    subparsers.add_parser("plan")
    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("--user", required=True)
    apply_parser.add_argument("--confirm", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "apply":
            result = apply(args.user, args.confirm)
        elif args.action == "plan":
            result = plan()
        else:
            result = snapshot()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "data": result}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
