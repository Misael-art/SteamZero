# SPDX-License-Identifier: GPL-3.0-or-later
"""Boot direto no Game Mode, independente e reversível.

O marcador do GRUB apenas solicita a sessão. Um preparador oneshot valida a
sessão instalada antes de publicar a configuração de autologin do SDDM. Se a
sessão estiver ausente, o arquivo gerenciado é removido e o SDDM volta ao
greeter, evitando ciclos de login ou uma queda silenciosa no Desktop.
"""

from __future__ import annotations

import argparse
import configparser
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
Geteuid = Callable[[], int]

_MARKERS = frozenset({"steamzero.gamemode=1"})
_MANAGED = "# SteamZero-Boot-Managed: true"
_USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
_UUID_RE = re.compile(r"^[A-Fa-f0-9-]{8,64}$")
_BOOT_PATH_RE = re.compile(r"^/[A-Za-z0-9_./@+-]+$")
_BOOT_ID_RE = re.compile(r"^[A-Fa-f0-9-]{8,64}$")
_STATE_OWNER = "SteamZero-Boot-Managed"
_STATE_VERSION = 1
_BACKOFF_THRESHOLD = 3


@dataclass(frozen=True)
class BootLayout:
    boot: Path = Path("/boot")
    config: Path = Path("/etc/steamzero/gamemode-user")
    sddm_config: Path = Path("/etc/sddm.conf.d/99-steamzero-gamemode.conf")
    # /usr/share é o único diretório varrido por todos os display managers;
    # /etc/sddm.conf de distros (BigLinux) restringe SessionDir a ele (ADR-0020).
    session: Path = Path("/usr/share/wayland-sessions/steamzero-gamemode.desktop")
    unit: Path = Path("/usr/local/lib/systemd/system/steamzero-gamemode-boot.service")
    grub_script: Path = Path("/etc/grub.d/42_steamzero_gamemode")
    grub_config: Path = Path("/boot/grub/grub.cfg")
    cmdline: Path = Path("/proc/cmdline")
    boot_id: Path = Path("/proc/sys/kernel/random/boot_id")
    state: Path = Path("/var/lib/steamzero/gamemode-boot/state.json")
    requested: Path = Path("/var/lib/steamzero/gamemode-boot/requested.json")
    started: Path | None = None
    sddm_system_config_dir: Path = Path("/usr/lib/sddm/sddm.conf.d")
    sddm_etc_config_dir: Path = Path("/etc/sddm.conf.d")
    sddm_config_file: Path = Path("/etc/sddm.conf")


_DEFAULT_LAYOUT = BootLayout()


def _geteuid() -> int:
    return os.geteuid()


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _lexists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return True


def _managed(path: Path) -> bool:
    return not _lexists(path) or (
        path.is_file() and not path.is_symlink() and _MANAGED in _read_text(path)
    )


def _read_config_user(layout: BootLayout) -> tuple[str, bool]:
    """(usuário configurado, acesso negado); EACCES nunca é lido como 'não configurado'."""
    try:
        raw = layout.config.read_text(encoding="utf-8").strip()
    except PermissionError:
        return "", True
    except OSError:
        return "", False
    lines = raw.splitlines()
    user = lines[1].strip() if len(lines) == 2 and lines[0].strip() == _MANAGED else ""
    return user, False


def _config_user(layout: BootLayout) -> str:
    return _read_config_user(layout)[0]


def _probe_owned(path: Path) -> tuple[bool, bool]:
    """(presente e gerenciado, acesso negado); Path.exists() esconde EACCES do diretório."""
    try:
        path.lstat()
    except PermissionError:
        return False, True
    except OSError:
        return False, False
    try:
        if path.is_symlink() or not path.is_file():
            return False, False
        text = path.read_text(encoding="utf-8")
    except PermissionError:
        return False, True
    except OSError:
        return False, False
    return _MANAGED in text, False


def _boot_id(layout: BootLayout, supplied: str | None = None) -> str:
    value = supplied if supplied is not None else _read_text(layout.boot_id)
    if not _BOOT_ID_RE.fullmatch(value):
        raise SteamZeroError(
            "E-SESSION-LAUNCH-FAILED", detail="identificador do boot atual inválido"
        )
    return value


