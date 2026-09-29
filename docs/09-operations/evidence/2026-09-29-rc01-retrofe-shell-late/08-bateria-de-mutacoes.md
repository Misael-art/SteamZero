# Bateria de mutações — o que cada mudança ilegal no produto mata

Corte 65. Método: cada mutante é aplicado ao produto, o gate roda, a cena que reprova é
lida do log, e o arquivo é restaurado por cópia. Verde de referência do lote inteiro:
`12-pytest-verde.log` (`.venv/bin/pytest tests/integration/test_ui_shell_retrofe_import_late_response.py -q`
→ `9 passed in 25.35s`) e `19-runner-verde-jornada.txt` / `21-runner-verde-ordem.txt`
(`Totals: 11 passed, 0 failed`, nas duas invocações do runner).

Comando de cada execução:
`.venv/bin/pytest tests/integration/test_ui_shell_retrofe_import_late_response.py -m visual -q`

Árvore restaurada ao fim da bateria, conferida por hash:
`sha256sum src/steamzero/ui/qml/ThemeEditorPanel.qml` =
`3966456b0693c0b7c60fa298c4f9b8a922958694f38b51fcdc5f6486c7367144` (idêntica à cópia
verde tirada antes do primeiro mutante).

| # | mutante (mudança ilegal) | matou | leitura |
| --- | --- | --- | --- |
| M1 | rollback do dedup escreve `retrofeImportBusy = false` incondicional (= a árvore antes da correção) | cena 08, nas **duas** camadas | `FAIL! … 'o Enter recusado DESARMou a bandeira…'` **e** `AssertionError: … ocupado vale '0', esperado '1'` — ver `07-vermelho-rollback-do-dedup.md` e `11-pytest-vermelho-rollback.log` |
| M2 | remover `panel.retrofeImportGeneration = geracao - 1` do rollback de `inspectRetrofeImport` | cena 08 | `FAIL! … 'o resultado do pedido CORRENTE foi descartado pela geração do Enter recusado: layouts=0, esperado 3'` → `14-mutante-m2-sem-rollback-de-geracao.log` |
| M3 | remover `panel.retrofeImportGeneration += 1` de `resetRetrofeImport()` | cenas 02, 04 e 09 **+** o contrafactual de re-listagem no log da ponte | ver abaixo → `15-mutante-m3-sem-bump-no-fechamento.log` |
| M4 | remover a porta de teclado (`onAccepted` do campo de origem) | cena 07 **+** a contagem da ponte | ver abaixo → `16-mutante-m4-sem-porta-de-teclado.log` |
| G | harness chama `harness.panel.inspectRetrofeImport()` em vez de uma tecla | o portão de intenção `test_o_harness_nao_pode_stubear_a_ponte_nem_a_callback` | `1 failed, 8 deselected in 0.40s` → `23-guarda-da-rota-real-vermelho-reproduzido.log` |

## M3 — o que a leitura ampliou

Era esperado que M3 matasse a cena 09 (o pino da recusa com pedido revogado). Matou, com
a mensagem prevista:

```
FAIL! …::test_09_… 'a resposta de um pedido revogado reabriu estado no diálogo
       reaberto: 2 layouts' returned FALSE.
```

e matou também as duas cenas que já estavam verdes antes desta rodada:

```
FAIL! …::test_02_… 'a resposta tardia reescreveu 3 layouts num diálogo fechado …'
FAIL! …::test_04_… "a resposta tardia do apply anunciou 'Cena RetroFE publicada com
        assets validados; ela ainda não foi ativada.' num diálogo fechado"
Totals: 8 passed, 3 failed, 0 skipped, 0 blacklisted, 10100ms
```

Mais o contrafactual lido do log da ponte, independente do veredito do QtTest
(`tests/integration/test_ui_shell_retrofe_import_late_response.py:979`-`:986`):

```
AssertionError: a resposta tardia do apply re-listou temas depois de a superfície
fechar (1 GET /theme_list após o último POST, posição 11 de 21)
```

Leitura honesta: o bump de geração do fechamento é **load-bearing para o contrato de
revogação inteiro**, não só para a cena nova. Um verde da suíte com essa linha apagada
significaria que as cenas 02/04/09 não estão medindo o que alegam.

## M4 — o que a leitura estreita

Com a porta removida, o Enter não dispatcha nada:

```
FAIL! …::test_07_… 'Enter real no campo de origem não despachou nenhum pedido pela
       rota autenticada (expirou o limite de 3000 ms após 3000 ms)'
AssertionError: a rota de examine foi exercitada 7x, esperado 8
Totals: 10 passed, 1 failed, 0 skipped, 0 blacklisted, 13062ms
```

A cena 08 **passa** sob M4, e isso está declarado em
`06-medida-seletor-nativo-offscreen.md` §4: "tecla recusada por dedup" e "tecla que não
faz nada" são indistinguíveis dentro de uma cena só. O que as separa é o par com a cena
07 e a contagem da ponte (origem `cena-lenta-corrente` uma única vez).

## O que a bateria NÃO cobre (limite declarado)

* Nenhuma mutação no `Main.qml` — o arquivo está intocado neste lote e a deduplicação
  (`:1119`) é assumida como contrato do shell, não como comportamento deste corte.
* O `atraso_ms` por alavanca não é lido pelo harness (vive só na config da ponte); a
  inversão de ordem é provada por `test_a_ordem_de_resposta_inverte`, não por tempo de
  parede.
* Captura PNG: nenhuma. `GAP-UI-VISUAL-CAPTURE-NOT-CERTIFIED-IN-CI` segue aberto.
