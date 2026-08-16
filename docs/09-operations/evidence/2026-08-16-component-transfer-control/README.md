# Componente: progresso e cancelamento durante aquisição

Data: 2026-08-16  
Branch: `codex/physical-functional-closure`  
Base do incremento: `bb5645f`

## Hipótese a reproduzir

O cliente de rede já lê artefatos em chunks, mas o job de componente não recebe
esses bytes nem conecta seu pedido de cancelamento à leitura. Assim o progresso
permanece em `preparing` durante o download e cancelar um job em execução só é
honrado depois que `ComponentLifecycle.apply()` retorna.

Este incremento começa com testes vermelhos que exigem contagem persistida de
bytes declarados e terminalização `cancelled` antes de o restante do artefato ou
qualquer operação ser aplicado.

## Reprodução vermelha

```text
.venv/bin/python tools/run_tests_isolated.py \
  tests/unit/test_core_net.py::test_transfer_observer_reports_declared_bytes_for_each_chunk \
  tests/unit/test_component_jobs.py::test_download_persists_real_byte_progress_while_job_is_running \
  tests/unit/test_component_jobs.py::test_cancel_during_download_stops_before_apply_and_terminalizes -q
```

Resultado anterior à correção: `3 failed`. As falhas provaram, respectivamente,
ausência do observador de transferência, progresso preso em `preparing` e job
terminando incorretamente em `succeeded` após pedido de cancelamento.

## Causa raiz e correção

`fetch_bytes()` já lia a resposta de forma limitada em chunks, porém não havia
uma ligação entre essa fronteira e o `JobContext`. O handler chamava um único
`safepoint()` antes de entrar no lifecycle e só voltava a ter controle quando
todo download/aplicação terminava.

- `transfer_observer()` mantém callbacks de progresso e cancelamento em
  `ContextVar`, isolados por thread e restaurados na saída;
- a leitura limitada publica zero inicial e bytes recebidos após cada chunk,
  usando `Content-Length` validado quando disponível;
- o handler traduz esses valores para progresso persistido `downloading/bytes`
  com o componente corrente;
- safepoints antes e depois da leitura interrompem o worker com `JobCancelled`;
- como o engine só publica cache/transação após receber e verificar o corpo
  completo, cancelamento durante aquisição não deixa operação parcial.

## Evidência verde focada

```text
.venv/bin/python tools/run_tests_isolated.py \
  tests/unit/test_core_net.py \
  tests/unit/test_component_jobs.py \
  tests/unit/test_engine_network.py \
  tests/integration/test_component_lifecycle.py -q
```

Resultado: `83 passed in 2.85s`; Ruff e mypy focados também passaram. A prova
cobre downloads internos de engine/AppImage/native e archives Libretro, que
compartilham `HttpsArtifactPort`. Operações Flatpak são subprocessos externos e
ainda precisam de prova separada de etapas/cancelamento; retomada após reinício
também permanece aberta.

## Gate integral

```text
4707 passed, 10 skipped in 971.86s (0:16:11)
real-state before: exists=True files=11912 directories=1940 bytes=1100911367
real-state after:  exists=True files=11912 directories=1940 bytes=1100911367
```

Os dez skips são os casos de conformance em que Flatpak fixa commit e o
checksum pertence ao executor portátil. O runner isolado confirmou novamente
que a suíte não alterou o estado real do usuário.