def _state_default() -> dict[str, Any]:
    return {
        "schemaVersion": _STATE_VERSION,
        "managedBy": _STATE_OWNER,
        "consecutiveFailures": 0,
        "backoff": False,
        "lastEvaluatedBootId": None,
        "lastStartedBootId": None,
        "lastFailure": None,
    }


def _read_owned_json(path: Path) -> dict[str, Any] | None:
    try:
        path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise SteamZeroError(
            "E-SESSION-LAUNCH-FAILED", detail=f"estado de boot ilegível: {path}"
        ) from exc
    if path.is_symlink() or not path.is_file():
        raise SteamZeroError("E-SESSION-LAUNCH-FAILED", detail=f"estado de boot inseguro: {path}")
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SteamZeroError(
            "E-SESSION-LAUNCH-FAILED", detail=f"estado de boot corrompido: {path}"
        ) from exc
    if (
        not isinstance(loaded, dict)
        or loaded.get("schemaVersion") != _STATE_VERSION
        or loaded.get("managedBy") != _STATE_OWNER
    ):
        raise SteamZeroError(
            "E-SESSION-LAUNCH-FAILED", detail=f"estado de boot não gerenciado: {path}"
        )
    return loaded


def _write_owned_json(path: Path, payload: dict[str, Any], *, mode: int = 0o600) -> None:
    data = {"schemaVersion": _STATE_VERSION, "managedBy": _STATE_OWNER, **payload}
    fs.write_atomic_text(
        path,
        json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n",
        mode=mode,
    )


def _started_path(layout: BootLayout, user: Any) -> Path:
    if layout.started is not None:
        return layout.started
    home = getattr(user, "pw_dir", "")
    if not isinstance(home, str) or not home.startswith("/"):
        raise SteamZeroError(
            "E-SESSION-LAUNCH-FAILED", detail="diretório do usuário de Game Mode inválido"
        )
    return Path(home) / ".local" / "state" / "steamzero" / "gamemode-boot-started.json"


def _load_state(layout: BootLayout) -> dict[str, Any]:
    loaded = _read_owned_json(layout.state)
    if loaded is None:
        return _state_default()
    failures = loaded.get("consecutiveFailures")
    if not isinstance(failures, int) or isinstance(failures, bool) or not 0 <= failures <= 1000:
        raise SteamZeroError("E-SESSION-LAUNCH-FAILED", detail="contador de boot inválido")
    if not isinstance(loaded.get("backoff"), bool):
        raise SteamZeroError("E-SESSION-LAUNCH-FAILED", detail="backoff de boot inválido")
    return loaded


def _persist_state(layout: BootLayout, state: dict[str, Any]) -> None:
    _write_owned_json(
        layout.state,
        {key: value for key, value in state.items() if key not in {"schemaVersion", "managedBy"}},
    )


def _reconcile_previous_attempt(
    layout: BootLayout, *, current_boot_id: str, started_path: Path
) -> dict[str, Any]:
    state = _load_state(layout)
    requested = _read_owned_json(layout.requested)
    started = _read_owned_json(started_path)
    started_id = started.get("bootId") if started else None
    requested_id = requested.get("bootId") if requested else None
    changed = False

    # Uma sessão iniciada manualmente após backoff é uma recuperação válida.
    if isinstance(started_id, str) and started_id != state.get("lastStartedBootId"):
        state["consecutiveFailures"] = 0
        state["backoff"] = False
        state["lastFailure"] = None
        state["lastStartedBootId"] = started_id
        if isinstance(requested_id, str):
            state["lastEvaluatedBootId"] = requested_id
        changed = True
    elif (
        isinstance(requested_id, str)
        and requested_id != current_boot_id
        and requested_id != state.get("lastEvaluatedBootId")
    ):
        if started_id == requested_id:
            state["consecutiveFailures"] = 0
            state["backoff"] = False
            state["lastFailure"] = None
            state["lastStartedBootId"] = started_id
        else:
            failures = int(state["consecutiveFailures"]) + 1
            state["consecutiveFailures"] = failures
            state["backoff"] = failures >= _BACKOFF_THRESHOLD
            state["lastFailure"] = {
                "bootId": requested_id,
                "reason": "session-not-started",
            }
        state["lastEvaluatedBootId"] = requested_id
        changed = True
    if changed:
        _persist_state(layout, state)
    return state


def _record_request(layout: BootLayout, *, boot_id: str) -> None:
    _write_owned_json(layout.requested, {"bootId": boot_id})


