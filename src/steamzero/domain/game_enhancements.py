# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Melhorias por jogo, agnósticas de plataforma.

``GameEnhancementManager`` é a fachada de domínio única para mods e cheats:
lê as mesmas tabelas já persistidas pelos donos Switch (nunca cria um segundo
armazenamento), resolve o papel do provedor pela declaração no manifesto do
adapter e aplica o invariante anti-cheat em qualquer entrada de instalação.

Contratos imutáveis desta camada:

- papel do provedor: ``steamzero-supplied`` (SteamZero escreve o arquivo de
  melhoria e carrega o marcador de ownership) ou ``emulator-supplied`` (o
  emulador é dono do arquivo; SteamZero apenas alterna, nunca copia assets);
- invariante anti-cheat: whitelist técnica x blacklist de gameplay, com nega
  padrão; categoria desconhecida ou proveniência ausente nunca passam;
- negação acontece no limite do domínio (``assert_allowed``), antes de
  qualquer plano de instalação ser formado.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from steamzero.core.errors import SteamZeroError
from steamzero.domain.game_identity import GameIdentity
from steamzero.domain.switch_cheats import CheatDatabasePort
from steamzero.domain.switch_mods import ModDatabasePort
from steamzero.ports import (
    CheatCandidate,
    CheatCatalogPort,
    ModCandidate,
    ModCatalogPort,
)


class EnhancementKind(StrEnum):
    MOD = "mod"
    CHEAT = "cheat"


class ProviderRole(StrEnum):
    STEAMZERO_SUPPLIED = "steamzero-supplied"
    EMULATOR_SUPPLIED = "emulator-supplied"


class ProviderNotDeclaredError(SteamZeroError):
    """O papel do provedor não foi declarado no manifesto do adapter."""


TECHNICAL_WHITELIST = frozenset({"quality-of-life", "display-only", "performance", "graphics"})
GAMEPLAY_BLACKLIST = frozenset({"gameplay", "unlock", "speedhack", "invincibility", "currency"})
MANIFEST_FORM_KINDS = frozenset({"mod", "cheat"})


def resolve_provider_role(manifest: Any, kind: EnhancementKind) -> ProviderRole:
    """Papel declarado no manifesto do adapter; ausência = steamzero-supplied.

    A declaração é por emulador e por formato: ``enhancements.supplied`` lista
    os kinds que o próprio emulador fornece (caso em que o SteamZero não
    escreve nada). Qualquer outro kind ou manifesto sem a seção é tratado como
    SteamZero que escreve e marca.
    """
    if not isinstance(manifest, dict):
        return ProviderRole.STEAMZERO_SUPPLIED
    enhancements = manifest.get("enhancements")
    if not isinstance(enhancements, dict):
        return ProviderRole.STEAMZERO_SUPPLIED
    supplied = enhancements.get("supplied")
    if not isinstance(supplied, list):
        return ProviderRole.STEAMZERO_SUPPLIED
    if kind.value in supplied:
        return ProviderRole.EMULATOR_SUPPLIED
    return ProviderRole.STEAMZERO_SUPPLIED


@dataclass(frozen=True)
class EnhancementDecision:
    allowed: bool
    reason: str | None = None


def policy_decision(
    kind: EnhancementKind,
    category: str,
    *,
    role: ProviderRole,
    source: str | None,
) -> EnhancementDecision:
    """Invariante anti-cheat: nega por padrão.

    - categoria de gameplay ou categoria desconhecida: nega;
    - categoria técnica (whitelist): permite, desde que com proveniência;
    - papel ``emulator-supplied``: o emulador é dono do arquivo; o SteamZero
      só alterna, então a decisão é de caratê informativo e não bloqueia
      alternância (a escrita é responsabilidade do emulador).
    """
    if role is ProviderRole.EMULATOR_SUPPLIED:
        return EnhancementDecision(True)
    if not source:
        return EnhancementDecision(False, "proveniência obrigatória ausente")
    if category in GAMEPLAY_BLACKLIST:
        return EnhancementDecision(False, f"categoria proibida: {category}")
    if category in TECHNICAL_WHITELIST:
        return EnhancementDecision(True)
    return EnhancementDecision(False, f"categoria não reconhecida: {category}")


@dataclass(frozen=True)
class InstalledEnhancementView:
    kind: EnhancementKind
    enhancement_id: str
    game_id: str
    name: str
    category: str
    role: ProviderRole
    state: str
    emulator_id: str | None
    install_path: str | None
    source: str | None


