#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
# SteamZero-Host-Managed: true
"""Instalador host versionado do SteamZero.

Executar com ``bigsudo``. A instalação vive em releases imutáveis sob
``/opt/steamzero``; ``current`` troca atomicamente e pode voltar a uma release
anterior sem tocar no estado XDG dos usuários.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from email.parser import Parser
from pathlib import Path
from typing import Any

_RELEASE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_COMMIT_RE = re.compile(r"^[a-f0-9]{40}$")
_MAX_WHEELS = 64
_MAX_WHEEL_SIZE = 50 * 1024 * 1024
_MAX_WHEELHOUSE_SIZE = 500 * 1024 * 1024
_MANAGED_MARKER = "X-SteamZero-Managed=true"
_MANAGER_MARKER = "# SteamZero-Host-Managed: true"
_INSTALLER_NAME = "install_host.py"


@dataclass(frozen=True)
class Layout:
    root: Path = Path("/opt/steamzero")
    command: Path = Path("/usr/local/bin/steamzero")
    gamemode_command: Path = Path("/usr/local/bin/steamzero-gamemode-session")
    session_selector_command: Path = Path("/usr/local/bin/steamos-session-select")
    gamemode_boot_command: Path = Path("/usr/local/libexec/steamzero-gamemode-boot")
    host_prepare_command: Path = Path("/usr/local/libexec/steamzero-host-prepare")
    admin_command: Path = Path("/usr/local/libexec/steamzero-admin")
    manager: Path = Path("/usr/local/sbin/steamzero-host")
    desktop: Path = Path("/usr/local/share/applications/org.steamzero.SteamZero.desktop")
    user_service: Path = Path("/usr/local/lib/systemd/user/steamzero-core.service")
    user_socket: Path = Path("/usr/local/lib/systemd/user/steamzero-core.socket")
    # /usr/share é o único diretório de sessões varrido por todos os display
    # managers; /etc/sddm.conf de distros (BigLinux) restringe SessionDir a ele
    # e invisibiliza sessões em /usr/local (incidente 2026-07-18, ADR-0020).
    gamemode_session: Path = Path("/usr/share/wayland-sessions/steamzero-gamemode.desktop")
    # Publicado por steam_boot.enable(), fora do ownership do instalador; sua
    # presença indica boot direto ativo e exige a cadeia de binários no venv.
    gamemode_boot_unit: Path = Path("/usr/local/lib/systemd/system/steamzero-gamemode-boot.service")
    legacy_gamemode_session: Path = Path(
        "/usr/local/share/wayland-sessions/steamzero-gamemode.desktop"
    )
    polkit_policy: Path = Path(
        "/usr/share/polkit-1/actions/io.github.misael-art.steamzero.admin.policy"
    )

    @property
    def releases(self) -> Path:
        return self.root / "releases"

    @property
    def current(self) -> Path:
        return self.root / "current"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _release_id(value: str) -> str:
    if not _RELEASE_RE.fullmatch(value):
        raise ValueError(f"release inválida: {value!r}")
    return value


def _wheel_identity(path: Path) -> tuple[str, str]:
    """Retorna nome e versão declarados no METADATA do wheel."""
    try:
        with zipfile.ZipFile(path) as archive:
            metadata_files = [
                name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
            ]
            if len(metadata_files) != 1:
                raise ValueError("wheel deve conter exatamente um METADATA")
            message = Parser().parsestr(archive.read(metadata_files[0]).decode("utf-8"))
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile, KeyError) as exc:
        raise ValueError("wheel inválido ou sem METADATA legível") from exc
    name = message.get("Name", "").strip().lower()
    version = message.get("Version", "").strip()
    if name != "steamzero" or not version or not _RELEASE_RE.fullmatch(version):
        raise ValueError("identidade do wheel não corresponde ao SteamZero")
    return name, version


def _canonical_release(version: str, source_commit: str) -> str:
    if not _RELEASE_RE.fullmatch(version):
        raise ValueError("versão do pacote inválida")
    if not _COMMIT_RE.fullmatch(source_commit):
        raise ValueError("commit de origem precisa ser SHA-1 completo em minúsculas")
    return _release_id(f"{version}-{source_commit[:12]}")


def _regular_file(path: Path, *, suffix: str | None = None) -> Path:
    resolved = path.resolve(strict=True)
    if path.is_symlink() or not resolved.is_file():
        raise ValueError(f"artefato precisa ser arquivo regular, sem symlink: {path}")
    if suffix is not None and resolved.suffix != suffix:
        raise ValueError(f"extensão inválida para {path}; esperado {suffix}")
    return resolved


def _wheelhouse(path: Path) -> tuple[Path, list[Path]]:
    resolved = path.resolve(strict=True)
    if path.is_symlink() or not resolved.is_dir():
        raise ValueError(f"wheelhouse inválido: {path}")
    wheels = sorted(resolved.glob("*.whl"))
    if not wheels or len(wheels) > _MAX_WHEELS:
        raise ValueError(f"wheelhouse deve conter 1..{_MAX_WHEELS} wheels")
    total = 0
    for wheel in wheels:
        if wheel.is_symlink() or not wheel.is_file():
            raise ValueError(f"wheel inseguro: {wheel}")
        size = wheel.stat().st_size
        if size <= 0 or size > _MAX_WHEEL_SIZE:
            raise ValueError(f"wheel fora do limite: {wheel.name}")
        total += size
    if total > _MAX_WHEELHOUSE_SIZE:
        raise ValueError("wheelhouse excede o limite total")
    return resolved, wheels


def _run(argv: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=1800,
            check=True,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"comando excedeu timeout: {Path(argv[0]).name}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or f"exit {exc.returncode}").strip()[-2000:]
        raise RuntimeError(f"comando {Path(argv[0]).name} falhou: {detail}") from exc


def _atomic_text(path: Path, text: str, *, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}.{secrets.token_hex(4)}")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_dir(path.parent)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()
        raise


def _atomic_symlink(path: Path, target: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}.{secrets.token_hex(4)}")
    try:
        os.symlink(target, temporary)
        os.replace(temporary, path)
        _fsync_dir(path.parent)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()
        raise


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_tree(path: Path) -> None:
    """Persiste conteúdo e entradas da release antes de publicar ``current``."""
    for root, directories, files in os.walk(path, topdown=False, followlinks=False):
        root_path = Path(root)
        for filename in files:
            candidate = root_path / filename
            if candidate.is_symlink():
                continue
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(candidate, flags)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        for directory in directories:
            candidate = root_path / directory
            if not candidate.is_symlink():
                _fsync_dir(candidate)
        _fsync_dir(root_path)


def _readlink(path: Path) -> str | None:
    return os.readlink(path) if path.is_symlink() else None


def _managed_desktop(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    if path.is_symlink() or not path.is_file():
        return False
    try:
        return _MANAGED_MARKER in path.read_text(encoding="utf-8")
    except OSError:
        return False


def _managed_manager(layout: Layout) -> bool:
    path = layout.manager
    if not path.exists() and not path.is_symlink():
        return True
    if path.is_symlink():
        return _readlink(path) == str(layout.current / "artifacts" / _INSTALLER_NAME)
    if not path.is_file():
        return False
    try:
        return _MANAGER_MARKER in path.read_text(encoding="utf-8")
    except OSError:
        return False


def _publish_manager(layout: Layout) -> None:
    if not _managed_manager(layout):
        raise RuntimeError(f"recusando substituir gerenciador não gerenciado: {layout.manager}")
    source = Path(__file__).resolve(strict=True)
    text = source.read_text(encoding="utf-8")
    if _MANAGER_MARKER not in text:
        raise RuntimeError("fonte do gerenciador não possui marcador de ownership")
    _atomic_text(layout.manager, text, mode=0o755)


def _desktop_entry(command: Path) -> str:
    return f"""[Desktop Entry]