def effective_session_dirs(layout: BootLayout = _DEFAULT_LAYOUT) -> list[Path]:
    """Reproduz a precedência relevante do SDDM; o último arquivo vence."""
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    candidates: list[Path] = []
    for directory in (layout.sddm_system_config_dir, layout.sddm_etc_config_dir):
        try:
            candidates.extend(sorted(directory.glob("*.conf")))
        except OSError as exc:
            raise SteamZeroError(
                "E-SESSION-LAUNCH-FAILED", detail=f"configuração SDDM ilegível: {directory}"
            ) from exc
    candidates.append(layout.sddm_config_file)
    for path in candidates:
        if not path.is_file():
            continue
        try:
            with path.open(encoding="utf-8") as handle:
                parser.read_file(handle)
        except (OSError, UnicodeDecodeError, configparser.Error) as exc:
            raise SteamZeroError(
                "E-SESSION-LAUNCH-FAILED", detail=f"configuração SDDM inválida: {path}"
            ) from exc
    raw = parser.get("Wayland", "SessionDir", fallback=str(layout.session.parent)).strip()
    directories = [Path(item.strip()) for item in re.split(r"[:,]", raw) if item.strip()]
    return directories or [layout.session.parent]


def _session_is_visible(layout: BootLayout) -> bool:
    session_parent = layout.session.parent.resolve(strict=False)
    return any(
        path.resolve(strict=False) == session_parent for path in effective_session_dirs(layout)
    )


def _validate_user(username: str, *, lookup: Callable[[str], Any] = pwd.getpwnam) -> Any:
    if not _USER_RE.fullmatch(username):
        raise SteamZeroError("E-API-SCHEMA", detail="usuário de Game Mode inválido")
    try:
        record = lookup(username)
    except KeyError as exc:
        raise SteamZeroError("E-API-SCHEMA", detail="usuário de Game Mode inexistente") from exc
    if int(record.pw_uid) < 1000 or int(record.pw_uid) == 65534:
        raise SteamZeroError("E-API-SCHEMA", detail="usuário de Game Mode não interativo")
    return record


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
    if _lexists(path) and not _managed(path):
        raise SteamZeroError(
            "E-SESSION-LAUNCH-FAILED", detail=f"recusando remover arquivo alheio: {path}"
        )
    fs.remove_file(path)


def _clear_one_shot_entry(
    layout: BootLayout, *, runner: Runner, which: Callable[[str], str | None]
) -> bool:
    """Remove somente o ``next_entry`` SteamZero que já produziu este boot.

    Algumas distribuições carregam um bloco de ambiente adicional e salvam a
    limpeza nele, deixando a variável original em ``grubenv``. Nesse caso o
    suposto boot único vira recorrente. O preparador roda como root e converge
    explicitamente apenas o identificador pertencente ao SteamZero.
    """
    grubenv = layout.boot / "grub" / "grubenv"
    if not _lexists(grubenv):
        return False
    if grubenv.is_symlink() or not grubenv.is_file():
        raise SteamZeroError(
            "E-SESSION-LAUNCH-FAILED", detail=f"bloco de ambiente GRUB inseguro: {grubenv}"
        )
    if "next_entry=steamzero-gamemode" not in _read_text(grubenv).splitlines():
        return False
    grub_editenv = which("grub-editenv")
    if grub_editenv is None:
        raise SteamZeroError(
            "E-SESSION-LAUNCH-FAILED",
            detail="grub-editenv ausente; recusando manter boot SteamZero recorrente",
        )
    _run([grub_editenv, str(grubenv), "unset", "next_entry"], runner=runner)
    if "next_entry=steamzero-gamemode" in _read_text(grubenv).splitlines():
        raise SteamZeroError(
            "E-SESSION-LAUNCH-FAILED",
            detail="não foi possível limpar a seleção única SteamZero do GRUB",
        )
    return True


