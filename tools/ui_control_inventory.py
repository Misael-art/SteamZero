#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Matriz de controles da central, medida na árvore QML viva.

Complementa ``ui_action_inventory.py``. Aquele inventário despacha os ``action``
que os read models publicam; este percorre a árvore de objetos de cada
superfície e aciona TODO elemento interativo — Button, ToolButton, aba,
combobox, slider, delegate, botão de diálogo — inclusive os que não nascem de
payload nenhum e que, por isso, nenhuma matriz de ações jamais veria.

Foi assim que apareceu o "Configurações avançadas" da tela Steam: um Button
habilitado, de largura total, com chevron e ``Accessible.name``, e sem nenhum
``onClicked``. Clicar nunca fez nada, e a tela era considerada a melhor da
central.

Uso:
  .venv/bin/python tools/ui_control_inventory.py
  .venv/bin/python tools/ui_control_inventory.py --json out.json --markdown out.md
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
QML = shutil.which("qml6") or shutil.which("qml")

#: Vereditos que reprovam a matriz. Ver ``ui_action_inventory`` para a semântica.
FAILING_VERDICTS = ("silent-no-op", "unrouted", "blocked-silent")


#: As fixtures sao DERIVADAS: `ui_scenario_fixtures` as gera deterministicamente
#: a partir do dominio real e dos contratos publicados. Commitar 5 MB de JSON
#: gerado seria guardar a saida em vez da fonte, e o `uiContracts` repetido em
#: cada arquivo responde por quase tudo isso.
SCENARIO_DIR = ROOT / "build" / "ui-scenarios"

#: Ordem de precedencia do veredito ao fundir cenarios. O pior resultado vence:
#: um botao que funciona num cenario e morre em outro continua sendo defeito.
_VERDICT_RANK = {
    "silent-no-op": 0,
    "unrouted": 1,
    "blocked-silent": 2,
    "not-probed": 3,
    "blocked-explained": 4,
    "handled-locally": 5,
    "routed": 6,
}


def scenario_paths() -> list[Path]:
    """Gera (ou regenera) as fixtures e devolve os caminhos.

    Regenerar sempre e de proposito: uma fixture obsoleta em disco mediria um
    contrato que o produto ja nao publica.
    """
    import ui_scenario_fixtures

    return ui_scenario_fixtures.write_all(SCENARIO_DIR)


