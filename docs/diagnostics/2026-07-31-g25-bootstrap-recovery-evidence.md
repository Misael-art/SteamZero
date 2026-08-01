# Evidência de recovery no bootstrap + auditoria no doctor — GAP-G25

**Data:** 2026-07-31

**Branch:** `codex/fix-g25-bootstrap-recovery`

**Base:** `831280a6b559a7c8c18f74f5e3309e6064a358db` (main, pós-G26)

**HEAD:** `77800fd4bfce8cbfd7abe6f5d58d36fbe2c8c8d7`

## Problema (G25 — P0, falso verde operacional)

Dois jobs `media.global` sobreviviam desde 2026-07-26 em estado `running`;
`JobManager.recover()` existia mas **não era chamado no bootstrap**. O
`doctor` reportava `ok` porque seu único check de recovery (`_pending_operations`)
contava journals não-terminais — **não jobs** — então jobs stalados em SQLite
passavam despercebidos. O `cancel()` de um job `running` sem runner ativo era
inerte (`request_cancel` só seta um flag que nada consome).

## Decisões de design (operator)

- **D1 (recover sem operation_id):** cancelar e marcar (`cancelled` +
  `error_code="recovered"`), **não reenfileirar** — reenfileirar reativaria
  rede no próximo request (caso `media.global`).
- **D2 (cancel sem runner):** forçar terminal via `recover()` quando não há
  handler vivo neste processo (`_controls` vazio); com handler vivo, manter
  `request_cancel` (sem regressão).
- **D3 (escopo do bootstrap):** chamar **ambos** — `JobManager.recover()`
  (cêntrico em jobs) + `transaction.recover_all()` (cêntrico em journals/órfãos).

## Mudanças (5 commits atômicos)

| Commit | Resumo |
|---|---|
| `eebc06d` | `jobs`: `recover()` termina jobs sem `operation_id` em `cancelled`+recovered (não `queued`); `cancel()` de running sem runner força terminal via recover. Estado `interrupted` ganha destino `cancelled`. |
| `d277d64` | `service`: `serve()` chama `_recover_at_boot()` uma vez (recover + recover_all), best-effort (§8: try/except, nunca impede `serve_forever`). |
| `ac46334` | `diagnostics`: novo módulo `domain/state_audit.py`; `doctor` consome `audit()` em 4 checks novos (`jobs.stale`, `staging.orphan`, `backup.orphan`, `journal.orphan`) + contadores no `data`. |
| `72b5904` | `cli`: `state audit` (read-only) + `state cleanup-plan`/`cleanup-apply` (2 fases, quarentena recoverable, token de confirmação); specs em `methods.py`. |
| `77800fd` | `fix`: escritas de FS em `state_audit.py` roteadas por `core.fs` (gate de fronteiras). |

## Pontos de inserção

- `src/steamzero/jobs/models.py:26` — `interrupted` → `{queued, rolling-back, completed, cancelled}`.
- `src/steamzero/jobs/manager.py` — `recover()` (sem op_id) e `cancel()` (running sem runner).
- `src/steamzero/service/core.py:441` — `_recover_at_boot(store)` após `store.migrate()`.
- `src/steamzero/diagnostics/doctor.py` — 4 checks novos dentro do bloco `StateStore`.
- `src/steamzero/domain/state_audit.py` — `audit()`, `plan_cleanup()`, `apply_cleanup()`.
- `src/steamzero/cli/main.py` — `_cmd_state_audit`, `_cmd_state_cleanup_plan`, `_cmd_state_cleanup_apply`.
- `src/steamzero/service/methods.py` — `state.audit` (read-only), `state.cleanup.plan`/`.apply` (mutation).

## Testes que provam

| Comportamento | Teste |
|---|---|
| recover de job sem op_id → cancelled+recovered (não queued) | `tests/integration/test_jobs.py::test_recover_cancels_running_without_op` |
| recover idempotente (2ª chamada = []) | `tests/integration/test_jobs.py::test_recover_is_idempotent` |
| cancel de running sem runner → terminal | `tests/integration/test_jobs.py::test_cancel_runnerless_running_forces_terminal` |
| cancel com handler vivo mantém request_cancel (regressão) | `tests/integration/test_jobs.py::test_cancel_running_with_live_control_still_requests` |
| serve() recupera jobs stalados no boot | `tests/unit/test_service_core.py::test_serve_recovers_stale_jobs_at_boot` |
| serve() sobe mesmo se recovery falha (§8) | `tests/unit/test_service_core.py::test_serve_boots_even_if_recovery_fails` |
| doctor: 4 checks passam quando limpo | `tests/unit/test_doctor.py::test_doctor_reports_g25_audit_checks_when_clean` |
| doctor: warn em job stalado | `tests/unit/test_doctor.py::test_doctor_warns_on_stale_jobs` |
| doctor: warn em staging órfão | `tests/unit/test_doctor.py::test_doctor_warns_on_orphan_staging` |
| state audit read-only (clean) | `tests/integration/test_cli.py::test_state_audit_reports_clean` |
| state audit flagga órfão | `tests/integration/test_cli.py::test_state_audit_flags_orphan_staging` |
| cleanup plan→apply move p/ quarentena (recoverable) | `tests/integration/test_cli.py::test_state_cleanup_plan_and_apply_roundtrip` |
| cleanup-apply rejeita token errado | `tests/integration/test_cli.py::test_state_cleanup_apply_rejects_wrong_token` |

## Gates (§6, verde em todos)

```
$ .venv/bin/python tools/run_tests_isolated.py tests -q
3324 passed in 298.99s
real-state before: files=11744 bytes=1054754262 max_mtime_ns=1785525373223019177
real-state after:  files=11744 bytes=1054754262 max_mtime_ns=1785525373223019177
(exit 0 — isolador confirma: nenhuma mutação do estado real do host)

$ .venv/bin/ruff check src tools tests
All checks passed!

$ .venv/bin/mypy src
Success: no issues found in 189 source files

$ make independence boundaries
independência de runtime: OK
lint de fronteiras: OK (0 violações)
```

Cobertura não regrediu (3312 → 3324 testes).

## Fora de escopo (defer)

- **`cleanup-apply` contra o acervo de ~1,1 GB existente no host:** bloqueado
  até autorização humana (AGENTS.md §1). O G25 entrega os comandos, não os
  executa contra o acervo.
- **G27/G28/G29/G30/G31/G32:** PRs separados.
- Sem toque em artefatos de host sob §5 (`/opt/steamzero`, units, GRUB, SDDM) —
  recovery/audit/cleanup operam apenas sob XDG state home.

## Passos que ainda exigem o operador

- Revisão e merge do PR (após CI verde).
- Eventual aplicação do `cleanup-apply` no host, com autorização explícita,
  após inspecionar o plano gerado por `state cleanup-plan`.
