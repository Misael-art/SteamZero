# Componente: confirmação inicia job assíncrono

Data: 2026-08-16  
Branch: `codex/physical-functional-closure`  
Base do incremento: `2150b57`

## Reprodução vermelha

O endpoint `/component/apply` delegava diretamente a
`DesktopDashboard.apply_component()`, que mantinha a requisição HTTP aberta
enquanto `ComponentLifecycle.apply()` resolvia, baixava, instalava e verificava.
A QML compensava o bloqueio com timeout de 1.900.000 ms.

O teste novo exige retorno em menos de 200 ms com lifecycle deliberadamente
bloqueado, deduplicação de confirmação repetida e conclusão observável por job.
Antes da implementação, a prova falhou na coleta porque a porta de jobs de
componentes não existia (`ModuleNotFoundError`).

## Causa raiz

O lifecycle já era persistente, mas a superfície de componentes não passava
pelo `JobManager`. O único vínculo entre confirmação e execução era a própria
thread HTTP. Isso impedia progresso independente da janela, retry auditável e
proteção durável contra clique repetido.

## Núcleo implementado

- `ComponentLifecycle.validate_apply()` valida schema, token, TTL, executor,
  tombstone e fingerprint sem preparar nem aplicar;
- `ComponentJobService` cria `component.apply` no State Store e retorna antes
  de iniciar o worker;
- um único job é aceito por `planId`, inclusive sob clique repetido;
- worker e requisição usam conexões SQLite separadas por thread;
- resultado, progresso, erro e `operationId` são persistidos;
- confirmação inválida não cria job;
- retry cria um novo id mantendo correlação e parâmetros auditáveis.

## Evidência verde do núcleo

```text
.venv/bin/python tools/run_tests_isolated.py \
  tests/unit/test_component_jobs.py \
  tests/integration/test_component_lifecycle.py -q
```

Resultado: `67 passed in 2.78s`. Ruff focado e mypy dos dois módulos também
passaram.

## Limite antes da integração

Este registro prova o núcleo, ainda não a jornada HTTP/QML. Dashboard,
contrato assíncrono, polling e mensagem honesta da UI entram no commit
compartilhado final. Cancelamento durante download, progresso real por bytes e
retomada após reboot continuam incrementos posteriores do mesmo item.
