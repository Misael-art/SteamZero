# Evidência de correção do gate de benchmark — GAP-G22

**Data:** 2026-07-30

**Branch:** `codex/fix-benchmark-g22`

**Implementação avaliada:** `45d652f121ddb1114b595b7f16a695eb640e9291`

**Run:** https://github.com/Misael-art/SteamZero/actions/runs/30578113121

## Causa

O teste `test_10k_fixture_apply_and_rollback_benchmark` em
`tests/integration/test_library_organize.py` misturava duas responsabilidades:

1. correção funcional de plan/apply/rollback para 10.000 arquivos;
2. teto absoluto de tempo de parede `< 180` segundos.

O segundo contrato não é comparável em runner compartilhado de CI, como
comprovado por quatro execuções em ambientes diferentes:

| Ambiente | Tempo observado | Fonte |
|---|---|---|
| Local (workstation do desenvolvedor) | ~13,7 s | Execução isolada |
| CI anterior (runner compartilhado) | ~196,1 s | Run anterior do PR #21 |
| PR #21, SHA `7c3e9fd` (runner compartilhado) | **234,557203127 s** | [Job Python 3.14](https://github.com/Misael-art/SteamZero/actions/runs/30567717600/job/90956302373) |
| PR #22, SHA `e7cb2fc` (runner compartilhado) | 44,461 s / 59,185 s / 37,809 s (por versão) | [Run 30571131742](https://github.com/Misael-art/SteamZero/actions/runs/30571131742) |

A asserção `assert elapsed < 180.0` foi rejeitada corretamente pelo CI, mas
não indicava regressão funcional. Todos os 3.092+ testes de lógica passaram.

## Correção aplicada

1. Removido o teto `elapsed < 180.0` do teste.
2. Removido `time.monotonic()` e o `import time` (sem outros usos no arquivo).
3. Preservadas todas as asserções funcionais (exatas 8, verificadas por AST
   com `Counter` que detecta duplicatas):
   - `result.status == 'ok'`
   - `sum((1 for _ in fs.iter_files(root / 'nes'))) == 10000`
   - `not (root / 'incoming' / 'game-00000.nes').exists()`
   - `len(plan.actions) == 10000`
   - `rollback.status == 'rolled-back'`
   - `sum((1 for _ in fs.iter_files(root / 'incoming'))) == 10000`
   - `not (root / 'nes' / 'game-00000.nes').exists()`
   - `not paths.staging_for(result.operation_id).exists()`
4. Adicionado `--durations=20` à execução de pytest no CI.
5. Adicionado `--junitxml=build/test-results-${{ matrix.python-version }}.xml`.
6. Adicionado step de publicação do JUnit XML como artifact (`if: always()`).
7. Contrato de workflow CI validado por `_validate_ci_contract()` que cobre
   11 cenários negativos (always em step errado, valor em comentário/echo,
   path sem versão, warn, propriedade ausente, step ausente/duplicado,
   action sem SHA, SHA curto, retention incorreto).

## Artifacts JUnit observados

### Run 30571131742 (SHA `e7cb2fc`)

| Versão | ID do artifact | Tamanho (bytes) | Tempo do benchmark |
|--------|----------------|-----------------|-------------------|
| 3.11   | 8770963113     | 53818           | 44,461 s          |
| 3.12   | 8770991496     | 54053           | 59,185 s          |
| 3.14   | 8770924809     | 53908           | 37,809 s          |

### Run 30574550249 (SHA `ee31286`)

| Versão | ID do artifact | Tamanho (bytes) | Tempo do benchmark |
|--------|----------------|-----------------|-------------------|
| 3.11   | 8772290384     | 54189           | 53,352 s          |
| 3.12   | 8772293242     | 54449           | 62,197 s          |
| 3.14   | 8772257830     | 54066           | 38,578 s          |

### Run 30578113121 (SHA `45d652f`)

| Versão | ID do artifact | Tamanho (bytes) | Tempo do benchmark |
|--------|----------------|-----------------|-------------------|
| 3.11   | 8773651201     | 54021           | 53,652 s          |
| 3.12   | 8773638230     | 54020           | 50,763 s          |
| 3.14   | 8773610135     | 54078           | 36,944 s          |

O próximo run será verificado externamente pelo supervisor.

Os três artifacts foram publicados com `if: always()` e contêm o elemento
`testcase` de `test_10k_fixture_apply_and_rollback_benchmark` com atributo
`time` numérico.

## Checks do PR #22 (SHA `45d652f`)

| Check | Tipo | Resultado |
|-------|------|-----------|
| Python 3.11 | GitHub Actions | ✅ SUCCESS |
| Python 3.12 | GitHub Actions | ✅ SUCCESS |
| Python 3.14 | GitHub Actions | ✅ SUCCESS |
| Wheel + smoke + supply chain | GitHub Actions | ✅ SUCCESS |
| Smoke Ubuntu 24.04 | GitHub Actions | ✅ SUCCESS |
| Smoke Arch Linux | GitHub Actions | ✅ SUCCESS |
| Smoke Manjaro | GitHub Actions | ✅ SUCCESS |
| Gate visual QML | GitHub Actions | ✅ SUCCESS |
| CodeRabbit | Check externo | ✅ SUCCESS |

Total: 8 checks GitHub Actions + 1 check externo (CodeRabbit). Todos verdes.

## Limitações

- O tempo de execução não é critério de aprovação neste PR.
- Não há baseline de performance entre máquinas diferentes.
- Os tempos observados são deste runner específico e não formam baseline
  comparável entre máquinas.
- A medição publicada serve para consulta, não para gate automático.
- Uma regressão de performance só poderá voltar a bloquear por comparação
  controlada no mesmo ambiente ou runner dedicado.

## Status GAP-G22

**FECHADA em 2026-07-30.** O benchmark permanece como teste funcional
obrigatório; o tempo virou medição publicada.
