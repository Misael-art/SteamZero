# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Instalador de mods nos diretórios de emuladores Switch.

Gerencia a colocação, ativação/desativação e remoção de arquivos de mod
nos diretórios ``load/`` (Citron/Eden) e ``mods/`` (Ryubing) dos emuladores.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar

from steamzero.core import fs
from steamzero.core.errors import SteamZeroError
from steamzero.domain.switch_emulators import SwitchEmulatorCatalog
from steamzero.ports import InstalledModView, ModIdentity, ModInstallerPort


class FilesystemModInstaller(ModInstallerPort):
    """Instala mods como diretórios nomeados no diretório ``load/<title_id>/`` do emulador."""

    EMULATOR_PATHS: ClassVar[dict[str, list[str]]] = {
        "citron": ["citron", "load"],
        "eden": ["eden", "load"],
    }

    def __init__(
        self,
        data_home: Path,
        catalog: SwitchEmulatorCatalog | None = None,
        config_home: Path | None = None,
    ) -> None:
        self._data_home = data_home
        self._config_home = config_home or Path.home() / ".config"
        self._catalog = catalog or SwitchEmulatorCatalog()

    def _emulator_base(self, emulator_id: str) -> Path | None:
        emulator = self._catalog.by_id(emulator_id)
        if emulator is None:
            return None
        parts = self.EMULATOR_PATHS.get(emulator_id)
        if emulator_id == "ryubing":
            return self._config_home / "Ryujinx" / "mods" / "contents"
        if parts is None:
            return None
        return self._data_home.joinpath(*parts)

    def install(
        self,
        candidate: ModIdentity,
        game_title_id: str,
        emulator_id: str,
        files: Sequence[tuple[str, bytes]],
    ) -> Path:
        base = self._emulator_base(emulator_id)
        if base is None:
            raise SteamZeroError(
                "E-MOD-EMULATOR-NOT-FOUND",
                detail=f"Emulador {emulator_id!r} não tem diretório de mods conhecido",
            )

        mod_dir = base / game_title_id / _sanitize_name(candidate.name)
        fs.ensure_dir(mod_dir)

        for filename, data in files:
            dest = mod_dir / filename
            fs.write_atomic(dest, data)

        return mod_dir

    def remove(self, install_path: Path) -> bool:
        if not install_path.exists():
            return False
        fs.remove_tree(install_path)
        return not install_path.exists()

    def activate(self, install_path: Path) -> bool:
        parent = install_path.parent
        active_link = parent / f"{install_path.name}.active"
        if not install_path.exists():
            return False
        fs.symlink_atomic(install_path, active_link)
        return active_link.exists()

    def deactivate(self, install_path: Path) -> bool:
        parent = install_path.parent
        active_link = parent / f"{install_path.name}.active"
        if active_link.exists():
            fs.remove_path(active_link)
        return not active_link.exists()

    def list_installed_mods(self, title_id: str, emulator_id: str) -> list[InstalledModView]:
        base = self._emulator_base(emulator_id)
        if base is None:
            return []
        game_dir = base / title_id
        if not game_dir.is_dir():
            return []
        results: list[InstalledModView] = []
        for entry in sorted(game_dir.iterdir()):
            if entry.name.endswith(".active"):
                continue
            if not entry.is_dir():
                continue
            active_link = game_dir / f"{entry.name}.active"
            results.append(
                InstalledModView(
                    mod_id=entry.name,
                    game_id="",
                    title_id=title_id,
                    build_id=None,
                    name=entry.name,
                    mod_type="other",
                    state="active" if active_link.exists() else "installed",
                    emulator_id=emulator_id,
                    install_path=str(entry),
                    source="filesystem",
                    version=None,
                )
            )
        return results


def _sanitize_name(name: str) -> str:
    import re

    return re.sub(r"[^a-zA-Z0-9 _.-]", "_", name).strip() or "mod"
