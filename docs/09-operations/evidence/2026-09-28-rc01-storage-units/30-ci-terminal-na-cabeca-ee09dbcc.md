# 30 — CI terminal na cabeça `ee09dbcc`, footprint do PR corrigido de 8 para 19 e os dois wheels comparados no artefato

Instrução do operador (2026-09-28, itens 1, 2a, 4 e 5): não encerrar com "CI rodando" —
ler o veredito terminal no SHA final e inspecionar os artefatos necessários; provar
empacotamento no wheel produzido pelo CI autorizado; declarar com honestidade o que a
árvore testada recebeu depois do verde. Saída crua em
`30-ci-terminal-na-cabeca-ee09dbcc.log` (17 seções, comandos listados na seção 0). Os
temporários vivem fora do checkout (`~/steamzero-retrofe-tmp`), e nenhuma suíte local foi
re-executada para produzir esta evidência.

Cabeça lida do PR #244: `ee09dbccdaaf897a0b3f8adb03389711c886e848` (branch
`codex/rc01-storage-units-2026-09-28`, base `main`). Run
[`36554123223`](https://github.com/Misael-art/SteamZero/actions/runs/36554123223)
(`workflowName=ci`, `event=pull_request`, `headSha` igual à cabeça do PR e ao `HEAD`
local, `conclusion=success`).

Esta é a terceira leitura terminal do PR (`37f0add4` → evidência 28, `2d04ac96` →
evidência 29, `ee09dbcc` → aqui). Ela existe por dois motivos: a cabeça se moveu três
commits documentais depois da evidência 29, e a evidência 29 continha uma alegação mal
rotulada sobre o tamanho do PR. Os dois são tratados aqui — o segundo em §3, sem reescrever
a evidência publicada.

## 1. O veredito terminal, com a identidade da árvore pinada em cada ciclo

Oito jobs, oito `success` (log §3): Wheel limpo/smoke/supply chain 39 s, Smoke Ubuntu 24.04
31 s, Smoke Manjaro 38 s, Smoke Arch Linux 41 s, Python 3.14 10m14s, Python 3.11 12m04s,
Python 3.12 12m44s, Gate visual QML 1250 s de job, dos quais 1172.59 s (19m32s) de sessão de teste. O run foi de
`10:12:33Z` a `10:33:27Z`. Dez checks no head: 9 `SUCCESS` + `Sourcery review` `SKIPPED`;
`CodeRabbit` concluído no rollup do PR. PR `OPEN`, `mergeable=MERGEABLE`,
`mergeStateStatus=CLEAN`, base `main`.

A espera usou o waiter `~/steamzero-ux04-tmp/wait_ci_244_run3.sh` (segmentos de 120 s,
log único `ci_244_run3.log`): **terminal no ciclo 11**, `2026-09-29T10:33:58Z`,
`pendentes=0`. Duas leituras preservadas, não suavizadas:

* o **ciclo 9** registrou `pendentes=ERRO` com `parse falhou Expecting value: line 1 column 1
  (char 0)` — a API do GitHub devolveu corpo vazio uma vez. O waiter registra e segue; o
  ciclo 10 voltou a ler o rollup e o 11 encerrou. O veredito não usa o ciclo 9. A linha
  fica no log em vez de ser apagada.
* `head_local=ee09dbcc…e848` nos **11 ciclos**: a árvore não se moveu enquanto o CI rodava,
  então o rollup terminal é do SHA lido, não de um SHA que trocou no meio da espera.

## 2. As suítes lidas dos artefatos do próprio run, não da cor do job

| leitura | valor medido | origem |
|---|---|---|
| junit 3.11 | `tests=6185 failures=0 errors=0 skipped=47` (678.537 s) | `test-results-3.11.xml` |
| junit 3.12 | `tests=6185 failures=0 errors=0 skipped=47` (718.292 s) | `test-results-3.12.xml` |
| junit 3.14 | `tests=6185 failures=0 errors=0 skipped=47` (557.578 s) | `test-results-3.14.xml` |
| rollup integral (logs) | `6138 passed, 47 skipped, 360 deselected` nas três pernas | log de cada job |
| cobertura 3.14 | `85.48858795854791 %` — 41 762 cobertas, 5 604 faltando, 47 366 afirmações | `coverage-3.14.json` |
| `fail_under` | 85 (`pyproject.toml:129`) | config |
| gate visual | `348 passed, 12 skipped, 6185 deselected in 1172.59s` | log do job `109359077030` |
| isolador do gate | `real-state before/after exists=False files=0 …` | mesmo log |

Reconciliação aritmética, não adjacência de números: `6138 + 47 = 6185` (o denominador do
junit) e `6185 + 360 = 6545`; pelo gate, `348 + 12 + 6185 = 6545`. As duas partições da
mesma suíte fecham no mesmo total. Os 12 skips do gate são todos de
`tests/integration/test_qml_asset_recipes.py` (linhas 100/111/120/131,
`QML-RHI-ENVIRONMENT-001`: goldens MultiEffect exigem RHI); nenhuma linha de skip menciona
armazenamento, prontidão ou importador.

**Cobertura: o `+1` não é deste lote.** Comparando arquivo por arquivo os
`coverage-3.14.json` dos dois runs (`2d04ac96` × `ee09dbcc`, log §12): 298 arquivos nos
dois, `num_statements` idêntico (47 366), `missing_lines` 5 605 → 5 604 e **exatamente um**
arquivo com delta — `src/steamzero/adapters/linux_runtime.py`, 25 → 24. Esse arquivo não
está entre os 19 `src/` do PR e o delta entre as cabeças não toca `src/`. A linha que virou
coberta é o fallback de nome de partição, cujo alcance depende do que o host do runner
monta. É variância de execução: "cobertura não regride" fica medido, com autoria por
arquivo, em vez de virar comemoração.

## 3. Correção: a footprint do PR é 19 arquivos em `src/`, não 8

A evidência 29, seção C, intitulou "os oito arquivos deste PR" um bloco que leu 8 caminhos.
Medido nesta passada pelas duas fontes independentes (`gh api pulls/244/files --paginate`
e `git diff --name-only origin/main...HEAD`): o PR #244 muda **359** arquivos — 295 `docs`,
40 `tests`, **19** `src`, 3 `tools`, 1 `IMPLEMENTATION-PROMPT.md`, 1 `.github` — e as duas
listas de `src/` são as mesmas 19 linhas.

O que estava errado era o rótulo, não a medição: os 8 são o subconjunto das duas últimas
fatias (readiness UX-03 + unidades UX-04), e aquilo que a evidência 29 afirmou sobre esses 8
continua verdadeiro. A correção é uma evidência nova porque evidência publicada não se
reescreve — o histórico imutável é o que permite ao operador auditar o que foi dito quando.
O bloco C desta rodada roda sobre a lista completa de 19 e fecha `19/19` idênticos ao HEAD
**e** ao merge ref, com SHA-256 por arquivo para conferência independente (log §9).

## 4. A prova de empacotamento, artefato por artefato

Os seis artefatos do run terminal foram baixados e conciliados contra a API (log §6): para
cada um, `size_in_bytes` declarado ≡ bytes no disco e `digest` declarado ≡ SHA-256 do zip
— **6/6 em tamanho e 6/6 em digest**. O runner anunciou `there will be 8 files uploaded` no
job do wheel e o diretório extraído tem 8 arquivos; o digest que o runner imprimiu ao fazer
upload (`5a49f064…`) é o mesmo que a API publica.

Dentro do artefato do wheel:

* `sha256sum -c build/SHA256SUMS` → **6 linhas, 6 `SUCESSO`**, rc=0. Os dois arquivos que o
  `SHA256SUMS` não lista são ele próprio e `requirements-runtime.lock`, e este está pinado
  na proveniência: `materials.runtimeLock.sha256` ≡ SHA-256 no disco
  (`33c7f069…`).
* `tools/release_provenance.py verify-wheel` (o verificador governado do repo) → rc=0,
  sujeito `steamzero-2.0.0rc1-py3-none-any.whl`.
* Cadeia de checksum do sujeito por três leituras independentes do mesmo valor:
  `subject.sha256` na proveniência ≡ SHA-256 calculado no disco ≡ linha 1 do `SHA256SUMS`
  (`60fc3973ebf8…`).
* O varredor `30-verificacao-wheel-na-cabeca-ee09dbcc.py`: bloco A lê a proveniência do
  próprio artefato (merge ref `8bdbb42a…`, `ref=refs/pull/244/merge`, `runId=36554123223`,
  `sourceTreeState=clean`); bloco B varre **todo** `steamzero/` do wheel contra os blobs
  Git — `pareados=619`, `identicos_HEAD=619`, `diferentes_HEAD=0`, e o mesmo `619/619`
  contra o merge ref; bloco C confere os 19 arquivos do PR por SHA-256. Veredito
  `APROVADO`.
* Não-vacuidade: a única entrada do wheel sem par na árvore é `steamzero/_build_info.py`,
  gerada em build, e ela é **conferida por conteúdo** — declara `SOURCE_COMMIT =` o merge
  ref do run e `SOURCE_DIRTY=False`. O pareamento é feito no espaço de nomes do artefato
  (o wheel desprefixa `src/`); com o prefixo o conjunto seria vazio e "0 diferentes" seria
  uma alegação sobre 0 comparações.
* O varredor é portátil e foi re-medido como tal: a constante do checkout era um caminho
  absoluto da máquina do autor, que não pertence a um repositório público. Passou a ser
  derivada da localização do próprio arquivo (sobrescrita opcional por `STEAMZERO_CHECKOUT`)
  e o arquivo foi formatado. Prova de que a edição não mudou a medição: `diff` entre a saída
  gravada em §9 e a saída das duas reexecuções é **vazio** — mesma cabeça, mesmo merge ref,
  `619/619` nos dois refs, `19/19`, rc=0.

Isto é o que a pendência 2a do lote pedia: a prova deixou de ser a configuração de
packaging e passou a ser o artefato que o CI autorizado produziu.

## 5. O defeito que a medição encontrou no meu próprio temporário

O diretório e o zip locais do artefato do wheel estavam com nome truncado em dois
caracteres — `…52a64` + `a3cd8…`, 38 hex em vez de 40. O conteúdo nunca dependeu do nome
(a proveniência é lida de dentro do artefato), mas a alegação "o artefato chamado X é o
artefato X do run" exige o nome exato. Registrado em vez de consertado em silêncio: o
`arts30_reconcile.py` renomeou para o nome da API, imprimiu a linha
`RENOMEADO … (nome local truncado)`, e o varredor foi re-executado depois do renomeio com o
mesmo veredito. Como checagem independente do caminho, o artefato foi baixado de novo com
o comando canônico (`gh run download … -n steamzero-wheel-8bdbb42a…`) em diretório novo:
8 arquivos e o mesmo `sha256` de wheel (`60fc3973…`).

O motivo interessa ao método: um nome truncado teria feito a varredura B falhar alto se a
prova dependesse do caminho. Ela não dependeu, e é por isso que a reconciliação de tamanho
e digest existe como seção separada — para pegar justamente o que o conteúdo não pega.

## 6. Os dois wheels do CI lado a lado: o produto é o mesmo, o carimbo não

O wheel deste run (`60fc3973…`) difere do wheel do run da cabeça anterior
(`232414d7…`). Comparação entrada por entrada dos dois arquivos zip (log §14):
**625 entradas em cada, 623 byte a byte idênticas, 2 diferentes** —
`steamzero/_build_info.py` (só a linha `SOURCE_COMMIT`, que aponta o merge ref de cada run)
e o hash dela no `RECORD`. Nenhum `.py`, `.qml`, `.js` ou schema mudou.

É esta a forma material de "a árvore testada só recebeu documento depois do verde": a
afirmação não depende da boa vontade de quem narra, ela está no pacote. O produto que a
suíte integral exercitou é o produto desta cabeça, com a diferença limitada ao carimbo de
proveniência que o CI escreve por construção.

## 7. O que a cabeça final recebeu da anterior

`2d04ac96..ee09dbcc` = 3 commits, 9 arquivos, **todos** em `docs/` — 4 na pasta de evidência
29 e 5 em views/cartão (`docs/STATUS.md`, `docs/ACTIVE-WORK.md`, `docs/status/COVERAGE.md`,
o item `ui-desktop-audit.json` e o workstream `rc01-storage-units-2026-09-28.json`).
`src=0`, `tools=0`, `tests=0` medidos por `git diff --name-only` no delta (log §13).

A distinção é deliberada. O intervalo anterior, `f9ec2815..2d04ac96`, continha 71 docs **e 1
arquivo de teste** (`tests/integration/test_storage_units_locale_matrix.py`), e a evidência
29 §4 teve de dizer isso e provar re-validação proporcional. Aqui o span é puramente
documental, e a frase estrita vale sem ajuste. Nenhuma das duas rodadas chama a árvore de
congelada: o que existe é a medição do delta e, no §6, a prova de que o pacote não mudou.

## 8. A cadeia de integração, re-medida nesta passada

`origin/main = 3495c49d`. Seis aberturas — #239 `069501ab`, #240 `c959be13`, #241 `190ea683`,
#242 `5d95034b`, #243 `c0de54c9`, #244 `ee09dbcc` — todas `OPEN` e `MERGEABLE`. A
ancestralidade real entre cabeças (a base declarada é `main` nos seis) é linear:
`239→240 SIM`, `240→241 SIM`, `241→242 SIM`, `242→243 SIM`, `243→244 SIM`. Contra
`origin/main`, cada cabeça está à frente por 2, 7, 20, 24, 34 e 48 commits e **atrás por 0**
em todos os seis.

Consequência prática: mesclar fora da ordem #239 → #240 → #241 → #242 → #243 → #244 faz o
PR seguinte perder base. Nenhum merge foi executado nem presumido — a autorização é do
operador, e o fecho de cada frente só acontece com o SHA realmente integrado.

## 9. O que esta leitura não fecha

* **`GAP-UI-VISUAL-CAPTURE-NOT-CERTIFIED-IN-CI` continua aberto.** O artefato
  `qml-visual-artifacts` deste run tem 59 arquivos (41 PNG, 15 JSON, 3 TXT) em três
  famílias de importador: `esde-import` 28, `retrofe-import` 23, `shell-esde-import` 8.
  Contagem de PNG por família: 20/16/5 = 41 — as duas contagens são do mesmo artefato com
  escopos diferentes, reconciliação na log §16 e em 29 §10. **Zero** capturas de
  armazenamento em escala de texto 100/125/150 %, que é critério físico de RC-01. Provar o
  pacote não prova o critério.
* **Nenhuma integração.** Os seis PRs seguem abertos; o veredito terminal deste lote é
  `ee09dbcc`, e a cabeça vai se mover de novo com os commits documentais desta evidência.
  A leitura do CI desse novo tip é a próxima obrigação, e vai registrada no corpo do PR
  (fora da árvore) para a árvore parar de envelhecer.
* **O que a prova de wheel não cobre**: o wheel é lido contra blobs Git, então prova
  conteúdo de arquivos, não execução instalada. A validação física do `2.0.0rc1` instalado
  continua pendência própria do RC-01, com o `make`/release existente como ponto de partida.
* **Limites da partição visual**: o job do gate roda `-q` e não imprime nomes de teste. A
  cobertura do gate no runner é provada por reconciliação de contagem (`348+12+6185=6545`) e
  pelas 4 linhas de skip atribuídas a `test_qml_asset_recipes.py`, não por listagem linha a
  linha. A resolução de nome do Qt na imagem do CI foi exercida (verde), não presumida.

## 10. Arquivos desta evidência

| arquivo | conteúdo |
|---|---|
| `30-ci-terminal-na-cabeca-ee09dbcc.md` | esta leitura: veredito terminal, suítes dos artefatos, correção de 8 → 19, prova de empacotamento, dois wheels, cadeia, pendências |
| `30-ci-terminal-na-cabeca-ee09dbcc.log` | as 17 seções cruas: `gh pr view`/`run view`/`check-runs`/`statusCheckRollup`, 11 ciclos do waiter com o ERRO do ciclo 9, reconciliação de 6 artefatos, `sha256sum -c`, `verify-wheel`, varredura A/B/C, footprint por API e por git, junit/coverage/gate, atribuição do `+1` de cobertura, diff dos dois wheels, delta documental e cadeia |
| `30-verificacao-wheel-na-cabeca-ee09dbcc.py` | o varredor reproduzível: recebe diretório do artefato e lista de arquivos, lê o merge ref da própria proveniência, desfaz o prefixo `src/`, confere 619 blobs + o gerado em build por conteúdo, e os 19 do PR por SHA-256 |

Fora da pasta de evidência, nada mudou nesta passada: o `git status` no momento da leitura
mostrava apenas o script novo, sem tracked modificado (log §17).
