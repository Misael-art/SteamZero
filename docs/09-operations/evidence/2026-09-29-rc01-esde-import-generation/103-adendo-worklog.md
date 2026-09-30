
## 2026-09-29 — RC-01 / nono elo, adendo: o checkpoint integral único e a fileira re-medida

**A dívida que a própria sessão declarou, paga — e o que ela cobrou.** A entrada
anterior registrou que a suíte integral arquivada era anterior ao trabalho
funcional do elo. Ela foi rodada uma única vez, com a árvore congelada em
`c4975979` e sem nada disputando CPU com as portas de atraso real:
`.venv/bin/python tools/run_tests_isolated.py tests -q` → **1 failed, 6528 passed, 47 skipped in 2529.34s (0:42:09)**
(rc=1), precedido dos gates leves de AGENTS §6 (`ruff check`, `ruff
format --check`, `mypy`, `make independence boundaries`), todos rc=0. Identidade
antes e depois do mesmo relatório: mesma cabeça e um único SHA-256 por arquivo do
corte — a árvore não se moveu durante a corrida. O comportamento passou inteiro; o
único falho foi o gate de catálogo gerado, e a causa é deste lote: 11
`scopeDigest` envelheceram. Lido dos JSONs dos cartões pelo próprio `103`: `Main.qml`
está no escopo de 8 deles, `ThemeEditorPanel.qml` no de 5, os
dois em `SZ-THEME-ENGINE`, `SZ-UI-DESKTOP-AUDIT`, e a união fecha 8 + 5 − 2 =
11, que é exatamente o conjunto renovado. O cartão desta frente
(`SZ-UI-DESKTOP-AUDIT`) já está entre os 2 que cobrem os dois, porque nomeia o
diretório `src/steamzero/ui`; a conta desta sessão escrita antes da medição
(`7 + 4 − 1 + 1 = 11`) acertou o total por acaso e errou as parcelas, e é a versão
medida que fica registrada. Na cabeça `c4975979` o mesmo teste
passou no CI — o job obrigatório "Python 3.11/3.12/3.14" roda
`python tools/project_status.py check` (`.github/workflows/ci.yml:72`) —, então
nenhum dos 11 estava envelhecido antes daqui. O remédio é o prescrito em AGENTS §6
para "só uma visão ou digest gerado obsoleto": `105-renovar-digests.py` renovou no
valor impresso pela ferramenta (dupla leitura `check` + `digest --item`), `render
--write` atualizou as três visões geradas (`docs/STATUS.md`, `docs/ACTIVE-WORK.md`,
`docs/status/COVERAGE.md`) e o `check` final fechou `rc=0`. Três coisas ficam
declaradas, não escondidas: o `100` omitiu `make status-check` dos seis gates de §6
(roda à parte, agora `OK`); a linha de parada que ele imprimiu — *suite integral nao voltou rc=0; a suite integral nao roda em arvore que ja reprovou um gate leve.* — é
template genérico e afirma uma razão falsa neste caso, já que nenhum gate leve havia
reprovado (o `103` a confere byte a byte justamente para registrá-la em vez de
repeti-la; o driver foi corrigido **depois** da corrida, então o script arquivado e o
log não voltam a dizer a mesma coisa, e é de propósito — o log é a medição, não o
texto); e renovação de digest não é prova de comportamento — é prova de que o
catálogo bate com a árvore. Saída completa em
`docs/09-operations/evidence/2026-09-29-rc01-esde-import-generation/100-checkpoint-integral-nono-elo.log`;
os números desta entrada foram lidos desse arquivo por script, não transcritos à
mão.

**Gate visual na mesma árvore**, pelo precedente do oitavo elo (PASSO 7 de `52`), e
só depois de o `110` verificar que os 9 arquivos funcionais são
byte a byte os mesmos que o `100` testou: **377 passed, 6199 deselected in 1711.56s (0:28:31)**
(`110-gate-visual-apos-governanca.log`), janela `2026-09-29T23:11:07-0300 → 2026-09-29T23:39:42-0300`. O `102` se recusou a
rodar com o checkpoint aberto, e a recusa está arquivada como está.

