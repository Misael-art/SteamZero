# Vermelho reproduzido — a sexta classe: o rollback do dedup desarma o pedido corrente

Corte 65 (rodada 3). Antes desta medição, o contrato de geração já estava verde
(corte 64). Este lote reproduz um defeito **novo**, deixado pela própria correção
anterior, e o lê em duas camadas independentes antes de tocar no produto.

## A alegação, em uma frase

Quando um clique é recusado porque o payload IDÊNTICO já está em voo
(`Main.qml:1119` devolve `false` sem disparar nenhuma callback), o rollback escrevia
`retrofeImportBusy = false` **incondicional** — baixando a bandeira do pedido que
ainda é o corrente. Efeito visível: "Importando…" desaparece e "Publicar cena"
(`ThemeEditorPanel.qml:1466`) habilita sobre um importador que ainda não respondeu.

O caso oposto tem de continuar verdadeiro: se o `onClosed` (`:1215`) já rodou
`resetRetrofeImport()` e baixou a bandeira (`:344`), o pedido em voo está **revogado**
e nada mais vai escrevê-lo — aí manter a bandeira armada é o diálogo preso para sempre.

## Árvore no momento do vermelho

| campo | valor |
| --- | --- |
| branch | `codex/rc01-retrofe-shell-late-response-2026-09-29` |
| HEAD | `af6a5c6ed8523c04030d25b1d391e885a3b3b48e` (= cabeça do PR #244) |
| produto modificado | `src/steamzero/ui/qml/ThemeEditorPanel.qml`, rollback antigo (`if (!despachado && panel.retrofeImportBusy) { …; busy = false }`) |
| comando | `.venv/bin/pytest tests/integration/test_ui_shell_retrofe_import_late_response.py -m visual -q` |
| saída integral | `11-pytest-vermelho-rollback.log` |

## Camada 1 — veredito do QtTest

`19-runner-verde-jornada.txt` mostra o mesmo arquivo depois da correção; o vermelho,
lido do log do runner naquela execução:

```
FAIL!  : …::test_08_a_repeticao_recusada_com_pedido_corrente_nao_desarma_a_bandeira()
         'o Enter recusado DESARMou a bandeira de um pedido que ainda está em voo:
          'Importando…' desaparece e 'Publicar cena' habilita sobre um importador que
          ainda não respondeu' returned FALSE. ()
Totals: 10 passed, 1 failed, 0 skipped, 0 blacklisted, 10223ms
```

## Camada 2 — leitura do log, independente do veredito

O harness imprime testemunhos `OBS|…`, e o portão
`test_a_resposta_tardia_do_importador_retrofe_nao_reabre_estado` os confronta com
`RECUSAS` (`tests/integration/test_ui_shell_retrofe_import_late_response.py:922`-`:933`).
A linha impressa no instante da recusa:

```
OBS|pedido-recusado-com-pedido-corrente|dialogo=aberto|pendentes=1|ocupado=0|layouts=0|indice=-1|aviso=0|erro=0|origem=34
```

e a reprovação:

```
AssertionError: pedido-recusado-com-pedido-corrente: a bandeira no instante da recusa
vale '0', esperado '1' — o POST em voo continua sendo o pedido corrente e ainda vai
escrever, então a bandeira tem de continuar armada
```

Não-vacuidade já embutida na mesma leitura: `pendentes=1` prova que havia **exatamente
um** request em voo no instante da recusa — se o Enter tivesse despachado um segundo
pedido, `pendentes` valeria 2 e a cena não estaria medindo dedup nenhuma
(asserção `verify(shell.pendingRequests === 1, …)` na cena 08).

## O pino do outro lado

A cena 09 (`test_09_…revogado…`) passa nos dois códigos e fica no lote como pino: ela
é o que impede a correção de 08 de virar "escreve `true` sempre". Sua testemunha no
mesmo instante, já verde:

```
OBS|pedido-recusado-com-pedido-revogado|dialogo=aberto|pendentes=1|ocupado=0|…
```

`ocupado=0` aqui é a alegação correta, porque o fechamento revogou o único pedido.
