"""Reenvolve as duas linhas que a conversao por simbolo deixou acima de 88 colunas.

`check_shell_retrofe_import_late_response.qml` tinha quatro comentarios acima do
largamento ANTES do corte (89 colunas, heranca dos elos anteriores); o corte passou de
quatro para cinco porque duas substituicoes juntaram frases que o numero curto
distribuia em tres linhas:

  * `:1340` -> "o `Repeater` de `retrofeImportLayouts`", duplicando o `Repeater` que a
    linha ja nomeava (97 colunas);
  * `:1265`/`:1287` -> "`themeImportRetrofeSource` e o `Binding` que o espelha", cuja
    linha ficou em 116 colunas.

Reenvolver e reescrever a redundancia: nenhuma palavra do argumento muda.
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path("/home/misael/Projects/Steam Zero/Canonical/2026-09-21")
ARQ = "tests/qml/check_shell_retrofe_import_late_response.qml"
LIMITE = 88

TRECHOS = [
    (
        "        /// diálogo: o `Repeater` (o `Repeater` de `retrofeImportLayouts`) monta um `RadioButton`\n"
        "        /// por entrada, e é isso que torna a contagem visível — não o `length` de um\n"
        "        /// array que ninguém vê.\n",
        "        /// diálogo: o `Repeater` de `retrofeImportLayouts` monta um\n"
        "        /// `RadioButton` por entrada, e é isso que torna a contagem visível — não o\n"
        "        /// `length` de um array que ninguém vê.\n",
    ),
    (
        "        /// (`themeImportRetrofeSource` e o `Binding` que o espelha). A primeira\n"
        "        /// edição pelo teclado ou por atribuição INTERROMPE a binding, então o `resetRetrofeImport()` do `onClosed`\n"
        "        /// limpa o estado e o pixel do campo continua mostrando a última origem. O\n"
        "        /// botão \"Examinar\" lê o ESTADO (`enabled` de `themeImportRetrofeInspect`): o\n"
        "        /// usuário reabre, vê um caminho no\n"
        "        /// campo e um botão desabilitado que ele não sabe explicar. Não é a resposta\n"
        "        /// tardia — é a superfície mentindo sobre o próprio estado.\n",
        "        /// (`themeImportRetrofeSource` e o `Binding` que o espelha). A primeira\n"
        "        /// edição pelo teclado ou por atribuição INTERROMPE a binding, então o\n"
        "        /// `resetRetrofeImport()` do `onClosed` limpa o estado e o pixel do campo\n"
        "        /// continua mostrando a última origem. O botão \"Examinar\" lê o ESTADO\n"
        "        /// (`enabled` de `themeImportRetrofeInspect`): o usuário reabre, vê um\n"
        "        /// caminho no campo e um botão desabilitado que ele não sabe explicar. Não é\n"
        "        /// a resposta tardia — é a superfície mentindo sobre o próprio estado.\n",
    ),
]


def main() -> int:
    caminho = ROOT / ARQ
    texto = caminho.read_text(encoding="utf-8")
    problemas: list[str] = []
    aplicadas = 0
    for antigo, novo in TRECHOS:
        n = texto.count(antigo)
        if n != 1:
            if texto.count(novo) == 1:
                problemas.append("já aplicada")
            else:
                problemas.append(f"{n} ocorrências de {antigo[:50]!r}")
            continue
        largos = [f"{len(l)}>{LIMITE}: {l.strip()[:60]}" for l in novo.splitlines()
                  if len(l) > LIMITE]
        if largos:
            problemas.extend(largos)
            continue
        texto = texto.replace(antigo, novo)
        aplicadas += 1
    if not problemas:
        caminho.write_text(texto, encoding="utf-8")
    print(f"APLICADAS: {aplicadas} de {len(TRECHOS)}")
    print(f"PROBLEMAS ({len(problemas)}):")
    for p in problemas:
        print("  " + p)
    return 1 if problemas else 0


if __name__ == "__main__":
    raise SystemExit(main())
