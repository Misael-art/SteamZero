# 12 — Isolamento do arquivo compartilhado (`Main.qml`) e o pino que faltava

## Por que esta rodada existe depois do checkpoint 10

O checkpoint 10 congelou a árvore, rodou a suíte integral uma vez e mediu os gates.
Deple dele, ao preparar os commits, uma regra de processo foi violada pelo formato da
pilha: `src/steamzero/ui/qml/Main.qml` — arquivo com **claim exclusivo** de
`WS-2026-09-LIBRARY-GOVERNED-MANAGEMENT` — entrou misturado no commit de páginas QML.
AGENTS.md §2 pede que a mudança em arquivo compartilhado vá **em commit próprio, por
último**. O precedente existe na própria casa: `7cb4e3b7` (4ª fatia) é um commit cujo
único arquivo de produção é `Main.qml`.

Nada no comportamento entregue estava errado; a entrega estava mal-atribuída. Quem
precisa reverter ou cherry-picar a intervenção no shell sem arrastar as outras três
páginas não tinha como.

## O que foi feito, na ordem

A pilha era local (`git ls-remote --heads origin codex/rc01-readiness-semantics-2026-09-28`
vazio; nenhum PR aberto). Reconstrução por cherry-pick, sem `rebase -i`, sem `reset`,
sem `stash`, com ref de backup:

| passo | comando |
|---|---|
| backup | `git branch tmp/rc01-ux03-oldstack ed0b3601` |
| base | `git checkout --detach 9891fb40` |
| commit A sem o arquivo compartilhado | `git cherry-pick -n d3b7e7f8` → `git restore --source=HEAD --staged --worktree -- src/steamzero/ui/qml/Main.qml` → `git commit -C d3b7e7f8` |
| vermelho | `pytest tests/unit/test_readiness_producers.py::test_fallback_do_shell_nao_fabrica_percentual_sem_medicao -q` **no estado A** (Main.qml ainda na base) |
| commit B | `git checkout d3b7e7f8 -- src/steamzero/ui/qml/Main.qml` → `git add tests/unit/test_readiness_producers.py` → `git commit -F …` |
| docs | `git cherry-pick ed0b3601` |
| reanexar | `git branch -f codex/rc01-readiness-semantics-2026-09-28 HEAD` |

A pilha passa de quatro para cinco commits:

```
905b0af0 feat(readiness): contrato v2 separa o que a prontidao afirma do que ela mede   (2 arquivos)
9891fb40 feat(emulation): os nove produtores publicam o contrato em vez de um percentual (14)
4c4d2b11 fix(ui): as paginas leem o contrato, e a dobra de prontidao chega completa      (9)
a3304baa fix(ui): o fallback do shell declara nao inspecao, nao um percentual medido      (2)
c65f6ebc docs(RC-01): fecha a 5a fatia (UX-03) com a integral congelada e a causa do catalogo (66)
```

## Prova de que a reestruturação não mudou conteúdo algum

Diferença entre a ponta antiga e a nova, inteira:

```
 tests/unit/test_readiness_producers.py | 18 ++++++++++++++++++
 1 file changed, 18 insertions(+)
```

`ed0b3601` → `c65f6ebc`, com `git diff --stat` entre as duas pontas mostrando **só** o
arquivo de teste. Todo conteúdo já congelado no checkpoint 10 — inclusive o hunk de
`Main.qml` — está byte a byte na mesma forma. É essa identidade, e não uma nova
execução, que autoriza não repetir o gate:

- **Nenhuma suíte integral foi re-rodada nesta rodada.** A integral do checkpoint 10 já
  exercitava exatamente este conteúdo de árvore; re-rodá-la seria repetição sem ganho de
  informação (instrução do operador, item 8). O ganho real desta rodada é o pino novo,
  e ele foi medido.
- A integral volta a valer como prova no SHA publicado, onde o CI a executa do zero.

## O pino novo (vermelho → verde medidos)

Antes desta rodada, **nenhum teste exercitava o literal do fallback do shell**:
`grep -rn "Ambiente Steam indispon" tests/` devolvia zero arquivos. O hunk de `Main.qml`
foi escrito durante o lote sem pino próprio — lacuna reconhecida aqui, não contornada.

O pino é semântico, não de implementação: `test_fallback_do_shell_nao_fabrica_percentual_sem_medicao`
exige que não exista `'"percent"'` em `Main.qml` **em lugar nenhum** e que o bloco
`fallbackSteamGameplay` publique a prontidão via `Readiness.notInspected(`. Uma
regravação do `"percent": 0` cai; qualquer percentual futuro fabricado no shell cai também.

Vermelho, com o commit A aplicado e o hunk de `Main.qml` ainda ausente:

```
shell = Path("src/steamzero/ui/qml/Main.qml").read_text(encoding="utf-8")
>       assert '"percent"' not in shell
E         '"percent"' is contained here:
E           diness": {"percent": 0, "title": "Ambiente Steam indisponível", "detail": ...
1 failed in 0.61s
```

Verde, com o hunk isolado (2026-09-28T19:37:48Z):

```
 src/steamzero/ui/qml/Main.qml | 4 +++-
 1 file changed, 3 insertions(+), 1 deletion(-)
1 passed in 0.43s
```

O que o pino **não** é: o comportamento visível já estava coberto. O leitor converte
payload sem contrato em `unverified` e esconde o número — pino de payload legado em
`tests/qml/check_readiness_surface.qml`, já verde no checkpoint 10. Sem o hunk, o usuário
não via um "0%" mentiroso. O hunk tira a mentira da fonte (um produtor que afirma medir
sem denominador); o pino impede que ela volte.

## Gates focados desta rodada

`.venv/bin/ruff check` + `ruff format --check` no arquivo alterado: `All checks passed!`,
`1 file already formatted`. `pytest tests/unit/test_readiness_producers.py
tests/unit/test_readiness_contract.py -q`: **51 passed in 0.94s** (50 antes + o pino novo).
`mypy src` não foi re-rodado no passo intermediário: nenhum arquivo Python de produção mudou.

Na ponta reconstruída, os gates de §6 que dependem de conteúdo foram re-rodados e estão
em `12-comandos-e-saidas.log` (seção "GATES NA PONTA"): ruff check, ruff format --check
(676 arquivos), mypy (298 arquivos, sem issues), `make independence boundaries` e
`tools/project_status.py check` — todos verdes. A suíte integral continua sendo a única
do lote, registrada no log `10`, pelo motivo de identidade de conteúdo acima.

## Limite declarado

`tmp/rc01-ux03-oldstack` fica até o push; depois é removido (`git branch -D`), porque a
prova de identidade está neste arquivo e no `git diff` registrado acima.
