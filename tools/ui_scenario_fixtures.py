#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Cenários de estado determinísticos para a matriz de controles.

A matriz media 288 controles e conseguia acionar 61: os outros 215 estavam
invisíveis porque, sem bridge, o shell cai nos fallbacks vazios. Um controle
invisível não é uma promessa ao usuário, mas também não é uma prova — ele
simplesmente não foi verificado.

Estes cenários alimentam ``desktopStatus`` com payloads fixos para que cada
superfície apareça nos estados que o produto realmente tem. Nada aqui entra no
produto: as fixtures vivem em ``tests/fixtures/ui-scenarios`` e só o harness as
carrega.

Cada fixture declara, como o contrato de governança exige:

``scenario``
    o estado que ela representa (``empty``, ``ready``, ``degraded``, …);
``origin``
    de onde o payload veio — contrato real, domínio real ou síntese declarada;
``schema``
    o schema que valida a parte ``status``; a parte ``dashboard`` é composta
    pelo ``/status`` depois da validação e por isso não está no schema.

Uso:
  .venv/bin/python tools/ui_scenario_fixtures.py --write
  .venv/bin/python tools/ui_scenario_fixtures.py --list
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from steamzero.adapters.desktop_contracts import handheld_ui_contracts  # noqa: E402
from steamzero.api import contracts  # noqa: E402
from steamzero.domain.emulation_workspace import (  # noqa: E402
    build_emulation_workspace,
    build_global_management,
)
from steamzero.domain.keys_firmware import RequirementCheck  # noqa: E402

FIXTURE_DIR = ROOT / "build" / "ui-scenarios"
STATUS_SCHEMA = "desktop-status-v1.schema.json"


def _context(*, dock: bool = False, displays: int = 1) -> dict[str, Any]:
    return {
        "deviceKind": "steamdeck",
        "sessionType": "wayland",
        "displays": [
            {
                "id": f"display-{index}",
                "name": f"Tela {index + 1}",
                "primary": index == 0,
                "width": 1280,
                "height": 800,
                "scale": 1.0,
                "refresh": 60.0,
            }
            for index in range(displays)
        ],
        "physicalDock": dock,
        "externalKeyboard": dock,
        "externalMouse": dock,
        "capabilities": [],
        "conflicts": [],
        "deckInputKeys": True,
    }


def _observation() -> dict[str, Any]:
    return {
        "checkedEffects": [],
        "unavailableEffects": [],
        "ambiguousCandidates": [],
        "errors": [],
    }


def _status(
    *,
    truth: str = "ready",
    applied: str | None = "handheld-desktop",
    observed: str | None = "handheld-desktop",
    desired: str = "handheld-desktop",
    recovery: bool = False,
    reasons: list[str] | None = None,
    dock: bool = False,
) -> dict[str, Any]:
    return {
        "context": _context(dock=dock),
        "truthState": truth,
        "recommendedProfile": "docked-desktop" if dock else "handheld-desktop",
        "desiredProfile": desired,
        "appliedProfile": applied,
        "observedProfile": observed,
        "effectiveProfile": observed or applied,
        "manualOverride": None,
        "current": None,
        "observation": _observation(),
        "statusReasons": reasons or [],
        "recoveryRequired": recovery,
        "independentRuntime": True,
        "conflictActions": [],
    }


def _job(job_id: str, state: str, progress: float | None, **extra: Any) -> dict[str, Any]:
    job: dict[str, Any] = {
        "jobId": job_id,
        "type": "emulator.install",
        "state": state,
        "rawState": state,
        "priority": "interactive",
        "progress": progress,
        "errorCode": None,
        "result": None,
        "canCancel": state == "running",
        "canRetry": state == "failed",
        "createdAt": "2026-08-13T00:00:00+00:00",
        "updatedAt": "2026-08-13T00:00:00+00:00",
    }
    job.update(extra)
    return job


