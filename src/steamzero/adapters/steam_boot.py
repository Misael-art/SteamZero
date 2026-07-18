# SPDX-License-Identifier: GPL-3.0-or-later
"""Boot direto no Game Mode, independente e reversível.

O marcador do GRUB apenas solicita a sessão. Um preparador oneshot valida a
sessão instalada antes de publicar a configuração de autologin do SDDM. Se a
sessão estiver ausente, o arquivo gerenciado é removido e o SDDM volta ao
greeter, evitando ciclos de login ou uma queda silenciosa no Desktop.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import pwd
import re
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from steamzero.core import fs
from steamzero.core.errors import SteamZeroError

Runner = Callable[..., subprocess.CompletedProcess[str]]

_MARKERS = frozenset({"steamzero.gamemode=1", "phasezero.steamos=1"})
_MANAGED = "# SteamZero-Boot-Managed: true"
_USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
_UUID_RE = re.compile(r"^[A-Fa-f0-9-]{8,64}$")
_BOOT_PATH_RE = re.compile(r"^/[A-Za-z0-9_./@+-]+$")


@dataclass(frozen=True)
class BootLayout:
    boot: Path = Path("/boot")
    config: Path = Path("/etc/steamzero/gamemode-user")
    sddm_config: Path = Path("/etc/sddm.conf.d/99-steamzero-gamemode.conf")
    session: Path = Path("/usr/local/share/wayland-sessions/steamzero-gamemode.desktop")
    unit: Path = Path("/usr/local/lib/systemd/system/steamzero-gamemode-boot.service")
    grub_script: Path = Path("/etc/grub.d/42_steamzero_gamemode")
    grub_config: Path = Path("/boot/grub/grub.cfg")
    cmdline: Path = Path("/proc/cmdline")
    legacy_sddm_config: Path = Path("/etc/sddm.conf.d/90-phasezero-steamos.conf")
    legacy_unit: str = "phasezero-steamos-boot-prepare.service"


_DEFAULT_LAYOUT = BootLayout()


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _managed(path: Path) -> bool:
    return not path.exists() or (
        path.is_file() and not path.is_symlink() and _MANAGED in _read_text(path)
    )


def _config_user(layout: BootLayout) -> str:
    lines = _read_text(layout.config).splitlines()
    return lines[1].strip() if len(lines) == 2 and lines[0].strip() == _MANAGED else ""


def _validate_user(username: str, *, lookup: Callable[[str], Any] = pwd.getpwnam) -> str:
    if not _USER_RE.fullmatch(username):
        raise SteamZeroError("E-API-SCHEMA", detail="usuário de Game Mode inválido")
    try:
        record = lookup(username)
    except KeyError as exc:
        raise SteamZeroError("E-API-SCHEMA", detail="usuário de Game Mode inexistente") from exc
    if int(record.pw_uid) < 1000 or int(record.pw_uid) == 65534:
        raise SteamZeroError("E-API-SCHEMA", detail="usuário de Game Mode não interativo")
    return username


def _requested(cmdline: str) -> bool:
    return bool(set(cmdline.split()) & _MARKERS)


def _sddm_text(username: str) -> str:
    return f"""{_MANAGED}