Type=Application
Name=SteamZero
Comment=Central resiliente para Steam Deck e Linux
TryExec={command}
Exec={command} desktop ui
Icon=input-gaming
Terminal=false
Categories=Game;
StartupNotify=true
X-SteamZero-Managed=true
"""


def _service_unit(layout: Layout) -> str:
    executable = layout.current / "venv" / "bin" / "steamzero-core"
    return f"""# SteamZero-Host-Managed: true
[Unit]
Description=SteamZero user control plane
Documentation=https://github.com/Misael-art/SteamZero
Requires=steamzero-core.socket
After=steamzero-core.socket

[Service]
Type=simple
ExecStart={executable} --systemd
Environment=PYTHONNOUSERSITE=1
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectControlGroups=true
ProtectKernelModules=true
ProtectKernelTunables=true
RestrictAddressFamilies=AF_UNIX
LockPersonality=true
MemoryDenyWriteExecute=true
"""


def _socket_unit() -> str:
    return """# SteamZero-Host-Managed: true
[Unit]
Description=SteamZero local user socket

[Socket]
ListenStream=%t/steamzero/core.sock
SocketMode=0600
DirectoryMode=0700
RemoveOnStop=true

[Install]
WantedBy=sockets.target
"""


def _gamemode_session_entry(layout: Layout) -> str:
    executable = layout.current / "venv" / "bin" / "steamzero-gamemode-session"
    return f"""[Desktop Entry]
