# Checkpoint 10 — suíte integral única na árvore congelada, gates restantes e a causa medida do único vermelho

Frente: UX-03 (prontidão semanticamente correta), quinto elo da pilha
#239 → #240 → #241 → #242. Esta pasta é a evidência canônica do lote.

## 1. Árvore sob teste (identidade)

Registrada **antes** da execução em `10-checkpoint-header.txt`,
`10-congelamento-lista.txt` e `10-congelamento-sha256.txt`:

| Campo | Valor medido |
| --- | --- |
| Branch | `codex/rc01-readiness-semantics-2026-09-28` |
| HEAD | `5d95034b67fb50fd1218f267afbfe189d4444bd2` (curto `5d95034b`) |
| Árvore git (`git write-tree`) | `4b23b239aa666de70ae72cbed59b8a61c0d0fa7b` |
| Arquivos em mudança no escopo congelado | 29 |
| Escopo do congelamento | `git ls-files -m --others --exclude-standard`, excluindo a própria pasta de evidência (escrita durante a execução) |

Os arquivos `06-congelamento-*.txt` e `06-suíte-integral.log` que existiam aqui
foram **removidos deste registro**: congelaram uma árvore anterior à rodada 4 e a
suíte neles registrada foi interrompida aos 26%, sem veredito. Nada neles vale
como resultado, e mantê-los na pasta deixaria duas "integrais" convivendo.

## 2. Comando e veredito

Comando único, exatamente como em `AGENTS.md` §6:

```
.venv/bin/python tools/run_tests_isolated.py tests -q
```

Saída integral em `10-suite-integral.log`. Veredito impresso pelo próprio pytest:

```
1 failed, 6483 passed, 47 skipped in 2071.39s (0:34:31)
```

**Correção sobre o log:** a última linha (`CODIGO_DE_SAIDA 0`) **não** é o código
da suíte. Meu envoltório chamou `echo "FIM $(date -Is)"` entre o pytest e o `echo`
de `$?`, então a variável mediu o `echo` anterior. O veredito real é o da linha do
pytest: uma falha, portanto saída não-zero. A anotação está prependida ao próprio
log para que quem abrir o arquivo não precise confiar nesta página.

## 3. Guard de estado (a árvore não se moveu durante a execução)

Recomputei o sha256 dos 29 arquivos depois da suíte e comparei com o congelado
antes: `diff` vazio. Nenhum byte foi movido durante os 34min31s — nenhuma
redução de tolerância, nenhum teste pulado por edição em voo.

O próprio executável isolado imprimiu o guard de estado real, antes e depois
idênticos:

```
real-state before: exists=True files=12816 directories=2068 bytes=1372712391 max_mtime_ns=1790607044829769561 source=HOME-default
real-state after:  exists=True files=12816 directories=2068 bytes=1372712391 max_mtime_ns=1790607044829769561 source=HOME-default
```

Ou seja: a suíte não tocou o acervo, os saves nem o estado do host.

## 4. Gates restantes, na mesma árvore congelada

`10-gates.log`, todos executados após a suíte sem editar nada:

| Gate | Resultado |
| --- | --- |
| `.venv/bin/ruff check src tools tests` | All checks passed! (código 0) |
| `.venv/bin/ruff format --check src tools tests` | 676 files already formatted (código 0) |
| `.venv/bin/mypy src` | Success: no issues found in 298 source files (código 0) |
| `make independence boundaries` | independência de runtime: OK; lint de fronteiras: OK (0 violações) (código 0) |
| `make status-check` | **FALHOU** — ver §5 |

## 5. Causa do único vermelho — medida, não presumida

`10-catalogo-status-check.log` traz a saída do gate. São 36 linhas de erro, em
três classes:

1. **33 itens** com `evidencia obsoleta; scopeDigest esperado X, atual Y`.
2. `arquivo alterado sem item de status responsavel: docs/06-api/JSON-SCHEMAS.md`.
3. `docs/ACTIVE-WORK.md` e `docs/status/COVERAGE.md` desatualizados (as visões
   geradas ainda não foram regrava para os cartões desta frente).

### 5.1 Por que os 33 digests envelheceram — atribuição por arquivo

O `scopeDigest` de um item é calculado sobre o **conteúdo atual** dos arquivos do
escopo dele (`tools/project_status.py:105`, `scope_digest`). Esta frente altera
quatro arquivos que estão no escopo de muitos itens — notoriamente
`src/steamzero/adapters/emulation.py` — e ainda criou arquivos novos dentro de
diretórios escopados. Logo, o digest de cada item que os lista envelhece no
momento em que o conteúdo muda, exatamente como o gate pretende.

