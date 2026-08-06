# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Read model versionado da central de emulação (WI-9).

O builder é deliberadamente orientado a dados: QML não precisa conhecer nomes
de emulador, áreas ou regras de prontidão. Falhas de probes são convertidas em
``unverified`` e o restante da central continua navegável.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from steamzero.api import contracts
from steamzero.domain.canonical_experiences import CanonicalExperienceRegistry
from steamzero.domain.keys_firmware import RequirementCheck
from steamzero.domain.platform_composer import EmulatorFacts, compose_platform
from steamzero.domain.platforms import (
    PlatformManifest,
    PlatformRegistry,
    platform_placeholder,
)
from steamzero.domain.retro_experience import preset_catalog
from steamzero.domain.switch_emulators import SwitchEmulatorCatalog

_SCOPE_DEFS = (
    ("global", "Global", "globe"),
    ("emulator", "Emulador", "emulator"),
    ("game", "Por jogo", "gamepad"),
    ("handheld", "Portátil", "handheld"),
    ("dock", "Dock", "dock"),
)


def _project_platform(
    manifest: PlatformManifest,
    emulator_facts: Callable[[str], EmulatorFacts] | None,
    core_present: Callable[[str], bool] | None,
    bios_present: Callable[[str, str, str], bool] | None,
) -> dict[str, Any]:
    """Compõe a plataforma quando há fatos reais; senão, projeta o placeholder.

    Os fatos vêm INJETADOS porque quem os conhece é a camada de adapters — o
    executor de lifecycle, a busca de core no host e o store central de BIOS.
    Domínio não importa adapters (fronteira BND-DOMAIN-ADAPTER), então a
    dependência é invertida.

    Sem fatos, o placeholder continua sendo a resposta honesta: significa que
    ninguém consultou o host, não que a plataforma esteja indisponível.
    """
    if emulator_facts is None:
        return platform_placeholder(manifest)
    return compose_platform(
        manifest,
        facts_for=emulator_facts,
        core_present_for=core_present,
        bios_present_for=bios_present,
    )