def _steam_games(count: int) -> list[dict[str, Any]]:
    return [
        {
            "id": str(100 + index),
            "name": f"Jogo Steam {index + 1}",
            "coverUrl": "",
            "state": "installed",
            "genre": "Ação",
            "year": 2020 + (index % 5),
            "developer": f"Estúdio {index % 3}",
        }
        for index in range(count)
    ]


def _emulation_workspace(*, installed: str | None = "eden") -> dict[str, Any]:
    """Workspace de emulação montado pelas funções de domínio REAIS.

    Sintetizar este payload à mão seria inútil: ele é o que decide quais cards,
    áreas e ações a tela desenha, e uma versão inventada mediria uma tela que
    não existe. O schema `emulation-workspace-v1` valida o resultado.
    """
    workspace = build_emulation_workspace(
        probe=lambda emulator_id: emulator_id == installed,
        keys=RequirementCheck("ok", "keys", "rev17", "rev18", "Keys compatíveis."),
        firmware=RequirementCheck("ok", "firmware", "17.0.0", "18.0.1", "Firmware compatível."),
        games=[],
        emulator_capabilities={},
    )
    workspace["globalManagement"] = build_global_management(
        platforms=workspace["platforms"],
        editorial_platforms=[],
        canonical_experiences=workspace["canonicalExperiences"],
        truth_state=workspace["truthState"],
        emulators=_emulator_rows(),
        directories=[],
        media_providers=[],
    )
    workspace["jobs"] = []
    return workspace


def _emulator_rows() -> list[dict[str, Any]]:
    """Os quatro estados de lifecycle que geram ação distinta."""

    def row(rid: str, name: str, state: str, install: str, action: dict[str, Any]):
        return {
            "id": rid,
            "displayName": name,
            "state": state,
            "installState": install,
            "action": action,
        }

    def act(aid: str, label: str, confirm: bool):
        return {
            "id": aid,
            "label": label,
            "enabled": True,
            "reason": None,
            "requiresConfirmation": confirm,
        }

    return [
        row(
            "dolphin",
            "Dolphin",
            "unavailable",
            "not-installed",
            act("emulator.install:dolphin", "Instalar", True),
        ),
        row("eden", "Eden", "ready", "installed", act("emulator.launch:eden", "Abrir", False)),
        row(
            "citron",
            "Citron",
            "attention",
            "degraded",
            act("emulator.repair:citron", "Reparar", True),
        ),
        row(
            "ryubing",
            "Ryubing",
            "ready",
            "installed",
            act("emulator.stop:ryubing", "Fechar", False),
        ),
    ]


def _cast_found() -> dict[str, Any]:
    return {
        "state": "ready",
        "orchestrator": {"configured": True, "detail": "Orquestrador local pronto."},
        "receivers": [
            {"id": "rx-1", "name": "TV da sala", "state": "available", "paired": False},
            {"id": "rx-2", "name": "Monitor do quarto", "state": "available", "paired": True},
        ],
    }


def _themes(active: str = "org.steamzero.default") -> dict[str, Any]:
    return {
        "activeId": active,
        "themes": [
            {"id": "org.steamzero.default", "name": "Padrão", "builtin": True, "version": "1.0.0"},
            {"id": "org.steamzero.aura", "name": "AURA", "builtin": True, "version": "1.0.0"},
            {
                "id": "org.steamzero.steamdeck",
                "name": "Steam Deck",
                "builtin": True,
                "version": "1.0.0",
            },
        ],
    }


def _components() -> list[dict[str, Any]]:
    return [
        {
            "id": "dolphin",
            "name": "Dolphin",
            "state": "unavailable",
            "statusLabel": "Não instalado",
            "action": {
                "kind": "component-plan",
                "label": "Instalar",
                "enabled": True,
                "operation": "install",
                "reason": None,
            },
        },
        {
            "id": "retroarch",
            "name": "RetroArch",
            "state": "attention",
            "statusLabel": "Degradado",
            "action": {
                "kind": "component-verify",
                "label": "Verificar",
                "enabled": True,
                "reason": None,
            },
        },
    ]


