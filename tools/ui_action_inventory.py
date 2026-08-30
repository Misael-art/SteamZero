#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Inventário das ações que a UI oferece e do que cada uma faz de fato.

A auditoria de 2026-08-11 encontrou um botão "Instalar" habilitado que não
chamava nada. Nenhum gate pegou porque nenhum gate sabia quais botões existiam.
Este inventário fecha essa lacuna por construção:

1. lê as ações que os read models realmente publicam (o que a UI desenha);
2. pergunta ao shell QML, por sonda comportamental, o que cada uma faz ao ser
   clicada — nenhuma heurística estática acerta isso;
3. cruza com o catálogo de contratos que a bridge publica.

O veredito por ação é um destes:

``routed``
    o shell despachou para um contrato — clicar produz efeito ou erro do backend.
``handled-locally``
    o shell resolveu sem backend (navegação, troca de view) e deu retorno.
``unrouted``
    habilitada, mas nenhum despachante entende: só sabe errar.
``silent-no-op``
    habilitada e sem efeito nem erro. **Deve ser zero.**
``blocked-explained`` / ``blocked-silent``
    desabilitada com e sem motivo. A segunda é defeito.

Contratos que nenhuma ação inventariada alcançou saem em um de dois campos, e a
diferença entre eles é o ponto:

``notCoveredContracts``
    a auditoria é parcial. O contrato pode muito bem ser alcançável por uma tela
    que esta execução nem abriu — não afirma nada sobre o produto.
``orphanContracts``
    só aparece quando ``coverage.complete`` é verdadeiro. Aí sim é capacidade
    que existe no backend e está invisível no produto inteiro.

Uso:
  .venv/bin/python tools/ui_action_inventory.py
  .venv/bin/python tools/ui_action_inventory.py --json out.json --markdown out.md
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

QML = shutil.which("qml6") or shutil.which("qml")

from steamzero.adapters.desktop_contracts import handheld_ui_contracts  # noqa: E402
from steamzero.domain.emulation_workspace import (  # noqa: E402
    build_emulation_workspace,
    build_global_management,
)
from steamzero.domain.keys_firmware import RequirementCheck  # noqa: E402

#: Prefixos de ação que carregam um alvo depois de ``:`` (``emulator.install:dolphin``).
#: O contrato publicado é a família, não a instância.
_FAMILY_CONTRACTS: dict[str, str] = {
    "emulator.install": "emulator.plan",
    "emulator.update": "emulator.plan",
    "emulator.uninstall": "emulator.plan",
    "emulator.repair": "emulator.plan",
    "emulator.launch": "emulator.launch",
    "emulator.stop": "emulator.stop",
    "game.launch": "game.launch",
    "cloud.launch": "cloud.launch",
}


#: Linhas de emulador na forma que ``EmulationAdapter`` publica em
#: ``globalManagement.emulators``. São fixture — o host não entra no inventário —
#: mas cobrem os quatro estados de lifecycle que geram ação: ausente, instalado,
#: degradado e em execução. Se o adapter mudar a forma da ação, o teste de
#: contrato em ``tests/unit/test_ui_action_inventory.py`` reprova.
_EMULATOR_ROW_FIXTURE: list[dict[str, Any]] = [
    {
        "id": "dolphin",
        "displayName": "Dolphin",
        "state": "unavailable",
        "installState": "not-installed",
        "action": {
            "id": "emulator.install:dolphin",
            "label": "Instalar",
            "enabled": True,
            "reason": None,
            "requiresConfirmation": True,
        },
    },
    {
        "id": "eden",
        "displayName": "Eden",
        "state": "ready",
        "installState": "installed",
        "action": {
            "id": "emulator.launch:eden",
            "label": "Abrir",
            "enabled": True,
            "reason": None,
            "requiresConfirmation": False,
        },
    },
    {
        "id": "citron",
        "displayName": "Citron",
        "state": "attention",
        "installState": "degraded",
        "action": {
            "id": "emulator.repair:citron",
            "label": "Reparar",
            "enabled": True,
            "reason": None,
            "requiresConfirmation": True,
        },
    },
    {
        "id": "ryubing",
        "displayName": "Ryubing",
        "state": "ready",
        "installState": "installed",
        "action": {
            "id": "emulator.stop:ryubing",
            "label": "Fechar",
            "enabled": True,
            "reason": None,
            "requiresConfirmation": False,
        },
    },
]


