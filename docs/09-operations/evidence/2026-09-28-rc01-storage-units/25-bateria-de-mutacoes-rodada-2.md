# 25 — bateria de mutações, rodada 2

Script: `25-bateria-de-mutacoes-rodada-2.py` (`sha256` `61cbfba337bcbadf`), saída
corrida em `25-bateria-de-mutacoes-rodada-2.log` (`sha256` `bd57aa024b3fdfa7`).
Cada mutante aplica **uma** substituição com âncora de contagem `== 1`, roda o
harness sob `C.UTF-8` **e** `pt_BR.UTF-8`, restaura e confere `sha256` — e o
resultado só é contado se o esperado e o observado coincidirem por locale.

Baseline da árvore real: `145 verificações ok`, rc 0 nos dois contextos.
Âncoras de restauração no fim do log: `sizes.js 6d5ca418e514258f` e
`Main.qml 391be85dd31e0b38`, ambos `identico`.

| mutante | o que faz | `C.UTF-8` | `pt_BR.UTF-8` | mordido por |
|---|---|---|---|---|
| M1 | formatador fixa `Qt.locale("en_US")` | verde (esperado) | **28 falhas** | oráculo + `testLocalizado` |
| M2 | formatador sem locale (`toFixed(2)`) | verde (esperado) | **28 falhas** | oráculo + `testLocalizado` |
| M3 | divisor `1000` sob rótulo IEC | **24 falhas** | **24 falhas** | oráculo (pino novo) |
| M4 | `GiB` vira `GB` no andar 3 | **14 falhas** | **14 falhas** | rótulo binário + oráculo |
| M5 | ausência vira `0 B` | **4 falhas** | **4 falhas** | `testAusencia`, `testCartaoMedido` |
| M6 | andar sem normalizar (mantissa < 1) | **14 falhas** | **14 falhas** | `testNadaSome`, `testZeroReal`, oráculo |
| M7 | prosa do shell com texto pronto | **1 falha** | verde (esperado) | `testProsaLocalizada` composta |
| H1 | o **gate** volta a pinar `Qt.locale("pt_BR")` | — | — | a matriz: `2 failed, 1 passed` |

**8/8 mortos, nenhum pino vazio.**

## Dois falsos resultados da rodada 1, corrigidos aqui

Registrados porque a tabela anterior diria mais do que provou.

1. **M1 e M2 da rodada 1 mutavam comentário.** `.toLocaleString(Qt.locale())`
   aparece também no bloco de documentação de `sizes.js` (linha 19), e a
   substituição pegava a primeira ocorrência. O código não mudava, o verde era
   inércia. A âncora agora é o corpo da função
   (`return (total / Math.pow(1024, expoente)).toLocaleString(Qt.locale())`) com
   `contagem == 1`, e o script recusa âncora ambígua.
2. **A primeira versão desta rodada ancorou no texto errado duas vezes.** M2
   produziu `976.56 KiB KiB` (rótulo duplicado) e morreu por um defeito que o
   autor do mutante criou; M3 sobreviveu *de verdade* — ver abaixo.

## O achado que mudou o gate: M3 sobrevivia

Divisor `1000` sob rótulo IEC, com os limiares de andar ainda em `1024`, imprime
`1000.00 KiB` onde a medida é `976.56 KiB`, e **nada do conjunto anterior via**:
o rótulo continua binário, o andar continua acima de GiB, a mantissa continua ≥ 1
e as quatro páginas continuam convergindo entre si — convergem todas para o
número errado. Essa é exatamente a forma do defeito F-1
(`26-fora-de-escopo.md`), o que indica que a classe não era coberta, e não que o
F-1 era único.

Fechado com um oráculo declarado no teste (`referencia(valor)` em
`check_storage_units.qml`): as potências de 1024 e a tabela IEC são afirmadas
aqui, não lidas da produção. Custo: 36 checagens (109 → 145). O oráculo também
morde M1, M2, M4 e M6, então a mensagem dele foi escrita para nomear as duas
causas possíveis (mantissa e separador) em vez de afirmar uma só — uma falha que
acusa o divisor quando o crime é o locale empurra a correção errada.

## H1 — o teste-do-teste

O defeito desta rodada não era da produção, era do gate, então nenhum mutante de
`sizes.js` o reproduz. H1 reintroduz `Qt.locale("pt_BR")` no **harness** e roda
`tests/integration/test_storage_units_locale_matrix.py`: `2 failed, 1 passed`
(o caso `C.UTF-8` e o caso de não vacuidade reprovam; o `pt_BR` passa, como
devia). A matriz é, portanto, a guarda contra a volta do pino — que é o que
produziria o "verde local, vermelho no CI" outra vez.