def _dashboard(**overrides: Any) -> dict[str, Any]:
    """Base do dashboard com os contratos REAIS publicados pela bridge.

    Só ``uiContracts`` vem do produto — é o que decide se uma ação é
    despachável, e substituí-lo por síntese tornaria todo veredito de rota
    ficção. O resto é declarado como síntese por cenário.
    """
    base: dict[str, Any] = {
        "uiContracts": handheld_ui_contracts(),
        "accessibility": {"reducedMotion": False, "highContrast": False},
        "doctor": {"status": "ok", "checks": []},
        "diagnostics": {},
        "resources": {},
        "components": [],
        "emulation": {},
        "steam": [],
        "steamGameplay": {},
        "sync": {},
        "cast": {},
        "theme": {},
        "playtime": {},
        "collections": {},
        "libraryHealth": {},
        "jobs": [],
    }
    base.update(overrides)
    return base


#: Os cenários. Cada entrada declara o estado que representa e a origem do
#: payload. Crescer esta lista é como a matriz fecha os ``not-probed``.
SCENARIOS: dict[str, dict[str, Any]] = {
    "offline": {
        "description": "Sem bridge: o shell cai nos fallbacks embutidos.",
        "origin": "nenhuma; ausência de payload é o próprio cenário",
        "status": None,
        "dashboard": None,
    },
    "empty": {
        "description": "Bridge respondendo, nenhum dado em nenhuma superfície.",
        "origin": "sintético declarado + uiContracts reais",
        "status": _status(),
        "dashboard": _dashboard(),
    },
    "ready-small-library": {
        "description": "Biblioteca Steam pequena, tudo pronto.",
        "origin": "sintético declarado + uiContracts reais",
        "status": _status(),
        "dashboard": _dashboard(
            steam=_steam_games(6),
            playtime={"totalSeconds": 7200, "games": 6},
            doctor={"status": "ok", "checks": [{"id": "core", "state": "ok", "detail": "OK"}]},
        ),
    },
    "emulation-ready": {
        "description": "Workspace de emulação completo: 36 plataformas, 4 estados de emulador.",
        "origin": "domínio real (build_emulation_workspace + build_global_management)",
        "status": _status(),
        "dashboard": _dashboard(
            emulation=_emulation_workspace(),
            components=_components(),
        ),
    },
    "emulation-no-emulator": {
        "description": "Nenhum emulador instalado: o bloqueador é instalação.",
        "origin": "domínio real (build_emulation_workspace + build_global_management)",
        "status": _status(truth="degraded"),
        "dashboard": _dashboard(
            emulation=_emulation_workspace(installed=None),
            components=_components(),
        ),
    },
    "cast-receiver-found": {
        "description": "Orquestrador pronto e dois receptores encontrados.",
        "origin": "sintético declarado + uiContracts reais",
        "status": _status(),
        "dashboard": _dashboard(cast=_cast_found()),
    },
    "themes-listed": {
        "description": "Tema ativo mais alternativas nativas.",
        "origin": "sintético declarado + uiContracts reais",
        "status": _status(),
        "dashboard": _dashboard(theme=_themes()),
    },
    "everything-ready": {
        "description": "Todas as superfícies com dados: o teto de visibilidade offscreen.",
        "origin": "domínio real para emulação + sintético declarado no resto",
        "status": _status(),
        "dashboard": _dashboard(
            steam=_steam_games(6),
            playtime={"totalSeconds": 7200, "games": 6},
            emulation=_emulation_workspace(),
            components=_components(),
            cast=_cast_found(),
            theme=_themes(),
            doctor={"status": "ok", "checks": [{"id": "core", "state": "ok", "detail": "OK"}]},
            jobs=[_job("job-1", "running", 0.42)],
        ),
    },
    "stale-profile": {
        "description": "Perfil aplicado diverge do desejado; banner de atenção ativo.",
        "origin": "sintético declarado + uiContracts reais",
        "status": _status(
            truth="stale",
            desired="docked-desktop",
            applied="handheld-desktop",
            observed="handheld-desktop",
            reasons=["O perfil aplicado não corresponde ao desejado."],
            dock=True,
        ),
        "dashboard": _dashboard(),
    },
    "degraded-doctor": {
        "description": "Doctor degradado com check falhando.",
        "origin": "sintético declarado + uiContracts reais",
        "status": _status(truth="degraded", reasons=["Backup órfão encontrado."]),
        "dashboard": _dashboard(
            doctor={
                "status": "degraded",
                "checks": [
                    {"id": "backup", "state": "degraded", "detail": "Backup órfão encontrado."}
                ],
            }
        ),
    },
    "recovery-required": {
        "description": "Estado exige recovery antes de qualquer mutação.",
        "origin": "sintético declarado + uiContracts reais",
        "status": _status(
            truth="recovery-required",
            applied=None,
            observed=None,
            recovery=True,
            reasons=["Uma operação anterior não foi concluída."],
        ),
        "dashboard": _dashboard(),
    },
    "jobs-running": {
        "description": "Um job em execução com progresso.",
        "origin": "sintético declarado + uiContracts reais",
        "status": _status(),
        "dashboard": _dashboard(jobs=[_job("job-1", "running", 0.42)]),
    },
    "jobs-mixed": {
        "description": "Vários jobs simultâneos: sucesso, falha e execução.",
        "origin": "sintético declarado + uiContracts reais",
        "status": _status(),
        "dashboard": _dashboard(
            jobs=[
                _job("job-1", "running", 0.42),
                _job("job-2", "completed", 1.0),
                _job(
                    "job-3",
                    "failed",
                    None,
                    errorCode="E-TX-001",
                    result={"message": "Falha na aplicação do plano."},
                ),
            ]
        ),
    },
    "task-error": {
        "description": "Central de tarefas falhou e oferece nova tentativa.",
        "origin": "sintético declarado + uiContracts reais",
        "status": _status(),
        "dashboard": _dashboard(),
        "taskError": "A central local não respondeu; o estado foi preservado.",
    },
    "long-error": {
        "description": "Erro com texto longo, para provar wrap e clipping.",
        "origin": "sintético declarado + uiContracts reais",
        "status": _status(
            truth="degraded",
            reasons=[
                "A operação foi interrompida porque o destino declarado pelo "
                "componente não pôde ser verificado dentro do tempo previsto, e "
                "nenhuma alteração foi aplicada ao host; revise o plano, confira "
                "a origem do artefato e tente novamente pela mesma superfície."
            ],
        ),
        "dashboard": _dashboard(),
    },
}