def _sample_workspace() -> dict[str, Any]:
    """Workspace determinístico: nada do host entra no inventário.

    A composição de plataformas e da gestão geral é a mesma que o produto monta
    — são as funções de domínio reais. Só as sondas e as linhas de emulador são
    fixas, para que duas execuções em máquinas diferentes deem o mesmo resultado.
    """
    workspace = build_emulation_workspace(
        probe=lambda emulator_id: emulator_id == "eden",
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
        emulators=_EMULATOR_ROW_FIXTURE,
        directories=[],
        media_providers=[],
    )
    return workspace


#: Um escopo de plataforma (``{id, label, enabled, reason}``) é indistinguível
#: de uma ação pela forma. O que os separa é a posição: a QML só despacha o que
#: está sob ``action`` ou dentro de ``actions[]`` — ``scopes[]`` é seleção de
#: contexto, não botão. Classificar por forma inventava 76 ações inexistentes.
def _is_action_slot(path: str) -> bool:
    tail = path.rsplit(".", 1)[-1]
    return tail == "action" or tail.startswith("actions[")


def _looks_like_action(node: dict[str, Any], path: str) -> bool:
    if "enabled" not in node or not _is_action_slot(path):
        return False
    return isinstance(node.get("id"), str) or isinstance(node.get("kind"), str)


def collect_published_actions(payload: Any, path: str = "") -> list[dict[str, Any]]:
    """Percorre um read model e recolhe toda ação com a sua origem na árvore."""
    found: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        if _looks_like_action(payload, path):
            found.append(
                {
                    "surface": path or "(raiz)",
                    "id": payload.get("id", ""),
                    "kind": payload.get("kind", ""),
                    "label": payload.get("label", ""),
                    "enabled": bool(payload.get("enabled")),
                    "reason": payload.get("reason", ""),
                    "confirmation": bool(payload.get("confirmation")),
                }
            )
        for key, value in payload.items():
            found.extend(collect_published_actions(value, f"{path}.{key}" if path else key))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            found.extend(collect_published_actions(value, f"{path}[{index}]"))
    return found


def contract_for(action_id: str) -> str:
    """Contrato que a ação deve alcançar, resolvendo a família antes do ``:``."""
    if ":" in action_id:
        family = action_id.split(":", 1)[0]
        if family in _FAMILY_CONTRACTS:
            return _FAMILY_CONTRACTS[family]
    return action_id


