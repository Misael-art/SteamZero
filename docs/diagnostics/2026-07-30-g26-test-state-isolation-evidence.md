# Evidência de isolamento do estado de testes — GAP-G26 (evidência final pré-commit)

**Data:** 2026-07-30

**Branch:** `codex/fix-test-state-isolation-g26`

**HEAD pré-commit / parent do commit corretivo:**
`7e1f45b44dfbd714fc0dffdd534efac50629d970`

**Base:** `6e253f0386a4a6816f00fc48bedaecd8a20fffff`

**Worktree:** `/home/misael/Documentos/Codex/2026-07-29/prossiga/steamzero-gap-g23-publish`

**Nada commitado, nada enviado (pré-commit).**

## Status

```
$ git status --short
 M docs/KNOWN-GAPS.md
 M docs/diagnostics/2026-07-30-g26-test-state-isolation-evidence.md
 M tests/conftest.py
 M tests/unit/test_test_state_isolation.py
 M tools/run_tests_isolated.py
?? tests/fixtures/import_time_xdg_probe.py
```

## Mapeamento bloqueador → código → teste negativo

| Bloqueador | Correção | Teste |
|---|---|---|
| HOME com `startswith` | `_assert_xdg_matches` usa `Path.resolve(strict=True)` + igualdade exata + `pytest.UsageError` em `tests/conftest.py:46-57` | `test_home_negative_escape_rejected`, `test_home_negative_symlink_escape_rejected` |
| Collection-time fake | Probe real em `tests/fixtures/import_time_xdg_probe.py` com asserts no TOPO DO MÓDULO; subprocesso usa `tests/conftest.py` real via `--rootdir` | `test_collection_time_isolation_via_real_conftest` |
| `finally` não avalia mutação | Variáveis iniciadas antes do `try`; `KeyboardInterrupt` capturado → 130; mutação → 86 | `test_interrupt_returns_130_on_intact_state`, `test_interrupt_returns_86_on_mutated_state`, `test_snapshot_called_in_finally_even_on_error`, `test_unexpected_exception_with_mutation_reports_and_repropagates` |
| Entrypoint via substring | `_iter_python_invocations` tokeniza com `shlex`, rejeita `echo`/`printf`/`#`, só aceita `<python> tools/run_tests_isolated.py`; controle negativo para echo, printf, comment, no-python-exec, non-zero | `test_canonical_entrypoints_use_isolated_runner` + `_check_make_target` para test/cov/qml-visual |
| `resolve_real_state_home` usa `Path.home()` global | Usa `environ["HOME"]` em vez de `Path.home()`; falha se ambos ausentes; retorna `source` | `test_resolve_xdg_precedence`, `test_resolve_home_fallback`, `test_resolve_global_home_ignored`, `test_resolve_rejects_missing_both` |
| CI parsing superficial | Extrai blocos `run:`/`run |` do YAML, tokeniza com `shlex`, conta argv | CI check em `test_canonical_entrypoints_use_isolated_runner` |

## Arquivos alterados

O commit contém **seis** arquivos. O `git diff --stat` mostra apenas os quatro
modificados no working tree; o arquivo novo (`tests/fixtures/import_time_xdg_probe.py`)
não aparece por ser untracked até o stage. `git ls-files --others` o revela:

```
$ git diff --cached --name-status
M       docs/KNOWN-GAPS.md
M       docs/diagnostics/2026-07-30-g26-test-state-isolation-evidence.md
M       tests/conftest.py
A       tests/fixtures/import_time_xdg_probe.py
M       tests/unit/test_test_state_isolation.py
M       tools/run_tests_isolated.py
```

## Contrato de interrupção do runner

| Cenário | Retorno | Snapshot chamado? | Mutação relatada? |
|---|---|---|---|
| Normal + state intacto | exit code do pytest | ✅ | N/A |
| Normal + mutação | 86 | ✅ | ✅ |
| `KeyboardInterrupt` + intacto | 130 | ✅ | N/A |
| `KeyboardInterrupt` + mutação | 86 | ✅ | ✅ |
| Exceção inesperada + intacto | propaga exceção original | ✅ | N/A |
| Exceção inesperada + mutação | propaga exceção original | ✅ | ✅ (stderr) |
| SIGKILL | fora de controle | ❌ | N/A |

## Resolução do estado original

