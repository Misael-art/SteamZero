# Componente: recovery e retomada após reinício

Data: 2026-08-16  
Branch: `codex/physical-functional-closure`  
Base do incremento: `e819bec`

## Hipótese a reproduzir

O job é persistido, mas um novo `ComponentJobService` ainda não reconcilia jobs
`running` sem worker nem retoma jobs `queued` autorizados. A prova vermelha deve
mostrar que o estado pode permanecer não terminal após a perda do processo.

O recovery precisa ser seletivo para `component.apply`: não pode terminalizar
jobs de mídia, biblioteca ou outras frentes que compartilham o mesmo State
Store. Jobs interrompidos sem operação devem terminar cancelados e permitir um
retry auditável; jobs ainda queued podem receber um novo worker sem duplicação.

## Reprodução vermelha

```text
.venv/bin/python tools/run_tests_isolated.py \
  tests/integration/test_jobs.py::test_recover_filters_job_types_without_touching_other_workers \
  tests/unit/test_component_jobs.py::test_recover_resumes_persisted_queued_component_job \
  tests/unit/test_component_jobs.py::test_recover_terminalizes_interrupted_component_and_retry_is_auditable -q
```

Resultado anterior à correção: `3 failed`. `JobManager.recover()` não aceitava
filtro e `ComponentJobService` não publicava recovery, confirmando que a perda
do processo deixava o registro sem novo executor.

## Causa raiz e correção

A persistência do job existia, mas a criação do worker era exclusivamente uma
consequência da requisição HTTP original. Um processo novo não diferenciava seu
job órfão dos demais tipos no banco nem reconstruía workers queued.

- `JobManager.recover(job_types=…)` reconcilia somente tipos explicitamente
  selecionados e também terminaliza `cancelling` órfão;
- `ComponentJobService.recover()` é idempotente por instância, recupera apenas
  `component.apply` e inicia novo worker somente para registros `queued`;
- `running` sem operação vira `cancelled` com `errorCode=recovered`, permitindo
  retry com novo id e correlação preservada;
- a primeira listagem da gaveta chama o serviço e funde os jobs por `jobId`, sem
  duplicar o registro que ambos os controladores enxergam no mesmo banco;
- jobs de mídia e outros tipos permanecem intocados pelo recovery do componente.

## Evidência verde focada

```text
.venv/bin/python tools/run_tests_isolated.py \
  tests/integration/test_jobs.py \
  tests/unit/test_component_jobs.py \
  tests/unit/test_desktop_dashboard.py \
  tests/integration/test_desktop_ui_bridge.py \
  tests/integration/test_ui_confirm_job_recovery_e2e.py -q
```

Resultado: `104 passed in 34.24s`. Ruff, formato e mypy focados passaram.
Recovery não tenta repetir cegamente um efeito que estava `running`; ele o
terminaliza/reconcilia primeiro. A retomada automática é restrita ao estado
`queued`, no qual nenhum handler havia iniciado.

## Gate integral

```text
4710 passed, 10 skipped in 974.44s (0:16:14)
real-state before: exists=True files=11912 directories=1940 bytes=1100911367
real-state after:  exists=True files=11912 directories=1940 bytes=1100911367
```

Os skips são a conformance Flatpak que fixa commit e delega checksum ao executor
portátil. O estado real do usuário permaneceu idêntico antes e depois.