def probe_dispatch(actions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Pergunta ao próprio shell QML o que cada ação faz ao ser clicada.

    Nenhuma heurística estática consegue responder isto: parte das ações é
    tratada dentro da QML (navegação, troca de view) e parte vai ao backend. A
    sonda roda offscreen e offline, então toda ação roteada morre na checagem de
    contrato e denuncia qual contrato tentou — e o que não denuncia nada é
    exatamente o botão que não faz nada.
    """
    if not QML:
        raise SystemExit("qml6 ausente; a matriz de controles exige o runtime QML")

    payload = [
        {
            "surface": action["surface"],
            "dispatch": "row",
            "action": {
                "id": action["id"],
                "kind": action["kind"],
                "label": action["label"],
                "enabled": action["enabled"],
                "reason": action["reason"],
            },
        }
        for action in actions
    ]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)
        probe_input = Path(handle.name)

    env = os.environ.copy()
    env.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QUICK_BACKEND": "software",
            "QT_FORCE_STDERR_LOGGING": "1",
            "QT_LOGGING_RULES": "",
            # A sonda lê a lista de ações de um arquivo local do próprio repo.
            "QML_XHR_ALLOW_FILE_READ": "1",
        }
    )
    try:
        completed = subprocess.run(
            [
                QML,
                str(ROOT / "tools" / "ui_action_probe.qml"),
                "--",
                "--steamzero-actions",
                str(probe_input),
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    finally:
        probe_input.unlink(missing_ok=True)

    results: dict[str, dict[str, Any]] = {}
    for line in (completed.stdout + completed.stderr).splitlines():
        marker = line.find("PROBE ")
        if marker < 0:
            continue
        try:
            record = json.loads(line[marker + len("PROBE ") :])
        except json.JSONDecodeError:
            continue
        results[f"{record['surface']}|{record['actionId']}|{record['actionKind']}"] = record

    if not results:
        raise SystemExit(
            "a sonda de despacho não produziu resultado "
            f"(returncode={completed.returncode}); stderr:\n{completed.stderr[-2000:]}"
        )
    return results


def classify(
    actions: list[dict[str, Any]],
    contracts_by_id: dict[str, Any],
    probed: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for action in actions:
        action_id = str(action["id"])
        target = contract_for(action_id) if action_id else ""
        contract = contracts_by_id.get(target)
        record = probed.get(f"{action['surface']}|{action_id}|{action['kind']}", {})
        rows.append(
            {
                **action,
                "contract": record.get("attemptedContract") or target,
                "endpoint": (contract or {}).get("endpoint", ""),
                "method": (contract or {}).get("method", ""),
                "screen": (contract or {}).get("screen", ""),
                "verdict": record.get("verdict", "not-probed"),
                "message": record.get("message", ""),
                "explains": bool(action["reason"]) if not action["enabled"] else None,
            }
        )
    return rows


#: As seções que a central publica em ``Main.qml`` (``navigationSections``),
#: mais as superfícies transversais que não são seção mas têm controles
#: próprios. Esta é a régua de cobertura: enquanto faltar qualquer uma, o
#: inventário não pode afirmar orfandade de contrato.
DECLARED_SURFACES: tuple[str, ...] = (
    "overview",
    "emulators",
    "steam",
    "profiles",
    "sync",
    "cast",
    "system",
    "themes",
    "library",
    "sidebar",
    "handheld-drawer",
    "task-drawer",
    "credentials",
    "plan-dialogs",
    "jobs",
    "recovery",
    "notifications",
)


def unreached_contracts(
    rows: list[dict[str, Any]], contracts_by_id: dict[str, Any]
) -> list[dict[str, Any]]:
    """Contratos publicados que nenhuma ação inventariada alcançou.

    Só isso. Se a ação que alcançaria o contrato vive numa superfície que o
    inventário ainda não visita, o contrato aparece aqui sem ser órfão — e é
    por isso que quem publica precisa dizer qual dos dois nomes está usando
    (ver :func:`coverage_report`).
    """
    reached = {row["contract"] for row in rows if row["contract"]}
    return [
        {"contract": key, "label": value.get("label", ""), "screen": value.get("screen", "")}
        for key, value in sorted(contracts_by_id.items())
        if key not in reached
    ]


def coverage_report(covered: Sequence[str]) -> dict[str, Any]:
    """Quanto da central o inventário realmente visitou."""
    covered_set = {str(item) for item in covered}
    unknown = sorted(covered_set - set(DECLARED_SURFACES))
    if unknown:
        raise SystemExit(
            "superfície coberta que não está declarada em DECLARED_SURFACES: "
            + ", ".join(unknown)
            + ". Declare a superfície antes de afirmar cobertura sobre ela."
        )
    missing = [surface for surface in DECLARED_SURFACES if surface not in covered_set]
    return {
        "declared": list(DECLARED_SURFACES),
        "covered": sorted(covered_set),
        "missing": missing,
        "complete": not missing,
    }


#: Superfícies que este inventário visita hoje. Cresce a cada incremento; é o
#: que separa "não alcançado por esta auditoria" de "órfão no produto".
COVERED_SURFACES: tuple[str, ...] = ("emulators",)


def build_inventory() -> dict[str, Any]:
    contracts = handheld_ui_contracts()
    contracts_by_id = dict(contracts.get("byId") or {})
    actions = collect_published_actions(_sample_workspace(), "emulationWorkspace")
    rows = classify(actions, contracts_by_id, probe_dispatch(actions))
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1

    coverage = coverage_report(COVERED_SURFACES)
    unreached = unreached_contracts(rows, contracts_by_id)
    inventory: dict[str, Any] = {
        "schemaVersion": 2,
        "kind": "steamzero-ui-action-inventory",
        "coverage": coverage,
        "contractCount": len(contracts_by_id),
        "publishedActionCount": len(rows),
        "verdictCounts": counts,
        # Um botão habilitado que não produz efeito nem erro. Deve ser zero.
        "silentNoOps": [row for row in rows if row["verdict"] == "silent-no-op"],
        # Habilitado, mas o shell não sabe despachar: erra sempre.
        "unrouted": [row for row in rows if row["verdict"] == "unrouted"],
        # Desabilitado sem dizer por quê.
        "unexplainedBlocked": [row for row in rows if row["verdict"] == "blocked-silent"],
        "actions": rows,
    }
    # Orfandade é uma afirmação sobre o produto inteiro. Uma auditoria que
    # visitou 1 de 17 superfícies não pode fazê-la: os 117 contratos que ela
    # não alcançou são, em quase todos os casos, contratos de telas que ela
    # nem abriu. Enquanto a cobertura for parcial, o nome é outro.
    if coverage["complete"]:
        inventory["orphanContracts"] = unreached
    else:
        inventory["notCoveredContracts"] = unreached
    return inventory


def render_markdown(inventory: dict[str, Any]) -> str:
    lines = [
        "# Matriz de controles — ações publicadas e contratos",
        "",
        f"- contratos publicados: **{inventory['contractCount']}**",
        f"- ações nos read models: **{inventory['publishedActionCount']}**",
        f"- veredito: `{inventory['verdictCounts']}`",
        "",
        "| Superfície | Ação | Rótulo | Habilitada | Contrato | Endpoint | Veredito | Motivo |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in inventory["actions"]:
        lines.append(
            "| {surface} | `{id}` | {label} | {enabled} | `{contract}` | {method} {endpoint} "
            "| **{verdict}** | {reason} |".format(**row)
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=None, help="grava o inventário em JSON")
    parser.add_argument("--markdown", type=Path, default=None, help="grava a matriz em Markdown")
    args = parser.parse_args(argv)

    inventory = build_inventory()
    if args.json:
        args.json.write_text(
            json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    if args.markdown:
        args.markdown.write_text(render_markdown(inventory), encoding="utf-8")
    coverage = inventory["coverage"]
    print(json.dumps(inventory["verdictCounts"], indent=2, ensure_ascii=False))
    print(f"no-op silencioso: {len(inventory['silentNoOps'])}")
    print(f"habilitada sem rota: {len(inventory['unrouted'])}")
    print(f"desabilitada sem motivo: {len(inventory['unexplainedBlocked'])}")
    print(
        f"cobertura: {len(coverage['covered'])}/{len(coverage['declared'])} superfícies"
        + ("" if coverage["complete"] else f"; faltam {', '.join(coverage['missing'])}")
    )
    if coverage["complete"]:
        print(f"contratos órfãos: {len(inventory['orphanContracts'])}")
    else:
        print(
            f"contratos não cobertos por esta auditoria: "
            f"{len(inventory['notCoveredContracts'])} (não são órfãos: a auditoria é parcial)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
