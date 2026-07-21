# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Gerenciamento de cheats para emuladores de Switch.

``SwitchCheatManager`` é a fachada de domínio: orquestra busca em catálogos
remotos, download, instalação, ativação, edição e remoção de cheats.
Opera sobre os protocols definidos em :mod:`steamzero.ports`.

Cheats do Switch usam o formato Atmosphere: arquivos ``<build_id>.txt``
dentro de ``contents/<title_id>/cheats/`` no diretório ``load/`` do emulador.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from steamzero.ports import (
    CheatCandidate,
    CheatCatalogPort,
    CheatInstallerPort,
    InstalledCheatView,
)


class CheatType(Enum):
    GOLD = "gold"
    INFINITE = "infinite"
    SPEED = "speed"
    ITEMS = "items"
    UNLOCK = "unlock"
    STATS = "stats"
    OTHER = "other"

    @classmethod
    def _missing_(cls, value: object) -> CheatType:
        if isinstance(value, str):
            for member in cls:
                if member.value == value:
                    return member
        return cls.OTHER


@dataclass(frozen=True)
class CheatEntry:
    id: str
    title_id: str
    build_id: str | None
    name: str
    cheat_type: CheatType
    source: str
    source_url: str
    codes: tuple[str, ...]
    description: str | None
    author: str | None
    version: str | None


@dataclass(frozen=True)
class InstalledCheat:
    id: str
    game_id: str
    title_id: str
    build_id: str | None
    name: str
    cheat_type: CheatType
    source: str
    version: str | None
    state: str
    install_path: str | None
    emulator_id: str | None
    code_count: int
    enabled: bool
    codes: tuple[str, ...] = ()


_CHEAT_TYPES_FOR_TITLE = frozenset(
    {
        "gold",
        "infinite",
        "speed",
        "items",
        "unlock",
        "stats",
        "other",
    }
)
VALID_CHEAT_STATES = frozenset(
    {"discovered", "downloaded", "installed", "active", "inactive", "error"}
)

_ATMOSPHERE_CODE_RE = None


def validate_cheat_codes(codes: tuple[str, ...]) -> bool:
    """Valida um arquivo Atmosphere sem rejeitar cabeçalhos de seção.

    Linhas de código precisam conter ao menos dois grupos hexadecimais de oito
    dígitos. Comentários, linhas vazias e nomes ``[Cheat]`` são permitidos.
    """
    import re

    pattern = re.compile(r"^(?:[0-9a-fA-F]{8})(?:\s+[0-9a-fA-F]{8})+(?:\s+.*)?$")
    for line in codes:
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]") and len(stripped) > 2:
            continue
        if not pattern.match(stripped):
            return False
    return True


class CheatDatabasePort(Protocol):
    """Porta interna para persistência de cheats."""

    def save_installed_cheat(self, cheat: InstalledCheat) -> None: ...

    def remove_installed_cheat(self, cheat_id: str) -> bool: ...

    def list_installed(self, game_id: str) -> list[InstalledCheat]: ...

    def update_state(self, cheat_id: str, new_state: str) -> None: ...

    def update_enabled(self, cheat_id: str, enabled: bool) -> None: ...

    def get_by_id(self, cheat_id: str) -> InstalledCheat | None: ...


