# Recursos e probe QML — leitura somente leitura — 2026-09-22

## Resource probe no host

```text
/usr/local/bin/steamzero system resources --json
```

O contrato retornou `readOnly=true`, `complete=false` e
`reason=proc-incomplete`, sem atribuir processos desconhecidos à UI. O daemon
foi observado com 1 processo e 55.499.776 bytes de PSS; não havia job de mídia
nem emulador atribuível naquele instante. O snapshot preservou 415 processos
como `unknown`, com falhas de procfs/permissão, total não atribuível de
3.650.822.144 bytes e 261 processos com memória desconhecida.

Esse resultado é degradado de forma explícita: não é uma medição completa e
não transforma consumo agregado do host em consumo da UI SteamZero.

## Canonical

```text
PYTHONPATH=src:tools:/opt/steamzero/current/venv/lib/python3.14/site-packages \
python3 tools/run_tests_isolated.py \
  tests/unit/test_resource_probe.py tests/unit/test_qml_runtime_probe.py \
  tests/unit/test_launcher_perf_probe.py -q -k 'resource or qml or perf'
```

Resultado: **49 passed**; a fotografia do state home real permaneceu idêntica.
O probe QML recusa timeout, sinal (`SIGABRT`/`SIGSEGV`), exit não-zero e stderr
crítico antes de aceitar qualquer PNG como renderização válida.
