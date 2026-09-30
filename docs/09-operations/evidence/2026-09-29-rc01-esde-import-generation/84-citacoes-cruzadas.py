"""Fecha as cinco ultimas citacoes numericas: entre arquivos de teste do proprio lote.

O 83 converteu o que apontava para o produto; sobraram cinco pontas que um arquivo de
teste aponta para OUTRO arquivo de teste, e o 83 mudou a contagem de linhas delas.
Troca por string unica, como no 83.
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path("/home/misael/Projects/Steam Zero/Canonical/2026-09-21")
LIMITE = {"qml": 88, "py": 100}

REPL: list[tuple[str, str, str]] = [
    (
        "tests/qml/check_shell_esde_import_late_response.qml",
        "//     `Item { Main {} }`, como em `check_shell_esde_import_dialog_journey.qml:77`;",
        "//     `Item { Main {} }`, como em `check_shell_esde_import_dialog_journey.qml`;",
    ),
    (
        "tests/qml/check_shell_esde_import_late_response.qml",
        "        /// (`check_shell_esde_import_dialog_journey.qml:456-468`) percorre: a seção é\n",
        "        /// (`check_shell_esde_import_dialog_journey.qml`, em `triggerButton()`) percorre:\n"
        "        /// a seção é\n",
    ),
    (
        "tests/qml/check_shell_retrofe_import_late_response.qml",
        "//     `Item { Main {} }`, como em `check_shell_esde_import_dialog_journey.qml:77`;",
        "//     `Item { Main {} }`, como em `check_shell_esde_import_dialog_journey.qml`;",
    ),
    (
        "tests/qml/check_shell_retrofe_import_late_response.qml",
        "        /// Limpeza controlada, não prova. A ordem é a da 4ª fatia (`resetSurface`\n"
        "        /// em `check_shell_esde_import_dialog_journey.qml:405`): QUIESCER antes de\n",
        "        /// Limpeza controlada, não prova. A ordem é a da 4ª fatia (o\n"
        "        /// `resetSurface` de `check_shell_esde_import_dialog_journey.qml`): QUIESCER\n"
        "        /// antes de\n",
    ),
    (
        "tests/integration/test_ui_shell_home_first_fold.py",
        "UX-07 (`test_ui_shell_esde_import_dialog.py:925`).",
        "UX-07 (`test_a_jornada_esde_do_shell_cabe_no_viewport_dado`, em\n"
        "`test_ui_shell_esde_import_dialog.py`).",
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
    raise SystemExit(main())
