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


def run_probe(timeout: int = 400) -> dict[str, Any]:
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
    completed = subprocess.run(
        [QML, str(ROOT / "tools" / "ui_control_probe.qml")],
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


def build_inventory() -> dict[str, Any]:
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
    return {
        "schemaVersion": 1,
        "kind": "steamzero-ui-control-matrix",
        "context": probe["context"],
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
