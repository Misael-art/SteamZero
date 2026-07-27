# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Porta única de lifecycle de componentes, roteada pelo tipo de fonte fixado.

O projeto tem dois executores especializados e ambos funcionam:

- ``AdapterEngine`` — fontes portáteis (AppImage, nativo), com digest obrigatório
  e transação sobre o payload;
- ``FlatpakExecutor`` — fontes Flatpak, com remote/ref/commit fixados e rollback
  do deployment.

O que faltava era a porta comum. ``AdapterEngine.plan_install`` recusava fonte
Flatpak com "executor Flatpak ainda não está habilitado" — apesar de o executor
existir, testado, ao lado. O efeito prático: oito dos treze emuladores declarados
usam Flatpak e nenhum podia ser instalado, mesmo com adapter, manifesto e fonte
fixada corretos.

Esta fachada não reimplementa nada. Ela lê a fonte preferida do manifesto e
entrega a operação ao executor que sabe conduzi-la, normalizando o formato de
status para que a UI não precise saber de qual executor a resposta veio.

O que NÃO muda: cada executor mantém suas garantias. Portátil continua exigindo
sha256; Flatpak continua exigindo commit fixado. Fonte sem a garantia da sua
família falha fechado, aqui como antes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from steamzero.adapters.registry import AdapterManifest, AdapterRegistry, AdapterSource
from steamzero.core.errors import SteamZeroError

#: Famílias de fonte com executor real. Fonte fora daqui não tem lifecycle e
#: precisa falhar fechado — habilitar ação para ela produziria botão que termina
#: em stub.
PORTABLE_SOURCES = frozenset({"appimage", "native"})
FLATPAK_SOURCES = frozenset({"flatpak"})


@dataclass(frozen=True)
class LifecycleRoute:
    """Para onde uma operação deste adapter deve ir, e por quê."""

    adapter_id: str
    source_type: str
    executor: str
    installable: bool
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapterId": self.adapter_id,
            "sourceType": self.source_type,
            "executor": self.executor,
            "installable": self.installable,
            "reason": self.reason,
        }


def _preferred(manifest: AdapterManifest, *, allow_eol: bool) -> AdapterSource | None:
    try:
        return manifest.preferred_source(None, allow_eol=allow_eol)
    except SteamZeroError:
        return None


def route_for(manifest: AdapterManifest) -> LifecycleRoute:
    """Decide o executor a partir da fonte fixada, sem executar nada.

    Read-only de propósito: a UI precisa saber se uma ação é aplicável antes de
    oferecê-la, e descobrir isso tentando instalar seria tarde demais.
    """
    source = _preferred(manifest, allow_eol=False)
    if source is None:
        eol = _preferred(manifest, allow_eol=True)
        if eol is not None:
            # Fonte existe mas está marcada como fim de vida: recusar é o
            # comportamento correto, e o motivo precisa ser dizível na UI.
            return LifecycleRoute(
                manifest.id,
                eol.type,
                "none",
                False,
                "a fonte fixada deste componente está marcada como fim de vida",
            )
        return LifecycleRoute(
            manifest.id, "", "none", False, "o componente não declara fonte instalável"
        )

    if source.type in FLATPAK_SOURCES:
        if not source.ref or not source.remote:
            return LifecycleRoute(
                manifest.id, source.type, "none", False, "fonte Flatpak sem ref ou remote fixados"
            )
        return LifecycleRoute(manifest.id, source.type, "flatpak", True)

    if source.type in PORTABLE_SOURCES:
        if not source.sha256:
            return LifecycleRoute(
                manifest.id, source.type, "none", False, "fonte portátil sem sha256"
            )
        return LifecycleRoute(manifest.id, source.type, "engine", True)

    return LifecycleRoute(
        manifest.id,
        source.type,
        "none",
        False,
        f"não há executor para fonte do tipo '{source.type}'",
    )


def routes_for(registry: AdapterRegistry) -> dict[str, LifecycleRoute]:
    """Rota de cada adapter declarado, para o read model publicar aplicabilidade."""
    return {manifest.id: route_for(manifest) for manifest in registry.list()}


def normalize_status(raw: dict[str, Any], route: LifecycleRoute) -> dict[str, Any]:
    """Formato único de status, venha do engine ou do executor Flatpak.

    Os dois publicam ``id`` e ``state``; o resto diverge (``version``/``sha256``
    de um lado, ``commit``/``remote`` do outro). A UI consome esta forma e não
    precisa saber quem respondeu.
    """
    state = str(raw.get("state", "unknown"))
    installed = state == "installed"
    version = raw.get("version") or raw.get("commit")
    return {
        "id": route.adapter_id,
        "state": state,
        "installed": installed,
        "installable": route.installable,
        "executor": route.executor,
        "sourceType": route.source_type,
        "version": str(version) if version else None,
        "origin": raw.get("origin"),
        "reason": route.reason,
        "endOfLife": bool(raw.get("endOfLife", False)),
    }


def unavailable_status(route: LifecycleRoute) -> dict[str, Any]:
    """Status de componente sem executor: declarado, não instalável, com motivo.

    Publicar ``unverified`` sem motivo é como a central passou a mostrar linhas
    mortas — o usuário vê uma plataforma listada e nenhuma explicação de por que
    nada acontece ao clicar.
    """
    return {
        "id": route.adapter_id,
        "state": "unavailable",
        "installed": False,
        "installable": False,
        "executor": route.executor,
        "sourceType": route.source_type,
        "version": None,
        "origin": None,
        "reason": route.reason,
        "endOfLife": False,
    }
