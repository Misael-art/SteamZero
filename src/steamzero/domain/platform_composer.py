# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Composição operacional de uma plataforma a partir dos registries.

``platform_placeholder`` projeta uma plataforma que ainda não foi composta: tudo
``unverified``, nada instalável, nenhum ícone e — o pior — **nenhum motivo**. O
usuário vê a linha e não descobre por que clicar não faz nada.

Este módulo compõe a mesma plataforma com verdade real: o executor de lifecycle
diz se é instalável e por quê, o manifesto do adapter diz nome e ícone, e o perfil
de launch diz se dá para jogar. Onde a informação não existe, o motivo aparece em
vez do silêncio.

O que NÃO acontece aqui: habilitar ação. Uma plataforma composta continua com
ações desabilitadas enquanto o caminho inteiro não for real — instalar, verificar
e lançar. Compor é dizer a verdade sobre o estado; habilitar é outra decisão, que
depende de o lifecycle estar completo.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from steamzero.domain.launch_profile import LaunchProfile, parse_launch
from steamzero.domain.platforms import PlatformManifest, platform_placeholder


@dataclass(frozen=True)
class EmulatorFacts:
    """O que se sabe de um emulador nesta plataforma, sem inventar nada."""

    adapter_id: str
    display_name: str | None = None
    icon_asset: str | None = None
    installable: bool = False
    installed: bool = False
    version: str | None = None
    reason: str | None = None


#: Como a UI deve ler cada combinação. A distinção entre "não instalado" e
#: "não instalável" importa: a primeira é um convite, a segunda é um impedimento
#: que precisa dizer sua causa.
def _emulator_state(facts: EmulatorFacts) -> tuple[str, str, str]:
    if facts.installed:
        return "ready", "Instalado", "installed"
    if facts.installable:
        return "unavailable", "Não instalado", "not-installed"
    return "unavailable", "Indisponível", "unverified"


def _launch_readiness(
    profile: LaunchProfile | None,
    *,
    installed: bool,
    core_present: bool | None,
    platform_label: str,
    adapter_id: str,
    bios_present: bool | None,
) -> tuple[bool, str | None]:
    """Se dá para jogar nesta plataforma, e o motivo quando não dá.

    ``core_present``/``bios_present`` são ``None`` quando a plataforma não exige
    core/BIOS ou quando ninguém leu o host — exigir de quem não usa, ou bloquear
    sem informação, produziria recusa falsa.
    """
    if profile is None:
        return False, "esta plataforma ainda não declara como lançar jogos"
    if not installed:
        return False, "o emulador desta plataforma não está instalado"
    if profile.requires_core and not core_present:
        return False, f"o core {profile.core} não está instalado no RetroArch"
    if profile.requires_bios and bios_present is False:
        # BIOS é conteúdo do próprio usuário: declaramos a exigência e a
        # verificamos pelo store central; nunca a obtemos nem baixamos. O
        # requisito faltante identifica plataforma e emulador afetados.
        return False, (
            f"a BIOS de {platform_label} · {adapter_id} está ausente "
            f"({', '.join(profile.requires_bios)}); importe o arquivo local"
        )
    return True, None


def _bios_presence(
    probe: Callable[[str, str, str], bool] | None,
    platform_id: str,
    adapter_id: str,
    names: tuple[str, ...],
) -> dict[str, bool] | None:
    """Presença de cada BIOS exigida no store central; ``None`` quando não lida.

    A falha de UMA sondagem degrada apenas este requisito (AGENTS.md §8): a
    ausência não pode ser provada, então o requisito sai como ausente — nunca
    derruba a composição da central.
    """
    if probe is None:
        return None
    result: dict[str, bool] = {}
    for name in names:
        try:
            result[name] = bool(probe(platform_id, adapter_id, name))
        except Exception:
            result[name] = False
    return result