def prepare(
    layout: BootLayout = _DEFAULT_LAYOUT,
    *,
    cmdline: str | None = None,
    boot_id: str | None = None,
    user_lookup: Callable[[str], Any] = pwd.getpwnam,
    runner: Runner = subprocess.run,
    which: Callable[[str], str | None] = shutil.which,
) -> dict[str, Any]:
    """Converge a seleção do SDDM para o marcador de boot observado."""
    raw_cmdline = _read_text(layout.cmdline) if cmdline is None else cmdline
    username = _config_user(layout)
    user = _validate_user(username, lookup=user_lookup) if username else None
    state = _state_default()
    current_boot_id: str | None = None
    if user is not None:
        current_boot_id = _boot_id(layout, boot_id)
        state = _reconcile_previous_attempt(
            layout,
            current_boot_id=current_boot_id,
            started_path=_started_path(layout, user),
        )
    if not _requested(raw_cmdline):
        _remove_managed(layout.sddm_config)
        return {
            "state": "inactive",
            "session": None,
            "consecutiveFailures": state["consecutiveFailures"],
            "backoff": state["backoff"],
        }

    _clear_one_shot_entry(layout, runner=runner, which=which)
    user = _validate_user(username, lookup=user_lookup)
    if current_boot_id is None:
        current_boot_id = _boot_id(layout, boot_id)
        state = _reconcile_previous_attempt(
            layout,
            current_boot_id=current_boot_id,
            started_path=_started_path(layout, user),
        )
    if state["backoff"]:
        _remove_managed(layout.sddm_config)
        return {
            "state": "backoff",
            "session": None,
            "user": username,
            "consecutiveFailures": state["consecutiveFailures"],
            "backoff": True,
            "reason": "Autologin suspenso após falhas consecutivas; use o greeter para recuperar.",
        }
    _record_request(layout, boot_id=current_boot_id)
    if not layout.session.is_file() or layout.session.is_symlink():
        _remove_managed(layout.sddm_config)
        raise SteamZeroError(
            "E-SESSION-LAUNCH-FAILED",
            detail="sessão SteamZero ausente; autologin removido para retornar ao greeter",
        )
    if not _session_is_visible(layout):
        _remove_managed(layout.sddm_config)
        visible = ", ".join(str(path) for path in effective_session_dirs(layout))
        raise SteamZeroError(
            "E-SESSION-LAUNCH-FAILED",
            detail=f"sessão fora do SessionDir efetivo do SDDM: {visible}",
        )
    if not _managed(layout.sddm_config):
        raise SteamZeroError(
            "E-SESSION-LAUNCH-FAILED", detail="configuração SDDM SteamZero não gerenciada"
        )
    fs.write_atomic_text(layout.sddm_config, _sddm_text(username), mode=0o644)
    return {
        "state": "selected",
        "session": "steamzero-gamemode.desktop",
        "user": username,
        "consecutiveFailures": state["consecutiveFailures"],
        "backoff": False,
    }


def mark_started(
    layout: BootLayout = _DEFAULT_LAYOUT,
    *,
    boot_id: str | None = None,
    marker_path: Path | None = None,
) -> dict[str, Any]:
    """Marca que a sessão realmente iniciou; funciona sem privilégio de root."""
    current_boot_id = _boot_id(layout, boot_id)
    target = marker_path
    if target is None:
        target = layout.started or (
            Path.home() / ".local" / "state" / "steamzero" / "gamemode-boot-started.json"
        )
    previous = _read_owned_json(target)
    _write_owned_json(target, {"bootId": current_boot_id})
    return {
        "state": "started",
        "bootId": current_boot_id,
        "recovered": previous is None or previous.get("bootId") != current_boot_id,
    }


def recover(
    layout: BootLayout = _DEFAULT_LAYOUT,
    *,
    user_lookup: Callable[[str], Any] = pwd.getpwnam,
    geteuid: Geteuid = _geteuid,
) -> dict[str, Any]:
    """Limpa somente o backoff próprio; não habilita autologin automaticamente."""
    if geteuid() != 0:
        raise PermissionError("execute com bigsudo")
    username = _config_user(layout)
    state_paths = [layout.state, layout.requested]
    if username:
        user = _validate_user(username, lookup=user_lookup)
        state_paths.append(_started_path(layout, user))
    for path in state_paths:
        _read_owned_json(path)
        fs.remove_file(path)
    _remove_managed(layout.sddm_config)
    return {"state": "recovered", "backoff": False, "consecutiveFailures": 0}


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
    # O initramfs exige a chave completa ``root=``. ``values["root"]`` contém
    # apenas o valor (por exemplo, ``UUID=...``); emitir esse valor isolado faz
    # o kernel enxergar uma raiz vazia e cair no emergency shell antes do
    # systemd. Preserve explicitamente o formato observado em /proc/cmdline.
    args = [f"root={root}", "rw" if "rw" in flags else "ro"]
    if rootflags:
        if not re.fullmatch(r"[A-Za-z0-9_=/@,.-]+", rootflags):
            raise SteamZeroError("E-SESSION-LAUNCH-FAILED", detail="rootflags inválido")
        args.append(f"rootflags={rootflags}")
    args.extend(flag for flag in ("quiet", "splash") if flag in flags)
    args.append("steamzero.gamemode=1")
    return kernel, initrd_name, root.removeprefix("UUID="), args


