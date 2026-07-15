# LOGGING — logs estruturados (§14)

## Formato

JSONL em `$XDG_STATE_HOME/steamzero/logs/core.jsonl`, rotação por tamanho (herda o gatilho de 5MB do PhaseZero common.sh:14) + retenção por dias; permissão 0600; dir 0700.

Campos obrigatórios por registro:

```json
{ "ts":"ISO8601", "level":"debug|info|warn|error",
  "component":"core.tx|jobs|domain.saves|adapter.duckstation|api|ui",
  "operation":"component.update", "jobId":"…", "operationId":"…",
  "correlationId":"…", "code":"E-…|null", "msg":"…",
  "ctx":{…}, "result":"ok|fail|null", "durationMs":123 }
```

## Política de conteúdo dos logs (proibições — SR-13/14)

Nunca registrar: keys/tokens/credenciais (tipos Secret bloqueados pelo handler), conteúdo de saves, dados pessoais desnecessários, conteúdo protegido. Paths de conteúdo do usuário registrados na forma anonimizável `{ROMS}/psx/…` (tabela de raízes conhecidas); paths fora das raízes conhecidas passam por hash no bundle.

## Regras

1. Um evento significativo = um registro (sem multi-linha; stacktraces em campo `ctx.trace` apenas em level debug local).
2. correlationId propaga UI→API→job→transação→helper (o audit log do helper referencia o mesmo ID).
3. Logs de nível user-facing (o que a UI mostra) derivam do event bus, não de parsing de log — logs são para diagnóstico, não IPC.
4. `steamzero logs tail --json --correlation <id>` para suporte.
5. Verificação contínua: ST-03 (canary secrets) roda no CI contra todos os fluxos.
