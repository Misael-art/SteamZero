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

## Integração HTTP/QML

O dashboard passou a iniciar `ComponentJobService`, e os endpoints de status,
cancelamento e retry reconhecem o job de componente antes de delegar aos jobs de
emulação. O catálogo publica `component.apply` como assíncrono e aponta para o
endpoint de polling já consumido pela gaveta de tarefas.

A confirmação QML agora:

- usa o timeout HTTP comum de 60 segundos, sem a exceção de 1.900.000 ms;
- só fecha o diálogo depois que a bridge devolve um `jobId`;
- informa que a tarefa foi iniciada, sem alegar instalação já verificada;
- mantém a proteção existente contra nova confirmação enquanto a requisição
  equivalente está pendente.

Prova focada da jornada integrada:

```text
.venv/bin/python tools/run_tests_isolated.py \
  tests/unit/test_component_jobs.py \
  tests/integration/test_component_lifecycle.py \
  tests/unit/test_desktop_dashboard.py \
  tests/unit/test_desktop_contracts.py \
  tests/integration/test_desktop_ui_bridge.py \
  tests/integration/test_ui_confirm_job_recovery_e2e.py -q
```

Resultado: `158 passed in 36.83s`. `qmllint
src/steamzero/ui/qml/Main.qml`, Ruff focado e verificação de formato passaram.

## Gate integral do incremento

A primeira execução integral expôs três lacunas de integração: o inventário não
classificava `validate_apply`, um teste de dashboard mínimo não construía o novo
serviço e o digest do item de UI ficou obsoleto após a mudança QML. As três
causas foram corrigidas e reproduzidas em testes focados (`70 passed` e depois
`53 passed`).

A execução integral definitiva, após a última alteração de código, terminou
com:

```text
4704 passed, 10 skipped in 970.46s (0:16:10)
real-state before: exists=True files=11912 directories=1940 bytes=1100910787
real-state after:  exists=True files=11912 directories=1940 bytes=1100910787
```

Os dez skips pertencem à conformance Flatpak que fixa o commit e usa o checksum
do executor portátil como garantia. O runner confirmou que o estado real do
usuário não foi alterado.

## Limites honestos deste incremento

O job já é persistente e independente da requisição HTTP, mas este incremento
não declara concluídos cancelamento durante download, progresso real por bytes,
retomada automática do worker após reinício nem a matriz física 33/33. Esses
itens permanecem nos próximos incrementos do mesmo item.
