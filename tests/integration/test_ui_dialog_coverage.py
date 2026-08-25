# SPDX-License-Identifier: GPL-3.0-or-later
"""Denominador dos diálogos: nenhum modal fica fora da auditoria em silêncio.

`test_ui_dialog_journeys` e `test_ui_dialog_keys` provam as jornadas dos modais
que a sonda alcança. Nenhum dos dois percebe um modal que a sonda **não**
alcança: `tools/ui_dialog_probe.qml` percorre uma lista fixa, e um `Dialog` novo
em `Main.qml` simplesmente não entra nela.

Este gate é estático de propósito — não precisa de runtime QML e por isso roda
no job de testes e cobertura, junto do resto. Ele compara os `Dialog` que
existem com os que estão expostos para sondagem, e obriga a diferença a ser uma
decisão escrita, não um esquecimento.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN_QML = ROOT / "src" / "steamzero" / "ui" / "qml" / "Main.qml"
DIALOG_PROBE = ROOT / "tools" / "ui_dialog_probe.qml"

#: Modais que NÃO são auditados pela sonda de jornadas, com o motivo. Entrar
#: aqui é uma decisão de escopo registrada, não uma forma de baixar o
#: denominador: cada linha precisa dizer por que o modal não é certificável
#: pela sonda.
EXCLUDED: dict[str, str] = {
    "diagnosticsExportDialog": (
        "FileDialog nativo do sistema: a janela é do portal/desktop, não da árvore "
        "QML do produto, e a sonda não pode abri-la nem inspecioná-la offscreen."
    ),
}


def _dialog_ids(source: str) -> list[str]:
    """Ids de todo `Dialog {`/`FileDialog {` declarado no shell."""
    ids: list[str] = []
    for match in re.finditer(r"\b\w*Dialog\s*\{", source):
        tail = source[match.end() : match.end() + 400]
        found = re.search(r"^\s*id:\s*(\w+)", tail, re.MULTILINE)
        if found:
            ids.append(found.group(1))
    return ids


def _exposed_ids(source: str) -> set[str]:
    """Ids alcançáveis de fora de `Main`, via alias.

    Casa pelo ALVO do alias, não pelo nome dele: o shell usa tanto
    `...DialogControl` quanto `...Control`, e um gate que casasse pelo nome
    daria falso vermelho em três modais que já estavam expostos.
    """
    return set(re.findall(r"property alias \w+:\s*(\w*Dialog)\b", source))


def _alias_targets(source: str) -> dict[str, str]:
    return dict(re.findall(r"property alias (\w+):\s*(\w*Dialog)\b", source))


def _journey_aliases(source: str) -> set[str]:
    """Aliases que a sonda de jornadas realmente percorre."""
    return set(re.findall(r'"dialog":\s*(\w+)', source))


def test_every_dialog_is_probeable_or_explicitly_excluded() -> None:
    """Estar exposto não basta: a sonda tem de percorrer o modal.

    Alias sem jornada é alcance sem prova — o modal continuaria fora da
    auditoria, só que de um jeito mais difícil de perceber.
    """
    source = MAIN_QML.read_text(encoding="utf-8")
    declared = _dialog_ids(source)
    assert len(declared) >= 10, f"parser não achou os modais do shell: {declared}"

    aliases = _alias_targets(source)
    journeys = _journey_aliases(DIALOG_PROBE.read_text(encoding="utf-8"))
    walked = {aliases[name] for name in journeys if name in aliases}

    unexposed = sorted(set(declared) - _exposed_ids(source) - set(EXCLUDED))
    unwalked = sorted(set(declared) - walked - set(EXCLUDED))

    assert unexposed == [], (
        f"{len(unexposed)} de {len(declared)} modais não têm alias e são inalcançáveis "
        "de um harness que estende Main:\n  " + "\n  ".join(unexposed)
    )
    assert unwalked == [], (
        f"{len(unwalked)} de {len(declared)} modais não têm jornada em "
        "tools/ui_dialog_probe.qml. Registre a jornada, ou declare a exclusão em "
        "EXCLUDED explicando por quê:\n  " + "\n  ".join(unwalked)
    )


def test_exclusions_are_real_dialogs_and_carry_a_reason() -> None:
    """Exclusão só vale para modal que existe, e com motivo escrito.

    Sem isto, a lista de exclusões viraria o lugar onde a cobertura some: bastaria
    acrescentar um nome para o denominador cair.
    """
    declared = set(_dialog_ids(MAIN_QML.read_text(encoding="utf-8")))
    ghosts = sorted(set(EXCLUDED) - declared)
    assert ghosts == [], f"exclusão para modal que não existe mais: {ghosts}"
    for name, reason in EXCLUDED.items():
        assert len(reason) > 40, f"exclusão de {name} sem motivo suficiente: {reason!r}"
