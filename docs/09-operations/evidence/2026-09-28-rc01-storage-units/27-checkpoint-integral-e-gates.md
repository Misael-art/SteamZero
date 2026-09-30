# 27 — checkpoint integral: uma suíte na árvore congelada, dois vermelhos com causa, e o `EEEEEE` desfeito por medição

Atende aos itens 1, 4 e 8 da instrução do operador: *uma* suíte integral na árvore
congelada sem a alterar durante a execução, preservando resultado, comando, identidade
e estado; vermelho exige causa; testes focados não substituem o veredito; um passo por
vez. Executado de 2026-09-28T23:41:47 a 2026-09-29T00:43:05 (horário do host) no
checkout canônico com o venv do projeto. Invólucro: `27-gates-integrais.sh`
(`sha256` `75738d334b4d1c9e`), saída crua dos sete passos em
`27-comandos-e-saidas.log` (405 linhas, `sha256` `f93bc5c390cb3b3b`), código de saída
por passo em `27-comandos-e-saidas.log.rc`, marcador de término em
`.concluido`.

Caminhos pessoais foram redigidos nas cópias desta pasta (`<checkout-canônico>`,
`<scratch-do-lote>`), por AGENTS.md §"não redistribuir caminhos pessoais em logs
públicos". A redação é só de prefixo de caminho; nenhum byte de resultado mudou.

## 1. Identidade da árvore, impressa antes e depois de CADA passo

14 leituras (7 passos × 2). Todas as quatro grandezas de cada leitura são **idênticas**
nas 14 amostras (contagem de valores distintos = 1 por linha):

```
branch=codex/rc01-storage-units-2026-09-28
HEAD=f9ec2815390e1dfd5b0076f80ee6b6a72e8b364a
git status --short:  M docs/06-api/JSON-SCHEMAS.md
                     M docs/status/items/ui-desktop-audit.json
                     ?? docs/status/workstreams/rc01-storage-units-2026-09-28.json
sha256 src+tests+tools=fff1806fe884d74a   (git ls-files -s src tests tools | sha256sum)
sha256 harness=919ab43351e2c080           (tests/qml/check_storage_units.qml)
sha256 matriz=6520c53faba868c7            (tests/integration/test_storage_units_locale_matrix.py)
```

A diferença tracked era só documentação — nada em `src/`, `tests/` ou `tools/` fora do
que o HEAD `f9ec2815` já carregava (verificado por `git status --short -- src tests
tools` vazio, registrado em `27-congelamento-header.txt`). Guarda de estado nos
arquivos `27-congelamento-{header,lista,sha256}.txt`.

O isolador registrou o estado do `HOME` em cada suíte: `files=12816`,
`directories=2068`, `bytes=1372712391`, `max_mtime_ns=1790607044829769561` — **idênticos
antes e depois** nas duas suítes. A execução não escreveu fora do tmp delimitado, não
tocou acervo, ROM, BIOS ou save.

## 2. Os sete passos

| # | comando | resultado | rc |
|---|---|---|---|
| 1 | `.venv/bin/python tools/run_tests_isolated.py tests -q` | **2 failed, 6496 passed, 47 skipped** em 2262,61 s (37:42) | 1 |
| 2 | `.venv/bin/python tools/run_tests_isolated.py -m visual --tb=short -q` | **360 passed**, 6185 deselected em 1400,29 s (23:20) | 0 |
| 3 | `.venv/bin/ruff check src tools tests` | **E501** (101 > 100) em `tests/integration/test_storage_units_locale_matrix.py:131` | 1 |
| 4 | `.venv/bin/ruff format --check src tools tests` | **1 file would be reformatted** (o mesmo arquivo), 677 já formatados | 1 |
| 5 | `.venv/bin/mypy src` | `Success: no issues found in 298 source files` | 0 |
| 6 | `make independence boundaries` | `independência de runtime: OK` + `lint de fronteiras: OK (0 violações)` | 0 |
| 7 | `.venv/bin/python tools/project_status.py check` | **31 itens com `scopeDigest` obsoleto** + as 3 visões desatualizadas | 2 |

