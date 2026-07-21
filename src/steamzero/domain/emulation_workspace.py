# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Read model versionado da central de emulação (WI-9).

O builder é deliberadamente orientado a dados: QML não precisa conhecer nomes
de emulador, áreas ou regras de prontidão. Falhas de probes são convertidas em
``unverified`` e o restante da central continua navegável.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from steamzero.api import contracts
from steamzero.domain.keys_firmware import RequirementCheck
from steamzero.domain.switch_emulators import SwitchEmulatorCatalog

_SCOPE_DEFS = (
    ("global", "Global", "globe"),
    ("emulator", "Emulador", "emulator"),
    ("game", "Por jogo", "gamepad"),
    ("handheld", "Portátil", "handheld"),
    ("dock", "Dock", "dock"),
)

_AREA_DEFS = (
    ("overview", "Visão geral", "dashboard"),
    ("keysFirmware", "Keys & firmware", "key"),
    ("updatesDlc", "Updates & DLC", "download"),
    ("graphicsPerformance", "Gráficos & desempenho", "speedometer"),
    ("controls", "Controles", "gamepad"),
    ("saves", "Saves", "save"),
    ("shaderCache", "Shader cache", "sparkles"),
    ("media", "Mídia", "image"),
    ("storage", "Armazenamento", "storage"),
    ("advanced", "Avançado", "tune"),
)

_PLANNED_AREAS = frozenset(
    {"updatesDlc", "graphicsPerformance", "controls", "saves", "shaderCache", "media", "storage"}
)


def build_switch_workspace(
    *,
    catalog: SwitchEmulatorCatalog | None = None,
    probe: Any = None,
    keys: RequirementCheck | Mapping[str, Any] | None = None,
    firmware: RequirementCheck | Mapping[str, Any] | None = None,
    games: Sequence[Mapping[str, Any]] = (),
    emulator_capabilities: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    selected_scope: str = "global",
    selected_area: str = "overview",
) -> dict[str, Any]:
    """Compõe o snapshot Switch e valida o próprio contrato antes de retornar."""
    valid_scopes = {item[0] for item in _SCOPE_DEFS}
    valid_areas = {item[0] for item in _AREA_DEFS}
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
    state, status_label, readiness = _readiness(requirements, emulators)
    areas = _areas(requirements, state)
    area_data = _area_data(requirements, emulators, game_rows)
    payload = {
        "schemaVersion": 1,
        "truthState": state,
        "contextLabel": f"Nintendo Switch · {_scope_label(selected_scope)}",
        "platforms": [
            {
                "id": "switch",
                "name": "Nintendo Switch",
                "shortName": "Switch",
                "iconKey": "switch",
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
                "areaData": area_data,
            }
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
            return {key: candidate[key] for key in expected}
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


def _readiness(
    requirements: Mapping[str, Mapping[str, Any]], emulators: Sequence[Mapping[str, Any]]
) -> tuple[str, str, dict[str, Any]]:
    blockers: list[str] = []
    requirement_states = {str(value["status"]) for value in requirements.values()}
    if "missing" in requirement_states:
        blockers.append(
            "Importe keys e firmware próprios antes de iniciar jogos que os exigem."
        )
    if "outdated" in requirement_states:
        blockers.append(
            "Atualize keys ou firmware para atender aos requisitos do jogo selecionado."
        )
    if "unverified" in requirement_states:
        blockers.append("Valide keys e firmware para concluir o diagnóstico de compatibilidade.")
    if not any(item.get("installState") == "installed" for item in emulators):
        blockers.append("Nenhum emulador Switch foi confirmado como instalado.")

    if "missing" in requirement_states:
        state, label, percent = "blocked", "Ação necessária", 20
    elif "outdated" in requirement_states:
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
    requirements: Mapping[str, Mapping[str, Any]], platform_state: str
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
    for area_id, label, icon in _AREA_DEFS:
        if area_id == "overview":
            state, status = platform_state, "Resumo do ambiente"
        elif area_id == "keysFirmware":
            state, status = requirement_state, requirement_label
        elif area_id == "advanced":
            state, status = "attention", "Uso especializado"
        elif area_id in _PLANNED_AREAS:
            state, status = "planned", "Planejado"
        else:
            state, status = "unverified", "Não verificado"
        rows.append(
            {
                "id": area_id,
                "label": label,
                "iconKey": icon,
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
            action=_action("keys.import", "Importar keys", enabled=True, confirmation=True),
            installed=keys["installed"],
            required=keys["required"],
        ),
        _card(
            "firmware",
            "Firmware",
            str(firmware["detail"]),
            _requirement_state(str(firmware["status"])),
            _requirement_label(str(firmware["status"])),
            action=_action("firmware.import", "Importar firmware", enabled=True, confirmation=True),
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
            "primaryAction": _action("platform.scan", "Verificar ambiente", enabled=True),
        },
        "keysFirmware": {
            "cards": requirement_cards,
            "primaryAction": _action("requirements.verify", "Validar requisitos", enabled=True),
        },
    }
    labels = {
        "updatesDlc": ("Updates & DLC", "Instale, ative e audite conteúdo do próprio usuário."),
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