def build(name: str) -> dict[str, Any]:
    spec = SCENARIOS[name]
    status = spec["status"]
    if status is not None:
        # Valida o que o schema cobre. `dashboard` é montado pelo /status DEPOIS
        # da validação, então fica fora — declarar isso é parte da fixture.
        contracts.validate(status, STATUS_SCHEMA)
    return {
        "schemaVersion": 1,
        "kind": "steamzero-ui-scenario",
        "scenario": name,
        "description": spec["description"],
        "origin": spec["origin"],
        "schema": STATUS_SCHEMA if status is not None else None,
        "schemaCovers": "status" if status is not None else None,
        "status": status,
        "dashboard": spec["dashboard"],
        "taskError": spec.get("taskError", ""),
    }


def write_all(directory: Path = FIXTURE_DIR) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for name in sorted(SCENARIOS):
        path = directory / f"{name}.json"
        path.write_text(
            json.dumps(build(name), indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="grava as fixtures em disco")
    parser.add_argument("--list", action="store_true", help="lista os cenários declarados")
    args = parser.parse_args(argv)

    if args.list or not args.write:
        for name in sorted(SCENARIOS):
            print(f"{name:22s} {SCENARIOS[name]['description']}")
        return 0
    for path in write_all():
        print(f"gravado {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
