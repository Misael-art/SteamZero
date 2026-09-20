# SPDX-License-Identifier: GPL-3.0-or-later
"""Preflights somente leitura para runtimes de consoles com estado externo.

O launcher deve distinguir "o emulador está instalado" de "a máquina que o
emulador precisa consegue iniciar". Este módulo não baixa firmware, não grava
configuração de terceiros e não cria arquivos: ele só lê a configuração já
existente e devolve razões estáveis para a UI e para o preflight de launch.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

_XEMU_APP_ID = "app.xemu.xemu"
_XEMU_REQUIRED_FILES = (
    ("eeprom_path", "eeprom"),
    ("flash_path", "flash"),
    ("mcpx_path", "mcpx"),
    ("hdd_path", "hdd"),
)


@dataclass(frozen=True)
class XboxRuntimeReadiness:
    """Estado verificável do hardware virtual necessário pelo xemu."""

    ready: bool
    config_found: bool
    missing: tuple[str, ...] = ()
    reason: str = ""


def _config_candidates(
    *,
    home: Path,
    config_root: Path | None,
    data_root: Path | None,
) -> tuple[Path, ...]:
    """Retorna os layouts nativo e Flatpak sem depender de um só deles."""

    config = config_root or Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    data = data_root or Path(os.environ.get("XDG_DATA_HOME", home / ".local/share"))
    return (
        config / "xemu" / "xemu.toml",
        config / "xemu" / "xemu" / "xemu.toml",
        data / "xemu" / "xemu" / "xemu.toml",
        home / ".var" / "app" / _XEMU_APP_ID / "data/xemu/xemu/xemu.toml",
    )


def _machine_files(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        return {}
    sys_table = raw.get("sys")
    if not isinstance(sys_table, dict):
        return {}
    files = sys_table.get("files")
    return files if isinstance(files, dict) else {}


def check_xemu_runtime(
    *,
    home: Path | None = None,
    config_root: Path | None = None,
    data_root: Path | None = None,
    candidates: Iterable[Path] | None = None,
    read_text: Callable[[Path], str] | None = None,
    is_file: Callable[[Path], bool] | None = None,
) -> XboxRuntimeReadiness:
    """Verifica a máquina virtual do Xbox sem abrir o xemu.

    O xemu pode guardar a configuração dentro do sandbox Flatpak ou no layout
    XDG nativo. Um arquivo de configuração parcial é uma pendência recuperável,
    não uma permissão para abrir a tela ``Configure machine settings`` depois
    do gesto de jogar.
    """

    selected_home = home or Path.home()
    paths = tuple(
        candidates
        or _config_candidates(
            home=selected_home,
            config_root=config_root,
            data_root=data_root,
        )
    )
    exists = is_file or (lambda path: path.is_file() and not path.is_symlink())
    reader = read_text or (lambda path: path.read_text(encoding="utf-8"))
    config_path = next((path for path in paths if exists(path)), None)
    if config_path is None:
        return XboxRuntimeReadiness(
            ready=False,
            config_found=False,
            reason="xbox-machine-config-missing",
        )
    try:
        raw = tomllib.loads(reader(config_path))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        return XboxRuntimeReadiness(
            ready=False,
            config_found=True,
            reason="xbox-machine-config-invalid",
        )

    files = _machine_files(raw)
    missing: list[str] = []
    for key, label in _XEMU_REQUIRED_FILES:
        value = files.get(key)
        if not isinstance(value, str) or not value.strip():
            missing.append(label)
            continue
        machine_file = Path(value).expanduser()
        if not exists(machine_file):
            missing.append(label)
    if missing:
        return XboxRuntimeReadiness(
            ready=False,
            config_found=True,
            missing=tuple(missing),
            reason="xbox-machine-files-missing",
        )
    return XboxRuntimeReadiness(ready=True, config_found=True)


__all__ = ["XboxRuntimeReadiness", "check_xemu_runtime"]
