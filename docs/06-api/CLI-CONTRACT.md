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
steamzero service status --json
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
steamzero session environment --json
steamzero session status --game-id APPID --json
steamzero session recover --game-id APPID
steamzero playtime list [--limit 64] [--cursor CURSOR] --json
steamzero playtime show --game-id ID --json
steamzero desktop status --json
steamzero desktop plan --profile auto|handheld|dock|safe
steamzero desktop apply --plan-id P --confirm TOKEN
steamzero desktop reset --plan-id P_SAFE --confirm TOKEN
steamzero desktop recover · steamzero desktop ui
steamzero controls profiles --platform switch --json
steamzero controls plan --platform switch --profile standard-gamepad \
  [--scope platform|game|device|mode] [--scope-id ID] \
  [--orientation landscape|portrait-left|portrait-right]
steamzero controls apply --plan-id P --confirm TOKEN
steamzero controls rollback --operation-id OP
steamzero jobs list|pause|resume|cancel <jobId>
steamzero jobs list --limit 64 [--cursor JOB_ID] [--state STATE]
steamzero jobs list --follow [--job-id ID] [--cursor SEQ] [--timeout SEG] --json
steamzero operations list --limit 64 [--cursor OPERATION_ID]
steamzero operations list --follow [--operation-id ID] [--cursor SEQ] [--timeout SEG] --json
steamzero events page [--cursor SEQ] [--limit 64] [--kind KIND] [--entity ENTITY] --json
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
8. `session status` expõe o lifecycle persistido sem comando/ambiente. Sessão interrompida
   retorna exit 4 e `E-SESSION-INTERRUPTED`; `session recover` reconhece o terminal falho
   antes de liberar outro lançamento gerenciado.
9. `session environment` é estritamente read-only e observa DMI/painel, sessão gráfica,
   energia, rede, conectores DRM e volumes montados por UUID. Fonte ausente degrada o
   campo correspondente; nunca dispara mount, KScreen, systemctl ou ação privilegiada.
10. Páginas de jobs/operações usam cursor keyset e limite entre 1 e 256.
    `--follow --json` não emite envelope de sucesso: cada linha é um `event-v1`.
    `--timeout 0` drena somente o backlog após o cursor e é útil para reconexão/testes.
    Paths internos de journal, backup, parâmetros e ambiente não entram nessas saídas.
11. Jobs, operações e eventos paginados preferem a allowlist JSON-RPC do daemon.
    O follow usa `events.subscribe` na mesma conexão; somente ausência antes da
    conexão permite fallback local. Depois do primeiro ack, o cliente reconecta
    pelo último cursor em vez de misturar fontes ou repetir saída.
12. `playtime list|show` publica `feat-playtime-v1`, sem PID, comando ou
    ambiente. O cursor é opaco, o limite máximo é 100 e sessões legadas sem
    origem não recebem ação executável.
13. `service status` é estritamente read-only e não atravessa o próprio daemon:
    lê o alvo de `/opt/steamzero/current` e, somente quando `current` é legível,
    consulta `system.hello` exatamente uma vez. Publica `converged`, `pending`,
    `timeout` ou `unreadable`; nunca reinicia units. Quarentena existente
    aparece em `data.quarantine`.
