# Update físico de componentes — Dolphin e RetroArch

Release: `2.0.0rc1-5127fbc855d9` (commit `5127fbc`, run CI verde `33341904384`)
instalada no host, rollback `2.0.0rc1-920ec79e875a`.

## Resultado no host

Matriz de componentes: **15 instalados, 0 outdated, 18 missing**.

- **Dolphin**: `outdated → installed` no commit fixado `377c3e63506e`.
- **RetroArch**: `outdated → installed` no commit `9c51e2bcb6f7`.

O update REAL de versão do executor Flatpak foi exercitado pela primeira vez
(antes só install/verify/rollback de cores eram provados), confirmando o ciclo
plan → apply (job no daemon) → verify → convergência.

## Causa raiz do RetroArch

O pin do RetroArch no manifest (`d8644a97df3d…`) estava **purgado do Flathub**:
`flatpak remote-info --commit=<pin>` retorna 404. O executor recusava com
`E-SUPPLY-REMOTE-FAILED` e fazia rollback automático (resiliência — sem estado
quebrado). Repinado para o commit atual confirmado `9c51e2bcb6f7…`
(`retroarch.adapter.json` + `component-lock.json`), e a nova release carregou a
correção: o update convergiu.

## Estados

- `doctor`: provenance `2.0.0rc1-5127fbc855d9`, `service.generation`
  convergente, `staging.orphan`/`backup.orphan` pass, `recovery.pending` 0.
- `state audit` → `clean: True`.

## Pendência restante (workstream COMPONENT-MATRIZ)

Progresso por bytes e cancelamento cooperativo; instalar os componentes
restantes (Azahar, PPSSPP, Xemu).