def _bios_requirement(
    platform_label: str,
    adapter_id: str,
    names: tuple[str, ...],
    present: dict[str, bool] | None,
) -> dict[str, Any]:
    """Requisito BIOS no formato do contrato (mesmas seis chaves de keys).

    O dado parcial nunca degrada em silêncio: sem leitura o status é
    ``unverified`` com motivo; com leitura, ``missing``/``ok`` e o detail
    identifica plataforma e emulador afetados (REQUIREMENTS-E2E).
    """
    if present is None:
        return {
            "kind": "bios",
            "status": "unverified",
            "required": ", ".join(names),
            "installed": None,
            "detail": (
                f"BIOS de {platform_label} · {adapter_id} ainda não verificada neste contexto."
            ),
            "blocksPlay": False,
        }
    missing = [name for name in names if not present.get(name)]
    if missing:
        return {
            "kind": "bios",
            "status": "missing",
            "required": ", ".join(names),
            "installed": ", ".join(name for name in names if present.get(name)) or None,
            "detail": (
                f"BIOS de {platform_label} · {adapter_id} ausente: {', '.join(missing)}; "
                "importe o arquivo local."
            ),
            "blocksPlay": True,
            "importAction": "bios.import",
        }
    return {
        "kind": "bios",
        "status": "ok",
        "required": ", ".join(names),
        "installed": ", ".join(names),
        "detail": f"BIOS de {platform_label} · {adapter_id} presente e reconhecida.",
        "blocksPlay": False,
    }


