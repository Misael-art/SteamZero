# 16 — CI terminal no SHA final, wheel lido do próprio run, e o corpo do PR revisado

Instrução do operador (2026-09-28, itens 2a e 5): *confirmar o CI terminal no SHA
final e inspecionar os artefatos necessários; não encerrar com "CI rodando";
verificar o empacotamento no wheel produzido pelo CI autorizado, não na
configuração declarada.*

Saída crua em `16-ci-terminal-e-wheel-no-sha-final.log` (106 linhas, montada com
`cat` dos logs do próprio executor mais as leituras diretas do `gh`, sem
retranscrição).

## 1. O veredito terminal, no SHA que é a cabeça do PR

Cabeça de `codex/rc01-readiness-semantics-2026-09-28` e do PR #243:
`ba2ec0a8b1702835d5ecfc23670b376e64244513` (documental; conteúdo funcional =
`ec86c228` + harness `041139e9`). Run [`36497630184`](https://github.com/Misael-art/SteamZero/actions/runs/36497630184):

```
conclusao=success atualizado=2026-09-28T23:43:48Z
Gate visual QML (Linux)          :: completed :: success   (21m30s)
Python 3.11 / 3.12 / 3.14        :: completed :: success   (9m6s / 12m43s / 9m17s)
Wheel limpo, smoke e supply chain:: completed :: success   (38s)
Smoke Ubuntu 24.04 / Arch / Manjaro :: completed :: success (36s / 45s / 37s)
```

Oito jobs `completed success`. `gh pr checks 243` lido depois da conclusão: 8
`pass`, 1 `skipping` (Sourcery) e CodeRabbit com review manual pendente.
`gh pr view 243`: `state=OPEN mergeable=MERGEABLE mergeStateStatus=CLEAN
base=main headRefOid=ba2ec0a8`. Merge é do operador; nada aqui o executou ou
presumiu.

A espera foi pelo waiter limitado `/tmp/ux03_ci_wait_16.sh` (segmentos de 120 s,
teto de 18, log único `/tmp/ux03_ci_16.log`), que imprime a rolagem por job ao
concluir — 11 segmentos até `completed`. Não houve consulta intercalada com
mudança na árvore: o checkout ficou em `ba2ec0a8` com `git status --short` vazio
durante todo o período, e a árvore foi reconferida depois (`git status --short`
vazio, `16-…log` no fim).

O item 5 proíbe encerrar com "CI rodando". Este arquivo é a leitura terminal, não
uma promessa de leitura.

## 2. O wheel do run terminal — a prova no próprio SHA, não por transferência

A rodada 13 provou o empacotamento lendo o artefato do run `36475422213`, cuja
cabeça era `ec86c228`. Faltava a prova **neste** SHA, e ela existe: o run
`36497630184` publicou `steamzero-wheel-55c0f07e133a3c7f8e6e28c56f92cdb79fbd3e6b`
(11 186 419 B). Execução (`/tmp/ux03_wheel_17.sh`, cwd = checkout, destino `-D`
fora da árvore):

```
entradas no wheel: 624
entradas .js no wheel: ['steamzero/ui/qml/readiness.js']
entradas ui/qml no wheel: 86
steamzero/ui/qml/readiness.js: wheel 8614 B sha256 7d76be27ab727d3f0ae7630e11fa3a2f68cafbdc5d633727429b89cd799e29f5
steamzero/ui/qml/readiness.js: git   8614 B sha256 7d76be27ab727d3f0ae7630e11fa3a2f68cafbdc5d633727429b89cd799e29f5
identico ao SHA final enviado: True
```

`sha256sum -c` contra o `build/SHA256SUMS` do próprio CI: `dist/steamzero-2.0.0rc1-py3-none-any.whl: SUCESSO`.
`tools/release_provenance.py verify-wheel --wheel dist/steamzero-…whl` → exit 0,
`{"project": "steamzero", "sha256": "1e3e333d5bba66dc47477130bb13cff79e217ded79796e61cdf80e97a578884d", "version": "2.0.0rc1"}`,
e o `subject.sha256` do `build/provenance.json` é o mesmo valor — o verificador
governado e a proveniência concordam entre si.

Identidade, sem escondê-la: `provenance.json` deste artefato diz
`ref=refs/pull/243/merge`, `commit=55c0f07e133a3c7f8e6e28c56f92cdb79fbd3e6b`,
`runId=36497630184`. Num run `pull_request` o nome do artefato usa o **merge ref**,
não a cabeça enviada; por isso o wheel se chama `55c0f07e…` enquanto este PR é
`ba2ec0a8`. O que a prova estabelece é que o `.js` entra no wheel construído pela
pipeline governada **a partir deste conteúdo**; o wheel nomeado pelo SHA
integrado continua artefato do fluxo de release do operador (AGENTS.md §4), e
nada aqui o antecipa.

Dois erros de execução desta rodada, registrados: (a) `verify-wheel` foi chamado
como posição (`verify-wheel <caminho>`) e pediu `--wheel`; (b) a comparação com
`git show` usou `steamzero/ui/qml/readiness.js`, caminho que no repositório é
`src/steamzero/…` — `exit 128`. Os dois foram corrigidos na mesma rodada e a
leitura acima é a corrigida. Não houve dano à árvore: nenhum dos dois escreve.

## 3. Cobertura lida do artefato do mesmo run — e o que a diferença de 1 linha significa

`coverage-python-3.14` do run `36497630184`:

```
pct=85.48812664907652  covered=41760  missing=5604  statements=47364
```

Contra `fail_under = 85`: verde. O run da cabeça anterior (`36475422213`)
publicara `85.48971612041835 / covered=41761 / missing=5603 / statements=47364`.
Mesmo total de declarações, diferença de 0,0016 pp. Em vez de atribuir isso a
esta frente, a comparação arquivo por arquivo foi executada nos dois JSON:

```
arquivos com diferenca real: 2
src/steamzero/adapters/linux_runtime.py     (227, 202, 25) -> (227, 203, 24)   +1 coberta
src/steamzero/adapters/scraping/cache.py    (121, 117, 4)  -> (121, 115, 6)    -2 cobertas
```

Saldo: +1 e −2 = −1 linha coberta, exatamente o delta do total. E os dois
arquivos **não pertencem a esta frente**: `git diff --name-only
origin/main...ba2ec0a8 -- <esses dois>` devolve vazio, e o único commit da
cabeça nova é documental (`ec86c228..ba2ec0a8` toca apenas `docs/` e o harness).
Conclusão registrada: entre dois runs de conteúdo funcional **idêntico** a
cobertura do CI move três linhas em dois arquivos alheios — ou seja, uma
diferença desta ordem não é sinal de regressão, e o que se alega é "acima do
piso", nunca "cobertura igual ao run anterior". As linhas exatas não foram
pinadas: nenhum dos dois arquivos está no diff desta branch, então identificar
qual `if` de platform-dependente mudou de lado não teria ganho de informação
para esta entrega.

## 4. Artefato de capturas: a lacuna visual continua, medida e não reinterpretada

Os artefatos do run terminal são 6: `qml-visual-artifacts` (2 004 709 B),
`test-results-3.11/3.12/3.14`, `coverage-python-3.14` e o wheel. Dentro de
`qml-visual-artifacts` (`/tmp/ux03_ci_captures_16`) há 59 arquivos e 41 PNG, e as
famílias são exatamente `esde-import`, `retrofe-import` e `shell-esde-import`. A
superfície de prontidão é provada no CI por harness offscreen
(`test_qml_handheld_offscreen`, job verde), mas **não publica PNG** no artefato.
Portanto `GAP-UI-VISUAL-CAPTURE-NOT-CERTIFIED-IN-CI` (escala de texto
100/125/150 %) permanece aberto — e o corpo do PR diz "permanece aberto", não
"fechado pela UX-04". O mecanismo que falta é o mesmo que o critério da UX-04
exige, o que faz do recorte seguinte o lugar honesto para fechá-lo; planejado,
registrado, ainda não feito.

## 5. O que foi corrigido no corpo do PR antes de publicar

Três alegações do corpo enviado em `ba2ec0a8` estavam envelhecidas, e a
revisão exigida pelo item 2 foi feita contra o que se mediu depois:

| alegação no corpo antigo | estado medido | correção |
| --- | --- | --- |
| "Empacotamento de `readiness.js` no wheel — **PENDENTE**" | provado nos runs `36475422213` e `36497630184`, mesmo sha256 do blob | seção reescrita como prova lida do artefato, com a nuance do merge ref e o comando de reprodução |
| "harness … com **112 pinos**" | `check_readiness_surface: 125 verificação(ões) ok` (log `14-…`, linha 129) | 125, com a causa da mudança de 112 para 125 (espera por condição) |
| "`1 failed, 6483 passed, 47 skipped` em 2071,39 s" como número do lote | checkpoint 13, na árvore com o harness corrigido: `1 failed, 6484 passed, 47 skipped` em 1966,18 s | os dois checkpoints passam a aparecer separados, cada um com seu conteúdo; cobertura e gate visual do CI terminal entram na lista |

Acrescentados: a seção de teste de cor (item 2b — pino de hex substituído por
relação estado→tinta, com as mutações M-k′/M-l da rodada 4 como prova de que
morde), a seção de geometria (causa do frame posterior), a verificação dos
consumidores do contrato v2 (item 3), o veredito terminal e a cobertura do
mesmo run. A tabela de pinos da rodada 5 foi conferida no arquivo antes de
citada: sete cenas M0–M6, não "seis mutações duas de cor" — as mutações de cor
são da rodada 4, e o corpo diz isso.
