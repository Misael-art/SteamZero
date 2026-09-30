# 25 — Checkpoint integral e gates do sétimo elo (árvore congelada, 2026-09-29)

Execução única de cada suíte, na árvore congelada, sem nada iniciar em paralelo e sem
tocar no produto durante o voo. Comando, resultado, contagem, identidade e limites do
guarda registrados como medidos. Wrapper: `24-gates-integrais.sh` (cópia deste diretório;
o script executável ficou **fora** do checkout em `~/steamzero-retrofe-tmp/` porque a
pasta de evidência está dentro do `scopePaths` dos cartões — escrever log aqui dentro
invalidaria o `scopeDigest` no meio da execução, ponto fixo já medido em lote anterior).

## 1. Os sete passos (`24-comandos-e-saidas.log`, `.rc`)

| # | comando | resultado lido | rc |
|---|---|---|---|
| 1 | `.venv/bin/ruff format --check src tests tools` | `679 files already formatted` | 0 |
| 2 | `.venv/bin/ruff check src tests tools` | `All checks passed!` | 0 |
| 3 | `.venv/bin/mypy src` | `Success: no issues found in 298 source files` | 0 |
| 4 | `make independence boundaries` | verde (`tools/check_independence.py`, sem violações) | 0 |
| 5 | `make status-check` | `STATUS-CHECK: OK` | 0 |
| 6 | `.venv/bin/python tools/run_tests_isolated.py tests -q` | **6507 passed, 47 skipped** em 2371,78 s (39:31), 11:26:12 → 12:05:48 | 0 |
| 7 | `.venv/bin/python tools/run_tests_isolated.py -m visual --tb=short -q` | **362 passed, 6192 deselected** em 1484,90 s (24:44), 12:05:48 → 12:30:37 | 0 |

Os textos das linhas 1 a 6 foram copiados do log (`24-comandos-e-saidas.log`, passos
registrados nas linhas 30, 77, 124, 171, 223 e 387); linha 7 preenchida com o texto exato
ao finalizar — nenhuma delas é alegada de memória.

## 2. Reconciliação de contagem (nada aqui é soma presumida)

Lote anterior (`2026-09-28-rc01-storage-units/27-comandos-e-saidas.log:174`):
`2 failed, 6496 passed, 47 skipped` — 6545 coletados.

Este lote acrescenta exatamente **9** funções de teste (a tupla `FUNCTIONS` de 9 em
`tests/integration/test_ui_shell_retrofe_import_late_response.py`). Esperado: 6554
coletados. Lido: 6507 + 47 = **6554**. Bate.

Os dois vermelhos do lote anterior eram `tests/unit/test_project_status.py::
test_committed_catalog_and_generated_views_are_consistent` e `::
test_status_table_publishes_operation_and_distribution_per_item` — causa registrada à
época: `|` dentro de `nextAction` (o renderer injeta o campo verbatim numa tabela de 9
colunas) e 31 `scopeDigest` obsoletos. Ambos são governança de documento, não produção.
Aqui eles passam porque este lote escreve `nextAction` sem pipe (varredura prévia dos 92
cartões) e renova os digests na árvore final antes do passo 5, que devolve `OK`.

**Visual:** lote anterior (`2026-09-28-rc01-storage-units`) fechou `360 passed` em
1400,29 s. Este lote acrescenta exatamente **2** funções marcadas `@pytest.mark.visual`
(`test_ui_shell_retrofe_import_late_response.py:881` e `:1001`, conferidas por `grep`
estático antes do voo — o arquivo tem 10 `def test_`, das quais 2 carregam o marcador).
Esperado: **362**. Lido: **362 passed** (`6192 deselected` é o resto da suíte sem o marcador). Bate.

## 3. Ritmo medido e contenção de ambiente (causa demonstrada, não hipótese)