O passo 2 é o comando do CI (`-m visual`). 360 = 356 do lote anterior **+3** da matriz de
locales **+1** do harness de armazenamento agora registrado na lista parametrizada —
as duas somas batem com os arquivos deste lote, e é a primeira vez que o gate de
unidades roda no caminho que o CI executa, com o locale da imagem (`C.UTF-8`).

## 3. Os dois vermelhos têm causa, e nenhuma é da produção

**(a) `test_status_table_publishes_operation_and_distribution_per_item` — 10 células
contra 9 colunas, em `SZ-UI-DESKTOP-AUDIT`.** Causa lida no renderer
(`tools/project_status.py:427-438`): a linha da tabela publica `nextAction` **verbatim**
dentro de uma tabela Markdown de nove colunas. O texto que esta frente escreveu no
cartão continha `integer|null` — o pipe quebrou a célula. Não é o teste sendo rígido
demais: é o teste fazendo o trabalho dele.

Correção no **cartão** (reescrito para "inteiro ou nulo, com minimum 0"), não no
renderer: `tools/project_status.py` não está em nenhum dos caminhos desta frente, e
mudar a renderização para escapar pipe seria alterar uma superfície compartilhada por
todas as 31 capacidades sem exigência correspondente. Fica registrado aqui, não editado.
Medição de contorno: antes da correção, **nenhum** outro cartão tinha pipe em
`nextAction`/`title`, e `docs/STATUS.md` não tinha `\|` escapado em lugar nenhum — ou
seja, este lote foi o primeiro a exercer o caso, e o pino existia antes dele.

**(b) `test_committed_catalog_and_generated_views_are_consistent` — os mesmos 31 itens
do passo 7.** É obsolescência de digest, não divergência de catálogo: cada item lista em
`scopePaths` arquivos que este lote tocou. Atribuição medida por arquivo, não alegada
(`27-atribuicao-digests.py`, `sha256` `4df88d49b7a0dfc6`; saída
`27-atribuicao-digests.log`, `sha256` `5aeb1dfd8b89ec6e`):

```
arquivos desta frente: 16
itens acusados: 31
com ao menos um arquivo desta frente no escopo: 31
SEM nenhum arquivo desta frente: 0
```

Mesma forma do lote anterior (33 de 33). Renovação é o último passo, sobre a árvore
final, a partir do valor `atual` impresso pela própria ferramenta — a pasta de evidência
deste lote está em `scopePaths` de `SZ-UI-DESKTOP-AUDIT`, então renovar antes de escrever
as evidências renovaria um digest que a escrita seguinte envelheceria.

**Tropeço metodológico registrado.** A primeira versão do script de atribuição leu o
**stdout** de `project_status.py check` e devolveu "0 itens acusados" — um falso verde de
atribuição, que diria "a frente não envelheceu item nenhum". A acusação vai para
**stderr** (medido: stdout com redirect = 0 linhas, stderr = 35 linhas). O script
copiado nesta pasta já lê stderr e carrega o comentário com a medição.

## 4. O `EEEEEE` da execução anterior: desfeito por medição, não por suposição

`23-suite-integral.log` (execução 2, interrompida) terminou aos 26 % com `EEEEEE` no
último byte, sem `short test summary`, sem rollup e sem traceback. O passo 1 deste
checkpoint passou do mesmo offset (a linha de 26 % e os 51 pontos seguintes, que na
ordem de coleta são `tests/integration/test_theme_catalog_routes.py`,
`test_transaction.py` e `test_ui_action_inventory.py`) **sem nenhum `E`**, e fechou com
`2 failed, 6496 passed, 47 skipped` — zero erros. Conclusão: os seis `E` eram artefato
do processo morto no meio de um teardown, não um aglomerado de erros reais. A frase
"provavelmente foi o kill" vira, agora, medição.