def build_global_management(
    *,
    platforms: Sequence[Mapping[str, Any]],
    editorial_platforms: Sequence[Mapping[str, Any]],
    canonical_experiences: Sequence[Mapping[str, Any]],
    truth_state: str,
    emulators: Sequence[Mapping[str, Any]],
    directories: Sequence[Mapping[str, Any]],
    media_providers: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Resume a gestão transversal sem transformá-la em uma plataforma.

    A central abre nesta superfície. Ela não reutiliza a primeira plataforma do
    registry como um atalho visual: cada card conserva o contrato técnico da
    própria plataforma e as experiências editoriais continuam uma dimensão
    separada. Steam é publicado como origem editorial adicional, não como uma
    trigésima-sétima plataforma técnica.
    """
    games_by_platform = {
        str(item.get("id")): len(item.get("games", ())) for item in editorial_platforms
    }
    cards: list[dict[str, Any]] = []
    for platform in platforms:
        requirements = platform.get("requirements", {})
        emulator_rows = platform.get("emulators", ())
        runtimes = [
            str(row.get("name") or row.get("displayName"))
            for row in emulator_rows
            if row.get("name") or row.get("displayName")
        ]
        cores = [
            str((row.get("launch") or {}).get("core"))
            for row in emulator_rows
            if (row.get("launch") or {}).get("core")
        ]
        blockers = list((platform.get("readiness") or {}).get("blockers") or ())
        blocker = str(platform.get("launchReason") or (blockers[0] if blockers else ""))
        cards.append(
            {
                "id": str(platform["id"]),
                "name": str(platform["name"]),
                "identity": str(platform.get("kind") or "emulated"),
                "gameCount": games_by_platform.get(str(platform["id"]), 0),
                "state": str(platform["state"]),
                "readiness": dict(platform["readiness"]),
                "runtime": ", ".join(runtimes) or "Nenhum runtime declarado",
                "coreRequired": cores,
                "keysStatus": dict(requirements.get("keys") or {}),
                "firmwareStatus": dict(requirements.get("firmware") or {}),
                "biosStatus": (dict(requirements["bios"]) if requirements.get("bios") else None),
                "blocker": blocker or None,
                "action": {
                    "id": "platform.open",
                    "label": "Abrir plataforma",
                    "enabled": True,
                    "reason": None,
                    "requiresConfirmation": False,
                },
            }
        )
    technical_count = len(platforms)
    return {
        "id": "emulation-global",
        "name": "Gestão geral",
        "iconKey": "applications-games",
        "state": truth_state,
        "statusLabel": "Estado consolidado das plataformas e componentes",
        "technicalPlatformCount": technical_count,
        "editorialDestinationCount": technical_count + 1,
        "editorialExperienceCount": len(canonical_experiences),
        "editorialSource": {
            "id": "steam",
            "name": "Steam",
            "detail": "Origem editorial adicional; não integra a contagem técnica.",
        },
        "platformCards": cards,
        "emulators": [dict(item) for item in emulators],
        "directories": [dict(item) for item in directories],
        "mediaProviders": [dict(item) for item in media_providers],
    }


def build_switch_workspace(
    *,
    catalog: SwitchEmulatorCatalog | None = None,
    probe: Any = None,
    keys: RequirementCheck | Mapping[str, Any] | None = None,
    firmware: RequirementCheck | Mapping[str, Any] | None = None,
    games: Sequence[Mapping[str, Any]] = (),
    emulator_capabilities: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    platform_registry: PlatformRegistry | None = None,
    selected_scope: str = "global",
    selected_area: str = "overview",
    emulator_facts: Callable[[str], EmulatorFacts] | None = None,
    core_present: Callable[[str], bool] | None = None,
    bios_present: Callable[[str, str, str], bool] | None = None,
) -> dict[str, Any]:
    """Compõe o snapshot Switch e valida o próprio contrato antes de retornar."""
    registry = platform_registry or PlatformRegistry.bundled()
    switch_manifest = registry.get("switch")
    valid_scopes = {item[0] for item in _SCOPE_DEFS}
    valid_areas = {str(item["id"]) for item in switch_manifest.areas}
    if selected_scope not in valid_scopes:
        selected_scope = "global"
    if selected_area not in valid_areas:
        selected_area = "overview"

    requirements = {
        "keys": _requirement_payload("keys", keys),
        "firmware": _requirement_payload("firmware", firmware),
    }
    emulators = _emulator_rows(catalog or SwitchEmulatorCatalog(), probe, emulator_capabilities)
    game_rows = [dict(game) for game in games]
    state, status_label, readiness = compute_readiness(requirements, emulators)
    areas = _areas(requirements, state, switch_manifest)
    area_data = _area_data(requirements, emulators, game_rows)
    area_data = {str(area["id"]): area_data[str(area["id"])] for area in switch_manifest.areas}
    switch_platform = {
        "id": switch_manifest.id,
        "kind": switch_manifest.kind,
        "name": switch_manifest.name,
        "shortName": switch_manifest.short_name,
        "iconKey": switch_manifest.icon_key,
        "state": state,
        "statusLabel": status_label,
        "readiness": readiness,
        "scopes": [
            {
                "id": scope_id,
                "label": label,
                "iconKey": icon,
                "enabled": True,
                "reason": None,
            }
            for scope_id, label, icon in _SCOPE_DEFS
        ],
        "selectedScope": selected_scope,
        "areas": areas,
        "selectedArea": selected_area,
        "emulators": emulators,
        "games": game_rows,
        "requirements": requirements,
        "fallbackArtworkAsset": switch_manifest.artwork_asset,
        "capabilities": [
            {
                "id": item["id"],
                "label": item["label"],
                "state": item["state"],
                "detail": item["detail"],
            }
            for item in switch_manifest.capabilities
        ],
        "media": dict(switch_manifest.media),
        "controls": dict(switch_manifest.controls),
        "timing": dict(switch_manifest.timing),
        "presets": [dict(item) for item in switch_manifest.presets],
        "cloud": None,
        "areaData": area_data,
    }
    payload = {
        "schemaVersion": 1,
        "truthState": state,
        "contextLabel": f"{switch_manifest.name} · {_scope_label(selected_scope)}",
        "retroExperience": preset_catalog(),
        "canonicalExperiences": CanonicalExperienceRegistry.bundled().project(),
        "platforms": [
            switch_platform,
            *[
                _project_platform(manifest, emulator_facts, core_present, bios_present)
                for manifest in registry.list()
                if manifest.id != "switch"
            ],
        ],
    }
    contracts.validate(payload, "emulation-workspace-v1.schema.json")
    return payload


def _scope_label(scope_id: str) -> str:
    return next(label for current, label, _icon in _SCOPE_DEFS if current == scope_id)


def _requirement_payload(
    kind: str, value: RequirementCheck | Mapping[str, Any] | None
) -> dict[str, Any]:
    if isinstance(value, RequirementCheck):
        return value.to_dict()
    if isinstance(value, Mapping):
        candidate = dict(value)
        expected = {"kind", "status", "required", "installed", "detail", "blocksPlay"}
        if expected.issubset(candidate):
            normalized = {key: candidate[key] for key in expected}
            # A posição no contrato é autoritativa; nunca aceite firmware
            # rotulado como keys (ou vice-versa) por um produtor defeituoso.
            normalized["kind"] = kind
            return normalized
        # G24: dado parcial gera diagnóstico, não degrada silenciosamente. O
        # valor informado é preservado (visível na UI), o status é honesto
        # (parcial não é confiável) e o detail nomeia exatamente o que falta —
        # o usuário distingue "faltou informação" de "sumiu".
        missing = sorted(expected - set(candidate))
        label = "Keys" if kind == "keys" else "Firmware"
        return {
            "kind": kind,
            "status": "unverified",
            "required": candidate.get("required"),
            "installed": candidate.get("installed"),
            "detail": (
                f"{label} parcial: faltam {', '.join(missing)}. O valor informado "
                "foi preservado, mas não é confiável; nenhuma ação será tomada "
                "sobre ele."
            ),
            "blocksPlay": False,
        }
    label = "Keys" if kind == "keys" else "Firmware"
    return {
        "kind": kind,
        "status": "unverified",
        "required": None,
        "installed": None,
        "detail": f"{label} ainda não verificado neste contexto.",
        "blocksPlay": False,
    }


def _emulator_rows(
    catalog: SwitchEmulatorCatalog,
    probe: Any,
    capability_map: Mapping[str, Sequence[Mapping[str, Any]]] | None,
) -> list[dict[str, Any]]:
    try:
        rows = catalog.availability(probe=probe)
    except Exception:
        rows = catalog.availability(probe=None)
    capability_map = capability_map or {}
    output: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        install_state = str(row.get("installState", "unverified"))
        if install_state == "installed":
            state, status_label = "ready", "Instalado"
        elif install_state == "degraded":
            # G27: degradado nunca colapsa em "não instalado" — arquivos existem
            # e o motivo do drift vem preservado para a UI oferecer "Reparar".
            state, status_label = "attention", "Reparar"
        elif install_state == "not-installed":
            state, status_label = "unavailable", "Não instalado"
        else:
            state, status_label = "unverified", "Não verificado"
        row.update(
            {
                "name": row["displayName"],
                "state": state,
                "statusLabel": status_label,
                "capabilities": [dict(item) for item in capability_map.get(row["id"], ())],
            }
        )
        output.append(row)
    return output


def compute_readiness(
    requirements: Mapping[str, Mapping[str, Any]], emulators: Sequence[Mapping[str, Any]]
) -> tuple[str, str, dict[str, Any]]:
    """Prontidão global a partir das linhas reais (inclui ``degraded``).

    Pública porque o controller recomputa com as linhas observadas do host:
    o probe do catálogo só sabe "instalado ou não", e um emulador degradado
    silencioso produziria 100% mesmo com drift.
    """
    blockers: list[str] = []
    requirement_states = {str(value["status"]) for value in requirements.values()}
    if "missing" in requirement_states:
        blockers.append("Importe keys e firmware próprios antes de iniciar jogos que os exigem.")
    if "outdated" in requirement_states:
        blockers.append(
            "Atualize keys ou firmware para atender aos requisitos do jogo selecionado."
        )
    if "unverified" in requirement_states:
        blockers.append("Valide keys e firmware para concluir o diagnóstico de compatibilidade.")
    if not any(item.get("installState") in {"installed", "degraded"} for item in emulators):
        blockers.append("Nenhum emulador Switch foi confirmado como instalado.")
    if any(item.get("installState") == "degraded" for item in emulators):
        blockers.append("Repare emuladores degradados antes de iniciar jogos.")

    if "missing" in requirement_states:
        state, label, percent = "blocked", "Ação necessária", 20
    elif "outdated" in requirement_states or any(
        item.get("installState") == "degraded" for item in emulators
    ):
        state, label, percent = "attention", "Atualização recomendada", 45
    elif blockers:
        state, label, percent = "unverified", "Verificação pendente", 35
    else:
        state, label, percent = "ready", "Pronto", 100
    return (
        state,
        label,
        {
            "percent": percent,
            "title": label,
            "detail": "Ambiente pronto para uso." if not blockers else blockers[0],
            "blockers": blockers,
        },
    )


def _areas(
    requirements: Mapping[str, Mapping[str, Any]],
    platform_state: str,
    manifest: PlatformManifest,
) -> list[dict[str, Any]]:
    requirement_states = {str(value["status"]) for value in requirements.values()}
    if "missing" in requirement_states:
        requirement_state, requirement_label = "blocked", "Importação necessária"
    elif "outdated" in requirement_states:
        requirement_state, requirement_label = "attention", "Atualização necessária"
    elif requirement_states == {"ok"}:
        requirement_state, requirement_label = "ready", "Compatível"
    else:
        requirement_state, requirement_label = "unverified", "Não verificado"

    rows: list[dict[str, Any]] = []
    capabilities = {item["id"]: item for item in manifest.capabilities}
    for declared in manifest.areas:
        area_id = str(declared["id"])
        capability = capabilities[declared["capabilityId"]]
        if area_id == "overview":
            state, status = platform_state, "Resumo do ambiente"
        elif area_id == "keysFirmware":
            state, status = requirement_state, requirement_label
        else:
            declared_state = str(capability["state"])
            state = "unverified" if declared_state == "ready" else declared_state
            status = {
                "ready": "Verificação pendente",
                "planned": "Planejado",
                "unavailable": "Indisponível",
            }[declared_state]
        rows.append(
            {
                "id": area_id,
                "label": declared["label"],
                "iconKey": declared["iconKey"],
                "state": state,
                "statusLabel": status,
                "badge": None,
            }
        )
    return rows


def _action(
    action_id: str,
    label: str,
    *,
    enabled: bool,
    reason: str | None = None,
    confirmation: bool = False,
) -> dict[str, Any]:
    return {
        "id": action_id,
        "label": label,
        "enabled": enabled,
        "reason": reason,
        "requiresConfirmation": confirmation,
    }


def _card(
    card_id: str,
    title: str,
    detail: str,
    state: str,
    status_label: str,
    *,
    action: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    result = {
        "id": card_id,
        "title": title,
        "detail": detail,
        "state": state,
        "statusLabel": status_label,
        **extra,
    }
    if action is not None:
        result["action"] = action
    return result


def _area_data(
    requirements: Mapping[str, Mapping[str, Any]],
    emulators: Sequence[Mapping[str, Any]],
    games: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    keys = requirements["keys"]
    firmware = requirements["firmware"]
    requirement_cards = [
        _card(
            "keys",
            "Keys",
            str(keys["detail"]),
            _requirement_state(str(keys["status"])),
            _requirement_label(str(keys["status"])),
            action=_action(
                "keys.import",
                "Importar keys",
                enabled=False,
                reason="Importação pela interface ainda não está conectada ao serviço.",
                confirmation=True,
            ),
            installed=keys["installed"],
            required=keys["required"],
        ),
        _card(
            "firmware",
            "Firmware",
            str(firmware["detail"]),
            _requirement_state(str(firmware["status"])),
            _requirement_label(str(firmware["status"])),
            action=_action(
                "firmware.import",
                "Importar firmware",
                enabled=False,
                reason="Importação pela interface ainda não está conectada ao serviço.",
                confirmation=True,
            ),
            installed=firmware["installed"],
            required=firmware["required"],
        ),
    ]
    planned = _action(
        "feature.planned",
        "Em desenvolvimento",
        enabled=False,
        reason="Capacidade ainda não exposta pelo backend.",
    )
    area_data: dict[str, Any] = {
        "overview": {
            "cards": [
                _card(
                    "emulators",
                    "Emuladores",
                    f"{len(emulators)} opções catalogadas com disponibilidade verificável.",
                    "unverified",
                    "Verifique no host",
                    count=len(emulators),
                ),
                _card(
                    "games",
                    "Biblioteca Switch",
                    f"{len(games)} jogos identificados neste contexto.",
                    "ready" if games else "unverified",
                    f"{len(games)} jogos" if games else "Nenhum jogo indexado",
                    count=len(games),
                ),
            ],
            "primaryAction": _action(
                "emulation.refresh",
                "Verificar ambiente",
                enabled=True,
            ),
        },
        "keysFirmware": {
            "cards": requirement_cards,
            "primaryAction": _action(
                "requirements.verify",
                "Validar requisitos",
                enabled=False,
                reason="Validação pela interface ainda não está conectada ao serviço.",
            ),
        },
    }
    labels = {
        "updatesDlc": ("Updates & DLC", "Instale, ative e audite conteúdo do próprio usuário."),
        "modsCheats": (
            "Mods & cheats",
            "Conteúdo local associado ao Title ID, Build ID e emulador do jogo.",
        ),
        "graphicsPerformance": (
            "Gráficos & desempenho",
            "Perfis por jogo, dock/portátil e frame generation.",
        ),
        "controls": ("Controles", "Mapeamento automático para até quatro jogadores."),
        "saves": ("Saves", "Backup e migração segura entre emuladores."),
        "shaderCache": ("Shader cache", "Backup, restauração e invalidação compatível."),
        "media": ("Mídia", "Capas, imagens e vídeos da biblioteca."),
        "storage": ("Armazenamento", "Deduplicação de conteúdo compartilhado."),
        "advanced": ("Avançado", "Configuração especializada com preview e rollback."),
    }
    for area_id, (title, detail) in labels.items():
        state = "attention" if area_id == "advanced" else "planned"
        status = "Uso especializado" if area_id == "advanced" else "Planejado"
        area_data[area_id] = {
            "cards": [_card(area_id, title, detail, state, status)],
            "primaryAction": planned,
        }
    return area_data


def _requirement_state(status: str) -> str:
    return {
        "ok": "ready",
        "outdated": "attention",
        "missing": "blocked",
        "not-required": "ready",
        "unverified": "unverified",
    }.get(status, "unverified")


def _requirement_label(status: str) -> str:
    return {
        "ok": "Compatível",
        "outdated": "Desatualizado",
        "missing": "Ausente",
        "not-required": "Não exigido",
        "unverified": "Não verificado",
    }.get(status, "Não verificado")