Name=SteamZero Game Mode
Comment=Sessão Steam em Gamescope com fallback seguro para o Desktop
Exec={executable}
TryExec={executable}
Type=Application
DesktopNames=gamescope
X-SteamZero-Managed=true
"""


def _polkit_policy(layout: Layout) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- SteamZero-Host-Managed: true -->
<!DOCTYPE policyconfig PUBLIC "-//freedesktop//DTD PolicyKit Policy Configuration 1.0//EN"
  "http://www.freedesktop.org/standards/PolicyKit/1/policyconfig.dtd">
<policyconfig>
  <vendor>SteamZero</vendor>
  <vendor_url>https://github.com/Misael-art/SteamZero</vendor_url>
  <action id="io.github.misael-art.steamzero.admin">
    <description>Executar uma ação privilegiada allowlisted do SteamZero</description>
    <message>Autenticação necessária para o helper protegido do SteamZero</message>
    <defaults>
      <allow_any>no</allow_any>
      <allow_inactive>auth_admin</allow_inactive>
      <allow_active>auth_admin_keep</allow_active>
    </defaults>
    <annotate key="org.freedesktop.policykit.exec.path">{layout.admin_command}</annotate>
    <annotate key="org.freedesktop.policykit.exec.allow_gui">false</annotate>
  </action>
</policyconfig>
"""


def _managed_unit(path: Path) -> bool:
    if not path.exists() and not path.is_symlink():
        return True
    if path.is_symlink() or not path.is_file():
        return False
    try:
        return _MANAGER_MARKER in path.read_text(encoding="utf-8")
    except OSError:
        return False


def _sync_user_units(layout: Layout, release_path: Path) -> None:
    for path in (layout.user_service, layout.user_socket):
        if not _managed_unit(path):
            raise RuntimeError(f"recusando substituir unidade não gerenciada: {path}")
    core = release_path / "venv" / "bin" / "steamzero-core"
    if core.is_file() and not core.is_symlink() and os.access(core, os.X_OK):
        _atomic_text(layout.user_service, _service_unit(layout))
        _atomic_text(layout.user_socket, _socket_unit())
        return
    for path in (layout.user_service, layout.user_socket):
        with contextlib.suppress(FileNotFoundError):
            path.unlink()


def _sync_gamemode_session(layout: Layout, release_path: Path) -> None:
    if not _managed_desktop(layout.gamemode_session):
        raise RuntimeError(f"recusando substituir sessão não gerenciada: {layout.gamemode_session}")
    if layout.legacy_gamemode_session.exists() and _managed_desktop(layout.legacy_gamemode_session):
        with contextlib.suppress(FileNotFoundError):
            layout.legacy_gamemode_session.unlink()
    executable = release_path / "venv" / "bin" / "steamzero-gamemode-session"
    if executable.is_file() and not executable.is_symlink() and os.access(executable, os.X_OK):
        _atomic_text(layout.gamemode_session, _gamemode_session_entry(layout))
        return
    with contextlib.suppress(FileNotFoundError):
        layout.gamemode_session.unlink()


def _managed_gamemode_command(layout: Layout) -> bool:
    path = layout.gamemode_command
    if not path.exists() and not path.is_symlink():
        return True
    return path.is_symlink() and _readlink(path) == str(
        layout.current / "venv" / "bin" / "steamzero-gamemode-session"
    )


def _sync_gamemode_command(layout: Layout, release_path: Path) -> None:
    if not _managed_gamemode_command(layout):
        raise RuntimeError(
            f"recusando substituir comando não gerenciado: {layout.gamemode_command}"
        )
    executable = release_path / "venv" / "bin" / "steamzero-gamemode-session"
    if executable.is_file() and not executable.is_symlink() and os.access(executable, os.X_OK):
        _atomic_symlink(
            layout.gamemode_command,
            str(layout.current / "venv" / "bin" / "steamzero-gamemode-session"),
        )
        return
    with contextlib.suppress(FileNotFoundError):
        layout.gamemode_command.unlink()


def _managed_session_selector_command(layout: Layout) -> bool:
    path = layout.session_selector_command
    if not path.exists() and not path.is_symlink():
        return True
    return path.is_symlink() and _readlink(path) == str(
        layout.current / "venv" / "bin" / "steamos-session-select"
    )


def _sync_session_selector_command(layout: Layout, release_path: Path) -> None:
    if not _managed_session_selector_command(layout):
        raise RuntimeError(
            "recusando substituir seletor de sessão não gerenciado: "
            f"{layout.session_selector_command}"
        )
    executable = release_path / "venv" / "bin" / "steamos-session-select"
    if executable.is_file() and not executable.is_symlink() and os.access(executable, os.X_OK):
        # /usr/local/bin precede /usr/bin na sessão Gamescope. O wrapper registra
        # explicitamente Desktop/restart para que uma queda transitória não seja
        # confundida com uma escolha do usuário.
        _atomic_symlink(
            layout.session_selector_command,
            str(layout.current / "venv" / "bin" / "steamos-session-select"),
        )
        return
    with contextlib.suppress(FileNotFoundError):
        layout.session_selector_command.unlink()