def run_probe(timeout: int = 400, scenario: Path | None = None) -> dict[str, Any]:
    """Executa a sonda offscreen e devolve contexto + registros por controle."""
    if not QML:
        raise SystemExit("qml6 ausente; a matriz de controles exige o runtime QML")

    env = os.environ.copy()
    env.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QUICK_BACKEND": "software",
            "QT_FORCE_STDERR_LOGGING": "1",
            "QT_LOGGING_RULES": "",
        }
    )
    argv = [QML, str(ROOT / "tools" / "ui_control_probe.qml")]
    if scenario is not None:
        # A sonda le a fixture do proprio repo por file://.
        env["QML_XHR_ALLOW_FILE_READ"] = "1"
        argv += ["--", "--steamzero-scenario", str(scenario)]
    completed = subprocess.run(
        argv,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    output = completed.stdout + "\n" + (completed.stderr or "")

    controls: list[dict[str, Any]] = []
    context: dict[str, Any] = {}
    sections: list[dict[str, Any]] = []
    for line in output.splitlines():
        for marker, sink in (
            ("PROBE-CONTROL ", controls),
            ("PROBE-SECTION ", sections),
        ):
            index = line.find(marker)
            if index >= 0:
                with contextlib.suppress(json.JSONDecodeError):
                    sink.append(json.loads(line[index + len(marker) :]))
        index = line.find("PROBE-CONTEXT ")
        if index >= 0:
            with contextlib.suppress(json.JSONDecodeError):
                context = json.loads(line[index + len("PROBE-CONTEXT ") :])

    if not controls:
        raise SystemExit(
            f"a sonda de controles não produziu registro (returncode={completed.returncode});"
            f" stderr:\n{(completed.stderr or '')[-2000:]}"
        )
    if "PROBE-FAIL" in output:
        raise SystemExit(
            "a sonda reprovou uma espera por condição; nenhum veredito é confiável:\n"
            + "\n".join(line for line in output.splitlines() if "PROBE-FAIL" in line)
        )
    return {
        "context": context,
        "sections": sections,
        "controls": controls,
        "returncode": completed.returncode,
    }


def merge_scenarios(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Funde os cenarios pela identidade estavel do controle.

    Casar por rotulo nao serve: o mesmo botao muda de texto entre estados, e
    dois botoes diferentes compartilham rotulo. A identidade estrutural e o que
    permite dizer "este controle foi exercitado em algum cenario".
    """
    merged: dict[str, dict[str, Any]] = {}
    for run in runs:
        scenario = str(run["context"].get("scenario", "?"))
        for control in run["controls"]:
            key = control["controlId"]
            control = {**control, "scenario": scenario}
            current = merged.get(key)
            if current is None:
                merged[key] = {**control, "scenarios": [scenario]}
                continue
            current["scenarios"].append(scenario)
            # O pior veredito vence; empate mantem o primeiro visto.
            if _VERDICT_RANK.get(control["verdict"], 9) < _VERDICT_RANK.get(current["verdict"], 9):
                scenarios = current["scenarios"]
                merged[key] = {**control, "scenarios": scenarios}
    return list(merged.values())


def build_inventory(scenarios: bool = True, only: list[str] | None = None) -> dict[str, Any]:
    """``only`` escolhe e ORDENA os cenarios; repetir um nome roda-o duas vezes.

    Os testes de estabilidade dependem disso: reordenar ou duplicar um cenario
    nao pode mudar identidade nem contagem.
    """
    paths = scenario_paths() if scenarios else []
    if only is not None:
        by_name = {path.stem: path for path in paths}
        paths = [by_name[name] for name in only]
    if paths:
        runs = [run_probe(scenario=path) for path in paths]
        controls = merge_scenarios(runs)
        probe = {"context": {**runs[0]["context"], "scenarioCount": len(runs)}}
    else:
        probe = run_probe()
        controls = probe["controls"]

    by_verdict: dict[str, int] = {}
    by_surface: dict[str, dict[str, int]] = {}
    for control in controls:
        verdict = str(control.get("verdict", "not-probed"))
        by_verdict[verdict] = by_verdict.get(verdict, 0) + 1
        surface = str(control.get("surface", "?"))
        by_surface.setdefault(surface, {})
        by_surface[surface][verdict] = by_surface[surface].get(verdict, 0) + 1

    failures = [control for control in controls if control.get("verdict") in FAILING_VERDICTS]
    # Uma superfície só está "coberta" quando nenhum dos seus controles ficou
    # sem sondar. Declarar cobertura com not-probed dentro seria afirmar o que
    # não foi medido.
    fully_probed = sorted(
        surface for surface, counts in by_surface.items() if counts.get("not-probed", 0) == 0
    )
    explicit = [c for c in controls if c.get("objectName")]
    seen_counts = [len(set(c.get("scenarios", []))) for c in controls]
    return {
        "schemaVersion": 3,
        "kind": "steamzero-ui-control-matrix",
        "context": probe["context"],
        "scenarios": [path.stem for path in paths],
        # Metricas de identidade: sem elas nao da para saber quanto da matriz
        # se apoia no fallback estrutural, que e o pedaco fragil.
        "explicitIdentityCount": len(explicit),
        "fallbackIdentityCount": len(controls) - len(explicit),
        "identityCollisionCount": len(controls) - len({c["controlId"] for c in controls}),
        "controlsSeenInMultipleScenarios": sum(1 for n in seen_counts if n > 1),
        "controlsSeenInOneScenario": sum(1 for n in seen_counts if n == 1),
        "notProbedCount": by_verdict.get("not-probed", 0),
        "controlCount": len(controls),
        "surfaceCount": len(by_surface),
        "verdictCounts": by_verdict,
        "bySurface": by_surface,
        "fullyProbedSurfaces": fully_probed,
        "failures": failures,
        "controls": controls,
    }


def render_markdown(inventory: dict[str, Any]) -> str:
    context = inventory["context"]
    lines = [
        "# Matriz de controles — árvore QML viva",
        "",
        f"- contexto: `{context.get('viewport')}` · tema `{context.get('themeId')}`"
        f" · alto contraste `{context.get('highContrast')}`"
        f" · dados `{context.get('dataOrigin')}`",
        f"- controles inventariados: **{inventory['controlCount']}**"
        f" em **{inventory['surfaceCount']}** superfícies",
        f"- veredito: `{inventory['verdictCounts']}`",
        "",
        "| Tela | Controle | Label | AccessibleName | Enabled | ActionId | "
        "Efeito observável | Resultado |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for control in inventory["controls"]:
        lines.append(
            "| {surface} | {kind} | {label} | {accessibleName} | {enabled} | "
            "`{contract}` | {effect} | **{verdict}** |".format(
                surface=control.get("surface", ""),
                kind=control.get("kind", ""),
                label=(control.get("label") or "—").replace("\n", " "),
                accessibleName=(control.get("accessibleName") or "—").replace("\n", " "),
                enabled=control.get("enabled"),
                contract=control.get("attemptedContract") or "—",
                effect=control.get("probeNote")
                or ("mudou estado" if control.get("changedState") else "—"),
                verdict=control.get("verdict", "not-probed"),
            )
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--markdown", type=Path, default=None)
    args = parser.parse_args(argv)

    inventory = build_inventory()
    if args.json:
        args.json.write_text(
            json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    if args.markdown:
        args.markdown.write_text(render_markdown(inventory), encoding="utf-8")

    print(json.dumps(inventory["verdictCounts"], indent=2, ensure_ascii=False))
    print(f"controles: {inventory['controlCount']} em {inventory['surfaceCount']} superfícies")
    print(f"superfícies sem pendência de sondagem: {inventory['fullyProbedSurfaces']}")
    for failure in inventory["failures"]:
        print(
            f"  REPROVA {failure['verdict']}: {failure['surface']} → "
            f"{failure.get('label') or failure.get('accessibleName')!r}"
        )
    return 1 if inventory["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
