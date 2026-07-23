# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Gerenciamento de mods para emuladores de Switch.

``SwitchModManager`` é a fachada de domínio: orquestra busca em catálogos
remotos, download, instalação, ativação e remoção de mods de performance /
gráficos. Opera sobre os protocols definidos em :mod:`steamzero.ports`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from steamzero.ports import (
    BuildIdProviderPort,
    InstalledModView,
    ModCandidate,
    ModCatalogPort,
    ModInstallerPort,
)


class ModType(Enum):
    PERFORMANCE = "performance"
    GRAPHICS = "graphics"
    ULTRAWIDE = "ultrawide"
    GAMEPLAY = "gameplay"
    PATCH = "patch"
    OTHER = "other"

    @classmethod
    def _missing_(cls, value: object) -> ModType:
        if isinstance(value, str):
            for member in cls:
                if member.value == value:
                    return member
        return cls.OTHER


@dataclass(frozen=True)
class ModEntry:
    id: str
    title_id: str
    build_id: str | None
    name: str
    mod_type: ModType
    source: str
    source_url: str
    version: str | None
    description: str | None
    author: str | None
    requirements: str | None


@dataclass(frozen=True)
class InstalledMod:
    id: str
    game_id: str
    catalog_id: str | None
    title_id: str
    build_id: str | None
    name: str
    mod_type: ModType
    source: str
    version: str | None
    state: str
    install_path: str | None
    emulator_id: str | None


@dataclass(frozen=True)
class GameBuildId:
    game_id: str
    title_id: str
    build_id: str
    detected_from: str
    detected_at: str


_MOD_TYPES_FOR_TITLE = frozenset(
    {
        "performance",
        "graphics",
        "ultrawide",
        "gameplay",
        "patch",
        "other",
    }
)
VALID_MOD_STATES = frozenset(
    {"discovered", "downloaded", "installed", "active", "inactive", "error"}
)


def _validate_mod_type(t: str) -> str:
    if t not in _MOD_TYPES_FOR_TITLE:
        return "other"
    return t


class ModDatabasePort(Protocol):
    """Porta interna (não em ports.py) para persistência de mods.

    Implementada por adapters.mods.state_store_mods.
    """

    def save_installed_mod(self, mod: InstalledMod) -> None: ...

    def remove_installed_mod(self, mod_id: str) -> bool: ...

    def list_installed(self, game_id: str) -> list[InstalledMod]: ...

    def update_state(self, mod_id: str, new_state: str) -> None: ...

    def get_by_id(self, mod_id: str) -> InstalledMod | None: ...

    def save_build_id(self, entry: GameBuildId) -> None: ...

    def list_build_ids(self, game_id: str) -> list[GameBuildId]: ...