class SwitchCheatManager:
    """Fachada de domínio para gerenciamento de cheats.

    Depende de portas injetadas para catálogo, instalador e persistência.
    """

    def __init__(
        self,
        catalog: CheatCatalogPort,
        installer: CheatInstallerPort,
        db: CheatDatabasePort,
    ) -> None:
        self._catalog = catalog
        self._installer = installer
        self._db = db

    # --- Catalog search ------------------------------------------------------

    def list_candidates(self, title_id: str, build_id: str | None = None) -> list[CheatCandidate]:
        if build_id:
            return self._catalog.search_by_build_id(title_id, build_id)
        return self._catalog.search_by_title_id(title_id)

    def refresh_catalog(self) -> int:
        return self._catalog.refresh_catalog()

    # --- Install / lifecycle -------------------------------------------------

    def download_and_install(
        self,
        candidate: CheatCandidate,
        emulator_id: str,
        game_id: str,
    ) -> InstalledCheat:
        from uuid import uuid4

        install_path = self._installer.install(
            candidate.title_id,
            candidate.build_id,
            candidate.identity.name,
            candidate.codes,
            emulator_id,
        )

        cheat_id = str(uuid4())
        cheat = InstalledCheat(
            id=cheat_id,
            game_id=game_id,
            title_id=candidate.title_id,
            build_id=candidate.build_id,
            name=candidate.identity.name,
            cheat_type=CheatType(candidate.identity.cheat_type),
            source=candidate.identity.source,
            version=candidate.identity.version,
            state="installed",
            install_path=str(install_path),
            emulator_id=emulator_id,
            code_count=len(candidate.codes),
            enabled=False,
            codes=candidate.codes,
        )
        self._db.save_installed_cheat(cheat)
        return cheat

    def enable(self, cheat_id: str) -> bool:
        cheat = self._db.get_by_id(cheat_id)
        if cheat is None or cheat.build_id is None or cheat.emulator_id is None:
            return False
        ok = self._installer.enable(cheat.title_id, cheat.build_id, cheat.emulator_id)
        if ok:
            self._db.update_enabled(cheat_id, True)
            self._db.update_state(cheat_id, "active")
        return ok

    def disable(self, cheat_id: str) -> bool:
        cheat = self._db.get_by_id(cheat_id)
        if cheat is None or cheat.build_id is None or cheat.emulator_id is None:
            return False
        ok = self._installer.disable(cheat.title_id, cheat.build_id, cheat.emulator_id)
        if ok:
            self._db.update_enabled(cheat_id, False)
            self._db.update_state(cheat_id, "inactive")
        return ok

    def remove(self, cheat_id: str) -> bool:
        cheat = self._db.get_by_id(cheat_id)
        if cheat is None or cheat.build_id is None or cheat.emulator_id is None:
            return False
        ok = self._installer.remove(cheat.title_id, cheat.build_id, cheat.emulator_id)
        if ok:
            self._db.remove_installed_cheat(cheat_id)
        return ok

    def edit_codes(self, cheat_id: str, codes: tuple[str, ...]) -> bool:
        cheat = self._db.get_by_id(cheat_id)
        if cheat is None or cheat.build_id is None or cheat.emulator_id is None:
            return False
        if not validate_cheat_codes(codes):
            return False
        ok = self._installer.edit_codes(cheat.title_id, cheat.build_id, cheat.emulator_id, codes)
        if ok:
            updated = InstalledCheat(
                id=cheat.id,
                game_id=cheat.game_id,
                title_id=cheat.title_id,
                build_id=cheat.build_id,
                name=cheat.name,
                cheat_type=cheat.cheat_type,
                source=cheat.source,
                version=cheat.version,
                state=cheat.state,
                install_path=cheat.install_path,
                emulator_id=cheat.emulator_id,
                code_count=len(codes),
                enabled=cheat.enabled,
                codes=codes,
            )
            self._db.remove_installed_cheat(cheat_id)
            self._db.save_installed_cheat(updated)
        return ok

    def list_installed(self, game_id: str) -> list[InstalledCheat]:
        return self._db.list_installed(game_id)

    def list_installed_views(self, title_id: str, emulator_id: str) -> list[InstalledCheatView]:
        return self._installer.list_installed(title_id, emulator_id)

    def to_dict(self, cheat: InstalledCheat) -> dict[str, Any]:
        return {
            "id": cheat.id,
            "gameId": cheat.game_id,
            "titleId": cheat.title_id,
            "buildId": cheat.build_id,
            "name": cheat.name,
            "cheatType": cheat.cheat_type.value,
            "source": cheat.source,
            "version": cheat.version,
            "state": cheat.state,
            "installPath": cheat.install_path,
            "emulatorId": cheat.emulator_id,
            "codeCount": cheat.code_count,
            "enabled": cheat.enabled,
        }
