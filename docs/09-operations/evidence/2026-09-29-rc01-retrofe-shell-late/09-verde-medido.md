# Verde medido e contagens reconciliadas — corte 65

Comandos (executados um por vez, sem mutação da árvore durante a execução):

```
.venv/bin/pytest tests/integration/test_ui_shell_retrofe_import_late_response.py -q
    -> 9 passed in 25.35s                                   (12-pytest-verde.log)
.venv/bin/pytest tests/integration/test_ui_shell_retrofe_import_late_response.py \
                 tests/integration/test_ui_shell_esde_import_dialog.py -q
    -> 29 passed in 110.50s    (gate deste lote + vizinho ES-DE, pós-passo de citações)
                                                            (13-gates-retrofe-mais-esde-pos-citacoes.log)
```

## As duas invocações do runner

| artefato | conteúdo |
| --- | --- |
| `19-runner-verde-jornada.txt` | `Totals: 11 passed, 0 failed, 0 skipped, 0 blacklisted, 10197ms` |
| `21-runner-verde-ordem.txt` | `Totals: 11 passed, 0 failed, 0 skipped, 0 blacklisted, 10219ms` |
| `20-ponte-verde-jornada.txt` | 20 eventos, `status_calls=9 unauthorized=0` |
| `22-ponte-verde-ordem.txt` | idem, corrida de ordem de resposta |

Onze = 9 cenas + `initTestCase` + `cleanupTestCase`. O denominador da suíte vive em
`FUNCTIONS` (`tests/integration/test_ui_shell_retrofe_import_late_response.py:68`-`:78`)
e reprova renomear, excluir ou pular uma cena.

## Conciliação cliente ↔ ponte (nada aqui é afirmado sem contagem)

| alegação | leitura |
| --- | --- |
| 9 cenas examinam 8 vezes | `ESPERADO_INSPECT = 8` bate com 8 `POST …/inspect` no log (`20-ponte-verde-jornada.txt`, posições 01, 05, 07, 08, 10, 15, 17, 19) |
| publicar acontece 2 vezes | `ESPERADO_APPLY = 2`, posições 02 e 11 |
| os dois cliques recusados **não** chegam à ponte | as origens `cena-lenta-corrente` e `cena-revogada-revogada` aparecem **uma** vez cada (`test_o_clique_recusado_nao_chegou_a_ponte`) |
| a tecla é uma porta real de exame | `cena-curta-teclado` aparece **uma** vez, posição 15 |
| a rota é autenticada | `unauthorized=0` em ambas as corridas |
| o apply verde re-lista, o tardio não | `GET /theme/list` na posição 03 (depois do apply 02) e nenhum `GET` de lista depois do apply 11 |

## As duas recusas, lidas como campos do log

```
OBS|pedido-recusado-com-pedido-corrente|dialogo=aberto|pendentes=1|ocupado=1|…
OBS|pedido-recusado-com-pedido-revogado|dialogo=aberto|pendentes=1|ocupado=0|…
```

`RECUSAS` exige `ocupado=1` no primeiro e `ocupado=0` no segundo
(`tests/integration/test_ui_shell_retrofe_import_late_response.py:662`-`:671`), e
`pendentes != 0` em ambos — sem voo não houve deduplicação e a cena teria medido outra
coisa. Os dez testemunhos obrigatórios estão listados em `TESTEMUNHOS`
(`:643`-`:655`); a porta de recusa de cada cena é medida pelo próprio `until()` do
harness, não por tempo de parede.

## Passo de citações aplicado na árvore final

33 citações de número de linha foram reconfrontadas com o conteúdo real do arquivo e
corrigidas (`grep -n` medido, não memória): 25 no harness
`tests/qml/check_shell_retrofe_import_late_response.qml`, 6 no gate
`tests/integration/test_ui_shell_retrofe_import_late_response.py`, 1 no produto
`src/steamzero/ui/qml/ThemeEditorPanel.qml` e 1 em
`tests/qml/check_shell_esde_import_dialog_journey.qml:22`
(`ThemeEditorPanel.qml:968` → `:1016`, arquivo committado de fatia anterior).

Mapa medido na árvore deste corte, para quem auditar as asserções:

| símbolo | linha |
| --- | --- |
| `Main.qml` `property int pendingRequests` | 382 |
| `Main.qml` `const xhr = new XMLHttpRequest()` | 986 |
| `Main.qml` `pendingRequests += 1` / `… - 1` | 988 / 1003 |
| `Main.qml` header `X-SteamZero-Token` / `timeout` | 996 / 997 |
| `Main.qml` recusa de payload idêntico | 1119 |
| `Main.qml` `restoreDialogFocus()` | 838-844 |
| `Main.qml` `navigationSections[7]` = temas | 107 |
| `Main.qml` `themeEditorTab` / `ThemeEditorPanel {` / `id:` | 6491 / 6544 / 6545 |
| `ThemeEditorPanel.qml` `resetRetrofeImport()` (bump / bandeira) | 332 (335 / 344) |
| `ThemeEditorPanel.qml` `inspectRetrofeImport()` / `applyRetrofeImport()` | 349 / 397 |
| `ThemeEditorPanel.qml` rollback do dedup | 391-394 / 440-443 |
| `ThemeEditorPanel.qml` `Dialog` RetroFE / `onClosed` | 1203 / 1215 |
| `ThemeEditorPanel.qml` campo de origem (`text:` / `onTextChanged:` / Enter) | 1265 / 1270 / 1275 |
| `ThemeEditorPanel.qml` "Pasta" / "XML" / "Examinar" (`enabled`) | 1293 / 1300 / 1307 (`:1309`) |
| `ThemeEditorPanel.qml` `Repeater` de layouts / Overwrite / "Publicar cena" | 1340 / 1434 / 1464 (`:1466`) |
| `ThemeEditorPanel.qml` `FolderDialog` / `FileDialog` RetroFE | 1503 (`onAccepted` 1506) / 1509 (`onAccepted` 1514, despacho 1516) |
| `theme_import_retrofe.py` `{id,path,name}` / layouts / `activated: False` | 39-44 / 209-217 / 340 |

O que **não** foi reescrito, de propósito: `00-vermelho-reproduzido.md` (vale na árvore
vermelha em que foi medido), `docs/WORKLOG.md` (append-only) e
`docs/expansion/PROMPT-NORMALIZACAO-PRE-RELEASE.md` (registro histórico de outra frente).
