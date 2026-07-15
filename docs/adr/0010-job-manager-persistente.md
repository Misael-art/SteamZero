# ADR-0010 — Job Manager persistente no daemon (não filas por processo)

**Status:** aceito

## Contexto
§9.2. PhaseZero-Windows tem checkpoint/resume por pipeline (Save/Load-BootstrapCheckpoint) — resiliente, mas acoplado ao pipeline único. Nenhum dos quatro tem fila genérica com prioridades/limites/bateria.

## Alternativas
1. **Fila persistida no State Store, executor no daemon, jobs = transações ou leituras** (escolhida).
2. systemd user units por job — contras: granularidade/pausa/eventos pobres para o nosso caso; dependência forte.
3. Sem fila (executar na chamada) — contras: sem pausa/bateria/gameplay-block/reboot-recovery (GA-01).

## Decisão
Conforme JOB-LIFECYCLE.md: estados persistidos, pontos de segurança, constraints declarativas (rede/AC/gameplay), recovery na subida, limites via nice/ionice/cgroup quando disponível.

## Consequências
Todo domínio produz jobs com checkpoints; UI de Jobs é consumidor direto.

## Revisão
Se cgroups v2 delegation não estiver disponível no SteamOS para user slices, documentar limites best-effort.
