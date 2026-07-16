# CLI-CONTRACT — contrato da CLI `steamzero`

## Convenções globais

- `steamzero <domínio> <ação> [alvo] [flags]`; domínios incluem `component, library,
  bios, saves, media, perf, controls, frontend, session, mode, desktop, storage, jobs,
  state, config, doctor, backup, support`.
- **Saída:** humana por padrão; `--json` emite envelope v2 (abaixo) em stdout **puro** (nada mais em stdout; avisos em stderr) — herda a disciplina do PhaseZero `-UiContractJson` ("MUST emit JSON only, no stderr").
- **Exit codes estáveis:** 0 ok · 1 falha da operação (ver `error.code`) · 2 uso inválido · 3 precisa confirmação (`--confirm` ausente) · 4 bloqueado (lock/rede/compat) · 69 dependência ausente · 77 privilégio requerido (herdados dos usos 69/77 no PhaseZero common.sh).
- **Mutação:** toda ação mutável tem `--dry-run`, `--plan` (só plana e imprime `planId`+`confirmToken`), `--confirm <token>`; `--yes` só em ações de risco baixo declarado.
- **Progresso:** `--json` + `--follow` emite NDJSON de eventos (EVENTS-AND-PROGRESS).
- Compat: contrato é semver; quebra de contrato = major da CLI; `steamzero --contract-version`.

## Envelope v2 (evolução do json-envelope.sh do PhaseZero)

```json
{ "ok": true, "contract": "2.0", "module": "component", "action": "update",
  "status": "ok|degraded|failed|blocked|noop",
  "operationId": "ULID|null", "jobId": "ULID|null", "correlationId": "ULID",
  "data": { …específico da ação, schemado… },
  "checks": [{"name":"…","status":"pass|warn|fail","message":"…"}],
  "blockers": [{"code":"E-…","message":"…"}],
  "error": {"code":"E-…","title":"…","detail":"…","action":"…"} ,
  "generatedAt": "ISO8601" }
```

## Exemplos normativos

```
steamzero doctor --json
steamzero component list --json
steamzero component status --id retroarch --json
steamzero component plan --id retroarch                # → planId + confirmToken + preview
steamzero component apply --plan-id P --confirm TOKEN
steamzero component rollback --operation-id OP
steamzero component recover
steamzero library scan --scope directory --path ~/Roms --json
steamzero library apply --plan-id P --confirm TOKEN [--dry-run]
steamzero library rollback --operation-id OP
steamzero bios status [--platform psx] --json
steamzero saves timeline <gameId> · steamzero saves restore <gameId> --entry SEQ --confirm T
steamzero mode apply docked-tv · steamzero mode status --json
steamzero desktop status --json
steamzero desktop plan --profile auto|handheld|dock|safe
steamzero desktop apply --plan-id P --confirm TOKEN
steamzero desktop reset --plan-id P_SAFE --confirm TOKEN
steamzero desktop recover · steamzero desktop ui
steamzero jobs list|pause|resume|cancel <jobId>
steamzero state export --out state.json · steamzero backup create --full
steamzero support bundle --preview
```

(Espelha a gramática consagrada do `pz emulation library scan/plan/apply/verify/rollback` — evidência: `linux/pz` usage 96-100.)

## Regras

1. CLI é cliente do daemon; com daemon ausente, roda o núcleo in-process com os mesmos contratos.
2. Nenhuma ação aceita path cru onde exista ID de entidade (T-05); comandos de import aceitam paths (validados).
3. `--json` é estável e testado por golden files; mudanças aditivas apenas dentro do mesmo major.
4. `desktop status` é read-only e funciona sem Qt, KDE, Steam ou InputPlumber. `apply`
   revalida o fingerprint do contexto e recusa ownership concorrente. Quando existe
   remediação segura, `data.conflictActions` expõe actionId, escopo, privilégio e argv
   exato; a bridge exige planId + confirmToken antes de executá-la.
5. `desktop recover` só restaura snapshot pendente; `desktop reset` aceita exclusivamente
   plano `safe` já confirmado.
6. `component plan` resolve o commit Flatpak pinado e congela o deployment user-scoped
   anterior. `apply` revalida esse snapshot, nunca usa `--system` e não aceita fonte EOL.
7. Rollback Flatpak tem garantia `G-DEPLOYMENT`: restaura o commit anterior ou remove o
   deployment recém-instalado, sem `--delete-data`; runtimes órfãos podem permanecer para GC.
