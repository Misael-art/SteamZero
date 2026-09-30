"""Converte as tres ultimas citacoes numericas cruas (`:NNN`) em referencia de simbolo.

O auditorio 82 procurava `arquivo:NNN`; uma `:NNN` solta nao era pega. Sobraram tres,
cada uma apontando para um arquivo nomeado na frase anterior, e o corte deslocou o
numero de duas delas:

  * `:2993-3000` era o callback de sucesso do examine na RAIZ em `c4975979` — hoje a
    mesma prosa diz "Hoje o callback escreve por cima", o que a arvore desmente: o
    corte acrescentou a guarda de geracao. Pinar ao commit medido e o conserto;
  * `:250-252` era `applyEsdeImport()` de `ThemeEditorPanel.qml`, que o corte moveu;
  * `:209-217` e `theme_import_retrofe.py`, arquivo que o corte NAO tocou — o numero
    continua certo, mas sem nome de arquivo a prosa so se decide por contexto.

Nos dois primeiros casos a frase no tempo presente descrevia o vermelho; vira passado
pinado a `c4975979`, como o cabecalho do proprio arquivo ja faz.
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path("/home/misael/Projects/Steam Zero/Canonical/2026-09-21")
LIMITE = {"qml": 88, "py": 100}

TRECHOS = [
    (
        "tests/qml/check_shell_esde_import_late_response.qml",
        "        /// 2 — a resposta chega depois do fechamento. Este é o vermelho da fatia:\n"
        "        /// hoje o callback (callback de `inspectEsdeImport`) escreve em cima de uma\n"
        "        /// superfície fechada, sem conferir geração nenhuma.\n",
        "        /// 2 — a resposta chega depois do fechamento. Este é o vermelho da fatia:\n"
        "        /// em `c4975979` o callback de `inspectEsdeImport()` escrevia em cima de uma\n"
        "        /// superfície fechada, sem conferir geração nenhuma.\n",
    ),
    (
        "tests/qml/check_shell_esde_import_late_response.qml",
        "        /// (`inspectEsdeImport()`) arma a bandeira ANTES de despachar e não tem\n"
        "        /// rollback nenhum (o molde RetroFE, `inspectRetrofeImport()`, tem) — hoje o\n"
        "        /// clique\n"
        "        /// recusado deixa \"Importando…\" armado sem nenhum pedido seu por trás, e a\n"
        "        /// resposta do pedido antigo (que a recusa tentava repetir) ainda reescreve o\n"
        "        /// resultado do pedido que produziu algo.\n",
        "        /// (`inspectEsdeImport()`) arma a bandeira ANTES de despachar e em\n"
        "        /// `c4975979` não tinha rollback nenhum (o molde RetroFE,\n"
        "        /// `inspectRetrofeImport()`, tinha) — o clique recusado deixava\n"
        "        /// \"Importando…\" armado sem nenhum pedido seu por trás, e a resposta do\n"
        "        /// pedido antigo (que a recusa tentava repetir) ainda reescrevia o\n"
        "        /// resultado do pedido que produzia algo.\n",
    ),
    (
        "tests/qml/check_shell_esde_import_late_response.qml",
        "        /// assim os deve deixar. Hoje o callback escreve por cima (`:2993-3000`).\n",
        "        /// assim os deve deixar. Em `c4975979` o callback de sucesso do examine da\n"
        "        /// raiz escrevia por cima.\n",
    ),
    (
        "tests/integration/test_ui_shell_esde_import_late_response.py",
        "    apply devolve (`:250-252`). O marcador da alavanca viaja em `scheme`/`id`/`name`\n",
        "    apply devolve (`applyEsdeImport()`, em `ThemeEditorPanel.qml`). O marcador da\n"
        "    alavanca viaja em `scheme`/`id`/`name`\n",
    ),
    (
        "tests/integration/test_ui_shell_retrofe_import_late_response.py",
        "    `report`, `assets`, `degraded` e `scene` (`:209-217`). O `name` carrega o prefixo\n",
        "    `report`, `assets`, `degraded` e `scene` (o `layouts.append` de `inspect()` de\n"
        "    `theme_import_retrofe.py`). O `name` carrega o prefixo\n",
    ),
]


def main() -> int:
    aplicadas: list[str] = []
    problemas: list[str] = []
    for arq, antigo, novo in TRECHOS:
        caminho = ROOT / arq
        texto = caminho.read_text(encoding="utf-8")
        n = texto.count(antigo)
        if n != 1:
            if texto.count(novo) == 1:
                problemas.append(f"{arq}: ja aplicada")
            else:
                problemas.append(f"{arq}: {n} ocorrencias de {antigo[:60]!r}")
            continue
        limite = LIMITE["py" if arq.endswith(".py") else "qml"]
        largos = [f"{len(l)}>{limite}: {l.strip()[:60]}" for l in novo.splitlines()
                  if len(l) > limite]
        if largos:
            problemas.extend(f"{arq}: {w}" for w in largos)
            continue
        caminho.write_text(texto.replace(antigo, novo), encoding="utf-8")
        aplicadas.append(arq)
    print(f"APLICADAS: {len(aplicadas)} de {len(TRECHOS)}")
    for a in aplicadas:
        print("  " + a)
    print(f"PROBLEMAS ({len(problemas)}):")
    for p in problemas:
        print("  " + p)
    return 1 if problemas else 0


if __name__ == "__main__":
    raise SystemExit(main())
