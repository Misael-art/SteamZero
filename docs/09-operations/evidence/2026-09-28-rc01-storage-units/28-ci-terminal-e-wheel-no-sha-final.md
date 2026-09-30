# 28 — CI terminal na cabeça do PR, wheel lido do próprio run e o que a leitura não cobre

Instrução do operador (2026-09-28, itens 2a e 5): *confirmar o CI terminal no SHA
final e inspecionar os artefatos necessários; não encerrar com "CI rodando";
verificar empacotamento no wheel produzido pelo CI autorizado, não na configuração
declarada.* Saída crua em `28-ci-terminal-e-wheel-no-sha-final.log` (14 seções,
montada com `cat`/`grep` do log do próprio job mais leituras diretas do `gh` e do
`git`, sem retranscrição).

## 1. O veredito terminal, no SHA que é a cabeça

Cabeça de `codex/rc01-storage-units-2026-09-28` e do PR #244:
`37f0add44efa15fef55496698254ef0722ae552b`. Run
[`36521236686`](https://github.com/Misael-art/SteamZero/actions/runs/36521236686)
(`pull_request`, `conclusion=success`):

```
Wheel limpo, smoke e supply chain   completed success  (04:21:09 → 04:21:46, 37s)
Smoke Ubuntu 24.04                  completed success  (04:21:10 → 04:21:42, 32s)
Smoke Arch Linux                    completed success  (04:21:09 → 04:21:43, 34s)
Smoke Manjaro                       completed success  (04:21:11 → 04:21:51, 40s)
Python 3.14                         completed success  (04:21:10 → 04:31:21, 10m11s)
Python 3.11                         completed success  (04:21:10 → 04:33:59, 12m49s)
Python 3.12                         completed success  (04:21:10 → 04:38:40, 17m30s)
Gate visual QML (Linux)             completed success  (04:21:10 → 04:42:39, 21m29s)
```

Oito jobs `completed success`. A espera foi pelo waiter `/home/misael/steamzero-ux04-tmp/wait_ci_244.sh`
(segmentos de 120 s, teto de 30, log único `ci_244.log`): **terminal no ciclo 12**,
`2026-09-29T04:44:05Z`, com `pendentes=0`. Limite do método, declarado: o waiter não
pinou a identidade da árvore em cada ciclo (o do lote de prontidão pinava). O que se
pode provar é que esta frente não escreveu na árvore durante os 22 minutos de espera e
que a identidade foi conferida nos dois extremos — `HEAD = 37f0add4…` com
`git status --short` vazio antes do envio e reconferida na leitura terminal.

Cadeia re-medida nesta passada (seções 2 e 3 do log): as seis cabeças
(#239 `069501ab`, #240 `c959be13`, #241 `190ea683`, #242 `5d95034b`, #243 `c0de54c9`,
#244 `37f0add4`) estão `OPEN`, base `main`, `mergeable=MERGEABLE`,
`mergeStateStatus=CLEAN`, cada uma com **10 checks: 9 `pass` + 1 `skipping`**
(`Sourcery review`); as cinco arestas de ancestralidade devolvem `SIM`. Merge é do
operador — nada aqui o executou, agendou ou presumiu.

## 2. A matriz de locales exerceu os dois fusos dentro da imagem do CI

O risco residual declarado no PR era este: a perna `pt_BR` da matriz exige que o Qt
da **imagem do gate** resolva `LC_ALL=pt_BR.UTF-8` para o nome `pt_BR`; se resolvesse
para `C`, o teste reprovaria. O gate visual terminou verde, então a perna passou —
mas "passou" precisa de prova de que o teste **rodou**, e o log do job usa `-q`, que
não imprime nomes. A reconciliação é aritmética sobre números do próprio CI:

| grandeza | valor | fonte |
| --- | --- | --- |
| coleção visual no host | `360/6545 tests collected (6185 deselected)` | seção 9 do log, `pytest -m visual --collect-only -q` |
| rollup do CI | `348 passed, 12 skipped, 6185 deselected in 1220.44s` | seção 6, linha terminal do job |
| skips nomeados | 4 linhas, todas `tests/integration/test_qml_asset_recipes.py` (`:100`, `:111`, `:120`, `:131`), motivo `QML-RHI-ENVIRONMENT-001` | seção 6 |

`348 + 12 = 360` e `6185` batem com a coleção do host, logo a matriz (3 testes: dois
por locale + a prova de não vacuidade) entrou na execução e não está entre os skips —
nenhum skip é atribuído a ela. Adicionalmente o harness de unidades está registrado em
`tests/integration/test_qml_handheld_offscreen.py` (commit `f9ec2815`), que é do mesmo
conjunto visual. **Limite declarado da inferência:** é reconciliação de contagem sobre
o rollup do CI, não uma linha do CI nomeando o teste. Se a discordância fosse
possível, ela apareceria na própria aritmética.

O isolador publicou a prova de estado do host nas duas pontas do job
(`real-state before/after: exists=False files=0 … source=HOME-default`), ou seja, o
gate não tocou estado real do runner.

## 3. O wheel do run terminal: a prova saiu da configuração e foi para o artefato

`22-empacotamento-do-formatador.md` deixara a afirmação em "configuração inclui,
artefato ainda não conferido". Agora conferida, arquivo por arquivo, com
`28-verificacao-wheel.py` (seção 12 do log):

```
src/steamzero/ui/qml/sizes.js              2377 B  OK  sha256=6d5ca418e514258f…315a4829
src/steamzero/schemas/emulation-workspace-v1.schema.json  45 390 B  OK  sha256=631a6e99c2f58ca0…
… 8 arquivos, total=8 identicos_head=8 identicos_merge=8
```

Os oito caminhos `src/` alterados por esta frente (de `c0de54c9..HEAD`) estão no wheel
com bytes **idênticos** aos blobs da cabeça enviada (`37f0add4`) e aos do merge ref
sobre o qual o run construiu (`a555999c`). Dentro do artefato, o `$defs/card` lido do
próprio `.whl` traz `metricBytes` e `capacityBytes` como `{"type": ["integer","null"],
"minimum": 0}`, `required` inalterada (`id,title,detail,state,statusLabel`) e
`additionalProperties: true` — o contrato aditivo v1 viaja como publicado.

Provas de integridade do artefato, todas no mesmo run:

* `sha256sum -c build/SHA256SUMS` (publicado pelo CI): seis `SUCESSO`, incluindo
  `dist/steamzero-2.0.0rc1-py3-none-any.whl = 50cafc76745cadef…a6d0c880`;
* verificador governado: `tools/release_provenance.py verify-wheel --wheel …` →
  `exit 0` e `{"project":"steamzero","sha256":"50cafc76…","version":"2.0.0rc1"}`, o
  mesmo valor do `subject.sha256` do `build/provenance.json`;
* `provenance.json`: `ref=refs/pull/244/merge`, `commit=a555999c…`,
  `sourceTreeState=clean`, `runId=36521236686`.

Identidade sem escondê-la: num run `pull_request` o nome do artefato carrega o SHA do
**merge commit** que o GitHub fez (`a555999c`), não a cabeça enviada (`37f0add4`). O
que a prova estabelece é que o formatador entra no wheel construído pela pipeline
governada a partir **deste conteúdo**; o wheel nomeado pelo SHA integrado continua
artefato do fluxo de release do operador (`AGENTS.md §4`), e nada aqui o antecipa.

Com isso, a pendência 2a do lote está fechada por leitura de artefato, e a frase
"configuração inclui" deixa de ser a alegação — vira premissa da qual se passou à
verificação empírica.

## 4. Cobertura lida do mesmo run, e o que o delta significa aqui

`coverage-python-3.14` do run `36521236686`: `pct=85.48858795854791`,
`covered=41762`, `missing=5604`, `statements=47366` contra `fail_under = 85`
(`pyproject.toml:129`) — acima do piso.

Contra a run terminal do lote de prontidão (`36497630184`, evidência 16 daquele
batch): `85.48812664907652 / 41760 / 5604 / 47364`. Delta: **+2 declarações, +2
cobertas, 0 não cobertas**. Os dois arquivos que naquele batch se moveram por ruído
de ambiente estão **idênticos** aqui — `linux_runtime.py (227, 203, 24)` e
`scraping/cache.py (121, 115, 6)` —, o que é compatível com o delta pertencer ao
código Python desta frente (`adapters/emulation.py`, 4408 declarações). Não se alega
"cobertura igual" nem "cobertura subiu por causa daqui": alega-se **acima do piso, sem
regressão de não-coberto**, com os dois números e a atribuição pendente de teste
arquivístico.

## 5. O que a leitura NÃO cobre: a captura física continua aberta

`qml-visual-artifacts` (2 004 709 B, 59 arquivos) contém exatamente três famílias:
`esde-import` (28), `retrofe-import` (23), `shell-esde-import` (8). Busca por PNG com
`storage|unidade|sizes|emulation` no nome: **0**. A superfície de unidades é provada
no CI pelo harness offscreen (`test_qml_handheld_offscreen`, `test_storage_units_locale_matrix`,
jobs verdes), mas **não publica PNG** em 100/125/150 % de escala de texto.

Portanto `GAP-UI-VISUAL-CAPTURE-NOT-CERTIFIED-IN-CI` permanece aberto e continua
critério da RC-01. O mecanismo que falta é o mesmo que a frente de prontidão registrou
na seção 4 da sua evidência 16 — é o lugar honesto para fechá-lo, não este lote.

## 6. O que mudou no corpo do PR depois desta leitura

Três alegações foram atualizadas contra o medido, não contra o lembrado: a seção de
empacotamento deixa de dizer "PENDENTE" e passa a citar o run, o artefato, os sha256 e
o verificador governado; o risco residual da matriz passa de "será lido no veredito"
para "lido, com o limite da inferência declarado"; e a cadeia de integração ganha as
medidas desta passada (seis cabeças, 9+1 checks cada, cinco arestas `SIM`).

Nada nesta evidência alega merge, release instalada ou RC-01 completa.

## 7. Arquivos desta evidência

* `28-ci-terminal-e-wheel-no-sha-final.log` — as 14 seções cruas;
* `28-verificacao-wheel.py` — a comparação wheel × blobs (reproduzível: recebe o
  diretório do artefato e a lista de arquivos);
* este arquivo.
