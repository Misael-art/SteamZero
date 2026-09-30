# Evidência do lote RC-01 / contrato de geração no importador ES-DE (2026-09-29)

Frente: `WS-2026-09-RC01-ESDE-IMPORT-GENERATION`, branch
`codex/rc01-esde-import-generation-2026-09-29`, base `c4975979` (ponta do PR #246),
**nono elo** da pilha #239 → #240 → #241 → #242 → #243 → #244 → #245 → #246. Item
normativo: `SZ-UI-DESKTOP-AUDIT`. Este corte fecha a pendência que o sétimo elo
declarou no próprio cartão (`rc01-retrofe-shell-late-2026-09-29.json`, campo
`nextAction`): "contrato de geração no importador ES-DE". Não é um elo aberto para
continuar avançando — é o item que a frente anterior nomeou como faltante.

Conteúdo funcional: `src/steamzero/ui/qml/ThemeEditorPanel.qml` **+47/−7** e
`src/steamzero/ui/qml/Main.qml` **+43/−2** (dois arquivos compartilhados, cada um em
commit próprio por AGENTS.md §2), mais o gate novo
`tests/integration/test_ui_shell_esde_import_late_response.py` (1181 linhas) e o
harness `tests/qml/check_shell_esde_import_late_response.qml` (1247 linhas, 10 cenas).

## O que o lote entrega

1. **O mesmo contrato que a 6ª/7ª fatias estabeleceram para RetroFE, agora no ES-DE.** A
   rota do painel (`ThemeEditorPanel.qml`) e a rota raiz do shell (`Main.qml`) passam a
   carregar um contador de geração do pedido (`esdeImportGeneration`, painel `:83`,
   raiz `:539`): o despacho captura `geracao = geração + 1` e escreve nela, o callback
   de sucesso e o de erro só escrevem na superfície se `geracao === esdeImportGeneration`
   ainda valer, e fechar o diálogo revoga o pedido em voo (`onClosed` move a geração,
   `Main.qml:2910`; `resetEsdeImport()` faz o mesmo no painel, `:218`). Uma resposta
   tardia que chega depois do fechamento não reabre estado, não anuncia sucesso e não
   re-lista temas.
2. **Rollback do dedup nas duas rotas.** Um clique recusado por `actionIsPending`
   devolve a bandeira ao valor que ela tinha ANTES do clique (`ocupadoAntes`), em vez de
   deixá-la armada — o defeito que travava o diálogo (cena 06) — e as rotas de examine e
   aplicar têm rollback próprio (`:265`/`:310` no painel, `:3031`/`:3131` na raiz).
3. **Gate com ponte real e atraso de verdade.** As dez cenas exercitam cliques reais
   sobre o shell renderizado, com um `ThreadingHTTPServer` em loopback que dorme antes de
   responder; nenhum `requestAction` é stubado e nenhuma callback é chamada à mão — é o
   que as três fatias anteriores faziam e por isso não conseguiam ver resposta tardia.

## Como foi provado

`74-gate-esde-raiz-green3.log`: **8 passed** no gate (a nona asserção de alcance,
`test_o_mutante_equivalente_do_apply_na_raiz_e_pino_por_reachability`, ainda não
existia). Antes disso, `71`/`72` registram o vermelho que não era do produto: sob carga
a cena 07 do apply raiz reprovava por `notify` — leitura correta do desfecho quando a
superfície está aberta, defeito quando fechou; a distinção virou asserção nomeada
(`raiz-depois-do-apply-tardio`) e não um `wait()` maior.

Bateria de mutações, duas frentes, `rc=0` nas duas com a árvore restaurada por SHA-256:

| mutante | rota | resultado |
|---|---|---|
| M1 callback de sucesso do examine sem guarda | painel | vermelho — detectado |
| M2 `resetEsdeImport()` sem revogar o pedido | painel | vermelho — detectado |
| M3 examine sem rollback da recusa | painel | vermelho — detectado |
| M4 rollback escrevendo `true` em vez de `ocupadoAntes` | painel | vermelho — detectado |
| M5 callback de sucesso do apply sem guarda | painel | vermelho — detectado |
| M6 examine raiz sem guarda no sucesso | raiz | vermelho — detectado |
| M7 `onClosed` da raiz sem revoke | raiz | vermelho — detectado |
| M8 examine raiz sem rollback da recusa | raiz | vermelho — detectado |
| **M9 rollback do apply raiz escrevendo `true`** | raiz | **sobreviveu — mutante equivalente** |
| M10 apply raiz sem guarda no sucesso | raiz | vermelho — detectado |

M9 sobreviveu (`73-bateria-mutacoes-esde-raiz.log:117-121`) e a causa é do produto, não
do gate: escrever `true` só difere de `ocupadoAntes` quando o clique encontra a bandeira
armada, e a recusa exige um segundo clique que o próprio produto proíbe — o botão
Importar só se habilita com a bandeira baixada. Em vez de afrouxar a asserção, o limite
ficou pinado por um teste de reachability, que falha se a janela de equivalência mudar.

## O corte de citações — e a colisão que ele causou

O corte converteu citações de número de linha (`ThemeEditorPanel.qml:265`) em referência
ao símbolo (`applyEsdeImport()`), que é o que sobrevive a um corte que insere linhas.
`87-verificacao-final-citacoes.log`: 20/20 citações conferindo com HEAD, zero cruas
(`:NNN`), zero estouros de largamento, `VEREDITO PASSO`.

**O corte quebrou duas portas, e não foi pego pelo classificador de papel da linha.**
`92-revalidacao-portar-gates-afetados.log` chegou com **1 failed / 8 passed** nas duas
portas de resposta tardia (ES-DE e RetroFE); as outras duas (diálogo ES-DE, primeira
dobra) ficaram verdes. Causa: as "guardas de intenção" conferem o fonte do harness por
substring (`assert "applyEsdeImport(" not in fonte`), e substring não distingue código de
comentário — o símbolo citado em prosa de comentário acendeu a guarda. `90`/`91` tinham
provado "linha adicionada não é executável" e "nenhuma citação em linha executável": as
duas afirmações continuam verdadeiras e as duas são insuficientes, porque o critério da
guarda é o arquivo inteiro.

`93-guardas-substring-harness.py` reproduz as guardas por AST, sem Qt, escopando por
função o que `fonte` lê (harness, o próprio `.py` ou o produto) — e casa exatamente com o
pytest: 7 ocorrências proibidas, nos dois arquivos que falharam. `94-colisao-guarda-simbolo.py`
corrigiu pelo lado da prosa (o símbolo fica sem o parêntese de chamada: `applyEsdeImport`
continua exato e grepável, e uma chamada real continua tendo parêntese), e o texto de
falha das duas guardas ganhou a convenção — sem isso, quem citar o símbolo numa nota do
harness lê "o harness chama o importador direto" sem como saber que estava num
comentário. Nenhuma condição de asserção foi tocada; estreitar a guarda foi recusado
justamente porque ela é conservadora por desenho.

**Atribuição, corrigida uma vez no meio da rodada.** A primeira leitura disse que a
colisão era pré-corte, porque `cit-backup-83` não a continha como novidade. O snapshot é
de 21:29 — **depois** do `80-corrigir-citacoes.py` (21:16), que é quem escreve
`applyEsdeImport()`/`inspectEsdeImport()` (linhas 33, 59, 63, 87) e
`applyRetrofeImport()` (linha 121). As sete colisões são do corte de citações. O que não
se achou em artefato nenhum: uma corrida da porta ES-DE entre 21:16 e 21:57 — o verde
registrado é `74`, de 20:50, anterior às conversões, e o primeiro verde posterior é `98`.

Revalidação proporcional, registrada em arquivo: `98-gates-tardias-pos-colisao-completo.log`
**9 passed / rc=0** nas duas portas afetadas; `97-verificacao-citacoes-pos-colisao.log`
repete o veredito do corte (20/20, cruas 0, largura 0); `93-…-depois.log` com zero
tokens proibidos; ruff check "All checks passed!", `ruff format --check` 681 arquivos
formados, `mypy` 298 arquivos sem issue, `lint_boundaries` 0 violações.
`95-identidade-arquivos-antes-94.txt` guarda o SHA-256 dos quatro arquivos tocados antes
da correção. `96-….parcial-sigterm` é o log descartado: um `pkill` meu matou a primeira
porta no meio da corrida, e o log foi preservado com esse nome em vez de virar evidência.

## Manifesto

`28` nota de fora-de-escopo que abriu o corte · `70`/`73` baterias de mutações (painel e
raiz, driver + log + `.rc`) · `71`/`72`/`74` corridas da porta ES-DE · `75` conferência
de âncoras da raiz · `76`–`83` auditoria de citações (duas árvores, classificação,
deriva, diff, reauditoria, conversão por símbolo) · `84`–`88` conversões residuais e
re-envelopes de largamento · `87` verificação final das quatro invariantes · `90`/`91`
provas de papel da linha e de citação em linha executável · `92` o vermelho proporcional
· `93`–`98` a colisão, sua atribuição e o verde depois dela.

## O que NÃO está provado aqui

Nada disso muda com este lote: o **seletor nativo de diretório** continua sem porta
comprovada (uma rota alternativa funcional por Enter não é prova da rota não testada); a
experiência na **release instalada** não foi medida; não há prova de **empacotamento**
nova; e nada correu em **host físico** — a validação física do conjunto integrado está
preparada em `2026-09-29-rc01-home-first-fold/62-preparacao-de-validacao-fisica.md` e
espera o merge.


## Adendo — checkpoint integral, o vermelho que ele achou, e o gate visual depois dele

O lote tinha uma dívida declarada na própria entrada: a última suíte integral
arquivada era anterior ao trabalho funcional do elo. Ela foi paga aqui, uma única
vez, com a árvore parada em `c4975979`. Os números abaixo foram lidos dos
logs por `103-gerar-adendos-checkpoint.py`, que aborta se o vermelho for outro, se
a árvore tiver mudado entre as duas leituras de identidade do mesmo log, ou se a
renovação posterior não tiver fechado.

Comando: `.venv/bin/python tools/run_tests_isolated.py tests -q`, precedido dos
gates leves de AGENTS §6. Saída completa em `100-checkpoint-integral-nono-elo.log`
(esta pasta), janela `2026-09-29T22:23:18-0300 → 2026-09-29T23:05:46-0300`.

| passo | resultado |
|---|---|
| `ruff check` | rc=0 |
| `ruff format --check` | rc=0 |
| `mypy src` | rc=0 |
| `independence` | rc=0 |
| `suite integral` | rc=1 |

Suíte: **1 failed, 6528 passed, 47 skipped in 2529.34s (0:42:09)**, rc=1. O comportamento passou inteiro. O único
falho é o gate de catálogo gerado — `test_committed_catalog_and_generated_views_are_consistent` —, e a causa
é deste próprio lote: 11 `scopeDigest` envelheceram. A conta dos
escopos é lida dos JSONs dos cartões pelo `103`, não lembrada: `Main.qml` está no
escopo de 8 deles, `ThemeEditorPanel.qml` no de 5, os dois em
`SZ-THEME-ENGINE`, `SZ-UI-DESKTOP-AUDIT` (2), e a união fecha 8 + 5 − 2 =
11 — exatamente o conjunto renovado; fora da união, nenhuma. O cartão desta
frente (`SZ-UI-DESKTOP-AUDIT`) é um dos 2 que cobrem os dois porque nomeia o
diretório `src/steamzero/ui` no escopo, e não um acréscimo à parte; a conta anterior
desta sessão, `7 + 4 − 1 + 1`, estava errada nos dois primeiros números e só fechava
por acaso. Nenhum dos 11 estava envelhecido antes: na cabeça `c4975979` o
mesmo teste passou no CI, cujo job obrigatório "Python 3.11/3.12/3.14" roda
`python tools/project_status.py check` (`.github/workflows/ci.yml:72`).

O remédio é o que AGENTS §6 prescreve para exatamente este caso — *"se só uma visão
ou digest gerado ficou obsoleto, regenere-o e rode apenas a validação de status
aplicável"* — e não uma re-corrida da suíte: `105-renovar-digests.py` renovou no
valor impresso pela ferramenta (dupla leitura: `check` e `digest --item`), `render
--write` atualizou as três visões geradas (`docs/STATUS.md`, `docs/ACTIVE-WORK.md`,
`docs/status/COVERAGE.md`) e o `check` final fechou `rc=0`. Iguais de hash não são
prova de comportamento; o que se afirma aqui é que o **catálogo está consistente com
a árvore**, que é o que aquele teste verifica.

Três limites deste checkpoint, declarados em vez de escondidos:

* `100` rodou **cinco** dos seis gates integrais de §6 e omite `make status-check`.
  Ele foi executado logo depois, antes do gate visual, e está em `OK` — mas a
  corrida de `100` não é, sozinha, "os seis gates na mesma árvore".
* A linha de parada impressa pelo próprio `100` — `suite integral nao voltou rc=0; a suite integral nao roda em arvore que ja reprovou um gate leve.` — diz uma coisa que não
  é verdade neste caso: nenhum gate leve havia reprovado; quem reprova é a suíte. É
  template genérico do driver, fixado byte a byte pelo `103` para que ele possa
  registrar o defeito sem reescrever o log arquivado. O texto do script foi corrigido
  **depois** da corrida, então o `100-checkpoint-integral-nono-elo.py` arquivado e o
  `.log` da mesma pasta já não concordam nessa linha — divergência deliberada e
  declarada aqui: o log é a medição, e a medição não se reescreve.
* Falta aqui o que o `110` trouxe: o gate visual correu na **mesma** árvore, pelo
  precedente do oitavo elo (PASSO 7 de `52`), porque o elo toca duas superfícies
  desenhadas — **377 passed, 6199 deselected in 1711.56s (0:28:31)**, `110-gate-visual-apos-governanca.log`. Ele se
  recusou a rodar no `102` enquanto o checkpoint estava aberto, e o `110` só correu
  depois de verificar cinco premissas lidas da árvore, entre elas que os
  9 arquivos funcionais são byte a byte os mesmos que o `100` testou.

Identidade: mesma cabeça nos dois logs e um único SHA-256 por arquivo entre ANTES
e DEPOIS; agregado dos quatro arquivos do corte `src`/`tests` neste momento =
`49e2044f65ffc29b`.

## Fileira re-medida (passo 5 do operador)

`101-reconcilio-entrega-acumulada.py` consulta o GitHub e roda
`git merge-base --is-ancestor` par a par; saída crua em
`101-reconcilio-entrega-acumulada.log`. A coluna `checks` é `success+skipped / total`
de check-runs da cabeça, contados pelo `101` — por isso `9/9`: as oito obrigatórias em
`SUCCESS` mais o `Sourcery review`, que vem `SKIPPED`. Quem confere a lista
obrigatória nome a nome é o `106`, adiante.

```
    PR estado base                                         cabeça      checks mergeável
  #239   OPEN main                                         069501ab       9/9 MERGEABLE
  #240   OPEN main                                         c959be13       9/9 MERGEABLE
  #241   OPEN main                                         190ea683       9/9 MERGEABLE
  #242   OPEN main                                         5d95034b       9/9 MERGEABLE
  #243   OPEN main                                         c0de54c9       9/9 MERGEABLE
  #244   OPEN main                                         af6a5c6e       9/9 MERGEABLE
  #245   OPEN codex/rc01-storage-units-2026-09-28          2d6a8957       9/9 MERGEABLE
  #246   OPEN codex/rc01-retrofe-shell-late-response-2026-09-29 c4975979       9/9 MERGEABLE
  ### ancestralidade (git merge-base --is-ancestor)
  #239 (069501ab) eh ancestral de #240 (c959be13): SIM
  #240 (c959be13) eh ancestral de #241 (190ea683): SIM
  #241 (190ea683) eh ancestral de #242 (5d95034b): SIM
  #242 (5d95034b) eh ancestral de #243 (c0de54c9): SIM
  #243 (c0de54c9) eh ancestral de #244 (af6a5c6e): SIM
  #244 (af6a5c6e) eh ancestral de #245 (2d6a8957): SIM
  #245 (2d6a8957) eh ancestral de #246 (c4975979): SIM
  origin/main = 3495c49d5d7c3244267e8292beee34475f70236b
  #239: main eh ancestral da cabeca: SIM; commits acima de main: 2
  #240: main eh ancestral da cabeca: SIM; commits acima de main: 7
  #241: main eh ancestral da cabeca: SIM; commits acima de main: 20
  #242: main eh ancestral da cabeca: SIM; commits acima de main: 24
  #243: main eh ancestral da cabeca: SIM; commits acima de main: 34
  #244: main eh ancestral da cabeca: SIM; commits acima de main: 50
  #245: main eh ancestral da cabeca: SIM; commits acima de main: 58
  #246: main eh ancestral da cabeca: SIM; commits acima de main: 74
```

## Conta de commits, esclarecida (passo 2 do operador)

A frase "74, quatro a mais que 61" não fechava porque misturava duas coisas: um
**documento** (`61-reconcilio-rc01-oito-elos.md`, na pasta de evidência do oitavo elo
`docs/09-operations/evidence/2026-09-29-rc01-home-first-fold/`) com um **número de
commit**. Reescrita, ela não é contradição — os dois números saem do mesmo tipo de
conta em momentos diferentes, e a diferença é medida, não alegada. O que precisa de
cuidado é outra coisa: `git rev-list --count` leva dois refs, e o valor diz respeito
ao da esquerda. Três colunas, cada uma com seu lado esquerdo declarado:

| grandeza | o que mede | comando |
|---|---|---|
| ancestralidade | um elo está contido no seguinte | `git merge-base --is-ancestor <ant> <novo>` |
| tamanho da fileira | commits acima de `main` na última cabeça | `git rev-list --count origin/main..c4975979` |
| incremento por elo | o que este elo acrescenta sobre o anterior | `git rev-list --count <cabeca_anterior>..<cabeca>` |
| commits acima da base | o que o PR entrega sobre a base informada no GitHub | `git rev-list --count <base>..<cabeca>` |
| diff funcional | conteúdo, não história | `git diff --shortstat <base>...<cabeca>` |

Saída crua de `107-conta-de-commits-da-fileira.py` (rc=0, veredito `CONFERIDA`) em
`107-conta-de-commits-da-fileira.log`, com `origin/main = 3495c49d`:

```
  origin/main = 3495c49d5d7c3244267e8292beee34475f70236b
  comando de tudo: git -C '/home/misael/Projects/Steam Zero/Canonical/2026-09-21' ...
  #239  codex/project-design-audit-2026-09-26
     cabeca=069501ab954c42118b5aaf91c450b58800e90219  base=main@3495c49d  state=OPEN mergeable=MERGEABLE
     acima_da_base              = 2   `git rev-list --count 3495c49d..069501ab`
     acima_de_main              = 2   `git rev-list --count origin/main..069501ab`
     incremento_do_elo_anterior = 2   `git rev-list --count 3495c49d..069501ab`
     diff exclusivo vs a base: 51 files changed, 16057 insertions(+), 433 deletions(-)
     elo anterior eh ancestral deste (merge-base --is-ancestor): SIM
     base == cabeca do elo anterior? SIM  (base==main => a coluna por base conta de novo o trecho ja somado no elo anterior)
  #240  codex/rc01-central-loading-2026-09-26
     cabeca=c959be139f95c673dc258b9d8b8011313d5c97f6  base=main@3495c49d  state=OPEN mergeable=MERGEABLE
     acima_da_base              = 7   `git rev-list --count 3495c49d..c959be13`
     acima_de_main              = 7   `git rev-list --count origin/main..c959be13`
     incremento_do_elo_anterior = 5   `git rev-list --count 069501ab..c959be13`
     diff exclusivo vs a base: 98 files changed, 21585 insertions(+), 574 deletions(-)
     elo anterior eh ancestral deste (merge-base --is-ancestor): SIM
     base == cabeca do elo anterior? NAO  (base==main => a coluna por base conta de novo o trecho ja somado no elo anterior)
  #241  codex/rc01-readiness-focus-2026-09-27
     cabeca=190ea683a941f8dc37036ef6402ffabaf7843799  base=main@3495c49d  state=OPEN mergeable=MERGEABLE
     acima_da_base              = 20   `git rev-list --count 3495c49d..190ea683`
     acima_de_main              = 20   `git rev-list --count origin/main..190ea683`
     incremento_do_elo_anterior = 13   `git rev-list --count c959be13..190ea683`
     diff exclusivo vs a base: 181 files changed, 29934 insertions(+), 836 deletions(-)
     elo anterior eh ancestral deste (merge-base --is-ancestor): SIM
     base == cabeca do elo anterior? NAO  (base==main => a coluna por base conta de novo o trecho ja somado no elo anterior)
  #242  codex/rc01-shell-esde-dialog-2026-09-27
     cabeca=5d95034b67fb50fd1218f267afbfe189d4444bd2  base=main@3495c49d  state=OPEN mergeable=MERGEABLE
     acima_da_base              = 24   `git rev-list --count 3495c49d..5d95034b`
     acima_de_main              = 24   `git rev-list --count origin/main..5d95034b`
     incremento_do_elo_anterior = 4   `git rev-list --count 190ea683..5d95034b`
     diff exclusivo vs a base: 231 files changed, 36958 insertions(+), 942 deletions(-)
     elo anterior eh ancestral deste (merge-base --is-ancestor): SIM
     base == cabeca do elo anterior? NAO  (base==main => a coluna por base conta de novo o trecho ja somado no elo anterior)
  #243  codex/rc01-readiness-semantics-2026-09-28
     cabeca=c0de54c9f10c480693ce495a0533acb524fe53ad  base=main@3495c49d  state=OPEN mergeable=MERGEABLE
     acima_da_base              = 34   `git rev-list --count 3495c49d..c0de54c9`
     acima_de_main              = 34   `git rev-list --count origin/main..c0de54c9`
     incremento_do_elo_anterior = 10   `git rev-list --count 5d95034b..c0de54c9`
     diff exclusivo vs a base: 316 files changed, 45137 insertions(+), 1138 deletions(-)
     elo anterior eh ancestral deste (merge-base --is-ancestor): SIM
     base == cabeca do elo anterior? NAO  (base==main => a coluna por base conta de novo o trecho ja somado no elo anterior)
  #244  codex/rc01-storage-units-2026-09-28
     cabeca=af6a5c6ed8523c04030d25b1d391e885a3b3b48e  base=main@3495c49d  state=OPEN mergeable=MERGEABLE
     acima_da_base              = 50   `git rev-list --count 3495c49d..af6a5c6e`
     acima_de_main              = 50   `git rev-list --count origin/main..af6a5c6e`
     incremento_do_elo_anterior = 16   `git rev-list --count c0de54c9..af6a5c6e`
     diff exclusivo vs a base: 362 files changed, 50323 insertions(+), 1194 deletions(-)
     elo anterior eh ancestral deste (merge-base --is-ancestor): SIM
     base == cabeca do elo anterior? NAO  (base==main => a coluna por base conta de novo o trecho ja somado no elo anterior)
  #245  codex/rc01-retrofe-shell-late-response-2026-09-29
     cabeca=2d6a895760ef55bf3cbdf742808e6798946da9d5  base=codex/rc01-storage-units-2026-09-28@af6a5c6e  state=OPEN mergeable=MERGEABLE
     acima_da_base              = 8   `git rev-list --count af6a5c6e..2d6a8957`
     acima_de_main              = 58   `git rev-list --count origin/main..2d6a8957`
     incremento_do_elo_anterior = 8   `git rev-list --count af6a5c6e..2d6a8957`
     diff exclusivo vs a base: 59 files changed, 5268 insertions(+), 27 deletions(-)
     elo anterior eh ancestral deste (merge-base --is-ancestor): SIM
     base == cabeca do elo anterior? SIM  (base==main => a coluna por base conta de novo o trecho ja somado no elo anterior)
  #246  codex/rc01-home-first-fold-2026-09-29
     cabeca=c4975979b93a03e661294b6854146e76f22fa8c3  base=codex/rc01-retrofe-shell-late-response-2026-09-29@2d6a8957  state=OPEN mergeable=MERGEABLE
     acima_da_base              = 16   `git rev-list --count 2d6a8957..c4975979`
     acima_de_main              = 74   `git rev-list --count origin/main..c4975979`
     incremento_do_elo_anterior = 16   `git rev-list --count 2d6a8957..c4975979`
     diff exclusivo vs a base: 56 files changed, 4210 insertions(+), 96 deletions(-)
     elo anterior eh ancestral deste (merge-base --is-ancestor): SIM
     base == cabeca do elo anterior? SIM  (base==main => a coluna por base conta de novo o trecho ja somado no elo anterior)
  soma de acima_da_base              = 161   (nao e tamanho de fileira: #239..#244 contam todos a partir de main, entao a coluna se aninha)
  soma de incremento_do_elo_anterior = 74   (esta e a conta da fileira)
  acima_de_main na ultima cabeca     = 74   `git rev-list --count origin/main..c4975979`
  ### derivacao do 70 que `61-reconcilio-rc01-oito-elos.md` media
     `git rev-list --count origin/main..22773047` = 70   <- o numero que o documento de 61 registrou, na cabeza daquela rodada
     `git rev-list --count 2d6a8957..22773047`   = 12   <- commits proprios de #246 naquela cabeca
     `git rev-list --count 22773047..c4975979` = 4   <- rodada de reconcilio posterior, so `docs/`: ['docs']
        c4975979 docs(status): SZ-UI-DESKTOP-AUDIT scopeDigest renovado na arvore congelada
        71c49beb docs(WORKLOG): adendo de consolidacao do oitavo elo, apenas acrescentado
        7a8af0c1 chore(status): registra 61 e 62 no cartao e reduz o nextAction a orientacao operacional
        92e1bf4c docs(rc01): reconcilio de oito elos em cinco camadas e plano de validacao fisica
  VEREDITO: CONFERIDA — tamanho da fileira = 74 = 2 + 5 + 13 + 4 + 10 + 16 + 8 + 16 (incrementos por elo, cada um contra a cabeca anterior), igual ao 74 medido direto contra origin/main. A coluna por base somaria 161 e nao e tamanho de nada.
```

A reconciliação, conferida por script antes deste texto existir — o `103` aborta se
a conta não fechar:

* **Tamanho da fileira = 74**, medido direto com
  `git rev-list --count origin/main..c4975979`. É o mesmo número que o corpo do
  PR #246 registra.
* **2 + 5 + 13 + 4 + 10 + 16 + 8 + 16 = 74** é a mesma grandeza elo a elo: as oito parcelas vêm
  cada uma de `git rev-list --count <cabeça do elo anterior>..<cabeça>`, e somadas
  confrontam o acumulado lido de uma vez — nove comandos, nove pares de refs. A
  igualdade entre essa soma e o `74`
  medido de uma vez é uma conferência real — só vale porque o `107` confere
  `merge-base --is-ancestor` par a par antes de somar (saída no log), e é isso que
  impede a conta de esconder um commit duplicado ou perdido entre cabeças.
* **`61` media 70, não 74, e estava certo na época**:
  `#246` estava em `22773047` com `12` commits sobre a base. A diferença
  de 4 é a rodada de reconcílio posterior àquela medição
  (`c4975979`, `71c49beb`, `7a8af0c1`, `92e1bf4c`), que toca apenas `docs/` — nenhum `src/`, nenhum `tests/` — e
  levou a cabeça de `#246` a 16 commits próprios e a última
  cabeça a c4975979. O documento de `61` fica como foi escrito; a releitura é este
  adendo.
* A linha `soma de acima_da_base = 161` que o `107` imprime **não é
  tamanho de fileira**, e o motivo está medido no log: `#239`…`#244` têm base em
  `main@3495c49d`, então para eles a coluna por base *já é* o acumulado —
  `7` contém os `2` do elo
  anterior, e somar a coluna é contar o mesmo trecho seis vezes. Só `#245` e `#246`
  têm base no ramo do elo anterior; nesses dois a coluna coincide com o incremento
  (o `107` imprime `base == cabeca do elo anterior? SIM/NAO` linha a linha para isso
  não ficar presumido).
* **O corpo publicado de `#246` conferido célula a célula — porque foi o rótulo que
  faltou, não o número.** O `103` lê `gh pr view 246 --json body`, recorta as oito
  linhas da tabela de fileira e confronta cada célula com as três colunas que o
  `107` mediu; aborta se alguma célula não tiver par. A coluna **"commits próprios"**
  é `git rev-list --count <cabeça do elo anterior>..<cabeça>`: **0**
  linhas divergem dela, contra 7 de `acima_de_main`
  (`#240`, `#241`, `#242`, `#243`, `#244`, `#245`, `#246`) e 5 de `acima_da_base` (`#240`, `#241`, `#242`, `#243`, `#244`) — a
  escolha é por exclusão, não por leitura do nome. Ela sempre esteve certa, inclusive
  em "somam **74**, que é exatamente `git rev-list --count origin/main..c4975979`".
  O que "74, quatro a mais que 61" escondia era o ref esquerdo da *minha* frase de
  sessão, não um número publicado errado. A coluna **"commits" não segue um único
  ref**: vale `acima_de_main` em sete linhas e `acima_da_base` em `#245` (publica
  `8`, quando `git rev-list --count origin/main..2d6a8957` dá
  `58`); por isso divergiria exatamente uma linha de cada candidata
  (`acima_de_main` em `#245`, `acima_da_base` em `#246` — em
  `#246` a célula é `74` e pela base seriam `16`). Nenhum número
  publicado foi reescrito: o corpo de `#246` é artefato da cabeça `c4975979`, e mexer
  nele é decisão de integração, não de prosa. O que explicita o lado esquerdo é esta
  tabela e a saída do `107`, que imprime o comando ao lado de cada valor.

## Integração preparada, decisão reservada (passos 6 e 7)

`106-preparar-integracao-da-cadeia.py` relê, nesta execução e por elo: PR, cabeça,
base, dependência, diff exclusivo e o **resultado nominal** dos oito checks
obrigatórios — não apenas "concluíram". Estado medido: 8/8 elos com
os oito checks em `SUCCESS`, 8/8 sem nenhum não-SUCCESS e nenhum
ausente, 8/8 com `mergeStateStatus=CLEAN` e
`reviewDecision` vazio. Os dois checks fora da lista obrigatória são
`Sourcery review` (`SKIPPED`) e `CodeRabbit` (não obrigatório).

Bloqueio concreto, que só aparece quando se lê a base em vez de presumir:
#245 sobre o ramo `codex/rc01-storage-units-2026-09-28`, #246 sobre o ramo `codex/rc01-retrofe-shell-late-response-2026-09-29` — um `gh pr merge` nesses elos entregaria no **ramo de base**, não em
`main`. A sequência correta, com o `gh pr edit N --base main` no ponto em que ele
passa a ser seguro, está no fim de `106-preparar-integracao-da-cadeia.log`.

MERGEABLE/CLEAN quer dizer "o GitHub consegue calcular o merge", não "está
aprovado". A decisão de merge é do operador, e nada aqui foi mesclado.


## Como este lote foi montado

Os scripts e logs citados acima não foram colados aqui a mão: `108-arquivar-artefatos.py`
copiou cada um para esta pasta conferindo SHA-256 de origem e destino, recusa
sobrescrever destino cujo conteúdo difere (e só rejoga com `-rejogar`, guardando a
versão anterior no tmp e imprimindo os dois hashes), e reconcilia a lista por contagem
no próprio log. O arquivador não se arquiva — enquanto ele copia, o log dele está sendo
escrito, e cópia de escrita em andamento não é evidência. O `104` também não passa por
ele: o reconcílio é escrito direto nesta pasta pelo script que o gera. E os logs da
passada final do `105` ficam fora do checkout, pelo motivo declarado abaixo.


## O que isto muda, e o que não muda

Um checkpoint com o comportamento verde na árvore congelada prova contrato
offscreen naquele ponto — o gate de catálogo regenerado depois prova consistência
de governança, não comportamento. Nada dos dois prova empacotamento, prova release
instalada ou prova o seletor nativo de diretório. Integração continua sendo decisão
do operador.

Um custo do ponto fixo, medido pelo `104` e não presumido: esta pasta de evidência
está dentro do escopo do cartão desta frente, e a visão `docs/status/COVERAGE.md`
imprime a contagem de arquivos desse escopo. Cada arquivo de evidência escrito aqui
move uma linha daquela visão — o `104` leu o atraso pela própria ferramenta e achou
uma única linha trocada, `787 → 788` —, então o `make status-check` fica vermelho
*enquanto* o lote escreve, e a renovação de digest com `render --write` tem de ser a
última escrita dentro do checkout. É por isso que os logs da passada final do `105`
ficam fora da árvore: arquivá-los ali envelheceria o digest que eles certificam.