[Autologin]
User={username}
Session=steamzero-gamemode.desktop
Relogin=false
"""


def _remove_managed(path: Path) -> None:
    if path.exists() and not _managed(path):
        raise SteamZeroError(
            "E-SESSION-LAUNCH-FAILED", detail=f"recusando remover arquivo alheio: {path}"
        )
    fs.remove_file(path)


def prepare(
    layout: BootLayout = _DEFAULT_LAYOUT,
    *,
    cmdline: str | None = None,
    user_lookup: Callable[[str], Any] = pwd.getpwnam,
) -> dict[str, Any]:
    """Converge a seleção do SDDM para o marcador de boot observado."""
    raw_cmdline = _read_text(layout.cmdline) if cmdline is None else cmdline
    if not _requested(raw_cmdline):
        _remove_managed(layout.sddm_config)
        return {"state": "inactive", "session": None, "legacyMarker": False}

    username = _config_user(layout)
    _validate_user(username, lookup=user_lookup)
    if not layout.session.is_file() or layout.session.is_symlink():
        _remove_managed(layout.sddm_config)
        raise SteamZeroError(
            "E-SESSION-LAUNCH-FAILED",
            detail="sessão SteamZero ausente; autologin removido para retornar ao greeter",
        )
    if not _managed(layout.sddm_config):
        raise SteamZeroError(
            "E-SESSION-LAUNCH-FAILED", detail="configuração SDDM SteamZero não gerenciada"
        )
    fs.write_atomic_text(layout.sddm_config, _sddm_text(username), mode=0o644)
    if "PhaseZero managed" in _read_text(layout.legacy_sddm_config):
        fs.remove_file(layout.legacy_sddm_config)
    return {
        "state": "selected",
        "session": "steamzero-gamemode.desktop",
        "user": username,
        "legacyMarker": "phasezero.steamos=1" in raw_cmdline.split(),
    }


def _boot_spec(cmdline: str, boot: Path = Path("/boot")) -> tuple[str, str, str, list[str]]:
    tokens = cmdline.split()
    values: dict[str, str] = {}
    flags: list[str] = []
    for token in tokens:
        if "=" in token:
            key, value = token.split("=", 1)
            values[key] = value
        elif token in {"rw", "ro", "quiet", "splash"}:
            flags.append(token)
    kernel = values.get("BOOT_IMAGE", "")
    root = values.get("root", "")
    if not _BOOT_PATH_RE.fullmatch(kernel):
        raise SteamZeroError("E-SESSION-LAUNCH-FAILED", detail="kernel do boot não identificado")
    if not root.startswith("UUID=") or not _UUID_RE.fullmatch(root.removeprefix("UUID=")):
        raise SteamZeroError("E-SESSION-LAUNCH-FAILED", detail="UUID raiz do boot inválido")
    kernel_name = Path(kernel).name
    suffix = kernel_name.removeprefix("vmlinuz")
    initrd_name = f"initramfs{suffix}.img"
    if not (boot / kernel_name).is_file() or not (boot / initrd_name).is_file():
        raise SteamZeroError(
            "E-SESSION-LAUNCH-FAILED", detail="kernel/initramfs atuais não estão em /boot"
        )
    rootflags = values.get("rootflags")
    args = [root, "rw" if "rw" in flags else "ro"]
    if rootflags:
        if not re.fullmatch(r"[A-Za-z0-9_=/@,.-]+", rootflags):
            raise SteamZeroError("E-SESSION-LAUNCH-FAILED", detail="rootflags inválido")
        args.append(f"rootflags={rootflags}")
    args.extend(flag for flag in ("quiet", "splash") if flag in flags)
    args.append("steamzero.gamemode=1")
    return kernel, initrd_name, root.removeprefix("UUID="), args


def _grub_text(cmdline: str, boot: Path = Path("/boot")) -> str:
    kernel, initrd_name, uuid, args = _boot_spec(cmdline, boot)
    boot_prefix = str(Path(kernel).parent)
    initrds = []
    for name in ("amd-ucode.img", "intel-ucode.img"):
        if (boot / name).is_file():
            initrds.append(f"{boot_prefix}/{name}" if boot_prefix != "/" else f"/{name}")
    initrds.append(f"{boot_prefix}/{initrd_name}" if boot_prefix != "/" else f"/{initrd_name}")
    kernel_args = " ".join(shlex.quote(value) for value in args)
    menuentry = (
        "menuentry 'SteamZero Game Mode' --id='steamzero-gamemode' --hotkey=g "
        "--class steam --class gnu-linux --class gnu --class os"
    )
    return f"""#!/usr/bin/env bash
{_MANAGED}
exec tail -n +4 \"$0\"
{menuentry} {{
    insmod part_gpt
    insmod btrfs
    search --no-floppy --fs-uuid --set=root {uuid}
    echo 'Iniciando SteamZero Game Mode...'
    linux {kernel} {kernel_args}
    initrd {" ".join(initrds)}
}}
"""


def _unit_text() -> str:
    return f"""{_MANAGED}
[Unit]
Description=SteamZero Game Mode boot selector
DefaultDependencies=no
After=local-fs.target
Before=display-manager.service

[Service]
Type=oneshot
ExecStart=/usr/local/libexec/steamzero-gamemode-boot prepare