def _grub_text(cmdline: str, boot: Path = Path("/boot")) -> str:
    kernel, _initrd_name, uuid, args = _boot_spec(cmdline, boot)
    boot_prefix = str(Path(kernel).parent)
    kernel_args = " ".join(shlex.quote(value) for value in args)
    menuentry = (
        "menuentry 'SteamZero Game Mode' --id='steamzero-gamemode' --hotkey=g "
        "--class steam --class gnu-linux --class gnu --class os"
    )
    return f"""#!/usr/bin/env bash
{_MANAGED}
set -eu

boot_dir={shlex.quote(str(boot))}
grub_prefix={shlex.quote(boot_prefix)}
kernel_path=''
initrd_path=''
shopt -s nullglob
for candidate in \"$boot_dir\"/vmlinuz \"$boot_dir\"/vmlinuz-*; do
    [[ -f \"$candidate\" ]] || continue
    base=${{candidate##*/}}
    [[ \"$base\" =~ ^vmlinuz[A-Za-z0-9_.+-]*$ ]] || continue
    suffix=${{base#vmlinuz}}
    paired=''
    for possible in \\
        \"$boot_dir/initramfs${{suffix}}.img\" \\
        \"$boot_dir/initrd${{suffix}}.img\" \\
        \"$boot_dir/initrd.img${{suffix}}\"; do
        if [[ -f \"$possible\" ]]; then
            paired=$possible
            break
        fi
    done
    [[ -n \"$paired\" ]] || continue
    if [[ -z \"$kernel_path\" || \"$candidate\" -nt \"$kernel_path\" || \
          ( ! \"$kernel_path\" -nt \"$candidate\" && \"$candidate\" > \"$kernel_path\" ) ]]; then
        kernel_path=$candidate
        initrd_path=$paired
    fi
done

if [[ -z \"$kernel_path\" || -z \"$initrd_path\" ]]; then
    echo 'SteamZero: nenhum par kernel/initramfs válido encontrado' >&2
    exit 1
fi

kernel_name=${{kernel_path##*/}}
initrd_name=${{initrd_path##*/}}
if [[ \"$grub_prefix\" == '/' ]]; then
    kernel_grub=\"/$kernel_name\"
    initrd_grub=\"/$initrd_name\"
else
    kernel_grub=\"$grub_prefix/$kernel_name\"
    initrd_grub=\"$grub_prefix/$initrd_name\"
fi
initrd_line=''
for ucode in amd-ucode.img intel-ucode.img; do
    if [[ -f \"$boot_dir/$ucode\" ]]; then
        if [[ \"$grub_prefix\" == '/' ]]; then
            initrd_line+=\" /$ucode\"
        else
            initrd_line+=\" $grub_prefix/$ucode\"
        fi
    fi
done
initrd_line+=\" $initrd_grub\"

cat <<STEAMZERO_GRUB_ENTRY
{menuentry} {{
    insmod part_gpt
    insmod btrfs
    search --no-floppy --fs-uuid --set=root {uuid}
    echo 'Iniciando SteamZero Game Mode...'
    linux $kernel_grub {kernel_args}
    initrd$initrd_line
}}
STEAMZERO_GRUB_ENTRY
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


def _first_available(which: Callable[[str], str | None], names: Sequence[str]) -> str | None:
    for name in names:
        executable = which(name)
        if executable is not None:
            return executable
    return None


def _validate_generated_grub(path: Path, *, present: bool) -> None:
    if path.is_symlink() or not path.is_file():
        raise SteamZeroError(
            "E-SESSION-LAUNCH-FAILED", detail="grub.cfg não foi gerado como arquivo regular"
        )
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SteamZeroError(
            "E-SESSION-LAUNCH-FAILED", detail="grub.cfg gerado não pôde ser validado"
        ) from exc
    entry_present = "steamzero-gamemode" in content
    marker_present = "steamzero.gamemode=1" in content
    if not present and (entry_present or marker_present):
        raise SteamZeroError(
            "E-SESSION-LAUNCH-FAILED",
            detail="entrada SteamZero deveria estar ausente no grub.cfg",
        )
    if present and not (entry_present and marker_present):
        expectation = "ausente" if not present else "presente"
        raise SteamZeroError(
            "E-SESSION-LAUNCH-FAILED",
            detail=f"entrada SteamZero deveria estar {expectation} no grub.cfg",
        )
    if present:
        bootable = False
        for line in content.splitlines():
            tokens = line.split()
            if len(tokens) < 3 or tokens[0] != "linux" or "steamzero.gamemode=1" not in tokens:
                continue
            roots = [
                token.removeprefix("root=UUID=")
                for token in tokens
                if token.startswith("root=UUID=")
            ]
            if len(roots) == 1 and _UUID_RE.fullmatch(roots[0]):
                bootable = True
                break
        if not bootable:
            raise SteamZeroError(
                "E-SESSION-LAUNCH-FAILED",
                detail="entrada SteamZero inválida no grub.cfg: argumento root=UUID ausente",
            )


def enable(
    username: str,
    layout: BootLayout = _DEFAULT_LAYOUT,
    *,
    runner: Runner = subprocess.run,
    which: Callable[[str], str | None] = shutil.which,
    user_lookup: Callable[[str], Any] = pwd.getpwnam,
    geteuid: Geteuid = _geteuid,
) -> dict[str, Any]:
    """Instala a integração GRUB/SDDM sob ownership exclusivo do SteamZero."""
    if geteuid() != 0:
        raise PermissionError("execute com bigsudo")
    user = _validate_user(username, lookup=user_lookup)
    if not layout.session.is_file() or layout.session.is_symlink():
        raise SteamZeroError("E-SESSION-LAUNCH-FAILED", detail="sessão SteamZero não instalada")
    if not _session_is_visible(layout):
        visible = ", ".join(str(path) for path in effective_session_dirs(layout))
        raise SteamZeroError(
            "E-SESSION-LAUNCH-FAILED",
            detail=f"sessão fora do SessionDir efetivo do SDDM: {visible}",
        )
    for path in (layout.unit, layout.grub_script, layout.sddm_config):
        if not _managed(path):
            raise SteamZeroError(
                "E-SESSION-LAUNCH-FAILED", detail=f"arquivo de boot não gerenciado: {path}"
            )
    systemctl = which("systemctl")
    grub_mkconfig = which("grub-mkconfig")
    steam = which("steam")
    gamescope = which("gamescope")
    gamescope_session = which("gamescope-session-plus")
    desktop = _first_available(
        which, ("startkde-biglinux", "startplasma-wayland", "startplasma-x11")
    )
    if (
        systemctl is None
        or grub_mkconfig is None
        or steam is None
        or gamescope is None
        or gamescope_session is None
        or desktop is None
    ):
        raise SteamZeroError(
            "E-SESSION-LAUNCH-FAILED",
            detail=(
                "preflight incompleto: systemd, GRUB, Steam, Gamescope Session ou Desktop ausente"
            ),
        )
    cmdline = _read_text(layout.cmdline)
    started_path = _started_path(layout, user)
    previous = {
        path: path.read_bytes() if path.is_file() and not path.is_symlink() else None
        for path in (
            layout.config,
            layout.unit,
            layout.grub_script,
            layout.sddm_config,
            layout.grub_config,
            layout.state,
            layout.requested,
            started_path,
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
        if _lexists(layout.config) and not _managed(layout.config):
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
        _validate_generated_grub(layout.grub_config, present=True)
        prepared = prepare(
            layout,
            cmdline=cmdline,
            user_lookup=user_lookup,
            runner=runner,
            which=which,
        )
    except BaseException:
        for path, content in previous.items():
            if content is None:
                fs.remove_file(path)
            else:
                mode = (
                    0o755
                    if path == layout.grub_script
                    else 0o600
                    if path in {layout.config, layout.state, layout.requested, started_path}
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
    user_lookup: Callable[[str], Any] = pwd.getpwnam,
    geteuid: Geteuid = _geteuid,
) -> dict[str, Any]:
    """Remove somente integração própria e regenera o GRUB."""
    if geteuid() != 0:
        raise PermissionError("execute com bigsudo")
    username, _denied = _read_config_user(layout)
    started_path = (
        _started_path(layout, _validate_user(username, lookup=user_lookup)) if username else None
    )
    integration_paths = [layout.config, layout.unit, layout.grub_script, layout.sddm_config]
    state_paths = [layout.state, layout.requested]
    if started_path is not None:
        state_paths.append(started_path)
    for path in integration_paths:
        if _lexists(path) and not _managed(path):
            raise SteamZeroError(
                "E-SESSION-LAUNCH-FAILED", detail=f"arquivo não gerenciado: {path}"
            )
    for path in state_paths:
        _read_owned_json(path)
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
            *state_paths,
        )
    }
    for path in (*integration_paths, *state_paths):
        fs.remove_file(path)
    try:
        _run([systemctl, "disable", layout.unit.name], runner=runner)
        _run([systemctl, "daemon-reload"], runner=runner)
        _run([grub_mkconfig, "-o", str(layout.grub_config)], runner=runner)
        _validate_generated_grub(layout.grub_config, present=False)
    except BaseException:
        for path, content in previous.items():
            if content is None:
                fs.remove_file(path)
                continue
            mode = (
                0o755
                if path == layout.grub_script
                else 0o600
                if path in {layout.config, *state_paths}
                else 0o644
            )
            fs.write_atomic(path, content, mode=mode)
        raise
    return {"state": "disabled", "session": None}


def status(
    layout: BootLayout = _DEFAULT_LAYOUT,
    *,
    user_lookup: Callable[[str], Any] = pwd.getpwnam,
) -> dict[str, Any]:
    username, denied = _read_config_user(layout)
    owned = True
    for path in (layout.unit, layout.grub_script):
        present, path_denied = _probe_owned(path)
        if path_denied:
            denied = True
        elif not present:
            owned = False
    configured = bool(username) and owned
    health = _state_default()
    health_error: str | None = None
    try:
        health = _load_state(layout)
    except SteamZeroError as exc:
        if "ilegível" in (exc.detail or ""):
            denied = True
        else:
            health_error = exc.detail or str(exc)
    started_boot_id: str | None = None
    if username:
        try:
            user = _validate_user(username, lookup=user_lookup)
            started = _read_owned_json(_started_path(layout, user))
            if started is not None and isinstance(started.get("bootId"), str):
                started_boot_id = started["bootId"]
        except (SteamZeroError, OSError):
            started_boot_id = None
    if denied and not configured:
        return {
            "state": "unknown",
            "configured": False,
            "permissionDenied": True,
            "changesGrub": True,
            "session": "steamzero-gamemode.desktop",
            "marker": "steamzero.gamemode=1",
            "reason": "Sem permissão para inspecionar a configuração de boot.",
            "consecutiveFailures": health["consecutiveFailures"],
            "backoff": health["backoff"],
            "lastFailure": health["lastFailure"],
            "lastStartedBootId": started_boot_id,
        }
    if health_error is not None:
        state_name = "degraded"
        reason = health_error
    elif health["backoff"]:
        state_name = "backoff"
        reason = "Autologin suspenso após falhas consecutivas; recuperação manual disponível."
    else:
        state_name = "ready" if configured else "available"
        reason = (
            "Entrada SteamZero pronta; falha retorna ao greeter/Plasma."
            if configured
            else "Ativação privilegiada e reversível ainda não executada."
        )
    return {
        "state": state_name,
        "configured": configured,
        "permissionDenied": False,
        "changesGrub": True,
        "session": "steamzero-gamemode.desktop",
        "marker": "steamzero.gamemode=1",
        "reason": reason,
        "consecutiveFailures": health["consecutiveFailures"],
        "backoff": health["backoff"],
        "lastFailure": health["lastFailure"],
        "lastStartedBootId": started_boot_id,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Boot resiliente do SteamZero Game Mode")
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("status")
    subparsers.add_parser("prepare")
    subparsers.add_parser("started")
    subparsers.add_parser("recover")
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
        elif args.action == "started":
            result = mark_started()
        elif args.action == "recover":
            result = recover()
        else:
            result = status()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "data": result}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
