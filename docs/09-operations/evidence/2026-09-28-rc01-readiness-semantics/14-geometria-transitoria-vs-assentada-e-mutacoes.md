# 14 — Geometria transitória vs assentada: a causa do vermelho no gate visual

Instrução do operador (2026-09-28, itens 1, 2b e 8): a suíte integral não pode
ser substituída por testes focados; um vermelho precisa de causa; e uma bateria
verde não prova que o teste expressa o requisito.

## 1. O vermelho, citado do log do CI

Run 36475422213 (job `Gate visual QML (Linux)`, PR #243, cabeça `ec86c228`), comando
`python tools/run_tests_isolated.py -m visual --tb=short -q`:

```
_______ test_qml_handheld_harness_offscreen[check_readiness_surface.qml] _______
E   AssertionError: check_readiness_surface.qml falhou (1)
E     critical|FAIL: o texto quebrado continua dentro da largura do cartão
E     critical|check_readiness_surface: 1 falha(s) de 112 (primeira em #71)
1 failed, 343 passed, 12 skipped, 6176 deselected in 1185.23s (0:19:45)
```

Localmente o mesmo harness passava 112/112. Nenhuma mudança de produto separa as
duas execuções — o que differia era o *momento* em que o harness lia a geometria.

Precedente adjunto: `2026-09-27-pr241-verificacao-documental/02-gate-visual-vermelho-no-runner.log`
registrou a mesma classe (asserção geométrica que reprova só no runner) e foi
explícito ao dizer que o mecanismo **não** foi certificado lá, e ao recusar
baixar o limiar para ficar verde. Aqui o mecanismo foi medido.

## 2. A medição

Sonda com o mesmo estado do harness (página `Emulation` de 1360 px, cartão com
causa publicada), leitura na mesma volta do event loop da atribuição do modelo e
depois de um frame:

```
t0 … cartao=250.0x98.0  | causa.w=76.00  cw=74.17  delta=-1.83  lines=9 h=17.00 ch=153.00
t1 (+120 ms, 1 frame) … | causa.w=786.00 cw=489.70 delta=-296.30 lines=1 h=17.00 ch=17.00
t2 (+520 ms) … idêntico a t1
```

Repetido dentro do próprio harness instrumentado (três sítios, `ticks=0` é a
mesma volta do loop, `ticks=2` é quando a largura para de mudar):

| sítio | transitório (`ticks=0`) | assentado (`ticks=2`) |
| --- | --- | --- |
| Emulação 1360 | `w=76.00 cw=74.17 lines=9 h=17.00 ch=153.00` | `w=786.00 cw=489.70 lines=1 h=17.00 ch=17.00` |
| Ambiente 1208 | `w=159.00 cw=141.84 lines=6 h=17.00 ch=102.00` | `w=797.00 cw=689.45 lines=1 h=17.00 ch=17.00` |
| Ambiente 720x480 | `w=159.00 cw=141.84 lines=6 h=17.00 ch=102.00` | `w=309.00 cw=305.63 lines=3 h=51.00 ch=51.00` |

Conclusão, em camadas:

- Os Qt Quick Layouts são polidos num frame **posterior**. Medir `width` na mesma
  volta do loop em que o modelo foi atribuído devolve a distribuição anterior.
- Na coluna transitória de 76 px a causa legítima "estoura" a largura por
  construção: 76 px não comporta uma palavra inteira. É onde a folga local de
  1,83 px virou +1 px no runner — uma tolerância de 1 px é menor que a diferença
  entre duas famílias de fonte, então a asserção media métrica de fonte, não
  requisito.
- No mesmo transitório o item media 9 linhas ocupando 153 px de conteúdo dentro
  de 17 px de altura. Nenhuma verificação vertical faria sentido ali.
- Assentado, `contentWidth <= width` deixa de ser sorte de métrica: com
  `wrapMode: Text.WordWrap` o Qt quebra cada linha para caber, e o único modo de
  uma linha exceder a coluna é uma palavra maior que a coluna — o caso patológico
  que o transitório criava.

## 3. O que foi feito, e o que foi recusado

Recusado: baixar o limiar (o `+1` para `+8`), e também a substituição
imediata que esta própria rodada havia começado — trocar o pixel por uma
comparação de string e atribuir o vermelho inteiro à métrica de fonte. Aquela
explicação estava incompleta (a causa é o momento da leitura) e deixava o
requisito "nada é cortado" sem nenhuma medição.

Feito, em `tests/qml/check_readiness_surface.qml`:

1. **Esperar assentar por condição, não por tempo.** O harness acumula obrigações
   (`exigirGeometriaAssentada(rotulo, item, verificacao)`) e um espiador de 16 ms
   só as executa quando a largura de cada item se repete entre dois ticks
   consecutivos. O teto de 120 ticks (~2 s) é uma testemunha: se não assentar, a
   falha diz "medir agora mediria o frame anterior" em vez de reprovar por pixel.
2. **`contentWidth <= width` sem tolerância**, mais `contentHeight <= height`,
   mais a guarda de não-vacuidade `contentWidth > 100` (caber não pode ser
   consequência de o item estar vazio), nos dois cartões.
3. **A demonstração de quebra foi movida para um regime onde ela é exigida.**
   `Main.qml:12` fixa `minimumWidth: 720`. Nessa janela a coluna do cartão do
   ambiente assenta em 309 px e a causa de 121 caracteres precisa de 689 px numa
   linha só — folga de 2,2×. Ali `lineCount > 1` é o requisito, não sorte de
   fonte. Na Emulação à mesma largura a folga seria de 1,13× (539 px vs 476 px),
   por isso nenhuma asserção de contagem de linha foi posta lá: seria o mesmo
   erro com outro nome.
4. **Igualdade de texto continua**, mas declarada pelo que é: o texto chega
   inteiro ao item. Ela não detecta corte por elipse — a bateria abaixo mostra
   isso — e por isso coexiste com os pinos estruturais (`elide`, `wrapMode`,
   `maximumLineCount`).

## 4. Bateria de mutações rodada 5 (log cru em `14-bateria-mutacoes-rodada-5.log`)

Executada contra uma **cópia** do QML em `/tmp/rp/src` (pristine verificado por
`diff -rq` contra a árvore antes e depois); a árvore do checkout nunca foi
tocada — o erro da rodada anterior, que mutou `Emulation.qml` dentro do checkout,
não se repetiu.

| cena | mutação no produto | veredito |
| --- | --- | --- |
| M0 | nenhuma (cópia pristine) | 125 ok — baseline |
| M1 | Emulação: `wrapMode: Text.NoWrap` | 1 falha (#67) — pino estrutural do wrap |
| M2 | Emulação: coluna espremida a 200 px **com** WordWrap | **125 ok** — controle negativo real: a quebra acontece e nada estoura |
| M3 | Emulação: 200 px **sem** quebra | 2 falhas — `nenhuma linha da causa sai da coluna do cartão (folga medida: -290 px)` |
| M4 | Ambiente: `Text.NoWrap` | 3 falhas — pino estrutural, `linhas medidas: 1` no compacto e o overflow do compacto |
| M5 | Ambiente: `elide: Text.ElideRight` + `maximumLineCount: 1` | 2 falhas — "a causa do ambiente não é cortada" e o `lineCount` do compacto |
| M6 | Ambiente: `Layout.maximumHeight: 17` | 1 falha (#124) — "o cartão compacto cresce com as linhas extras" |

Atribuições honestas que a bateria obriga a registrar:

- Em M5, com elipse ativa, `contentWidth <= width`, `contentHeight <= height` e a
  igualdade de texto **continuam verdes**. Ou seja: nada nesse harness detecta
  corte por elipse pela geometria — quem detecta é o pino de `elide`/
  `maximumLineCount`. A igualdade de texto sozinha não é prova de legibilidade,
  e o comentário do harness diz isso em vez de fingir o contrário.
- M2 é o que impede a narrativa "todo FAIL é prova": sem um caso em que o produto
  aperta a coluna e o harness **não** reprova, o `contentWidth <= width` poderia
  estar medindo qualquer coisa.
- O pino vertical só é falsificável no regime que quebra (M6, compacto). No
  cartão largo a causa cabe numa linha, então `ch == h` por construção e a
  verificação não morderia sozinha — motivo pelo qual ela foi mantida nos dois
  sítios mas provada no único onde morde.

## 5. Estado depois da correção

- Harness na árvore: `check_readiness_surface: 125 verificação(ões) ok`, 1,09 s
  de parede (o gate concede 30 s por harness).
- Gate focado: `test_qml_handheld_harness_offscreen[check_readiness_surface.qml]`
  = 1 passed em 1,54 s.
- Suíte integral e demais gates de §6: uma única execução na árvore congelada,
  registrada em `15-checkpoint-13-gates-integrais.md` (saída crua em
  `15-comandos-e-saidas.log`). Veredito: **1 failed, 6484 passed, 47 skipped**, e
  a única falha é o guard de catálogo pedindo renovação de digest desta frente —
  o gate visual do CI passou (356 tests, 0 falhas) na árvore testada.

## 6. O que continua não provado

A captura física em escala 100/125/150 % não é certificada no CI
(`GAP-UI-VISUAL-CAPTURE-NOT-CERTIFIED-IN-CI` permanece). Este harness prova a
geometria no runtime offscreen Qt 6.11 do projeto; onde a geometria importa para
o usuário em DPI real, a prova é a captura inspecionada, e ela segue pendente.