Leituras intermediárias do mesmo arquivo, com relógio: 27 % às 11:55:58, 40 % às
12:02:54, 82 % às 12:05:10, fim às 12:05:48. Entre 40 % e 82 % há 3 024 testes em 97 s
(~31 testes/s) enquanto a banda 27–40 % correu a ~26 s por 1 % — a diferença é composição
do trecho (bloco de unitários puros versus gates de integração que sobem QML/ponte), não
uma releitura do mesmo ponto. O `load average` acompanhado no mesmo instante: 9,35 na
banda lenta e 3,63 na banda rápida, com um concorrente visível e não tocado — `bfs`
varrendo `/` (pid 2099519, ~18 % CPU, 7 min de voo às 12:00), de outra frente, competindo
só por relógio. Nada neste lote foi iniciado em paralelo.

**Segunda divergência de leitura, agora com causa medida (passo 7).** O log não cresceu
entre **12:18:10** (27 147 bytes) e **12:25:20** — 7 min sem um byte — e a leitura parece
uma paralisação. Não é: `qml6` pid 2241652, pai 2169163 (o processo do isolador), estava
vivo com 26 s de voo a ~51 % CPU executando
`tools/ui_control_probe.qml -- --steamzero-scenario build/ui-scenarios/ready-small-library.json`.
A causa é **bufferização**, não travamento: o wrapper faz
`timeout 3600 bash -c "$cmd" >>"$LOG" 2>&1` (`24-gates-integrais.sh:45`), então o stdout do
Python aponta para um arquivo e não para um tty — a stream é blocada em blocos de 8 KiB e
os pontos só aparecem quando o bloco fecha. As leituras de progresso do passo 7 são,
portanto, **atrasadas por construção**; o rollup final e o `rc` gravados pelo wrapper
depois do fechamento da stream são a versão autoritativa. Nenhuma hipótese de conteúdo
injetado ou de penduricalho é alegada aqui.

**Divergência de leitura registrada:** as três leituras acima foram tiradas com
`tail -c` sobre um arquivo em crescimento; a de 40 % foi lida às 12:02:54 e a de 82 % às
12:05:10, e o par `tail -c 200/300` não tem marca de tempo por linha. O arquivo completo
com `rc=0` e o rollup único de 6554 é a versão autoritativa; as leituras parciais ficam
aqui como foram vistas, sem serem promovidas a medida do ritmo da suíte.

## 4. Identidade da árvore e limites do guarda

- `identidade()` impressa **antes e depois** de cada um dos 7 passos — 14 leituras no log.
  Todas as leituras deste lote: `branch=codex/rc01-retrofe-shell-late-response-2026-09-29`,
  `HEAD=af6a5c6ed8523c04030d25b1d391e885a3b3b48e`,
  `sha256 src+tests+tools=f185438a112bc0b8`,
  produto `bddd117ac33fcbcf…`, harness `bc9d76d646685e20…`, gate `0cb7744eff344587…`.
  Conferência programática: `grep -c '^--- identidade'` = **14**, e as seis linhas de identidade (`branch`, `HEAD`, `src+tests+tools`, produto, harness, gate) aparecem **14 vezes cada, sem variante alguma**; as 13 linhas de `git status --short` também nunca mudaram (`grep -c '^ M \|^?? '` = 182 = 14 × 13). A árvore estava congelada de fato, não por intenção.
- Guarda de estado real do isolador (`tools/run_tests_isolated.py`), passo 6:
  `real-state before: exists=True files=12816 directories=2068 bytes=1372712391
  max_mtime_ns=1790607044829769561 source=HOME-default` e `after` **idêntico** campo a
  campo. Exit code 0, não 86 — nenhum arquivo do `$HOME` do operador foi tocado.
- Coleta: 47 `SKIPPED`, todos com motivo declarado no log (capacidades não declaradas,
  `reference/` não versionado de um **outro** checkout em `/mnt/sdcard/...`, que aparece
  porque o isolador roda com raiz de coleta ampla; nenhum skip é deste lote).

## 5. Estado do produto após o veredito

Depois do passo 7 a árvore recebeu **somente documento**: evidências deste lote, cartões
do catálogo, as três visões geradas e a redução de `nextAction` (item 9 do operador).
Nenhum byte de `src/`, `tests/` ou `tools/` mudou depois das duas suítes. Se mudar, este
lote exige revalidação proporcional e declara qual porta voltou a abrir.