Medi a interseção entre o escopo de cada item reprovado e os 29 arquivos desta
frente (`10-atribuicao-digests.log`):

- **33 de 33** reprovados têm ao menos um arquivo desta frente no escopo.
- **0 de 33** estão reprovando por obsolescência anterior a esta frente.

Distribuição dos arquivos desta frente que aparecem nas interseções (contagem de
itens atingidos):

```
19 src/steamzero/adapters/emulation.py
 7 src/steamzero/ui/qml/Main.qml
 7 src/steamzero/adapters/desktop_dashboard.py
 5 tests/integration/test_qml_handheld_offscreen.py
 3 tests/unit/test_desktop_dashboard.py
 3 src/steamzero/ui/qml/EditorialLibrary.qml
 3 src/steamzero/domain/platform_composer.py
 2 tests/unit/test_emulation_controller.py
 2 src/steamzero/ui/qml/Emulation.qml
 2 src/steamzero/schemas/emulation-workspace-v1.schema.json
 2 src/steamzero/domain/platforms.py
 1 tests/unit/test_gamemode_probe.py
 1 src/steamzero/ui/qml/SteamGameplay.qml
 1 src/steamzero/domain/emulation_workspace.py
```

Consequência: renovar os 33 digests **é** atribuição desta frente, e não uma
limpeza alheia. A alternativa — reprová-los como "estrago do vizinho" — estava
medida antes de ser descartada; o número 0 na terceira linha do diagnóstico é a
prova de que nenhum item reprovado é inocente.

### 5.2 O caso de `docs/06-api/JSON-SCHEMAS.md`

Nenhum item do catálogo declarava esse arquivo em `scopePaths` (medido: `grep -l`
por todo `docs/status/items/` não retorna a path). A frente reescreveu a
documentação do contrato de prontidão v2 ali, então o gate de propriedade fez o
que dele se espera: recusou mudança normativa sem dono. Correção: o arquivo entra
em `scopePaths` de `SZ-UI-DESKTOP-AUDIT`, o item normativo desta frente, junto com
os arquivos novos do contrato (`src/steamzero/domain/readiness.py`,
`src/steamzero/ui/qml/readiness.js`, `tests/qml/readiness_fixture.js`,
`tests/qml/check_readiness_surface.qml`, `tests/unit/test_readiness_contract.py`,
`tests/unit/test_readiness_producers.py`) e a pasta de evidência deste lote — o
mesmo padrão das fatias RC-01 anteriores, que escopam a própria evidência.

### 5.3 O que a suíte **não** provou contra esta frente

Os outros 6483 testes passaram, incluindo os gates QML, os contratos de
produtores e a jornada de prontidão. A falha é de governança de catálogo, não de
comportamento do contrato. Ela estava prevista na sequência da frente: o passo
documental (digests + visões + cartão) vem **depois** da integral, porque o
digest se renova sobre a árvore já final.

## 6. Revalidação proporcional, e o que ela não é

Depois da passada documental, a árvore **deixa de ser** a árvore congelada deste
checkpoint. Declaro portanto, sem rodeios:

- A suíte integral de §2 correu na árvore de 29 arquivos identificada em §1.
- As alterações posteriores a esse congelamento são **somente documentais**: a
  pasta de evidência, `docs/status/items/*.json` (digests renovados a partir do
  valor impresso pelo próprio `tools/project_status.py digest --item ...`),
  `docs/STATUS.md`, `docs/ACTIVE-WORK.md`, `docs/status/COVERAGE.md` (regravados
  por `render --write`) e o acréscimo de uma sessão ao `docs/WORKLOG.md`
  (append-only).
- A revalidação proporcional a uma mudança documental é o gate que falhou:
  `make status-check` e `tests/unit/test_project_status.py`, re-executados após a
  passada. Não re-executo a integral de 34 minutos localmente por dois motivos
  mensuráveis: (a) o único arquivo alterado desde o congelamento está fora de
  todo código de produção e de teste do contrato; (b) a integral volta a correr
  por inteiro no CI do SHA final enviado, e é aquele veredito — não este — que
  declaro como resultado integral do lote.
- Nenhum gate de código foi re-executado "por garantia": ruff, mypy e
  independência já estavam verdes na árvore congelada (§4) e a passada documental
  não toca `src/`, `tests/` nem `tools/`.
