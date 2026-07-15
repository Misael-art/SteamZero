# ADR-0016 — Estratégia de sync de saves: timeline local primeiro, nuvem como replica

**Status:** aceito

## Contexto
§10.5. EmuDeck sync espelha com rclone (conflitos resolvidos por heurística — risco de perda); RetroDECK cloud_sync é parcial. Pior falha possível do produto = perder save (R-07).

## Alternativas
1. **Timeline local append-only como fonte de verdade; nuvem = réplica versionada; conflito nunca auto-resolvido** (escolhida).
2. Espelho bidirecional direto (EmuDeck-style) — contras: last-writer-wins destrói progresso (J6 é exatamente o caso que quebra).
3. Nuvem como fonte de verdade — contras: offline-first violado.

## Decisão
Conforme DF-3/DF-4, GA-04/05, FM-16: checkpoints pré-suspensão, flush pré-shutdown, fila offline, criptografia opcional (idade do dado ≠ conteúdo visível ao provedor), identidade de dispositivo, ambos-preservados por padrão.

## Consequências
Custo de armazenamento (mitigado por dedupe de blobs — BACKUP-FORMAT §3); UX de conflito obrigatória (W4); feature flag até M9.

## Riscos
Emuladores com formato de save opaco/locks próprios — adapter declara pontos seguros de captura (pós-flush, sessão fechada).

## Revisão
Fase 3, com dados reais de tamanho/frequência.