def _managed_gamemode_boot_command(layout: Layout) -> bool:
    path = layout.gamemode_boot_command
    if not path.exists() and not path.is_symlink():
        return True
    return path.is_symlink() and _readlink(path) == str(
        layout.current / "venv" / "bin" / "steamzero-gamemode-boot"
    )


def _sync_gamemode_boot_command(layout: Layout, release_path: Path) -> None:
    if not _managed_gamemode_boot_command(layout):
        raise RuntimeError(
            f"recusando substituir comando de boot não gerenciado: {layout.gamemode_boot_command}"
        )
    executable = release_path / "venv" / "bin" / "steamzero-gamemode-boot"
    if executable.is_file() and not executable.is_symlink() and os.access(executable, os.X_OK):
        _atomic_symlink(
            layout.gamemode_boot_command,
            str(layout.current / "venv" / "bin" / "steamzero-gamemode-boot"),
        )
        return
    with contextlib.suppress(FileNotFoundError):
        layout.gamemode_boot_command.unlink()


def _managed_host_prepare_command(layout: Layout) -> bool:
    path = layout.host_prepare_command
    if not path.exists() and not path.is_symlink():
        return True
    return path.is_symlink() and _readlink(path) == str(
        layout.current / "venv" / "bin" / "steamzero-host-prepare"
    )


def _sync_host_prepare_command(layout: Layout, release_path: Path) -> None:
    if not _managed_host_prepare_command(layout):
        raise RuntimeError(
            f"recusando substituir preparador não gerenciado: {layout.host_prepare_command}"
        )
    executable = release_path / "venv" / "bin" / "steamzero-host-prepare"
    if executable.is_file() and not executable.is_symlink() and os.access(executable, os.X_OK):
        _atomic_symlink(
            layout.host_prepare_command,
            str(layout.current / "venv" / "bin" / "steamzero-host-prepare"),
        )
        return
    with contextlib.suppress(FileNotFoundError):
        layout.host_prepare_command.unlink()


def _managed_admin(layout: Layout) -> bool:
    command = layout.admin_command
    command_ok = (not command.exists() and not command.is_symlink()) or (
        command.is_symlink()
        and _readlink(command) == str(layout.current / "venv" / "bin" / "steamzero-admin")
    )
    policy = layout.polkit_policy
    if not policy.exists() and not policy.is_symlink():
        policy_ok = True
    elif policy.is_symlink() or not policy.is_file():
        policy_ok = False
    else:
        try:
            policy_ok = "SteamZero-Host-Managed: true" in policy.read_text(encoding="utf-8")
        except OSError:
            policy_ok = False
    return command_ok and policy_ok


def _sync_admin(layout: Layout, release_path: Path) -> None:
    if not _managed_admin(layout):
        raise RuntimeError("recusando substituir helper/policy privilegiado não gerenciado")
    executable = release_path / "venv" / "bin" / "steamzero-admin"
    if executable.is_file() and not executable.is_symlink() and os.access(executable, os.X_OK):
        _atomic_symlink(
            layout.admin_command,
            str(layout.current / "venv" / "bin" / "steamzero-admin"),
        )
        _atomic_text(layout.polkit_policy, _polkit_policy(layout))
        return
    with contextlib.suppress(FileNotFoundError):
        layout.admin_command.unlink()
    with contextlib.suppress(FileNotFoundError):
        layout.polkit_policy.unlink()