class SwitchModManager:
    """Fachada de domínio para gerenciamento de mods.

    Depende de portas injetadas para catálogo, instalador e persistência.
    """

    def __init__(
        self,
        catalog: ModCatalogPort,
        installer: ModInstallerPort,
        build_id_provider: BuildIdProviderPort,
        db: ModDatabasePort,
    ) -> None:
        self._catalog = catalog
        self._installer = installer
        self._build_id_provider = build_id_provider
        self._db = db

    # --- Discovery / scan ----------------------------------------------------

    def scan_games_for_build_ids(self, game_ids: list[str]) -> dict[str, list[str]]:
        """Escaneia jogos instalados e persiste Build IDs encontrados."""
        from datetime import datetime

        result: dict[str, list[str]] = {}
        for gid in game_ids:
            ids = self._build_id_provider.scan_game(gid)
            if ids:
                existing = {b.build_id for b in self._db.list_build_ids(gid)}
                now = datetime.now(UTC).isoformat()
                for bid in ids:
                    if bid not in existing:
                        entry = GameBuildId(
                            game_id=gid,
                            title_id="",
                            build_id=bid,
                            detected_from="rom",
                            detected_at=now,
                        )
                        self._db.save_build_id(entry)
                result[gid] = ids
        return result

    # --- Catalog search ------------------------------------------------------

    def list_candidates(self, title_id: str, build_id: str | None = None) -> list[ModCandidate]:
        """Busca mods disponíveis para um Title ID, opcionalmente filtrados por Build ID."""
        if build_id:
            return self._catalog.search_by_build_id(title_id, build_id)
        return self._catalog.search_by_title_id(title_id)

    def refresh_catalog(self) -> int:
        """Atualiza o catálogo remoto de mods."""
        return self._catalog.refresh_catalog()

    # --- Install / lifecycle -------------------------------------------------

    def download_and_install(
        self,
        candidate: ModCandidate,
        emulator_id: str,
        game_id: str,
    ) -> InstalledMod:
        """Baixa e instala um mod candidato para um jogo em um emulador."""
        from uuid import uuid4

        files = self._fetch_candidate_files(candidate)
        install_path = self._installer.install(
            candidate.identity,
            candidate.title_id,
            emulator_id,
            files,
        )

        mod_id = str(uuid4())
        mod = InstalledMod(
            id=mod_id,
            game_id=game_id,
            catalog_id=candidate.identity.source_url,
            title_id=candidate.title_id,
            build_id=candidate.build_id,
            name=candidate.identity.name,
            mod_type=ModType(candidate.identity.mod_type),
            source=candidate.identity.source,
            version=candidate.identity.version,
            state="installed",
            install_path=str(install_path),
            emulator_id=emulator_id,
        )
        self._db.save_installed_mod(mod)
        return mod

    def _fetch_candidate_files(self, candidate: ModCandidate) -> list[tuple[str, bytes]]:
        from steamzero.core.errors import SteamZeroError
        from steamzero.core.net import NetworkFailure, fetch_bytes

        source_url = candidate.identity.source_url
        max_bytes = 64 * 1024 * 1024
        try:
            data = fetch_bytes(
                source_url,
                max_bytes=max_bytes,
                headers={"User-Agent": "SteamZero/0.1"},
            )
        except NetworkFailure as exc:
            raise SteamZeroError(
                "E-MOD-DOWNLOAD-FAILED",
                detail=f"{source_url}: {exc.detail}",
            ) from exc
        return [("mod.zip", data)]

    def activate(self, mod_id: str) -> bool:
        """Ativa um mod instalado."""
        mod = self._db.get_by_id(mod_id)
        if mod is None or mod.install_path is None:
            return False
        ok = self._installer.activate(Path(mod.install_path))
        if ok:
            self._db.update_state(mod_id, "active")
        return ok

    def deactivate(self, mod_id: str) -> bool:
        """Desativa um mod instalado."""
        mod = self._db.get_by_id(mod_id)
        if mod is None or mod.install_path is None:
            return False
        ok = self._installer.deactivate(Path(mod.install_path))
        if ok:
            self._db.update_state(mod_id, "inactive")
        return ok

    def remove(self, mod_id: str) -> bool:
        """Remove um mod instalado (desinstala + apaga registro)."""
        mod = self._db.get_by_id(mod_id)
        if mod is None or mod.install_path is None:
            return False
        ok = self._installer.remove(Path(mod.install_path))
        if ok:
            self._db.remove_installed_mod(mod_id)
        return ok

    def list_installed(self, game_id: str) -> list[InstalledMod]:
        return self._db.list_installed(game_id)

    def list_installed_views(self, title_id: str, emulator_id: str) -> list[InstalledModView]:
        return self._installer.list_installed_mods(title_id, emulator_id)

    def to_dict(self, mod: InstalledMod) -> dict[str, Any]:
        return {
            "id": mod.id,
            "gameId": mod.game_id,
            "titleId": mod.title_id,
            "buildId": mod.build_id,
            "name": mod.name,
            "modType": mod.mod_type.value,
            "source": mod.source,
            "version": mod.version,
            "state": mod.state,
            "installPath": mod.install_path,
            "emulatorId": mod.emulator_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InstalledMod:
        return InstalledMod(
            id=data["id"],
            game_id=data["gameId"],
            catalog_id=data.get("catalogId"),
            title_id=data["titleId"],
            build_id=data.get("buildId"),
            name=data["name"],
            mod_type=ModType(data.get("modType", "other")),
            source=data["source"],
            version=data.get("version"),
            state=data["state"],
            install_path=data.get("installPath"),
            emulator_id=data.get("emulatorId"),
        )
