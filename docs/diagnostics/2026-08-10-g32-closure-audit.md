# G32 stress log — 2026-08-10 — **NÃO VINCULANTE / NÃO É CLOSURE**

> **Status (2026-08-10, pós-auditoria):** este arquivo e o commit `f57a34d`
> **não comprovam** o fechamento de G32 e **não devem ser integrados** como
> closure. Preservados apenas como trabalho preparatório na branch
> `codex/docs-g7-g32-m14`. Ver `docs/diagnostics/2026-08-10-docs-parallel-a-correction.md`
> e o plano pós–code freeze no WORKLOG.

## Por que não conta como fechamento

1. Base da branch: `origin/main@39bd325` — a auditoria de integração considera
   que essa base **não** é o tip válido para provar G32 em relação ao fluxo
   M10+M11 / linha de desenvolvimento atual; o stress não foi refeito sobre o
   tip final que a orquestração exige (tip com `242ba38` **e** árvore M10+M11).
2. Gates integrais obrigatórios (`run_tests_isolated` suíte, ruff, format-check,
   mypy, `make independence boundaries`) **não** foram executados nesta frente.
3. G7 e M14 foram combinados em `216f87e` (viola “um item por commit”).
4. Inventário G7 cobre o tree de `39bd325`, não a árvore final M10+M11.
5. `.venv` (symlink no worktree) permanece não rastreado e **nunca** deve ser
   commitado.

## Log bruto (histórico; não usar para KNOWN-GAPS)

- Branch: `codex/docs-g7-g32-m14`
- Base: `39bd325`
- Node ids: `TestEngineProtocol::test_start_session_already_running` e
  `test_pause_resume_with_pipeline`
- 50× o par + 5× `test_cast_engine_ipc.py` → 0 falhas **nessa base**
- Isso demonstra no máximo “verde local num ponto antigo”, não closure de G32
  na linha de desenvolvimento.

## Re-prova obrigatória (após code freeze M10)

1. Nova branch limpa a partir do tip final que **contenha** `242ba38`.
2. Stress G32 dirigido sobre **esse** tip (par 50× + arquivo completo ≥5–10×).
3. Só então atualizar `KNOWN-GAPS` se 0 falhas.
4. Gates integrais sem VM/suíte M10 concorrente.
5. WORKLOG: iniciado/fechado por item; um commit por item.
6. Sem push sem autorização.
