# Correção — frente paralela A (G7 / G32 / M14) — 2026-08-10

## Decisão

A branch `codex/docs-g7-g32-m14` **permanece** como arquivo de trabalho
preparatório. **Não** é reescrita nem apagada. **Não** há push nem PR.

Os commits existentes **não** entram na linha principal como fechamento:

| Commit | Conteúdo | Uso permitido |
|---|---|---|
| `216f87e` | G7 inventário + M14 plano (misturados) | fonte para **reaplicar** docs; não closure G7; não um-item-por-commit |
| `f57a34d` | “fechamento” G32 + WORKLOG | **inválido como closure**; stress log preservado só como rascunho |

## Achados da auditoria (aceitos)

1. `f57a34d` não comprova fechamento G32 e não deve ser integrado como closure.
2. Inventário G7 cobre só o tree de `39bd325`; regenerar na árvore final M10+M11.
3. G7 e M14 em `216f87e` violam um item por commit.
4. Gates integrais obrigatórios ausentes.
5. `.venv` (symlink no worktree) não rastreado e **nunca** commitável.

## Estado corrigido em KNOWN-GAPS (este follow-up)

- **G7:** reaberta — inventário preparatório apenas.
- **G32:** reaberta — re-provar após code freeze; `f57a34d` invalidada.

## Checklist pós–code freeze M10 (executar só então)

Pré-condições:

- [ ] Operador declara **code freeze M10** e publica o SHA do tip final.
- [ ] Tip final **contém** `242ba38` (`git merge-base --is-ancestor 242ba38 <tip>`).
- [ ] Preferível: tip já é integração M10+M11 estável (ou base explicitamente
  autorizada que contenha ambos).
- [ ] Sem suíte/VM M10 concorrente para gates integrais.
- [ ] Sem push sem autorização.

Passos:

1. **Nova branch limpa** a partir do tip final (não rebasear/reescrever
   `codex/docs-g7-g32-m14`).
   ```bash
   git fetch origin
   TIP=<sha-code-freeze>
   git worktree add /mnt/sdcard/Projects/Port_Steam-docs-g7-g32-m14-v2 \
     -b codex/docs-g7-g32-m14-v2 "$TIP"
   git merge-base --is-ancestor 242ba38 HEAD  # deve passar
   ```
2. **M14** — copiar/adaptar `docs/09-operations/M14-DISTRIBUTION-PLAN.md` da
   branch preparatória → **commit só M14**.
   WORKLOG: iniciado M14 / fechado M14.
3. **G7** — regenerar inventário (hashes, paths novos da árvore M10+M11),
   atualizar notices/matrix → **commit só G7**.
   WORKLOG: iniciado G7 / fechado G7 (só se inventário completo do tip).
4. **G32** — stress dirigido **sobre o código do tip** (que contém `242ba38`):
   - 50× par `TestEngineProtocol::test_start_session_already_running` +
     `test_pause_resume_with_pipeline`
   - ≥5–10× `tests/integration/test_cast_engine_ipc.py`
   - evidência nova em `docs/diagnostics/YYYY-MM-DD-g32-closure-audit.md`
   - se 0 falhas: fechar G32 em KNOWN-GAPS + **commit só G32**
   - se falhar: manter aberto; não reimplementar sem causa
   WORKLOG: iniciado G32 / fechado ou bloqueado G32.
5. **Gates integrais** (quando o host estiver livre da VM M10):
   ```bash
   .venv/bin/python tools/run_tests_isolated.py tests -q
   .venv/bin/ruff check src tools tests
   .venv/bin/ruff format --check src tools tests
   .venv/bin/mypy src
   make independence boundaries
   ```
6. **Push** somente com autorização explícita; nunca force-push; nunca
   commitar `.venv` / `dist/` / wheels.

## O que não fazer agora

- Não push / PR de `codex/docs-g7-g32-m14`.
- Não mergear `f57a34d` / `216f87e` como fechamento na main/integração.
- Não apagar a branch preparatória.
- Não reabrir stress G32 “de fechamento” sobre base antiga.
- Não competir com VM M10 em suíte integral.
