# Medida, não narrativa: o seletor nativo não é dirigível sob `offscreen`

Corte 65 (rodada 2) da fatia "RetroFE na shell" de RC-01. Este arquivo registra a
medição que mudou a rota do lote, porque sem ela a alegação das cenas 08 e 09 ("o
clique recusado por payload idêntico") seria sustentada por uma chamada de função,
não por um evento do usuário.

## 1. O vermelho que abriu esta rodada

A primeira versão da cena de recusa chamava a função do painel diretamente:

```qml
harness.panel.inspectRetrofeImport()
```

O portão de intenção do próprio gate reprova isso —
`tests/integration/test_ui_shell_retrofe_import_late_response.py:730`
(`test_o_harness_nao_pode_stubear_a_ponte_nem_a_callback`) — porque chamar
`inspectRetrofeImport()` é exercitar o painel, não o shell. Verificado, e a verificação
não foi enfraquecida: a cena reprovada está em
`23-guarda-da-rota-real-vermelho-reproduzido.log` (comando
`.venv/bin/pytest tests/integration/test_ui_shell_retrofe_import_late_response.py -q -k "stubear"`,
`1 failed, 8 deselected in 0.62s`).

A correção não foi "deixar de medir": foi achar uma entrada real.

## 2. Por que a entrada real não podia ser o seletor

`ThemeEditorPanel.qml` tem duas portas de origem, e o `onAccepted` de uma delas
(`:1514`-`:1516`) grava a origem **e** despacha o exame — é a rota por onde uma
repetição idêntica é alcançável com o pedido ainda em voo, porque os botões de
seleção (`:1293`, `:1300`) não são gated por `retrofeImportBusy`.

Sonda fora da árvore (`18-sonda-dialogo-nativo-fonte.qml`), executada com o MESMO
mecanismo do gate (`qmltestrunner`, `QT_QPA_PLATFORM=offscreen`, e
`QT_FORCE_STDERR_LOGGING=1` — a variável que `CanonicalEnvironment.to_env()` já põe),
saída em `17-sonda-qmltestrunner-dialogo-nativo.log`:

```
SONDA antes: visivel=false contentItem=nao
SONDA depois: visivel=true contentItem=nao
SONDA fim do teste 01
Totals: 3 passed, 0 failed, 0 skipped, 0 blacklisted, 1357ms
```

O que a sonda mede, lido da própria saída:

* `dlg.open()` sob `offscreen` põe `visible = true`;
* `contentItem` é **nulo** antes e depois — a varredura recursiva por `children`
  (até profundidade 7, imprimindo todo nó com `objectName`, `text` e `visible`) não
  publicou **nenhuma** linha `SONDA NO`;
* nenhum `SONDA aceitou` / `SONDA rejeitou`: não há caminho de aceite nem de rejeição
  acionável por evento, logo não há como fazer o `onAccepted` do produto rodar a partir
  do harness.

Conclusão declarada como limite, não como conveniência: **nenhuma cena deste lote pode
nascer de seletor nativo**; uma que tentasse dependeria do tema de desktop da máquina
e mediria a plataforma, não o produto.

Nota de bancada que já vale confissão: uma primeira sonda usando a ferramenta `qml`
devolveu rc=124 com saída zero, o que quase virou evidência de "o diálogo nativo bloqueia".
Um experimento de controle (uma `Component.onCompleted` banal, que também não imprimiu
nada) provou que o `qml` não encaminha `console.log` — a leitura anterior era artefato
da ferramenta, não do Qt. A sonda válida é a acima, dentro de `qmltestrunner`.

## 3. A porta que ficou: Enter no campo de origem

`ThemeEditorPanel.qml:1275` ganhou

```qml
onAccepted: panel.inspectRetrofeImport()
```

no `TextField` `themeImportRetrofeSource`. É tecla real (`keyPress(Qt.Key_Return)` /
`keyRelease`), é a segunda entrada dirigível por evento do diálogo, e tem justificativa
de produto declarada no comentário do próprio arquivo: num shell operado por controle,
os dois seletores nativos são becos — o pad não alcança a janela de arquivo do sistema,
e sem esta tecla o caminho **digitado** nunca viraria pedido.

A cena 07 (`test_07_a_tecla_enter_despacha_o_exame_pela_rota_real`) prova que a porta
despacha, e a ponte a vê: posição `15` do log,
`POST /theme/import/retrofe/inspect  /media/retrofe/cena-curta-teclado`
(`20-ponte-verde-jornada.txt`).

## 4. Consequência honesta sobre o poder de discriminação da cena 08

Com a porta removida (mutante M4, `16-mutante-m4-sem-porta-de-teclado.log`) a cena 08
**passa**: sem `onAccepted`, o Enter não faz nada, `pendentes` continua 1 e a bandeira
continua armada — o observável é idêntico ao de uma recusa por dedup. Ou seja, a
asserção de recusa da cena 08 não discrimina "dedup" de "a tecla não fez nada"
sozinha; ela discrimina **em par com a cena 07**, que prova que a mesma tecla despacha
cuando o payload não está em voo, e com a leitura da ponte, que conta a origem
`cena-lenta-corrente` exatamente **uma** vez (`test_o_clique_recusado_nao_chegou_a_ponte`,
em `tests/integration/test_ui_shell_retrofe_import_late_response.py:940`-`:947`).

Isso está registrado em vez de passar como "9 cenas verdes cobrem tudo".