@dataclass(frozen=True)
class EnhancementCandidate:
    kind: EnhancementKind
    identity: str
    name: str
    category: str
    source: str
    version: str | None
    build_id: str | None
    match_confidence: float


class EnhancementStorePort(Protocol):
    """Vista unificada de persistência de melhorias.

    Implementações existentes (StateStoreModsAdapter / StateStoreCheatsAdapter)
    servem esta porta sem duplicar tabelas.
    """

    def list_installed(self, game_id: str, kind: EnhancementKind) -> list[Any]: ...

    def list_catalog(self, title_id: str, kind: EnhancementKind) -> list[Any]: ...


@dataclass(frozen=True)
class GameEnhancementManager:
    """Fachada única de melhorias por jogo, parametrizada por identidade.

    Não faz I/O próprio: delega para os catálogos e armazenamentos existentes
    (Mod/Cheat do Switch) e adiciona a camada de política e de papel do
    provedor. ``game_selector`` traduz identidade -> id do jogo no
    armazenamento; retorna ``None`` quando o jogo não é gerenciável.
    """

    mod_catalog: ModCatalogPort
    mod_store: ModDatabasePort
    cheat_catalog: CheatCatalogPort
    cheat_store: CheatDatabasePort
    game_selector: Callable[[GameIdentity], str | None]
    role_resolver: Callable[[EnhancementKind], ProviderRole] = lambda _kind: (
        ProviderRole.STEAMZERO_SUPPLIED
    )

    def list_enhancements(
        self, identity: GameIdentity, *, emulator_id: str | None = None
    ) -> list[InstalledEnhancementView]:
        game_id = self.game_selector(identity)
        if game_id is None:
            return []
        rows: list[InstalledEnhancementView] = []
        for mod in self.mod_store.list_installed(game_id):
            rows.append(
                InstalledEnhancementView(
                    kind=EnhancementKind.MOD,
                    enhancement_id=mod.id,
                    game_id=mod.game_id,
                    name=mod.name,
                    category=mod.mod_type.value,
                    role=self.role_resolver(EnhancementKind.MOD),
                    state=mod.state,
                    emulator_id=mod.emulator_id,
                    install_path=mod.install_path,
                    source=mod.source,
                )
            )
        for cheat in self.cheat_store.list_installed(game_id):
            rows.append(
                InstalledEnhancementView(
                    kind=EnhancementKind.CHEAT,
                    enhancement_id=cheat.id,
                    game_id=cheat.game_id,
                    name=cheat.name,
                    category=cheat.cheat_type.value,
                    role=self.role_resolver(EnhancementKind.CHEAT),
                    state=cheat.state,
                    emulator_id=cheat.emulator_id,
                    install_path=cheat.install_path,
                    source=cheat.source,
                )
            )
        if emulator_id is not None:
            rows = [row for row in rows if row.emulator_id == emulator_id]
        return rows

    def list_candidates(
        self,
        identity: GameIdentity,
        kind: EnhancementKind,
        build_id: str | None = None,
    ) -> list[EnhancementCandidate]:
        title_id = identity.value
        if kind is EnhancementKind.MOD:
            raw: list[ModCandidate] = (
                self.mod_catalog.search_by_build_id(title_id, build_id)
                if build_id
                else self.mod_catalog.search_by_title_id(title_id)
            )
            return [
                EnhancementCandidate(
                    kind=kind,
                    identity=c.identity.name,
                    name=c.identity.name,
                    category=c.identity.mod_type,
                    source=c.identity.source,
                    version=c.identity.version,
                    build_id=c.build_id,
                    match_confidence=c.match_confidence,
                )
                for c in raw
            ]
        raw_cheats: list[CheatCandidate] = (
            self.cheat_catalog.search_by_build_id(title_id, build_id)
            if build_id
            else self.cheat_catalog.search_by_title_id(title_id)
        )
        return [
            EnhancementCandidate(
                kind=kind,
                identity=c.identity.name,
                name=c.identity.name,
                category="cheat",
                source=c.identity.source,
                version=c.identity.version,
                build_id=c.build_id,
                match_confidence=c.match_confidence,
            )
            for c in raw_cheats
        ]

    def assert_allowed(
        self,
        kind: EnhancementKind,
        category: str,
        *,
        role: ProviderRole,
        source: str | None,
    ) -> None:
        """Negação padrão no limite do domínio; bloqueia planos de instalação."""
        decision = policy_decision(kind, category, role=role, source=source)
        if not decision.allowed:
            raise SteamZeroError(
                "E-ENHANCEMENT-DENIED",
                detail=f"melhoria negada pelo invariante anti-cheat: {decision.reason}",
            )