def _verify_release(release_path: Path, *, expected_release: str | None = None) -> dict[str, Any]:
    if release_path.is_symlink() or not release_path.is_dir():
        raise RuntimeError(f"diretório de release inválido: {release_path}")
    manifest_path = release_path / "manifest.json"
    executable = release_path / "venv" / "bin" / "steamzero"
    core_executable = release_path / "venv" / "bin" / "steamzero-core"
    session_executable = release_path / "venv" / "bin" / "steamzero-gamemode-session"
    selector_executable = release_path / "venv" / "bin" / "steamos-session-select"
    boot_executable = release_path / "venv" / "bin" / "steamzero-gamemode-boot"
    host_prepare_executable = release_path / "venv" / "bin" / "steamzero-host-prepare"
    installer = release_path / "artifacts" / _INSTALLER_NAME
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise RuntimeError(f"manifesto ausente em {release_path}")
    if not executable.is_file() or executable.is_symlink() or not os.access(executable, os.X_OK):
        raise RuntimeError(f"executável inválido em {release_path}")
    if not installer.is_file() or installer.is_symlink() or not os.access(installer, os.X_OK):
        raise RuntimeError(f"gerenciador host inválido em {release_path}")
    loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise RuntimeError("manifesto da release precisa ser um objeto")
    data: dict[str, Any] = loaded
    expected = expected_release or release_path.name
    schema_version = data.get("schemaVersion")
    if schema_version not in {1, 2, 3, 4} or data.get("release") != expected:
        raise RuntimeError("manifesto da release não corresponde ao diretório")
    if schema_version in {2, 3, 4}:
        source_commit = data.get("sourceCommit")
        package_version = data.get("packageVersion")
        if (
            not isinstance(source_commit, str)
            or not isinstance(package_version, str)
            or data.get("sourceTreeState") != "clean"
        ):
            raise RuntimeError("proveniência ausente no manifesto v2")
        try:
            canonical = _canonical_release(package_version, source_commit)
        except ValueError as exc:
            raise RuntimeError("proveniência inválida no manifesto v2") from exc
        if canonical != expected:
            raise RuntimeError("release não corresponde à versão e ao commit de origem")
    if schema_version in {3, 4} and (
        not core_executable.is_file()
        or core_executable.is_symlink()
        or not os.access(core_executable, os.X_OK)
    ):
        raise RuntimeError(f"daemon inválido em {release_path}")
    if schema_version in {3, 4} and (
        not session_executable.is_file()
        or session_executable.is_symlink()
        or not os.access(session_executable, os.X_OK)
    ):
        raise RuntimeError(f"Session Manager inválido em {release_path}")
    if schema_version == 4 and (
        not boot_executable.is_file()
        or boot_executable.is_symlink()
        or not os.access(boot_executable, os.X_OK)
    ):
        raise RuntimeError(f"preparador de boot inválido em {release_path}")
    if schema_version == 4 and (
        not selector_executable.is_file()
        or selector_executable.is_symlink()
        or not os.access(selector_executable, os.X_OK)
    ):
        raise RuntimeError(f"seletor de sessão inválido em {release_path}")
    if schema_version == 4 and (
        not host_prepare_executable.is_file()
        or host_prepare_executable.is_symlink()
        or not os.access(host_prepare_executable, os.X_OK)
    ):
        raise RuntimeError(f"preparador de host inválido em {release_path}")
    wheel_file = data.get("wheelFile")
    if not isinstance(wheel_file, str) or Path(wheel_file).name != wheel_file:
        raise RuntimeError("nome do wheel inválido no manifesto")
    wheel = release_path / "artifacts" / wheel_file
    requirements = release_path / "artifacts" / "requirements-runtime.lock"
    integrity = (
        (wheel, data.get("wheelSha256"), "wheel"),
        (requirements, data.get("requirementsSha256"), "lock de runtime"),
        (installer, data.get("installerSha256"), "gerenciador host"),
    )
    for artifact, expected_hash, label in integrity:
        if artifact.is_symlink() or not artifact.is_file():
            raise RuntimeError(f"{label} ausente na release")
        if not isinstance(expected_hash, str) or _sha256(artifact) != expected_hash:
            raise RuntimeError(f"integridade inválida: {label}")
    if os.geteuid() == 0:
        protected_paths = [
            release_path,
            release_path / "artifacts",
            release_path / "venv",
            manifest_path,
            executable,
            wheel,
            requirements,
            installer,
        ]
        if schema_version in {3, 4}:
            protected_paths.extend((core_executable, session_executable))
        if schema_version == 4:
            protected_paths.extend((boot_executable, host_prepare_executable, selector_executable))
        for protected in protected_paths:
            stat = protected.stat()
            if stat.st_uid != 0 or stat.st_mode & 0o022:
                raise RuntimeError(f"permissões inseguras em {protected}")

    with tempfile.TemporaryDirectory(prefix="steamzero-host-smoke-") as smoke_directory:
        smoke_root = Path(smoke_directory)
        environment = {
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/bin",
            "HOME": "/nonexistent",
            "XDG_STATE_HOME": str(smoke_root / "state"),
            "XDG_DATA_HOME": str(smoke_root / "data"),
            "XDG_CONFIG_HOME": str(smoke_root / "config"),
            "PYTHONNOUSERSITE": "1",
        }
        version = _run([str(executable), "--version"], env=environment).stdout.strip()
        if schema_version in {3, 4}:
            _run([str(core_executable), "--help"], env=environment)
            _run([str(session_executable), "--help"], env=environment)
        if schema_version == 4:
            _run([str(boot_executable), "status"], env=environment)
            _run([str(host_prepare_executable), "status"], env=environment)
        doctor = _run([str(executable), "doctor", "--json"], env=environment)
        payload = json.loads(doctor.stdout)
        if (
            not version
            or (schema_version == 2 and version != data["packageVersion"])
            or payload.get("status") not in {"ok", "degraded"}
        ):
            raise RuntimeError("smoke da release não retornou estado saudável")
    return data


_BOOT_CHAIN_BINARIES = (
    "steamzero-gamemode-boot",
    "steamzero-gamemode-session",
    "steamos-session-select",
)