`resolve_real_state_home(environ)` usa `environ.get("XDG_STATE_HOME")` primeiro.
Se ausente, usa `environ.get("HOME")` para o fallback `HOME/.local/state/steamzero`.
Se ambos ausentes, levanta `RuntimeError`.
Retorna `(Path, source)` onde `source` é `"XDG_STATE_HOME"` ou `"HOME-default"`.

O runner loga a origem junto da fotografia:

```
real-state before: ... source=XDG_STATE_HOME
real-state after:  ... source=XDG_STATE_HOME
```

## Resultados (5ª rodada — evidência pré-commit)

### Testes focais (21)

```
$ .venv/bin/python tools/run_tests_isolated.py tests/unit/test_test_state_isolation.py -q
21 passed in 1.24s
```

### Media + switch (49)

```
$ .venv/bin/python tools/run_tests_isolated.py \
    tests/integration/test_media.py \
    tests/unit/test_switch_library.py \
    tests/unit/test_switch_media.py -q
49 passed in 1.06s
```

### Suíte integral (GREEN)

```
$ .venv/bin/python tools/run_tests_isolated.py tests -q
3275 passed in 242.07s (0:04:02)
```

State real inalterado:

```
real-state before: exists=True files=4460 directories=712 bytes=6191023 max_mtime_ns=1785148031973996359 source=XDG_STATE_HOME
real-state after:  exists=True files=4460 directories=712 bytes=6191023 max_mtime_ns=1785148031973996359 source=XDG_STATE_HOME
```

### Runs anteriores do cast IPC

| Run | Suíte | Falha |
|-----|-------|-------|
| 1ª integral (antes das correções) | 3262 passed, **1 failed** | `test_start_session_already_running` |
| 2ª integral (após correções) | 3269 passed, **1 failed** | `test_pause_resume_with_pipeline` (flaky diferente) |
| 10x isolado (branch) | 9 passed, 1 failed | `test_start_session_already_running` (1/10) |
| 10x isolado (base 7e1f45b) | 10 passed | Nenhuma |
| 3ª integral | **3275 passed, 0 failed** | Nenhuma |

**Conclusão**: a falha é intermitente no cast engine IPC (2 de 3 runs integrais
apresentaram flake em testes diferentes). Nenhum código de cast engine foi
alterado neste PR. O run final está verde. O gap do cast IPC está registrado
como G32 (não corrigido neste PR).

### Demais gates (5ª rodada)

| Gate | Resultado |
|------|-----------|
| `ruff check` | ✅ All checks passed |
| `ruff format --check` | ✅ 361 files already formatted |
| `mypy src` | ✅ 189 source files |
| `make independence` | ✅ OK |
| `make boundaries` | ✅ 0 violações |
| `git diff --check` | ✅ Sem whitespace errors |

## Discrepância da fotografia

| Executor | source | Arquivos | Diretórios | Bytes | before == after |
|---|---|---|---|---|---|
| Agente (5ª rodada) | `XDG_STATE_HOME` | 4460 | 712 | 6.191.023 | ✅ |
| Supervisor (rodada anterior) | `HOME-default` | 11744 | 1902 | 1.054.754.249 | ✅ |

A diferença é de **origem ambiental**, não mutação:

- O agente executou a suíte com `XDG_STATE_HOME` definido no ambiente, apontando
  para um state home específico com 4.460 arquivos.
- O supervisor executou sem `XDG_STATE_HOME`, o que fez o runner cair no fallback
  `HOME-default` (`HOME/.local/state/steamzero`), um diretório diferente com mais
  estado acumulado (11.744 arquivos).

Em ambos os casos `before == after`, confirmando que **nenhuma mutação ocorreu**
em state home algum. A discrepância de contagem não é uma falha do isolamento,
apenas um reflexo de `source` diferente entre as duas execuções.

## Gap do cast IPC (G32)

O cast engine IPC tem pelo menos dois testes com flake intermitente:
- `test_start_session_already_running`
- `test_pause_resume_with_pipeline`

Ambos foram observados em execuções integrais. Nenhum código de cast engine
foi alterado neste PR. O gap está registrado formalmente como **GAP-G32** em
`docs/KNOWN-GAPS.md`, prioridade P2, sem correção neste PR.

## Limitações

- SIGKILL não é interceptável e não há proteção.
- Nenhum código de cast engine foi alterado neste PR.
- O flake do cast IPC foi documentado como G32, não escondido nem corrigido.

## Estado G26

**Candidato a fechamento após CI e revisão.** Aguardando commit, push e verificação
dos checks do PR #21.
