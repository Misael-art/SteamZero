# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Instalador de cheats nos diretórios de emuladores Switch.

Cheats do Switch seguem o padrão Atmosphere:
``load/<title_id>/cheats/<build_id>.txt`` (Citron/Eden)
ou ``mods/contents/<title_id>/cheats/<build_id>.txt`` (Ryubing).
"""

from __future__ import annotations

from pathlib import Path

from steamzero.core import fs
from steamzero.core.errors import SteamZeroError
from steamzero.domain.switch_emulators import SwitchEmulatorCatalog
from steamzero.ports import CheatInstallerPort, InstalledCheatView


class FsCheatInstaller(CheatInstallerPort):
    """Instala cheats como arquivos ``<build_id>.txt`` no diretório ``cheats/`` do emulador."""

    def __init__(
        self,
        data_home: Path,
        catalog: SwitchEmulatorCatalog | None = None,
        config_home: Path | None = None,
    ) -> None:
        self._data_home = data_home
        self._config_home = config_home or Path.home() / ".config"
        self._catalog = catalog or SwitchEmulatorCatalog()

    def _cheats_dir(self, emulator_id: str, title_id: str) -> Path | None:
        emulator = self._catalog.by_id(emulator_id)
        if emulator is None:
            return None
        paths = {
            "citron": self._data_home / "citron" / "load" / title_id / "cheats",
            "eden": self._data_home / "eden" / "load" / title_id / "cheats",
            "ryubing": self._config_home / "Ryujinx" / "mods" / "contents" / title_id / "cheats",
        }
        return paths.get(emulator_id)

    def install(
        self,
        title_id: str,
        build_id: str | None,
        name: str,
        codes: tuple[str, ...],
        emulator_id: str,
    ) -> Path:
        if not build_id:
            build_id = "default"

        cheats_dir = self._cheats_dir(emulator_id, title_id)
        if cheats_dir is None:
            raise SteamZeroError(
                "E-CHEAT-EMULATOR-NOT-FOUND",
                detail=f"Emulador {emulator_id!r} não tem diretório de cheats conhecido",
            )

        fs.ensure_dir(cheats_dir)
        cheat_file = cheats_dir / f"{build_id}.txt"

        header = f"// {name}\n"
        if build_id and build_id != "default":
            header += f"// BuildID: {build_id}\n"
        content = header + "\n".join(codes)

        fs.write_atomic_text(cheat_file, content)
        return cheat_file

    def remove(self, title_id: str, build_id: str, emulator_id: str) -> bool:
        cheats_dir = self._cheats_dir(emulator_id, title_id)
        if cheats_dir is None:
            return False
        cheat_file = cheats_dir / f"{build_id}.txt"
        if not cheat_file.exists():
            return False
        fs.remove_path(cheat_file)
        return not cheat_file.exists()

    def enable(self, title_id: str, build_id: str, emulator_id: str) -> bool:
        return self._toggle_cheat(title_id, build_id, emulator_id, enabled=True)

    def disable(self, title_id: str, build_id: str, emulator_id: str) -> bool:
        return self._toggle_cheat(title_id, build_id, emulator_id, enabled=False)

    def _toggle_cheat(self, title_id: str, build_id: str, emulator_id: str, enabled: bool) -> bool:
        cheats_dir = self._cheats_dir(emulator_id, title_id)
        if cheats_dir is None:
            return False
        cheat_file = cheats_dir / f"{build_id}.txt"
        disabled_file = cheats_dir / f"{build_id}.txt.disabled"
        if enabled:
            if not disabled_file.exists():
                return cheat_file.exists()
            fs.move_file(disabled_file, cheat_file)
            return cheat_file.is_file() and not disabled_file.exists()
        if not cheat_file.exists():
            return False
        fs.move_file(cheat_file, disabled_file)
        return not cheat_file.exists()

    def list_installed(self, title_id: str, emulator_id: str) -> list[InstalledCheatView]:
        cheats_dir = self._cheats_dir(emulator_id, title_id)
        if cheats_dir is None or not cheats_dir.is_dir():
            return []
        results: list[InstalledCheatView] = []
        for entry in sorted(cheats_dir.iterdir()):
            if not entry.is_file() or not (
                entry.name.endswith(".txt") or entry.name.endswith(".txt.disabled")
            ):
                continue
            if entry.name.endswith(".txt.disabled"):
                build_id = entry.name.removesuffix(".txt.disabled")
                enabled = False
            else:
                build_id = entry.name.removesuffix(".txt")
                enabled = True
            try:
                text = entry.read_text("utf-8")
            except Exception:
                text = ""
            lines = [
                ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("//")
            ]
            results.append(
                InstalledCheatView(
                    cheat_id=build_id,
                    game_id="",
                    title_id=title_id,
                    build_id=None if build_id == "default" else build_id,
                    name=build_id,
                    cheat_type="other",
                    state="active" if enabled else "inactive",
                    emulator_id=emulator_id,
                    install_path=str(entry),
                    source="filesystem",
                    version=None,
                    code_count=len(lines),
                    enabled=enabled,
                )
            )
        return results

    def edit_codes(
        self,
        title_id: str,
        build_id: str,
        emulator_id: str,
        codes: tuple[str, ...],
    ) -> bool:
        cheats_dir = self._cheats_dir(emulator_id, title_id)
        if cheats_dir is None:
            return False
        cheat_file = cheats_dir / f"{build_id}.txt"
        if not cheat_file.exists():
            return False
        # Preserva cabeçalho existente (linhas //)
        existing = cheat_file.read_text("utf-8")
        header_lines = [ln for ln in existing.splitlines() if ln.strip().startswith("//")]
        content = "\n".join(header_lines) + "\n" + "\n".join(codes)
        fs.write_atomic_text(cheat_file, content)
        return True
