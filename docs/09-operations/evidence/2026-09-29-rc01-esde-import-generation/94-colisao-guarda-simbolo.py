"""Fecha a colisão entre citação de símbolo e guarda de substring no fonte do harness.

Causa medida (log `93-…-antes.log`, batendo com o `92-…log` do pytest): as "guardas de
intenção" conferem o arquivo do harness por substring — `assert "applyEsdeImport("
not in fonte` — e substring não sabe o que é comentário. O lote escreveu o símbolo do
produto em prosa de comentário com o parêntese de chamada, e a guarda acendeu.

Correção pelo lado da prosa, não pelo da guarda: estreitar a guarda seria perder a
força justamente onde ela é conservadora (qualquer chamada real tem parêntese). A
citação fica `applyEsdeImport` — continua exata e grepável, e deixa de ler como
invocação.

Na mão contrária, o texto da falha ganha a convenção: sem ela, quem citar o símbolo
numa nota do harness vê "o harness chama o importador direto" e não tem como saber
que estava num comentário. Mensagem e comentário, nenhum deles condição de asserção.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path("/home/misael/Projects/Steam Zero/Canonical/2026-09-21")
LIMITE = {"qml": 88, "py": 100}

REPL: list[tuple[str, str, str]] = [
    # --- prosa do harness ES-DE: símbolo sem o parêntese de chamada ---
    (
        "tests/qml/check_shell_esde_import_late_response.qml",
        "//      callback de sucesso de `applyEsdeImport()`) — e a ponte TEM de registrar",
        "//      callback de sucesso de `applyEsdeImport`) — e a ponte TEM de registrar",
    ),
    (
        "tests/qml/check_shell_esde_import_late_response.qml",
        "//      mesma callback de `applyEsdeImport()`);",
        "//      mesma callback de `applyEsdeImport`);",
    ),
    (
        "tests/qml/check_shell_esde_import_late_response.qml",
        "// tem de RESTAURAR esse valor (não deixá-la armada, como `inspectEsdeImport()`",
        "// tem de RESTAURAR esse valor (não deixá-la armada, como `inspectEsdeImport`",
    ),
    (
        "tests/qml/check_shell_esde_import_late_response.qml",
        "        /// em `c4975979` o callback de `inspectEsdeImport()` escrevia em cima de uma",
        "        /// em `c4975979` o callback de `inspectEsdeImport` escrevia em cima de uma",
    ),
    (
        "tests/qml/check_shell_esde_import_late_response.qml",
        "            // re-listagem de temas (`applyEsdeImport()`, `refreshThemeList()`",
        "            // re-listagem de temas (`applyEsdeImport`, `refreshThemeList()`",
    ),
    (
        "tests/qml/check_shell_esde_import_late_response.qml",
        "        /// (`inspectEsdeImport()`) arma a bandeira ANTES de despachar e em",
        "        /// (`inspectEsdeImport`) arma a bandeira ANTES de despachar e em",
    ),
    # --- prosa do harness RetroFE ---
    (
        "tests/qml/check_shell_retrofe_import_late_response.qml",
        "            // de temas (`applyRetrofeImport()`, `panel.refreshThemeList()`). A prova",
        "            // de temas (`applyRetrofeImport`, `panel.refreshThemeList()`). A prova",
    ),
    # --- a convenção aparece na falha ---
    (
        "tests/integration/test_ui_shell_esde_import_late_response.py",
        '    assert "inspectEsdeImport(" not in fonte, (\n'
        '        "o harness chama o importador direto: o pedido tem de sair pelo clique real"\n'
        "    )\n",
        '    #: A conferência é por substring do fonte inteiro, comentário incluído: citar\n'
        '    #: o símbolo do produto numa nota do harness se faz sem o parêntese de chamada.\n'
        '    assert "inspectEsdeImport(" not in fonte, (\n'
        '        "o harness chama o importador direto: o pedido tem de sair pelo clique real "\n'
        '        "(a guarda é substring e vale para comentário — cite o símbolo sem parêntese)"\n'
        "    )\n",
    ),
    (
        "tests/integration/test_ui_shell_retrofe_import_late_response.py",
        '    assert "inspectRetrofeImport(" not in fonte, (\n'
        '        "o harness chama o importador direto: o pedido tem de sair pelo clique real"\n'
        "    )\n",
        '    #: A conferência é por substring do fonte inteiro, comentário incluído: citar\n'
        '    #: o símbolo do produto numa nota do harness se faz sem o parêntese de chamada.\n'
        '    assert "inspectRetrofeImport(" not in fonte, (\n'
        '        "o harness chama o importador direto: o pedido tem de sair pelo clique real "\n'
        '        "(a guarda é substring e vale para comentário — cite o símbolo sem parêntese)"\n'
        "    )\n",
    ),
]


def main() -> int:
    aplicadas: list[str] = []
    problemas: list[str] = []
    estouradas: list[str] = []
    for arq, old, new in REPL:
        caminho = ROOT / arq
        texto = caminho.read_text(encoding="utf-8")
        n = texto.count(old)
        if n != 1:
            problemas.append(f"{arq}: {n} ocorrencias de {old[:70]!r}")
            continue
        limite = LIMITE["py" if arq.endswith(".py") else "qml"]
        for linha in new.splitlines():
            if len(linha) > limite:
                estouradas.append(f"{arq}: {len(linha)} cols  {linha.strip()[:80]}")
        caminho.write_text(texto.replace(old, new), encoding="utf-8")
        aplicadas.append(arq)
    print(f"APLICADAS: {len(aplicadas)} de {len(REPL)}")
    for a in aplicadas:
        print("  " + a)
    print(f"PROBLEMAS ({len(problemas)}):")
    for p in problemas:
        print("  " + p)
    print(f"ESTOURAM O LARGAMENTO ({len(estouradas)}):")
    for e in estouradas:
        print("  " + e)
    return 0 if not problemas and not estouradas else 1


if __name__ == "__main__":
    sys.exit(main())