def _venv_binary_ok(release_path: Path, name: str) -> bool:
    binary = release_path / "venv" / "bin" / name
    return binary.is_file() and not binary.is_symlink() and os.access(binary, os.X_OK)


def _require_boot_chain(layout: Layout, target: Path) -> None:
    """Boot direto ativo exige a cadeia de binários no venv da release alvo.

    Incidente 2026-07-19: uma release sem entry points de Game Mode foi ativada
    com o unit oneshot, o autologin SDDM e a sessão publicados apontando para
    ``current`` — o boot caiu no greeter com sessão morta. A publicação por
    capacidade continua valendo para os artefatos do próprio instalador; a
    integração de boot pertence ao steam_boot e deve ser desativada antes de
    ativar uma release sem esses binários.
    """
    if not layout.gamemode_boot_unit.exists() and not layout.gamemode_boot_unit.is_symlink():
        return
    missing = [name for name in _BOOT_CHAIN_BINARIES if not _venv_binary_ok(target, name)]
    if missing:
        raise RuntimeError(
            "recusando ativar release sem binários exigidos pelo boot direto ativo: "
            + ", ".join(missing)
            + "; desative o boot Game Mode antes de ativar esta release"
        )


def _activate(layout: Layout, release: str) -> None:
    release = _release_id(release)
    target = layout.releases / release
    _verify_release(target)
    _require_boot_chain(layout, target)
    if layout.current.exists() and not layout.current.is_symlink():
        raise RuntimeError(f"recusando substituir current não gerenciado: {layout.current}")
    if layout.command.exists() and not layout.command.is_symlink():
        raise RuntimeError(f"recusando substituir arquivo não gerenciado: {layout.command}")
    if not _managed_desktop(layout.desktop):
        raise RuntimeError(f"recusando substituir desktop entry não gerenciada: {layout.desktop}")
    for unit in (layout.user_service, layout.user_socket):
        if not _managed_unit(unit):
            raise RuntimeError(f"recusando substituir unidade não gerenciada: {unit}")
    if not _managed_desktop(layout.gamemode_session):
        raise RuntimeError(f"recusando substituir sessão não gerenciada: {layout.gamemode_session}")
    if not _managed_desktop(layout.legacy_gamemode_session):
        raise RuntimeError(
            f"recusando remover sessão legada não gerenciada: {layout.legacy_gamemode_session}"
        )
    if not _managed_gamemode_command(layout):
        raise RuntimeError(
            f"recusando substituir comando não gerenciado: {layout.gamemode_command}"
        )
    if not _managed_session_selector_command(layout):
        raise RuntimeError(
            "recusando substituir seletor de sessão não gerenciado: "
            f"{layout.session_selector_command}"
        )
    if not _managed_gamemode_boot_command(layout):
        raise RuntimeError(
            f"recusando substituir comando de boot não gerenciado: {layout.gamemode_boot_command}"
        )
    if not _managed_host_prepare_command(layout):
        raise RuntimeError(
            f"recusando substituir preparador não gerenciado: {layout.host_prepare_command}"
        )
    if not _managed_admin(layout):
        raise RuntimeError("recusando substituir helper/policy privilegiado não gerenciado")

    previous_current = _readlink(layout.current)
    previous_command = _readlink(layout.command)
    previous_gamemode_command = _readlink(layout.gamemode_command)
    previous_session_selector_command = _readlink(layout.session_selector_command)
    previous_gamemode_boot_command = _readlink(layout.gamemode_boot_command)
    previous_host_prepare_command = _readlink(layout.host_prepare_command)
    previous_admin_command = _readlink(layout.admin_command)
    previous_desktop = layout.desktop.read_bytes() if layout.desktop.is_file() else None
    previous_service = layout.user_service.read_bytes() if layout.user_service.is_file() else None
    previous_socket = layout.user_socket.read_bytes() if layout.user_socket.is_file() else None
    previous_session = (
        layout.gamemode_session.read_bytes() if layout.gamemode_session.is_file() else None
    )
    previous_legacy_session = (
        layout.legacy_gamemode_session.read_bytes()
        if layout.legacy_gamemode_session.is_file()
        else None
    )
    previous_policy = layout.polkit_policy.read_bytes() if layout.polkit_policy.is_file() else None
    try:
        _sync_user_units(layout, target)
        _sync_gamemode_session(layout, target)
        _sync_gamemode_command(layout, target)
        _sync_session_selector_command(layout, target)
        _sync_gamemode_boot_command(layout, target)
        _sync_host_prepare_command(layout, target)
        _sync_admin(layout, target)
        _atomic_symlink(layout.command, str(layout.current / "venv" / "bin" / "steamzero"))
        _atomic_text(layout.desktop, _desktop_entry(layout.command))
        # Único ponto que publica uma versão nova; os demais links são estáveis.
        _atomic_symlink(layout.current, f"releases/{release}")
    except BaseException:
        _restore_link(layout.current, previous_current)
        _restore_link(layout.command, previous_command)
        _restore_link(layout.gamemode_command, previous_gamemode_command)
        _restore_link(layout.session_selector_command, previous_session_selector_command)
        _restore_link(layout.gamemode_boot_command, previous_gamemode_boot_command)
        _restore_link(layout.host_prepare_command, previous_host_prepare_command)
        _restore_link(layout.admin_command, previous_admin_command)
        if previous_desktop is None:
            with contextlib.suppress(FileNotFoundError):
                layout.desktop.unlink()
        else:
            _atomic_text(layout.desktop, previous_desktop.decode("utf-8"))
        _restore_managed_text(layout.user_service, previous_service)
        _restore_managed_text(layout.user_socket, previous_socket)
        _restore_managed_text(layout.gamemode_session, previous_session)
        _restore_managed_text(layout.legacy_gamemode_session, previous_legacy_session)
        _restore_managed_text(layout.polkit_policy, previous_policy)
        raise


