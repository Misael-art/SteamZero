"""Reenvolve as tres linhas que as substituicoes de citacao estouraram.

83/84 trocaram numero de linha por simbolo; onde o simbolo e mais longo que o
numero, a frase passou do limite (100 colunas no Python, 88 no QML). Uma das
linhas e um docstring, portanto `ruff check src tests tools` -- que o CI roda --
reprova por E501. Reenvolver e o unico conserto: nenhuma palavra muda.

Cada reenvolvimento chaveado pelo trecho inteiro, com o texto verificado linha a
linha antes e depois.
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path("/home/misael/Projects/Steam Zero/Canonical/2026-09-21")

TRECHOS = [
    (
        "tests/integration/test_ui_shell_esde_import_late_response.py",
        100,
        "* **a re-listagem de temas como evento da ponte** — `refreshThemeList()`\n"
        "  dispara `GET /theme/list` na callback de sucesso do apply. Num diálogo já "
        "fechado isso é invisível na superfície; a asserção\n"
        '  é "nenhum `GET /theme/list` depois do último `POST /theme/import/esde/apply`", e\n',
        "* **a re-listagem de temas como evento da ponte** — `refreshThemeList()`\n"
        "  dispara `GET /theme/list` na callback de sucesso do apply. Num diálogo já\n"
        "  fechado isso é invisível na superfície; a asserção é \"nenhum `GET /theme/list`\n"
        "  depois do último `POST /theme/import/esde/apply`\", e\n",
    ),
    (
        "tests/qml/check_shell_esde_import_dialog_journey.qml",
        88,
        "// Por que este diálogo e não outro: `Main.qml`, `esdeImportDialog` é o segundo "
        "exemplar do\n"
        "// importador ES-DE no produto (o primeiro, corrigido na 3ª fatia, vive em\n"
        "// `ThemeEditorPanel.qml`, `esdeImportDialog`). Aqui o corpo é um\n"
        "// `ColumnLayout` com\n",
        "// Por que este diálogo e não outro: `Main.qml`, `esdeImportDialog` é o segundo\n"
        "// exemplar do importador ES-DE no produto (o primeiro, corrigido na 3ª fatia,\n"
        "// vive em `ThemeEditorPanel.qml`, `esdeImportDialog`). Aqui o corpo é um\n"
        "// `ColumnLayout` com\n",
    ),
    (
        "tests/qml/check_shell_esde_import_dialog_journey.qml",
        88,
        "            /// não há esquema nenhum (o aviso `theme-import-esde-notice`) ou a "
        "lista, com a requisição\n"
        "            /// fora de voo.\n",
        "            /// não há esquema nenhum (o aviso `theme-import-esde-notice`) ou a\n"
        "            /// lista, com a requisição fora de voo.\n",
    ),
]


def main() -> int:
    problemas: list[str] = []
    for arq, limite, antigo, novo in TRECHOS:
        caminho = ROOT / arq
        texto = caminho.read_text(encoding="utf-8")
        n = texto.count(antigo)
        if n != 1:
            problemas.append(f"{arq}: {n} ocorrencias do trecho antigo")
            continue
        for linha in novo.splitlines():
            if len(linha) > limite:
                problemas.append(f"{arq}: {len(linha)} > {limite}: {linha[:70]}")
        caminho.write_text(texto.replace(antigo, novo), encoding="utf-8")
        print(f"reenvolvido em {arq} (limite {limite})")
    print(f"PROBLEMAS ({len(problemas)}):")
    for p in problemas:
        print("  " + p)
    return 1 if problemas else 0


if __name__ == "__main__":
    raise SystemExit(main())
