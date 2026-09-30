"""Converte as citacoes `arquivo:NNN` driftadas em referencias ao simbolo.

Este corte inseriu 7 linhas em `Main.qml` (bloco `esdeImport*`) e 38 em
`ThemeEditorPanel.qml` (contrato de geracao do ES-DE), entao toda prosa escrita
contra `c4975979` endereca agora outra linha. A conferencia previa (79-alvos-drift)
confirmou, para cada uma, o conteudo que o numero apontava em HEAD: todas estavam
certas quando escritas — e todas eram substitutiveis por um simbolo estavel.

Cada entrada e (arquivo, linha, trecho-antigo, trecho-novo) e so se aplica se o
trecho antigo estiver EXATAMENTE naquela linha: nada de busca cega. A saida e a
conta por arquivo, mais as linhas que passaram de 88 colunas (QML) ou 100 (Python)
depois da substiticao — essas sao reenvolvidas a mao.
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path("/home/misael/Projects/Steam Zero/Canonical/2026-09-21")

# fmt: off
TABELA = [
    # ---- gate QML desta frente -------------------------------------------------
    ("tests/qml/check_shell_esde_import_late_response.qml", 10,
     "`ThemeEditorPanel.qml:210-275`", "`ThemeEditorPanel.qml`, trio `*EsdeImport()`"),
    ("tests/qml/check_shell_esde_import_late_response.qml", 11,
     "`ThemeEditorPanel.qml:349-395`", "`ThemeEditorPanel.qml`, trio `*RetrofeImport()`"),
    ("tests/qml/check_shell_esde_import_late_response.qml", 17,
     "`Main.qml:2894`", "`Main.qml`, `esdeImportDialog`"),
    ("tests/qml/check_shell_esde_import_late_response.qml", 20,
     "(`Main.qml:1001`, `timeout` `:1012`)", "(o `request()` de `Main.qml`, `xhr.timeout`)"),
    ("tests/qml/check_shell_esde_import_late_response.qml", 26,
     "`ThemeEditorPanel.qml:265`", "`applyEsdeImport()`"),
    ("tests/qml/check_shell_esde_import_late_response.qml", 30,
     "`ThemeEditorPanel.qml:1028`", "`esdeImportDialog.onClosed` do painel"),
    ("tests/qml/check_shell_esde_import_late_response.qml", 34,
     "`Main.qml:1134`", "o `requestAction`"),
    ("tests/qml/check_shell_esde_import_late_response.qml", 38,
     "`Main.qml:1134`", "`requestAction`"),
    ("tests/qml/check_shell_esde_import_late_response.qml", 40,
     "`ThemeEditorPanel.qml:353/393`", "o par `*RetrofeImport()`"),
    ("tests/qml/check_shell_esde_import_late_response.qml", 323,
     "`Main.qml:6562`", "`Main.qml`"),
    ("tests/qml/check_shell_esde_import_late_response.qml", 347,
     "`ThemeEditorPanel.qml:1028`", "`esdeImportDialog.onClosed` do painel"),
    ("tests/qml/check_shell_esde_import_late_response.qml", 464,
     "`ThemeEditorPanel.qml:221`", "`panel.esdeImportSource`"),
    ("tests/qml/check_shell_esde_import_late_response.qml", 569,
     "`Main.qml:2991`", "o campo `esdeImportSourceField`"),
    ("tests/qml/check_shell_esde_import_late_response.qml", 656,
     "`ThemeEditorPanel.qml:1126-1139`", "o `Repeater` de `esdeImportSchemes`"),
    ("tests/qml/check_shell_esde_import_late_response.qml", 763,
     "`ThemeEditorPanel.qml:229`", "callback de `inspectEsdeImport`"),
    ("tests/qml/check_shell_esde_import_late_response.qml", 815,
     "`ThemeEditorPanel.qml:1028`", "`esdeImportDialog.onClosed`"),
    ("tests/qml/check_shell_esde_import_late_response.qml", 817,
     "`Main.qml:1134`", "o `requestAction`"),
    ("tests/qml/check_shell_esde_import_late_response.qml", 907,
     "`ThemeEditorPanel.qml:264`", "`applyEsdeImport()`"),
    ("tests/qml/check_shell_esde_import_late_response.qml", 923,
     "`Main.qml:1134`", "O `requestAction`"),
    ("tests/qml/check_shell_esde_import_late_response.qml", 926,
     "`ThemeEditorPanel.qml:220-245`", "`inspectEsdeImport()`"),
    ("tests/qml/check_shell_esde_import_late_response.qml", 968,
     "`ThemeEditorPanel.qml:393`", "o `*RetrofeImport()`"),
    ("tests/qml/check_shell_esde_import_late_response.qml", 1068,
     "`Main.qml:3096`", "`esdeImportDialog.close()`"),
    ("tests/qml/check_shell_esde_import_late_response.qml", 1073,
     "`Main.qml:3096`", "`esdeImportDialog.close()`"),
    ("tests/qml/check_shell_esde_import_late_response.qml", 1083,
     "`Main.qml:2898-2906`", "`esdeImportDialog.onClosed`"),
    ("tests/qml/check_shell_esde_import_late_response.qml", 1137,
     "`Main.qml:3095`", "o `root.notify` do apply"),

    # ---- gate Python desta frente ----------------------------------------------
    ("tests/integration/test_ui_shell_esde_import_late_response.py", 5,
     "`ThemeEditorPanel.qml:210-275`", "`ThemeEditorPanel.qml`, trio `*EsdeImport()`"),
    ("tests/integration/test_ui_shell_esde_import_late_response.py", 17,
     "(`Main.qml:1001`, `timeout`", "(o `request()` de `Main.qml`, `xhr.timeout`"),
    ("tests/integration/test_ui_shell_esde_import_late_response.py", 27,
     "`ThemeEditorPanel.qml:204`", "`refreshThemeList()`"),
    ("tests/integration/test_ui_shell_esde_import_late_response.py", 131,
     "`Main.qml:1134`", "O `requestAction`"),
    ("tests/integration/test_ui_shell_esde_import_late_response.py", 217,
     "`ThemeEditorPanel.qml:1134`", "o texto `modelData.scheme`"),
    ("tests/integration/test_ui_shell_esde_import_late_response.py", 354,
     "`ThemeEditorPanel.qml:262-269`", "`applyEsdeImport()`"),
    ("tests/integration/test_ui_shell_esde_import_late_response.py", 372,
     "`Main.qml:1011`", "`request()`"),
    ("tests/integration/test_ui_shell_esde_import_late_response.py", 871,
     "`Main.qml:853-859`", "`restoreDialogFocus()`"),
    ("tests/integration/test_ui_shell_esde_import_late_response.py", 919,
     "`Main.qml:1076`", "`backendAction()`"),
    ("tests/integration/test_ui_shell_esde_import_late_response.py", 1015,
     "`Main.qml:1134`", "`requestAction`"),

    # ---- frentes vizinhas cuja prosa este corte deslocou ------------------------
    ("tests/qml/check_shell_retrofe_import_late_response.qml", 17,
     "(`Main.qml:1001`, `timeout` `:1012`)", "(o `request()` de `Main.qml`, `xhr.timeout`)"),
    ("tests/qml/check_shell_retrofe_import_late_response.qml", 25,
     "`ThemeEditorPanel.qml:1215`", "`retrofeImportDialog.onClosed`"),
    ("tests/qml/check_shell_retrofe_import_late_response.qml", 28,
     "`Main.qml:1134`", "o `requestAction`"),
    ("tests/qml/check_shell_retrofe_import_late_response.qml", 46,
     "`Main.qml:1134`", "`requestAction`"),
    ("tests/qml/check_shell_retrofe_import_late_response.qml", 77,
     "`Main.qml:853-859`", "`restoreDialogFocus()`"),
    ("tests/qml/check_shell_retrofe_import_late_response.qml", 320,
     "`Main.qml:6563`", "`Main.qml`"),
    ("tests/qml/check_shell_retrofe_import_late_response.qml", 345,
     "`ThemeEditorPanel.qml:1215`", "`retrofeImportDialog.onClosed`"),
    ("tests/qml/check_shell_retrofe_import_late_response.qml", 451,
     "`ThemeEditorPanel.qml:350`", "`panel.retrofeImportSource`"),
    ("tests/qml/check_shell_retrofe_import_late_response.qml", 543,
     "`ThemeEditorPanel.qml:1340`", "o `Repeater` de `retrofeImportLayouts`"),
    ("tests/qml/check_shell_retrofe_import_late_response.qml", 652,
     "`ThemeEditorPanel.qml:1309`", "`themeImportRetrofeInspect`"),
    ("tests/qml/check_shell_retrofe_import_late_response.qml", 655,
     "`Main.qml:1134`", "o `requestAction`"),
    ("tests/qml/check_shell_retrofe_import_late_response.qml", 764,
     "`ThemeEditorPanel.qml:427`", "`applyRetrofeImport()`"),
    ("tests/qml/check_shell_retrofe_import_late_response.qml", 886,
     "`ThemeEditorPanel.qml:1466`", "`themeImportRetrofeApply`"),
    ("tests/qml/check_shell_retrofe_import_late_response.qml", 942,
     "`ThemeEditorPanel.qml:1309`", "`themeImportRetrofeInspect`"),
    ("tests/qml/check_shell_retrofe_import_late_response.qml", 945,
     "`Main.qml:1134`", "`requestAction`"),

    ("tests/integration/test_ui_shell_retrofe_import_late_response.py", 10,
     "(`Main.qml:1001`, `timeout` `:1012`)", "(o `request()` de `Main.qml`, `xhr.timeout`)"),
    ("tests/integration/test_ui_shell_retrofe_import_late_response.py", 19,
     "`ThemeEditorPanel.qml:204`", "`refreshThemeList()`"),
    ("tests/integration/test_ui_shell_retrofe_import_late_response.py", 119,
     "`Main.qml:1134`", "O `requestAction`"),
    ("tests/integration/test_ui_shell_retrofe_import_late_response.py", 355,
     "`Main.qml:1011`", "`request()`"),
    ("tests/integration/test_ui_shell_retrofe_import_late_response.py", 743,
     "`Main.qml:853-859`", "`restoreDialogFocus()`"),
    ("tests/integration/test_ui_shell_retrofe_import_late_response.py", 791,
     "`Main.qml:1076`", "`backendAction()`"),

    ("tests/qml/check_shell_esde_import_dialog_journey.qml", 20,
     "`Main.qml:2896`", "`Main.qml`, `esdeImportDialog`"),
    ("tests/qml/check_shell_esde_import_dialog_journey.qml", 56,
     "`Main.qml:852-860`", "`restoreDialogFocus()`"),
    ("tests/qml/check_shell_esde_import_dialog_journey.qml", 470,
     "`Main.qml:852-860`", "`restoreDialogFocus()`"),
    ("tests/qml/check_shell_esde_import_dialog_journey.qml", 616,
     "`Main.qml:3000`", "o aviso `theme-import-esde-notice`"),

    ("tests/integration/test_ui_shell_esde_import_dialog.py", 5,
     "`Main.qml:2896`", "outro `esdeImportDialog`, em `Main.qml`"),
    ("tests/integration/test_ui_shell_esde_import_dialog.py", 771,
     "(`Main.qml:852-860`)", "(`restoreDialogFocus()`)"),
    ("tests/integration/test_ui_shell_esde_import_dialog.py", 830,
     "`Main.qml:2896`", "`Main.qml`"),
]
# fmt: on

LIMITE = {"qml": 88, "py": 100}
por_arquivo: dict[str, int] = {}
estouradas: list[str] = []
faltando: list[str] = []

for arq, linha, antigo, novo in TABELA:
    caminho = ROOT / arq
    corpo = caminho.read_text(encoding="utf-8").splitlines()
    atual = corpo[linha - 1]
    if antigo not in atual:
        faltando.append(f"{arq}:{linha}  PROCURADO {antigo!r}  LINHA {atual.strip()[:100]!r}")
        continue
    substituida = atual.replace(antigo, novo)
    limite = LIMITE["py" if arq.endswith(".py") else "qml"]
    if len(substituida) > limite:
        estouradas.append(f"{arq}:{linha}  {len(substituida)} cols: {substituida.strip()}")
    corpo[linha - 1] = substituida
    caminho.write_text("\n".join(corpo) + "\n", encoding="utf-8")
    por_arquivo[arq] = por_arquivo.get(arq, 0) + 1

print("APLICADAS por arquivo:")
for arq, n in por_arquivo.items():
    print(f"  {n:>3}  {arq}")
print(f"TOTAL: {sum(por_arquivo.values())} de {len(TABELA)}")
print(f"\nNAO ENCONTRADAS ({len(faltando)}):")
for f in faltando:
    print("  " + f)
print(f"\nESTOURAM O LARGAMENTO ({len(estouradas)}):")
for e in estouradas:
    print("  " + e)