[Install]
WantedBy=graphical.target
"""


def _run(
    argv: Sequence[str], *, runner: Runner = subprocess.run
) -> subprocess.CompletedProcess[str]:
    return runner(
        list(argv),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        text=True,
        timeout=300,
    )


def enable(
    username: str,
    layout: BootLayout = _DEFAULT_LAYOUT,
    *,
    runner: Runner = subprocess.run,
    which: Callable[[str], str | None] = shutil.which,
    user_lookup: Callable[[str], Any] = pwd.getpwnam,
) -> dict[str, Any]:
    """Instala a integração GRUB/SDDM sob ownership exclusivo do SteamZero."""
    if os.geteuid() != 0:
        raise PermissionError("execute com bigsudo")
    _validate_user(username, lookup=user_lookup)
    if not layout.session.is_file() or layout.session.is_symlink():
        raise SteamZeroError("E-SESSION-LAUNCH-FAILED", detail="sessão SteamZero não instalada")
    for path in (layout.unit, layout.grub_script, layout.sddm_config):
        if not _managed(path):
            raise SteamZeroError(
                "E-SESSION-LAUNCH-FAILED", detail=f"arquivo de boot não gerenciado: {path}"
            )
    systemctl = which("systemctl")
    grub_mkconfig = which("grub-mkconfig")
    if systemctl is None or grub_mkconfig is None:
        raise SteamZeroError(
            "E-SESSION-LAUNCH-FAILED", detail="systemd ou grub-mkconfig indisponível"
        )
    cmdline = _read_text(layout.cmdline)
    previous = {
        path: path.read_bytes() if path.is_file() and not path.is_symlink() else None
        for path in (
            layout.config,
            layout.unit,
            layout.grub_script,
            layout.sddm_config,
            layout.grub_config,
        )
    }
    was_enabled = (
        runner(
            [systemctl, "is-enabled", layout.unit.name],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
            timeout=30,
        ).returncode
        == 0
    )
    try:
        if layout.config.exists() and not _managed(layout.config):
            raise SteamZeroError(
                "E-SESSION-LAUNCH-FAILED",
                detail=f"configuração de boot não gerenciada: {layout.config}",
            )
        fs.write_atomic_text(layout.config, f"{_MANAGED}\n{username}\n", mode=0o600)
        fs.write_atomic_text(layout.unit, _unit_text(), mode=0o644)
        fs.write_atomic_text(layout.grub_script, _grub_text(cmdline, layout.boot), mode=0o755)
        _run([systemctl, "daemon-reload"], runner=runner)
        _run([systemctl, "enable", layout.unit.name], runner=runner)
        _run([grub_mkconfig, "-o", str(layout.grub_config)], runner=runner)
        prepared = prepare(layout, cmdline=cmdline, user_lookup=user_lookup)
        with contextlib.suppress(subprocess.CalledProcessError):
            _run([systemctl, "disable", layout.legacy_unit], runner=runner)
    except BaseException:
        for path, content in previous.items():
            if content is None:
                fs.remove_file(path)
            else:
                mode = (
                    0o755
                    if path == layout.grub_script
                    else 0o600
                    if path == layout.config
                    else 0o644
                )
                fs.write_atomic(
                    path,
                    content,
                    mode=mode,
                )
        with contextlib.suppress(Exception):
            _run([systemctl, "daemon-reload"], runner=runner)
            _run(
                [systemctl, "enable" if was_enabled else "disable", layout.unit.name],
                runner=runner,
            )
        raise
    return {
        "state": "enabled",
        "user": username,
        "session": "steamzero-gamemode.desktop",
        "grubEntry": "SteamZero Game Mode",
        "prepared": prepared,
    }


def disable(
    layout: BootLayout = _DEFAULT_LAYOUT,
    *,
    runner: Runner = subprocess.run,
    which: Callable[[str], str | None] = shutil.which,
) -> dict[str, Any]:
    """Remove somente integração própria e regenera o GRUB."""
    if os.geteuid() != 0:
        raise PermissionError("execute com bigsudo")
    for path in (layout.config, layout.unit, layout.grub_script, layout.sddm_config):
        if path.exists() and not _managed(path):
            raise SteamZeroError(
                "E-SESSION-LAUNCH-FAILED", detail=f"arquivo não gerenciado: {path}"
            )
    systemctl = which("systemctl")
    grub_mkconfig = which("grub-mkconfig")
    if systemctl is None or grub_mkconfig is None:
        raise SteamZeroError(
            "E-SESSION-LAUNCH-FAILED", detail="systemd ou grub-mkconfig indisponível"
        )
    previous = {
        path: path.read_bytes() if path.is_file() and not path.is_symlink() else None
        for path in (
            layout.config,
            layout.unit,
            layout.grub_script,
            layout.sddm_config,
            layout.grub_config,
        )
    }
    for path in (layout.sddm_config, layout.config, layout.grub_script, layout.unit):
        fs.remove_file(path)
    try:
        _run([systemctl, "disable", "steamzero-gamemode-boot.service"], runner=runner)
        _run([systemctl, "daemon-reload"], runner=runner)
        _run([grub_mkconfig, "-o", str(layout.grub_config)], runner=runner)
    except BaseException:
        for path, content in previous.items():
            if content is None:
                fs.remove_file(path)
                continue
            mode = (
                0o755 if path == layout.grub_script else 0o600 if path == layout.config else 0o644
            )
            fs.write_atomic(path, content, mode=mode)
        raise
    return {"state": "disabled", "session": None}


def status(layout: BootLayout = _DEFAULT_LAYOUT) -> dict[str, Any]:
    configured = bool(_config_user(layout))
    owned = all(_managed(path) and path.exists() for path in (layout.unit, layout.grub_script))
    return {
        "state": "ready" if configured and owned else "available",
        "configured": configured and owned,
        "changesGrub": True,
        "session": "steamzero-gamemode.desktop",
        "marker": "steamzero.gamemode=1",
        "legacyMarkerAccepted": True,
        "reason": (
            "Entrada SteamZero pronta; falha retorna ao greeter/Plasma."
            if configured and owned
            else "Ativação privilegiada e reversível ainda não executada."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Boot resiliente do SteamZero Game Mode")
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("status")
    subparsers.add_parser("prepare")
    subparsers.add_parser("disable")
    enable_parser = subparsers.add_parser("enable")
    enable_parser.add_argument("--user", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "enable":
            result = enable(args.user)
        elif args.action == "disable":
            result = disable()
        elif args.action == "prepare":
            result = prepare()
        else:
            result = status()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "data": result}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
