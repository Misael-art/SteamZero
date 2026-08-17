# Componente: progresso e cancelamento Flatpak

Data: 2026-08-16  
Branch: `codex/physical-functional-closure`  
Base do incremento: `f52a945`

## Hipótese a reproduzir

O executor Flatpak registra rollback durável, porém as operações de até 1.800 s
rodam em `subprocess.run()`. O job não recebe etapas e um pedido de cancelamento
não alcança o processo enquanto ele está ativo.

A prova vermelha deve exigir etapas persistidas, safepoints entre fases e
terminação do processo Flatpak real quando o controle do job pede cancelamento,
sem usar o Flatpak instalado nem alterar o host.

## Reprodução vermelha

```text
.venv/bin/python tools/run_tests_isolated.py \
  tests/unit/test_flatpak.py::test_real_runner_terminates_flatpak_when_job_cancels \
  tests/integration/test_flatpak_executor.py::test_apply_publishes_ordered_flatpak_stages \
  tests/unit/test_component_jobs.py::test_flatpak_stage_is_persisted_by_component_job -q
```

Resultado anterior à correção: `3 failed`. Não existiam observador, etapas nem
propagação do controle do job. Uma reprodução adicional provou que
`JobCancelled` era convertido em `E-COMPONENT-UPDATE-ROLLEDBACK`, produzindo
estado de falha apesar do rollback bem-sucedido.

## Causa raiz e correção

`FlatpakCLI` recebia um runner síncrono baseado em `subprocess.run()`, enquanto
`FlatpakExecutor` só conhecia sucesso/falha no retorno de cada chamada. O
`JobContext` ficava fora das duas camadas.

- o runner real usa `Popen` sem shell, sessão nova, stdout/stderr capturados e
  espera cooperativa de no máximo 250 ms por ciclo;
- cancelamento termina o processo; se ele não sair em dois segundos, usa kill;
- timeout continua normalizado como retorno 124, preservando stdout/stderr;
- um observador `ContextVar` isolado por thread publica etapas e safepoints;
- install novo publica `installing`, `deploying`, `verifying`, `smoke` e
  `persisting`; update/noop/uninstall publicam somente suas etapas aplicáveis;
- cancelamento depois de efeito entra no rollback existente, preserva os dados
  da aplicação e volta a propagar `JobCancelled`, permitindo estado terminal
  `cancelled` no manager;
- os argv permanecem user-scoped, não interativos e sem `--delete-data`.

## Evidência verde focada

```text
.venv/bin/python tools/run_tests_isolated.py \
  tests/unit/test_flatpak.py \
  tests/integration/test_flatpak_executor.py \
  tests/unit/test_component_jobs.py \
  tests/integration/test_component_lifecycle.py -q
```

Resultado: `107 passed in 3.48s`. Ruff, formato e mypy focados passaram. Todos
os processos e deployments desta prova são fakes; o Flatpak do host não foi
executado.

## Gate integral

```text
4714 passed, 10 skipped in 974.72s (0:16:14)
real-state before: exists=True files=11912 directories=1940 bytes=1100911367
real-state after:  exists=True files=11912 directories=1940 bytes=1100911367
```

Os skips são a conformance Flatpak que fixa commit e delega checksum ao executor
portátil. O runner isolado confirmou que nenhum estado real do usuário mudou.