def _restore_managed_text(path: Path, content: bytes | None) -> None:
    if content is None:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
    else:
        _atomic_text(path, content.decode("utf-8"))


def _restore_link(path: Path, target: str | None) -> None:
    if target is None:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
    else:
        _atomic_symlink(path, target)


def _copy_artifacts(
    destination: Path,
    wheel: Path,
    requirements: Path,
    dependency_wheels: list[Path],
) -> tuple[Path, Path, Path, Path]:
    artifact_dir = destination / "artifacts"
    dependency_dir = destination / "wheelhouse"
    artifact_dir.mkdir(mode=0o755)
    dependency_dir.mkdir(mode=0o755)
    copied_wheel = artifact_dir / wheel.name
    copied_requirements = artifact_dir / "requirements-runtime.lock"
    copied_installer = artifact_dir / _INSTALLER_NAME
    shutil.copyfile(wheel, copied_wheel)
    shutil.copyfile(requirements, copied_requirements)
    shutil.copyfile(Path(__file__).resolve(strict=True), copied_installer)
    os.chmod(copied_wheel, 0o644)
    os.chmod(copied_requirements, 0o644)
    os.chmod(copied_installer, 0o755)  # noqa: S103 - executável global somente leitura
    for dependency in dependency_wheels:
        copied = dependency_dir / dependency.name
        shutil.copyfile(dependency, copied)
        os.chmod(copied, 0o644)
    return copied_wheel, copied_requirements, copied_installer, dependency_dir