**Fileira re-medida, não presumida** (`101-reconcilio-entrega-acumulada.py`,
`106-preparar-integracao-da-cadeia.py`, `107-conta-de-commits-da-fileira.py`): os
oito PRs `#239`…`#246` seguem abertos e os oito checks obrigatórios estão em
`SUCCESS` nas oito cabeças (8/8 com `mergeStateStatus=CLEAN` e
nenhum review pendente exigido). `#246` está a **74**
commits acima de `origin/main` (`3495c49d`), lido com
`git rev-list --count origin/main..c4975979`; a mesma grandeza elo a elo é
`2 + 5 + 13 + 4 + 10 + 16 + 8 + 16` = **74**, com cada parcela medida contra a cabeça do elo
anterior e o `merge-base --is-ancestor` par a par conferido antes de somar.

**A conta que não fechava, e o que estava errado era o rótulo.** "74, quatro a mais
que 61" misturou um documento com um número e escondia o lado esquerdo do `rev-list`.
Re-medido: `61-reconcilio-rc01-oito-elos.md` media **70** e estava certo na
rodada em que foi escrito — `#246` estava em `22773047`, com **12**
commits sobre a base `2d6a8957`. A diferença de **4** é a rodada de
reconcílio posterior (`c4975979`, `71c49beb`, `7a8af0c1`, `92e1bf4c`), que toca apenas `docs/` e levou aquela
cabeça aos 16 commits próprios de hoje. O que precisava
de correção era o nome, e ele foi conferido célula a célula em vez de lido do jeito:
o `103` relê o corpo publicado de `#246` (`gh pr view 246 --json body`), recorta as
oito linhas da tabela de fileira e confronta cada célula com as três colunas medidas
pelo `107`, abortando se alguma ficar sem par. A coluna **"commits próprios"** é
`rev-list --count <cabeça do elo anterior>..<cabeça>` — **0**
linhas em desacordo com ela, contra 7 de `acima_de_main`
(`#240`, `#241`, `#242`, `#243`, `#244`, `#245`, `#246`) e 5 de `acima_da_base` (`#240`, `#241`, `#242`, `#243`, `#244`), então
a identificação é por exclusão e ela nunca esteve errada, soma incluída. A coluna
**"commits"** é que não segue um ref só: vale `acima_de_main` em sete linhas e
`acima_da_base` em `#245`, que publica `8` onde
`git rev-list --count origin/main..2d6a8957` dá `58` — soma
**161** se a tratarmos como por base, e nada que seja tamanho de
fileira. Os dois números convivem sem contradição desde que cada um declare seu ref;
o corpo publicado de `#246` não foi reescrito (é artefato da cabeça `c4975979`, e a
decisão sobre ele é de integração, não de prosa), e o `107` desta entrada imprime as
três colunas com o comando de cada uma. O documento de `61` também não foi tocado: a
releitura é esta entrada.

**O bloqueio passou a ser a integração, e a medição achou um bloqueio dentro do
bloqueio:** #245 sobre o ramo `codex/rc01-storage-units-2026-09-28`, #246 sobre o ramo `codex/rc01-retrofe-shell-late-response-2026-09-29` — os dois têm base em **ramo**, não em `main`, e mergear
neles entregaria no ramo de base. A sequência com o `gh pr edit N --base main` no ponto
seguro de cada um está registrada em
`106-preparar-integracao-da-cadeia.log`; nada foi mesclado e a decisão é do
operador.

**Camadas, depois do checkpoint.** Contrato testado offscreen: sim, agora com
suíte integral e gate visual na árvore do elo. Integrado: **não** — merge é
decisão do operador e a fileira está pronta, sequenciada. Empacotado: **não**.
Experiência na release instalada: **não**. Seletor nativo de diretório: **não
comprovado**.