def compose_platform(
    manifest: PlatformManifest,
    *,
    facts_for: Callable[[str], EmulatorFacts],
    core_present_for: Callable[[str], bool] | None = None,
    bios_present_for: Callable[[str, str, str], bool] | None = None,
) -> dict[str, Any]:
    """Compõe a plataforma sobre o placeholder, substituindo o que é sabido.

    Parte do placeholder de propósito: ele já produz a forma completa que o
    schema exige, e reescrever essa estrutura aqui criaria duas verdades sobre o
    mesmo contrato — o defeito que este trabalho existe para eliminar.

    ``bios_present_for`` responde ``(platform_id, adapter_id, nome) -> presente``
    para cada BIOS declarada no perfil de launch. Quem conhece o host é a camada
    de adapters; domínio só projeta.
    """
    payload = platform_placeholder(manifest)

    rows: list[dict[str, Any]] = []
    any_installed = False
    launchable = False
    launch_reason: str | None = None
    selected_primary = False
    primary_bios_names: tuple[str, ...] = ()
    primary_adapter_id: str | None = None
    primary_bios_present: dict[str, bool] | None = None

    declared = sorted(manifest.emulators, key=lambda item: item["precedence"])
    for emulator in declared:
        adapter_id = str(emulator["adapterId"])
        # A falha de UM adapter degrada apenas as plataformas dele. Deixar a
        # exceção subir derrubaria a central inteira por causa de um componente
        # que não respondeu — degradação pior que a informação faltante
        # (AGENTS.md §8).
        try:
            facts = facts_for(adapter_id)
        except Exception:
            facts = EmulatorFacts(
                adapter_id=adapter_id,
                display_name=str(emulator["name"]),
                reason="não foi possível consultar este componente agora",
            )
        state, status_label, install_state = _emulator_state(facts)
        any_installed = any_installed or facts.installed

        try:
            profile = parse_launch(
                manifest.id,
                adapter_id,
                emulator.get("launch"),
                systems=manifest.systems,
            )
        except Exception:
            # Perfil de launch malformado invalida o lançamento desta plataforma,
            # não a listagem dela nem as demais.
            profile = None
        core_present: bool | None = None
        system_core_presence: dict[str, bool] = {}
        if profile is not None and profile.requires_core and core_present_for is not None:
            # Não usar `all(generator)`: o curto-circuito esconderia os demais
            # cores ausentes e faria a sessão parecer mais pronta do que o
            # diagnóstico realmente conseguiu verificar.
            core_presence = {core: core_present_for(core) for core in profile.required_cores}
            system_core_presence = {
                system: core_presence[core]
                for system, core in profile.system_cores
                if core in core_presence
            }
            default_core = profile.core_for_system(None)
            core_present = (
                core_presence.get(default_core)
                if default_core is not None
                else all(core_presence.values())
            )

        row = {
            "id": adapter_id,
            "displayName": facts.display_name or str(emulator["name"]),
            "name": facts.display_name or str(emulator["name"]),
            "platform": manifest.id,
            "state": state,
            "statusLabel": status_label,
            "installState": install_state,
            "sourceState": "verified" if facts.installable else "unverified",
            "installable": facts.installable,
            "capabilities": [],
            "adapterId": adapter_id,
            "precedence": emulator["precedence"],
            "role": emulator["role"],
            "reason": facts.reason,
        }
        if facts.icon_asset:
            row["iconAsset"] = facts.icon_asset
        if facts.version:
            row["version"] = facts.version
        if profile is not None:
            row["launch"] = profile.to_dict()
            if profile.requires_core:
                row["coreInstalled"] = bool(core_present)
                if profile.system_cores:
                    row["systemCoreInstalled"] = system_core_presence
            if profile.requires_bios:
                row["biosRequired"] = list(profile.requires_bios)
                bios_present = _bios_presence(
                    bios_present_for, manifest.id, adapter_id, profile.requires_bios
                )
                if bios_present is not None:
                    row["biosPresent"] = bios_present

        # A primeira linha INSTALADA por precedência define o emulador padrão.
        # Antes a primeira linha do manifesto definia a jogabilidade mesmo
        # quando estava ausente; assim um fallback instalado não aparecia como
        # primário e a sessão mostrava "Nenhum emulador definido" apesar de
        # haver runtime, core e ROMs disponíveis.
        if not selected_primary and facts.installed:
            selected_primary = True
            primary_adapter_id = adapter_id
            primary_bios_names = profile.requires_bios if profile is not None else ()
            primary_bios_present = (
                _bios_presence(bios_present_for, manifest.id, adapter_id, profile.requires_bios)
                if profile is not None and profile.requires_bios
                else None
            )
            launchable, launch_reason = _launch_readiness(
                profile,
                installed=facts.installed,
                core_present=core_present,
                platform_label=manifest.name,
                adapter_id=adapter_id,
                bios_present=(
                    None if primary_bios_present is None else all(primary_bios_present.values())
                ),
            )
        rows.append(row)

    primary_row = next(
        (row for row in rows if row.get("installState") in {"installed", "degraded"}),
        None,
    )
    payload["defaultEmulatorId"] = primary_row["id"] if primary_row else None
    payload["primaryEmulator"] = {
        "id": primary_row["id"] if primary_row else None,
        "name": str(primary_row["name"]) if primary_row else "",
        "state": str(primary_row["state"]) if primary_row else "unavailable",
        "statusLabel": (
            str(primary_row["statusLabel"]) if primary_row else "Nenhum emulador instalado"
        ),
        "source": "precedence" if primary_row else "none",
    }

    if not rows:
        # Plataforma sem emulador declarado. É o caso das de nuvem, que não são
        # emuladas: sem este ramo o laço acima nunca roda e a plataforma sairia
        # não-lançável SEM MOTIVO — exatamente a linha morta que este composer
        # existe para eliminar.
        launch_reason = (
            "esta plataforma é de streaming e não usa emulador local"
            if manifest.kind == "cloud"
            else "esta plataforma ainda não declara emulador"
        )
    elif not selected_primary:
        # Há emuladores declarados, mas nenhum runtime instalado. A plataforma
        # precisa continuar explicando o bloqueio mesmo depois de publicar o
        # estado explícito de ``primaryEmulator`` como ``none``.
        launch_reason = "o emulador desta plataforma não está instalado"

    payload["emulators"] = rows
    payload["launchable"] = launchable
    payload["launchReason"] = launch_reason

    if primary_bios_names and primary_adapter_id is not None:
        payload["requirements"]["bios"] = _bios_requirement(
            manifest.name,
            primary_adapter_id,
            primary_bios_names,
            primary_bios_present,
        )

    if any_installed:
        payload["state"] = "unverified" if not launchable else "ready"
        payload["statusLabel"] = "Pronto" if launchable else "Verificação pendente"
        blockers = [] if launchable else [launch_reason or "verificação pendente"]
        payload["readiness"] = {
            "percent": 100 if launchable else 45,
            "title": payload["statusLabel"],
            "detail": launch_reason or "Ambiente pronto para uso.",
            "blockers": blockers,
        }
    elif launch_reason is not None:
        # Sem emulador instalado a plataforma continua planejada, mas o motivo
        # deixa de ser genérico: diz o que falta, não apenas que falta algo.
        payload["readiness"] = {
            "percent": 0,
            "title": "Integração pendente",
            "detail": launch_reason,
            "blockers": [launch_reason],
        }
    return payload


def facts_from_status(
    adapter_id: str,
    status: Mapping[str, Any] | None,
    presentation: Mapping[str, str] | None,
) -> EmulatorFacts:
    """Traduz o status normalizado do lifecycle para os fatos da composição."""
    if status is None:
        return EmulatorFacts(
            adapter_id=adapter_id,
            display_name=(presentation or {}).get("displayName"),
            icon_asset=(presentation or {}).get("iconAsset"),
            reason="componente não declarado no registry de adapters",
        )
    return EmulatorFacts(
        adapter_id=adapter_id,
        display_name=(presentation or {}).get("displayName"),
        icon_asset=(presentation or {}).get("iconAsset"),
        installable=bool(status.get("installable")),
        installed=bool(status.get("installed")),
        version=status.get("version"),
        reason=status.get("reason"),
    )
