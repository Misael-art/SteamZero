# 29 — CI terminal na cabeça final, pacote conferido byte a byte e a correção honesta sobre "só documento"

Instrução do operador (2026-09-28, itens 1, 2a, 4 e 5): terminar a suíte integral sem
alterar a árvore; provar empacotamento no wheel produzido pelo CI autorizado, não na
configuração; confirmar o CI terminal no SHA final e inspecionar os artefatos, sem
encerrar com "CI rodando"; e, depois do integral, declarar com honestidade o que a
árvore testada recebeu — sem chamar de congelada uma árvore que foi modificada.
Saída crua em `29-ci-terminal-no-sha-final.log` (13 seções). Cada número do log vem de
um comando executado nesta passada — os comandos estão listados na seção 0 e são
reproduzíveis sem depender dos temporários do operador, que vivem fora do checkout.

Cabeça final do PR #244: `2d04ac96c56e0b7921cad98dbcf5183a7a78391f`. Run
[`36544698400`](https://github.com/Misael-art/SteamZero/actions/runs/36544698400)
(`pull_request`, `conclusion=success`).

## 1. O veredito terminal, com a identidade da árvore pinada em cada ciclo

Oito jobs `completed success` (seções 2 e 3 do log): Wheel limpo/smoke/supply chain em
48 s, três smokes de plataforma (Arch e Manjaro 37 s, Ubuntu 24.04 42 s), Python
3.14 encerrado às 08:52:58Z, 3.12 às 08:54:43Z, 3.11 às 08:57:54Z e Gate visual QML
encerrado às 09:06:31Z (21m27s). Dez checks no head: 9 `pass` + `Sourcery review`
`skipping`. PR `OPEN`, base `main`, `mergeable=MERGEABLE`, `mergeStateStatus=CLEAN`.

A espera foi pelo waiter `~/steamzero-ux04-tmp/wait_ci_244_run2.sh` (segmentos de 120 s,
teto de 40, log único `ci_244_run2.log`): **terminal no ciclo 12**,
`2026-09-29T09:08:24Z`, `pendentes=0`. O ciclo 4 registra `pendentes=ERRO` — uma
consulta de checks que falhou e foi re-consultada no ciclo seguinte; o contador que
encerra a espera é o do ciclo 12, e a linha fica no log em vez de ser apagada.

Isto fecha o limite que a evidência 28 declarou sobre si mesma ("o waiter não pinou a
identidade da árvore em cada ciclo"): aqui cada um dos 12 ciclos imprime
`head_local=2d04ac96…` e `linhas_status=0` (seção 5 do log). A ausência de escrita na
árvore durante os 23 minutos de espera é, portanto, medida por ciclo, não inferida dos
extremos.

## 2. As suítes lidas dos artefatos do próprio run, não da cor do job

Seção 10 do log. Os três XMLs junit publicados (`test-results-3.11/3.12/3.14`) somam,
cada um, **6185 testes, 0 falhas, 0 erros, 47 skips** (725 s / 542 s / 436 s de tempo de
teste). O rollup do gate visual, lido do log do job `109328169087`:
`348 passed, 12 skipped, 6185 deselected in 1222.86s` — os 12 skips nomeados são todos
`tests/integration/test_qml_asset_recipes.py` (`:100`, `:111`, `:120`, `:131`, motivo
`QML-RHI-ENVIRONMENT-001`), nenhum atribuído à matriz de unidades. `348 + 12 = 360`
bate com a coleção visual medida no host pela evidência 28. O isolador publicou
`real-state before/after: exists=False … source=HOME-default`: o gate não tocou estado
real do runner.

Cobertura (`coverage-python-3.14`): `pct=85.4854091169178`, `covered=41761`,
`missing=5605`, `statements=47366`, contra `fail_under = 85` (`pyproject.toml:129`).
Contra o run anterior do mesmo PR (36521236686, evidência 28): `85.48858795854791 /
41762 / 5604 / 47366`. O delta é **−1 coberta, +1 não coberta, 0 em declarações**.

Esse delta não pode vir de código, e a prova é dupla (seções 11 e 12 do log):

* entre `37f0add4` e `2d04ac96`, `src/`, `tests/` e `tools/` têm **0** arquivos
  alterados — os 10 caminhos do intervalo são todos de `docs/`;
* os dois wheels do CI, comparados entrada a entrada, diferem em **exatamente duas**
  entradas de 625: `steamzero/_build_info.py` (só a linha `SOURCE_COMMIT`, que nomeia o
  merge commit de cada run) e a linha do `RECORD` que carrega o hash dessa mesma
  entrada. As outras 623 são byte a byte idênticas.

Pacote idêntico, contagem de cobertura que se move em uma linha: é nondeterminismo de
execução (linha condicional atingida ou não conforme o ambiente), não regressão. Não se
alega "cobertura igual" nem "cobertura melhorou"; alega-se **acima do piso**, com o
delta medido e a causa provável declarada.

## 3. A prova de empacotamento saiu da configuração e virou verificação do pacote inteiro

`28-verificacao-wheel.py` conferia os 8 caminhos que o PR altera. `29-verificacao-wheel-no-sha-final.py`
conferiu **o pacote inteiro** (seção 8 do log), comparando o hash de blob Git de cada
entrada do wheel com o blob da mesma path na árvore:

```
entradas_no_wheel=620 arquivos_no_HEAD=619
sem_par_no_wheel=['steamzero/_build_info.py'] (total=1)
sem_par_no_HEAD=[] (total=0)
pareados=619 identicos_HEAD=619 diferentes_HEAD=0
pareados_merge=619 identicos_merge=619 diferentes_merge=0
veredito=sujeito=True varredura_total=True arquivos_do_pr=True APROVADO   (exit 0)
```

* **619/619** arquivos de `src/steamzero` do wheel são byte a byte os blobs da cabeça
  enviada (`2d04ac96`) **e** do merge ref (`51442579…`) sobre o qual o run construiu;
* a única entrada do wheel sem par na árvore é `steamzero/_build_info.py`, gerada em
  build por `hatch_build.py` e auto-declarada no próprio corpo ("NÃO EDITE À MÃO"). Ela
  não é tolerada como ruído: é **conferida por conteúdo** — `SOURCE_COMMIT` igual ao
  merge ref da proveniência e `SOURCE_DIRTY=False`;
* `sem_par_no_HEAD=0`: nenhum arquivo do produto ficou de fora do pacote;
* o merge ref não é argumento do script: é lido de `build/provenance.json` do próprio
  artefato (`ref=refs/pull/244/merge`, `run=36544698400`, `builder=github-actions`,
  `sourceTreeState=clean`), junto com `repository=Misael-art/SteamZero`.

Integridade do artefato no mesmo run: `sha256sum -c build/SHA256SUMS` → seis `SUCESSO`;
verificador governado `tools/release_provenance.py verify-wheel --wheel …` → `exit 0`
com `sha256=232414d7865eb2a8…c718b7`, igual a `subject.sha256` da proveniência e ao hash
do arquivo no disco; os 8 arquivos do PR listados com SHA-256 individual (seção C),
para conferência independente.

Dois fatos operacionais, registrados porque a prova tem de ser reproduzível: o merge
commit `51442579…` **não estava no objeto local** — a passada precisou de
`git fetch --no-tags origin refs/pull/244/merge`, que acrescenta objetos sem tocar a
árvore de trabalho (reconferido: `git status --short` seguiu com uma linha, o próprio
script desta evidência). E a primeira versão do script indexou a árvore com o prefixo
`src/`, enquanto o wheel desprefixa `src/`: o pareamento ficou vazio. Em vez de ler
"620 sobrando, 0 diferentes" como verde, o script passou a exigir o conjunto pareado e
hoje imprime os totais dos dois lados.

**Limite do que isto prova:** que o wheel produzido pela pipeline governada a partir
deste conteúdo contém exatamente o código testado. Não é o artefato nomeado pelo SHA
integrado — num run `pull_request` o nome carrega o merge commit do GitHub, não a cabeça
enviada — e continua sendo produto do fluxo de release do operador (`AGENTS.md §4`),
que nada aqui antecipa.

## 4. Correção honesta: depois do checkpoint integral a árvore não recebeu só documento

A alegação fácil seria "a árvore testada só recebeu mudanças documentais". **Medida, ela
é falsa**, e o log diz o porquê (seção 9): entre o checkpoint integral `f9ec2815`
(evidência 27) e a cabeça final `2d04ac96`, há 6 commits — `src/` 0, `tools/` 0,
`docs/` 71 e **`tests/` 1**: `tests/integration/test_storage_units_locale_matrix.py`
(`1eae804c`, "o gate de locales passa no ruff, nenhuma assercao muda").

O que esse um arquivo mudou foi medido estruturalmente, não lido no diff:

```
funcoes_f9ec=9 funcoes_2d04=9 mesmos_nomes=True
sequencias_de_opcode_diferentes=0 []
pool_diferente_em=<module>.test_a_matriz_exerce_dois_contextos_de_formatacao_distintos
  f9ec=': gate reprovado antes da comparação'
  2d04=': o gate reprovou antes da comparação'
```

Nove unidades de código, mesmas sequências de opcodes — nenhuma condição de asserção,
nenhuma chamada, nenhum ramo mudou; a única diferença no pool de constantes é a **mensagem**
de uma asserção. O commit é de formatação (duas expressões refluidas para caber em
`line-length = 100`) mais esse texto.

Revalidação proporcional ao que se mudou, e ela existe:

* o arquivo foi re-executado localmente nesta cabeça: `3 passed in 26.32s`;
* os três jobs Python do run `36544698400` rodaram a suíte inteira (6185 testes) sobre
  essa árvore e o gate visual publicou o rollup acima — o que cobre qualquer efeito que a
  mudança de teste tivesse;
* o produto é o mesmo byte a byte desde o checkpoint: `src/` inalterado no intervalo
  (seção 9) e os 619 arquivos do pacote iguais aos blobs da cabeça final (seção 8). As
  duas afirmações compostas são o que permite dizer que **o conteúdo funcional testado
  no checkpoint é o conteúdo funcional do wheel do SHA final**, sem chamar a árvore de
  congelada.

Nada aqui reescreve a evidência 27: o checkpoint integral continua sendo `f9ec2815` com
a guarda de árvore que ele registrou.

## 5. Pendência que esta leitura não fecha

`qml-visual-artifacts` (2 004 711 B, 59 arquivos) tem três famílias — `esde-import`
(20 PNG), `retrofe-import` (16), `shell-esde-import` (5) — e **0** PNG cujo nome mencione
`storage|unidade|sizes|emulation`. A superfície de unidades é provada no CI pelo harness
offscreen e pela matriz de locales, mas não publica PNG em 100/125/150 % de escala de
texto. `GAP-UI-VISUAL-CAPTURE-NOT-CERTIFIED-IN-CI` permanece aberto e continua critério
da RC-01; o mecanismo que falta está registrado na frente de prontidão, e é lá que se
fecha.

## 6. A cadeia de integração, re-medida nesta passada

Seção 13 do log — medida agora, não herdada da evidência 28:

| PR | cabeça | estado | base |
| --- | --- | --- | --- |
| #239 | `069501ab` | `OPEN`, `MERGEABLE/CLEAN` | `main` |
| #240 | `c959be13` | `OPEN`, `MERGEABLE/CLEAN` | `main` |
| #241 | `190ea683` | `OPEN`, `MERGEABLE/CLEAN` | `main` |
| #242 | `5d95034b` | `OPEN`, `MERGEABLE/CLEAN` | `main` |
| #243 | `c0de54c9` | `OPEN`, `MERGEABLE/CLEAN` | `main` |
| #244 | `2d04ac96` | `OPEN`, `MERGEABLE/CLEAN` | `main` |

As cinco arestas de ancestralidade (`239→240→241→242→243→244`) devolvem `SIM`;
`origin/main` está em `3495c49d` e **todas as seis cabeças têm `behind=0`** — nenhuma
precisa de rebase, e a ordem que a própria ancestralidade impõe é a da tabela. O próximo
elo (RetroFE dentro do shell) nasce de `2d04ac96`, portanto entra depois do #244. Merge é
do operador: nada aqui executou, agendou ou presumiu merge, e nenhuma frente se declara
integrada.

Nada nesta evidência alega release instalada, merge ou RC-01 completa.

## 7. Arquivos desta evidência

* `29-ci-terminal-no-sha-final.log` — as 13 seções cruas, com os comandos de reprodução;
* `29-verificacao-wheel-no-sha-final.py` — varredura total do pacote contra a árvore
  (reproduzível: recebe o diretório do artefato e a lista de arquivos do PR; lê o merge
  ref da proveniência);
* este arquivo.
