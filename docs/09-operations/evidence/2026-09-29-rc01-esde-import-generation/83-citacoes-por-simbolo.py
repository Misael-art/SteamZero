"""Converte as citacoes NUMERICAS restantes (e as `:NNN` peladas) em referencias de simbolo.

Motor do 80 por string: cada substituição é um trecho que tem de aparecer UMA UNICA
VEZ no arquivo, sem depender de numero de linha — as trocas do 80 já mudaram a
contagem de linhas dos arquivos. A saida conta por arquivo e mede o largamento
(88 no QML, 100 no Python) de cada linha resultante.

O que muda é prosa: comentario `//`, `///`, `#`, docstring e mensagem de falha. A
asserção em si (condição, valores esperados) não é tocada — isso é conferido a parte
pelo diff, e os gates rodam depois.
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path("/home/misael/Projects/Steam Zero/Canonical/2026-09-21")
LIMITE = {"qml": 88, "py": 100}

REPL: list[tuple[str, str, str]] = [
    # ================= gate QML desta frente =================
    (
        "tests/qml/check_shell_esde_import_late_response.qml",
        "        /// O examine pela rota real. Sem `onAccepted` no campo (`:1075-1084`, ao\n"
        "        /// contrário do campo RetroFE `:1275`), o clique no \"Examinar\" é a ÚNICA\n",
        "        /// O examine pela rota real. Sem `onAccepted` no campo\n"
        "        /// `themeImportEsdeSource` — ao contrário do campo RetroFE —, o clique no\n"
        "        /// \"Examinar\" é a ÚNICA\n",
    ),
    (
        "tests/qml/check_shell_esde_import_late_response.qml",
        "        /// estado próprio (`shell.esdeImport*`, `Main.qml:528-531`) e despacho inline\n"
        "        /// nos dois botões (`:2987`, `:3085`). Não é o painel: aqui o aviso de sucesso\n"
        "        /// é um `notify` (`:3095`), e a origem mora no campo, não numa propriedade.\n",
        "        /// estado próprio (`shell.esdeImport*`) e despacho inline nos dois\n"
        "        /// botões (`esdeInspectButton`, `esdeApplyButton`). Não é o painel: aqui o\n"
        "        /// aviso de sucesso é um `root.notify` no apply, e a origem mora no campo,\n"
        "        /// não numa propriedade.\n",
    ),
    (
        "tests/qml/check_shell_esde_import_late_response.qml",
        "        /// = 0, e o `onClosed` (`:2898-2906`) limpa o estado sem revogar pedido algum.\n",
        "        /// = 0, e o `esdeImportDialog.onClosed` limpa o estado sem revogar pedido\n"
        "        /// algum.\n",
    ),
    (
        "tests/qml/check_shell_esde_import_late_response.qml",
        "        /// (idêntica ao molde RetroFE): examinar, FECHAR (o `onClosed` roda\n"
        "        /// `resetEsdeImport()`, `esdeImportDialog.onClosed`, que limpa a bandeira em\n"
        "        /// `:215`), reabrir e examinar outra origem.",
        "        /// (idêntica ao molde RetroFE): examinar, FECHAR (o\n"
        "        /// `esdeImportDialog.onClosed` do painel roda `resetEsdeImport()`, que limpa a\n"
        "        /// bandeira), reabrir e examinar outra origem.",
    ),
    (
        "tests/qml/check_shell_esde_import_late_response.qml",
        "        /// (`inspectEsdeImport()`) arma a bandeira em `:224` ANTES de\n"
        "        /// despachar e não tem\n"
        "        /// rollback nenhum (o molde RetroFE `:353/:391-394` tem) — hoje o clique\n",
        "        /// (`inspectEsdeImport()`) arma a bandeira ANTES de despachar e não tem\n"
        "        /// rollback nenhum (o molde RetroFE, `inspectRetrofeImport()`, tem) — hoje o\n"
        "        /// clique\n",
    ),
    (
        "tests/qml/check_shell_esde_import_late_response.qml",
        "+ \"valor de antes do clique (`ocupadoAntes`, como em \"",
        "+ \"valor de antes do clique (`ocupadoAntes`, como no par \"",
    ),
    (
        "tests/qml/check_shell_esde_import_late_response.qml",
        "+ \"o `*RetrofeImport()`), não deixá-la no `true` que o \"",
        "+ \"`*RetrofeImport()`), não deixá-la no `true` que o despacho \"",
    ),
    (
        "tests/qml/check_shell_esde_import_late_response.qml",
        "+ \"`:224` armou\")",
        "+ \"armou\")",
    ),
    (
        "tests/qml/check_shell_esde_import_late_response.qml",
        "        /// OCIOSA e utilizável: o clique recusado arma a bandeira (`:224`) e, sem o\n",
        "        /// OCIOSA e utilizável: o clique recusado arma a bandeira no despacho e, sem\n",
    ),
    (
        "tests/qml/check_shell_esde_import_late_response.qml",
        "        /// `:2988` já armou `esdeImportBusy = true`. Com o pedido revogado pelo\n",
        "        /// o clique em `esdeInspectButton` já armou `esdeImportBusy = true`. Com o\n"
        "        /// pedido revogado pelo\n",
    ),
    # ================= gate Python desta frente =================
    (
        "tests/integration/test_ui_shell_esde_import_late_response.py",
        "resposta que chega depois de a superfície mudar escreve por cima dela\n"
        "(`:229`/`:239`/`:263`/`:271`), o fechamento baixa a bandeira de um pedido vivo\n"
        "(`:215`) e a recusa por dedup não tem rollback (`:224` arma sem devolver).",
        "resposta que chega depois de a superfície mudar escreve por cima dela, nas\n"
        "callbacks de `inspectEsdeImport()` e `applyEsdeImport()`; o fechamento baixa a\n"
        "bandeira de um pedido vivo (`resetEsdeImport()`) e a recusa por dedup não tem\n"
        "rollback (o despacho arma e não devolve).",
    ),
    (
        "tests/integration/test_ui_shell_esde_import_late_response.py",
        "responder, e o cliente é o `XMLHttpRequest` do produto (o `request()` de `Main.qml`, `xhr.timeout`\n`:1012`).",
        "responder, e o cliente é o `XMLHttpRequest` do produto (o `request()` de\n`Main.qml`, `xhr.timeout`).",
    ),
    (
        "tests/integration/test_ui_shell_esde_import_late_response.py",
        "  (`refreshThemeList()`) dispara `GET /theme/list` na callback de sucesso do\n  apply (`:264`).",
        "  dispara `GET /theme/list` na callback de sucesso do apply.",
    ),
    (
        "tests/integration/test_ui_shell_esde_import_late_response.py",
        "#: de o fechamento ter baixado a bandeira (`resetEsdeImport` em `:215`), porque os\n"
        "#: dois botões despachantes são gated por `esdeImportBusy` (`:1095`/`:1190`) e não há\n"
        "#: segunda porta de teclado no campo de origem (ao contrário do campo RetroFE,\n"
        "#: `:1275`). Uma recusa que DEIXA a bandeira armada — o que `:224` faz hoje, sem\n"
        "#: rollback — é o vermelho lido aqui.",
        "#: de o fechamento ter baixado a bandeira (`resetEsdeImport()`), porque os dois\n"
        "#: botões despachantes (`themeImportEsdeInspect`, `themeImportEsdeApply`) são gated\n"
        "#: por `esdeImportBusy` e não há segunda porta de teclado no campo de origem\n"
        "#: (`themeImportEsdeSource`, ao contrário do campo RetroFE, que tem `onAccepted`).\n"
        "#: Uma recusa que DEIXA a bandeira armada — o que o despacho faz hoje, sem rollback\n"
        "#: — é o vermelho lido aqui.",
    ),
    (
        "tests/integration/test_ui_shell_esde_import_late_response.py",
        "    \"despachar (`Main.qml:2988`) e o fechamento já baixou a bandeira no `onClosed` \"\n"
        "    \"(`:2903`); sem rollback o clique recusado a rearma sobre um pedido que a ponte \"",
        "    \"despachar (o `onClicked` de `esdeInspectButton`) e o fechamento já baixou a \"\n"
        "    \"bandeira no `esdeImportDialog.onClosed`; sem rollback o clique recusado a \"\n"
        "    \"rearma sobre um pedido que a ponte \"",
    ),
    (
        "tests/integration/test_ui_shell_esde_import_late_response.py",
        "        \"(`ThemeEditorPanel.qml:616`), então o produto não foi exercitado\"",
        "        \"(`Component.onCompleted: refreshThemeList()`), então o produto não foi \"\n        \"exercitado\"",
    ),
    # ================= molde RetroFE (vizinho, deslocado por este corte) =================
    (
        "tests/qml/check_shell_retrofe_import_late_response.qml",
        "// aparência\", `Main.qml:6509`/`:6562`), pela rota real, com o importador\n"
        "// respondendo DEPOIS de a superfície ter mudado.",
        "// aparência\", `themeEditorTab` e `themeEditorPanel`), pela rota real, com o\n"
        "// importador respondendo DEPOIS de a superfície ter mudado.",
    ),
    (
        "tests/qml/check_shell_retrofe_import_late_response.qml",
        "//      raiz (a binding `text:`/`onTextChanged:` de `:1282`/`:1287` se interrompe na\n"
        "//      primeira edição), declarado",
        "//      raiz (a binding `text:`/`onTextChanged:` de `themeImportRetrofeSource` se\n"
        "//      interrompe na primeira edição), declarado",
    ),
    (
        "tests/qml/check_shell_retrofe_import_late_response.qml",
        "//      diálogo aberto (são os seletores, `:1523`/`:1531`) tem de alcançar o campo.\n",
        "//      diálogo aberto (`retrofeImportFolderDialog`, `retrofeImportFileDialog`) tem\n"
        "//      de alcançar o campo.\n",
    ),
    (
        "tests/qml/check_shell_retrofe_import_late_response.qml",
        "// O oráculo de \"a resposta chegou\" é `shell.pendingRequests` (`Main.qml:382`,\n"
        "// incrementado em `:1003` e decrementado em `:1018` dentro do próprio\n"
        "// `onreadystatechange`). Não há margem fixa depois dele:",
        "// O oráculo de \"a resposta chegou\" é `shell.pendingRequests`, o contador do\n"
        "// `request()` de `Main.qml` — incrementado no despacho e decrementado no\n"
        "// `finish()` dentro do próprio `onreadystatechange`. Não há margem fixa depois\n"
        "// dele:",
    ),
    (
        "tests/qml/check_shell_retrofe_import_late_response.qml",
        "        /// (`themeImportRetrofeOverwrite`, `:1451`) também é marcável, e contá-la como\n",
        "        /// (`themeImportRetrofeOverwrite`) também é marcável, e contá-la como\n",
    ),
    (
        "tests/qml/check_shell_retrofe_import_late_response.qml",
        "        /// examinar, FECHAR (o `onClosed` roda `resetRetrofeImport()`, `:1231`, que\n"
        "        /// limpa a bandeira em `:344`), reabrir e examinar outra origem — e aí os dois\n",
        "        /// examinar, FECHAR (o `retrofeImportDialog.onClosed` roda\n"
        "        /// `resetRetrofeImport()`, que limpa a bandeira), reabrir e examinar outra\n"
        "        /// origem — e aí os dois\n",
    ),
    (
        "tests/qml/check_shell_retrofe_import_late_response.qml",
        "        /// (`ThemeEditorPanel.qml:1265`/`:1287`). A primeira edição pelo teclado ou por\n"
        "        /// atribuição INTERROMPE a binding, então",
        "        /// (`themeImportRetrofeSource` e o `Binding` que o espelha). A primeira\n"
        "        /// edição pelo teclado ou por atribuição INTERROMPE a binding, então",
    ),
    (
        "tests/qml/check_shell_retrofe_import_late_response.qml",
        "        /// botão \"Examinar\" lê o ESTADO (`:1326`): o usuário reabre, vê um caminho no\n",
        "        /// botão \"Examinar\" lê o ESTADO (`enabled` de `themeImportRetrofeInspect`): o\n"
        "        /// usuário reabre, vê um caminho no\n",
    ),
    (
        "tests/qml/check_shell_retrofe_import_late_response.qml",
        "        /// ESTADO (`ThemeEditorPanel.qml:1506`/`:1531`, `panel.retrofeImportSource =\n"
        "        /// panel.localPath(...)`), nunca no campo. Morto o espelho pela digitação, quem\n",
        "        /// ESTADO (`retrofeImportFolderDialog`/`retrofeImportFileDialog`,\n"
        "        /// `panel.retrofeImportSource = panel.localPath(...)`), nunca no campo. Morto o\n"
        "        /// espelho pela digitação, quem\n",
    ),
    (
        "tests/qml/check_shell_retrofe_import_late_response.qml",
        "        /// (`:1326`). Não se abre seletor nativo aqui: escreve-se o caminho exato que\n",
        "        /// (`enabled` de `themeImportRetrofeInspect`). Não se abre seletor nativo\n"
        "        /// aqui: escreve-se o caminho exato que\n",
    ),
    (
        "tests/qml/check_shell_retrofe_import_late_response.qml",
        "        /// Por que o Enter e não o seletor: dos dois botões de seleção (`:1310`,\n"
        "        /// `:1317`) só o de arquivo despacha exame no `onAccepted` (`:1533`), mas a\n",
        "        /// Por que o Enter e não o seletor: dos dois botões de seleção\n"
        "        /// (`themeImportRetrofeBrowseFolder`, `themeImportRetrofeBrowseFile`) só o de\n"
        "        /// arquivo despacha exame no `onAccepted`, mas a\n",
    ),
    (
        "tests/qml/check_shell_retrofe_import_late_response.qml",
        "        /// `retrofeImportBusy`, mas o `onClosed` (`:1231`) roda\n"
        "        /// `resetRetrofeImport()` e a bandeira cai (`:344`): fechar, reabrir e pedir a\n",
        "        /// `retrofeImportBusy`, mas o `retrofeImportDialog.onClosed` roda\n"
        "        /// `resetRetrofeImport()` e a bandeira cai: fechar, reabrir e pedir a\n",
    ),
    (
        "tests/integration/test_ui_shell_retrofe_import_late_response.py",
        "        \"(`ThemeEditorPanel.qml:616`), então o produto não foi exercitado\"",
        "        \"(`Component.onCompleted: refreshThemeList()`), então o produto não foi \"\n        \"exercitado\"",
    ),
    # ================= frentes vizinhas =================
    (
        "tests/qml/check_shell_esde_import_dialog_journey.qml",
        "// `ThemeEditorPanel.qml:1016`). Aqui o corpo é um `ColumnLayout` com\n",
        "// `ThemeEditorPanel.qml`, `esdeImportDialog`). Aqui o corpo é um\n"
        "// `ColumnLayout` com\n",
    ),
    (
        "tests/qml/check_shell_esde_import_dialog_journey.qml",
        "// puderam stubear a ponte. `Main.qml` não — `request()` (Main.qml:982) fala por\n",
        "// puderam stubear a ponte. `Main.qml` não — o `request()` fala por\n",
    ),
    (
        "tests/qml/check_shell_esde_import_dialog_journey.qml",
        "//     Sistema (`Main.qml:6445`), muitas vezes abaixo da dobra. Revelar por\n",
        "//     Sistema (o botão \"Importar tema ES-DE\"), muitas vezes abaixo da dobra.\n"
        "//     Revelar por\n",
    ),
    (
        "tests/integration/test_ui_shell_esde_import_dialog.py",
        "`ThemeEditorPanel.qml` (corrigido na 3ª fatia); este vive em outro `esdeImportDialog`, em `Main.qml`, aberto\n"
        "por um botão da área de diagnósticos da seção Sistema (`Main.qml:6445`). Nada testava\n",
        "`ThemeEditorPanel.qml` (corrigido na 3ª fatia); este vive em outro\n"
        "`esdeImportDialog` de `Main.qml`, aberto por um botão da área de diagnósticos da\n"
        "seção Sistema. Nada testava\n",
    ),
    (
        "tests/integration/test_ui_shell_esde_import_dialog.py",
        "ponte. O shell não — `Main.qml:982` fala por `XMLHttpRequest` com `shell.apiUrl`.",
        "ponte. O shell não — o `request()` fala por `XMLHttpRequest` com `shell.apiUrl`.",
    ),
    (
        "tests/integration/test_ui_shell_esde_import_dialog.py",
        "        # `Main.qml:1002` envia `X-SteamZero-Token` em toda requisição. Exigir aqui",
        "        # O `request()` de `Main.qml` envia `X-SteamZero-Token` em toda requisição.\n"
        "        # Exigir aqui",
    ),
    (
        "tests/integration/test_ui_shell_home_first_fold.py",
        "`apiUrl`/`apiToken` vêm de argumento na inicialização (`Main.qml:901`-`:908`) e,\n",
        "`apiUrl`/`apiToken` vêm de argumento na inicialização (os marcadores\n`--steamzero-api`/`--steamzero-token`) e,\n",
    ),
    (
        "tests/integration/test_ui_shell_home_first_fold.py",
        "(`:339`) e `hasConflicts` (`:334`) ficam falsos e o banner não acende. O que a",
        "e `hasConflicts` ficam falsos e o banner não acende. O que a",
    ),
    (
        "tests/integration/test_ui_shell_home_first_fold.py",
        "renovação recusada (`pushError` `:496`).",
        "renovação recusada (`pushError()`).",
    ),
    (
        "tests/integration/test_ui_shell_home_first_fold.py",
        "statusStale || statusBandIsError` (`Main.qml:421`-`:422`), com",
        "statusStale || statusBandIsError`, com",
    ),
    (
        "tests/integration/test_ui_shell_home_first_fold.py",
        "Medido nesta bancada (qml6, 1280x800, janela em `compactLayout` por `:71`), com",
        "Medido nesta bancada (qml6, 1280x800, janela em `compactLayout`), com",
    ),
    (
        "tests/integration/test_ui_shell_home_first_fold.py",
        "    (`Main.qml:1248`-`:1249`), `statusBandIsError` (`:420`) põe a faixa na tela, e o\n",
        "    (o `else` do callback de recusa), `statusBandIsError` põe a faixa\n"
        "    na tela, e o\n",
    ),
]


def main() -> int:
    por_arquivo: dict[str, int] = {}
    problemas: list[str] = []
    estouradas: list[str] = []
    ja_aplicadas: list[str] = []
    for arq, old, new in REPL:
        caminho = ROOT / arq
        texto = caminho.read_text(encoding="utf-8")
        n = texto.count(old)
        if n == 0 and texto.count(new) == 1:
            ja_aplicadas.append(f"{arq}: {old[:50]!r}")
            continue
        if n != 1:
            problemas.append(f"{arq}: {n} ocorrencias de {old[:60]!r}")
            continue
        limite = LIMITE["py" if arq.endswith(".py") else "qml"]
        for linha in new.splitlines():
            if len(linha) > limite:
                estouradas.append(f"{arq}: {len(linha)} cols  {linha.strip()[:78]}")
        caminho.write_text(texto.replace(old, new), encoding="utf-8")
        por_arquivo[arq] = por_arquivo.get(arq, 0) + 1

    print("APLICADAS por arquivo:")
    for arq, n in por_arquivo.items():
        print(f"  {n:>3}  {arq}")
    print(f"TOTAL: {sum(por_arquivo.values())} de {len(REPL)} substituicoes")
    print(f"\nJA APLICADAS (reentrada): {len(ja_aplicadas)}")
    for j in ja_aplicadas:
        print("  " + j)
    print(f"\nPROBLEMAS ({len(problemas)}):")
    for p in problemas:
        print("  " + p)
    print(f"\nESTOURAM O LARGAMENTO ({len(estouradas)}):")
    for e in estouradas:
        print("  " + e)
    return 0 if not problemas else 1


if __name__ == "__main__":
    raise SystemExit(main())
