#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Audita a superfície pública da bridge Desktop sem tocar o estado do host.

A central Desktop não pode inferir que todo método Python é uma API. Este gate
mantém uma decisão explícita para cada método público do ``ComponentLifecycle``
e cruza essa decisão com o catálogo de contratos e com as rotas realmente
registradas. O relatório é derivado do código e não carrega caminhos, argv,
tokens ou qualquer conteúdo de BIOS/firmware.

Use ``--report`` durante o fechamento incremental para ver lacunas; ``--check``
é o gate estrito e falha enquanto uma superfície aprovada ainda não estiver
publicada com contrato fechado.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from steamzero.adapters.desktop_contracts import handheld_ui_contracts  # noqa: E402


@dataclass(frozen=True)
class SurfaceDecision:
    """Decisão de publicação para uma operação de lifecycle conhecida."""

    category: str
    action_ids: tuple[str, ...]
    reason: str


# Este catálogo é deliberadamente pequeno e fechado: adicionar um método
# público ao lifecycle sem classificá-lo faz o gate acusar ``unclassified``.
# Não há descoberta otimista de endpoint a partir do nome do método.
LIFECYCLE_SURFACES: dict[str, SurfaceDecision] = {
    "status": SurfaceDecision("bridge-now", ("component.status",), "consulta segura por id"),
    "status_all": SurfaceDecision("bridge-now", ("component.list",), "lista sanitizada"),
    "verify": SurfaceDecision("read-only", ("component.verify",), "verificação sem efeito"),
    "plan": SurfaceDecision("plan-apply", ("component.plan",), "plano persistido e token"),
    "apply": SurfaceDecision("plan-apply", ("component.apply",), "efeito confirmado"),
    "rollback": SurfaceDecision(
        "plan-apply",
        ("component.rollback.plan", "component.rollback.apply"),
        "operação auditável",
    ),
    "launch": SurfaceDecision(
        "bridge-now", ("component.launch",), "spawn só de payload gerenciado"
    ),
    "open_config": SurfaceDecision(
        "blocked",
        ("component.open-config",),
        "nenhum argumento direto comprovado para os emuladores ativos",
    ),
    "stop": SurfaceDecision("plan-apply", ("component.stop",), "somente payload Engine gerenciado"),
    "recover": SurfaceDecision(
        "plan-apply",
        ("component.recovery.inspect", "component.recovery.apply"),
        "inspeção antes de recuperação idempotente",
    ),
    "recovery_inspect": SurfaceDecision(
        "read-only", ("component.recovery.inspect",), "operações pendentes sanitizadas"
    ),
}


def _public_methods(path: Path, class_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                item.name
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and not item.name.startswith("_")
            }
    raise RuntimeError(f"classe {class_name} ausente em {path}")


def _registered_routes(path: Path) -> set[str]:
    """Extrai rotas literais do handler sem executar a bridge."""
    source = path.read_text(encoding="utf-8")
    return set(re.findall(r'path == "([^"]+)"', source)) | set(
        re.findall(r'path\.startswith\("([^"]+)"\)', source)
    )


def _route_exists(endpoint: str, routes: set[str]) -> bool:
    static = endpoint.split("/{", 1)[0]
    return static in routes or any(static.startswith(prefix) for prefix in routes)


def _consumer_action_ids(path: Path) -> set[str]:
    source = path.read_text(encoding="utf-8")
    return set(re.findall(r'requestAction\("([^"]+)"', source))


def audit() -> dict[str, Any]:
    contracts = handheld_ui_contracts()
    actions = {str(item["id"]): item for item in contracts["actions"]}
    lifecycle_methods = _public_methods(
        ROOT / "src/steamzero/adapters/lifecycle.py", "ComponentLifecycle"
    )
    dashboard_methods = _public_methods(
        ROOT / "src/steamzero/adapters/desktop_dashboard.py", "DesktopDashboard"
    )
    routes = _registered_routes(ROOT / "src/steamzero/adapters/desktop_ui.py")
    consumers = _consumer_action_ids(ROOT / "src/steamzero/ui/qml/Main.qml")

    issues: list[dict[str, str]] = []
    discoveries: list[dict[str, Any]] = []

    for method in sorted(lifecycle_methods):
        decision = LIFECYCLE_SURFACES.get(method)
        if decision is None:
            issues.append({"kind": "unclassified", "subject": method})
            continue
        action_rows = [actions.get(action_id) for action_id in decision.action_ids]
        missing = [
            action_id
            for action_id, action in zip(decision.action_ids, action_rows, strict=True)
            if action is None
        ]
        if missing:
            issues.append(
                {
                    "kind": "missing-contract",
                    "subject": method,
                    "detail": ", ".join(missing),
                }
            )
        discoveries.append(
            {
                "method": method,
                "category": decision.category,
                "actions": list(decision.action_ids),
                "reason": decision.reason,
                "published": not missing,
            }
        )

    for action_id, action in sorted(actions.items()):
        endpoint = action["endpoint"]
        applicable = action["applicability"] == "applicable"
        if applicable and not action["enabled"]:
            issues.append({"kind": "enabled-mismatch", "subject": action_id})
        if not applicable and (endpoint is not None or not action["reason"]):
            issues.append({"kind": "blocked-without-reason", "subject": action_id})
        if endpoint is None:
            continue
        if not _route_exists(str(endpoint), routes):
            issues.append({"kind": "missing-route", "subject": action_id, "detail": str(endpoint)})
        schema = action["inputSchema"]
        if schema.get("additionalProperties") is not False:
            issues.append({"kind": "open-schema", "subject": action_id})
        # ``theme.apply`` é semanticamente um *plan* apesar do nome histórico;
        # só ações que recebem ``planId`` podem produzir o efeito confirmado.
        # A regra permanece estrutural, não uma exceção por id.
        requires_apply_token = "planId" in schema.get("required", [])
        if requires_apply_token and not action["confirmation"]["required"]:
            issues.append({"kind": "mutation-without-confirmation", "subject": action_id})

    # Um controle QML só pode pedir actions do contrato. A ausência de consumo
    # não reprova por si: uma ação pode pertencer a uma tela ainda não montada,
    # mas a lista deixa essa decisão visível no relatório.
    undeclared_consumers = sorted(consumers - set(actions))
    for action_id in undeclared_consumers:
        issues.append({"kind": "consumer-without-contract", "subject": action_id})

    lifecycle_action_ids = {
        action_id for decision in LIFECYCLE_SURFACES.values() for action_id in decision.action_ids
    }
    return {
        "schemaVersion": 1,
        "lifecycleMethods": sorted(lifecycle_methods),
        "dashboardMethodCount": len(dashboard_methods),
        "registeredRoutes": sorted(routes),
        "consumerActionIds": sorted(consumers),
        "lifecycleDiscoveries": discoveries,
        "lifecycleActionIds": sorted(lifecycle_action_ids),
        "issues": issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="falha quando houver divergências")
    parser.add_argument("--report", action="store_true", help="imprime JSON sanitizado")
    args = parser.parse_args(argv)
    report = audit()
    if args.report or not args.check:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if args.check and report["issues"]:
        print(f"bridge audit encontrou {len(report['issues'])} divergência(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