Nota de ambiente, declarada sem suavização: entre ~26 % e ~40 % do passo 1 apareceu um `pytest` de
**outra** sessão (`/usr/bin/python /usr/sbin/pytest -q tests/test_accessibility_gate.py
tests/test_linux_hub_ui.py tests/test_native_navigation.py`, pid 350170, ~2m40s, 95 %
CPU). Não é deste lote, não foi tocado (item 9 do operador) e só compete por relógio: a
árvore, o isolamento e os resultados não mudam por isso — as 14 leituras de identidade e
o `real-state` idêntico do isolador são a prova. O passo 1 levou 37:42 contra 32:46 do
lote anterior; a diferença de wall-clock é coerente com essa concorrência.

## 5. O que a árvore recebeu DEPOIS da execução (item 4, declarado)

A árvore testada **não está congelada agora**: depois do veredito ela recebeu exatamente
duas correções, e nenhuma delas é funcional.

| arquivo | antes | depois | o que mudou |
|---|---|---|---|
| `docs/status/items/ui-desktop-audit.json` | `db9a225060bfdc3a` | `a8a1bacf23c40ceb` | causa (a): `integer\|null` → "inteiro ou nulo" |
| `tests/integration/test_storage_units_locale_matrix.py` | `6520c53faba868c7` | `7116e3ae5c858b92` | causas 3 e 4: `ruff format` + quebra da linha 131 (assert de `returncode`, mensagem encapsada) |

O `diff` real da formatação tem duas trocas, ambas de layout de código: a
compreensão de dicionário volta a uma linha e o `assert` passa a três. Guarda pós-leitura
em `27-pos-execucao-sha256.txt` (os três arquivos do congelamento re-verificados:
2 SUCESSO, 1 FALHOU — o cartão, que é a correção (a) acima; o harness `919ab433…` está
intocado).

A correção da matriz entrou como commit próprio, `1eae804c`; a do cartão entra no
commit documental desta mesma passada, com as evidências 23 a 27.

Revalidação proporcional, com o comando:
`.venv/bin/python tools/run_tests_isolated.py tests/integration/test_storage_units_locale_matrix.py
tests/unit/test_project_status.py tests/unit/test_emulation_storage_cards.py -q`
→ **1 failed, 24 passed** em 43,00 s. A única falha restante é o digest obsoleto (b),
que se fecha pela renovação final; o vermelho da tabela (a) sumiu, e a matriz de locales
passou nos dois fusos depois da formatação. `ruff check` (`All checks passed!`) e
`ruff format --check` (678 arquivos já formatados) foram re-corridos e estão verdes.

**Lição de processo, registrada:** os gates de lint de um arquivo **novo** rodam antes
do checkpoint integral, não depois. O erro de estilo existia desde a escrita do arquivo
e só foi exposto 61 minutos depois, quando a árvore já estava sob teste.

## 6. Arquivos desta evidência

| arquivo | conteúdo |
|---|---|
| `27-gates-integrais.sh` | invólucro dos sete passos, com a identidade impressa antes e depois de cada um |
| `27-comandos-e-saidas.log` | saída crua dos sete passos, com os 14 blocos de identidade e os `real-state` do isolador |
| `27-comandos-e-saidas.log.rc` | código de saída por passo (`1,0,1,1,0,0,2`) |
| `27-comandos-e-saidas.log.concluido` | marcador de término (arquivo vazio) |
| `27-congelamento-header.txt` / `-lista.txt` / `-sha256.txt` | identidade da árvore sob teste e o método da guarda, incluindo o pathspec que não sobreviveu ao `rtk` |
| `27-atribuicao-digests.py` / `.log` | atribuição por arquivo dos 31 itens obsoletos, lendo stderr |
| `27-pos-execucao-sha256.txt` | estado dos arquivos depois da execução, com as duas correções nomeadas |