def install(
    layout: Layout,
    *,
    release: str,
    wheel: Path,
    wheel_sha256: str,
    requirements: Path,
    wheelhouse: Path,
    source_commit: str,
) -> dict[str, Any]:
    if not _SHA256_RE.fullmatch(wheel_sha256):
        raise ValueError("sha256 do wheel inválido")
    wheel = _regular_file(wheel, suffix=".whl")
    _project_name, package_version = _wheel_identity(wheel)
    canonical_release = _canonical_release(package_version, source_commit)
    release = _release_id(release)
    if release != canonical_release:
        raise ValueError(f"release deve ser canônica para versão+commit: {canonical_release}")
    requirements = _regular_file(requirements, suffix=".lock")
    _wheelhouse_root, dependency_wheels = _wheelhouse(wheelhouse)
    if _sha256(wheel) != wheel_sha256:
        raise ValueError("sha256 do wheel não confere")

    os.umask(0o022)
    layout.releases.mkdir(parents=True, exist_ok=True, mode=0o755)
    final = layout.releases / release
    if final.exists():
        if final.is_symlink() or not final.is_dir():
            raise RuntimeError(f"release existente insegura: {final}")
        marker = final / ".installing.json"
        if marker.is_file() and not marker.is_symlink():
            try:
                interrupted = json.loads(marker.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise RuntimeError("marcador de instalação interrompida inválido") from exc
            if interrupted != {
                "release": release,
                "wheelSha256": wheel_sha256,
                "sourceCommit": source_commit,
            }:
                raise RuntimeError("instalação interrompida não corresponde ao artefato atual")
            shutil.rmtree(final)
            _fsync_dir(layout.releases)
        else:
            existing_manifest = _verify_release(final)
            if existing_manifest.get("wheelSha256") != wheel_sha256:
                raise RuntimeError("release existente usa outro wheel")
            if existing_manifest.get("sourceCommit") != source_commit:
                raise RuntimeError("release existente usa outro commit de origem")
            _publish_manager(layout)
            _activate(layout, release)
            return existing_manifest

    final.mkdir(mode=0o755)
    _atomic_text(
        final / ".installing.json",
        json.dumps(
            {
                "release": release,
                "wheelSha256": wheel_sha256,
                "sourceCommit": source_commit,
            },
            sort_keys=True,
        ),
    )
    try:
        copied_wheel, copied_requirements, copied_installer, copied_wheelhouse = _copy_artifacts(
            final, wheel, requirements, dependency_wheels
        )
        if _sha256(copied_wheel) != wheel_sha256:
            raise RuntimeError("wheel copiado divergiu do hash esperado")
        venv = final / "venv"
        _run([sys.executable, "-m", "venv", "--copies", str(venv)])
        pip = venv / "bin" / "pip"
        _run(
            [
                str(pip),
                "install",
                "--disable-pip-version-check",
                "--no-index",
                "--only-binary=:all:",
                "--require-hashes",
                f"--find-links={copied_wheelhouse}",
                "-r",
                str(copied_requirements),
            ]
        )
        _run(
            [
                str(pip),
                "install",
                "--disable-pip-version-check",
                "--no-index",
                "--no-deps",
                str(copied_wheel),
            ]
        )
        _run([str(pip), "check"])
        manifest: dict[str, Any] = {
            "schemaVersion": 4,
            "release": release,
            "packageVersion": package_version,
            "sourceCommit": source_commit,
            "sourceTreeState": "clean",
            "wheelFile": copied_wheel.name,
            "wheelSha256": wheel_sha256,
            "requirementsSha256": _sha256(copied_requirements),
            "installerSha256": _sha256(copied_installer),
            "installedAt": datetime.now(UTC).isoformat(),
            "python": sys.version.split()[0],
            "previousRelease": (_readlink(layout.current) or "").removeprefix("releases/") or None,
        }
        _atomic_text(final / "manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
        _verify_release(final)
        shutil.rmtree(final / "wheelhouse")
        (final / ".installing.json").unlink()
        _fsync_tree(final)
        _fsync_dir(layout.releases)
        _publish_manager(layout)
        _activate(layout, release)
        return manifest
    except BaseException:
        shutil.rmtree(final, ignore_errors=True)
        _fsync_dir(layout.releases)
        raise


def rollback(layout: Layout, release: str) -> dict[str, Any]:
    release = _release_id(release)
    manifest = _verify_release(layout.releases / release)
    _activate(layout, release)
    return manifest


def status(layout: Layout) -> dict[str, Any]:
    target = _readlink(layout.current)
    if target is None:
        return {"installed": False, "release": None}
    release = Path(target).name
    manifest = _verify_release(layout.releases / release)
    return {"installed": True, "release": release, "manifest": manifest}


def _require_root() -> None:
    if os.geteuid() != 0:
        raise PermissionError("execute este instalador com bigsudo")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Instalador host transacional do SteamZero")
    subparsers = parser.add_subparsers(dest="action", required=True)
    install_parser = subparsers.add_parser("install")
    install_parser.add_argument("--release", required=True)
    install_parser.add_argument("--wheel", type=Path, required=True)
    install_parser.add_argument("--wheel-sha256", required=True)
    install_parser.add_argument("--requirements", type=Path, required=True)
    install_parser.add_argument("--wheelhouse", type=Path, required=True)
    install_parser.add_argument("--source-commit", required=True)
    rollback_parser = subparsers.add_parser("rollback")
    rollback_parser.add_argument("--release", required=True)
    subparsers.add_parser("status")
    return parser


PENDING_REFRESH_NOTICE = (
    "release publicada, mas o serviço em segundo plano ainda executa a geração "
    "anterior; execute 'steamzero service refresh' na sessão do usuário para que "
    "ele passe a usar esta versão"
)


def _activation_notice(manifest: dict[str, Any]) -> dict[str, Any]:
    """Declara explicitamente que a publicação NÃO reiniciou o daemon.

    O instalador roda como root e as units são de escopo de usuário, válidas para
    todos os usuários da máquina: ele não sabe qual sessão reiniciar. Declarar o
    estado é o que impede o silêncio que produziu a a37, em que ``current``
    apontava para a release nova e o daemon seguia na anterior sem nada avisar.
    """
    return {
        **manifest,
        "daemonRefresh": {
            "state": "pending",
            "command": "steamzero service refresh",
            "detail": PENDING_REFRESH_NOTICE,
        },
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        _require_root()
        layout = Layout()
        if args.action == "install":
            result = _activation_notice(
                install(
                    layout,
                    release=args.release,
                    wheel=args.wheel,
                    wheel_sha256=args.wheel_sha256,
                    requirements=args.requirements,
                    wheelhouse=args.wheelhouse,
                    source_commit=args.source_commit,
                )
            )
        elif args.action == "rollback":
            result = _activation_notice(rollback(layout, args.release))
        else:
            result = status(layout)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "data": result}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
