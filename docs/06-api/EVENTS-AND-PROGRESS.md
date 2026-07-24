# EVENTS-AND-PROGRESS — eventos e progresso

## Canal

- API: notificações JSON-RPC após `events.subscribe {jobIds?|kinds?|entities?}`.
- CLI: `--follow` emite NDJSON (um evento por linha, schema `event-v1`).
- UI que reconecta: re-hidrata do State Store (`job.get` + `event_log` desde `seq`) — eventos têm `seq` monotônico por job; sem perda ao reconectar.
- F3 implementa a metade local: páginas crescentes limitadas a 256 eventos,
  cursor igual ao último `seq` consumido e polling sem acumular histórico em
  memória. A assinatura persistente do daemon/JSON-RPC pertence a F4.
- Sem cursor explícito, `--follow` começa no maior `seq` já persistido; para
  retomar uma conexão, o consumidor envia o último cursor confirmado.
- Eventos sistêmicos sem correlação de requisição usam o ULID reservado
  `00000000000000000000000000`; eventos de job recuperam o `correlationId`
  persistido no próprio job.

## Tipos

| kind | Conteúdo | Frequência |
|---|---|---|
| `job.state` | transições da máquina de JOB-LIFECYCLE | por transição |
| `operation.state` | `applying|committed|rolled-back|…` espelhado do journal | por mudança real |
| `session.state` | lifecycle canônico do jogo (`launching`…`failed`) | por transição |
| `session.environment` | digest + grupos materiais alterados no host | por mudança observada |
| `session.resume` | duração aproximada observada após suspend | por retomada |
| `job.progress` | `{stage, current, total, unit, rate, currentItem, etaSeconds?}` | throttle ≤ 4/s por job |
| `entity.changed` | `{entityType, id, change}` (component instalado, save novo, volume missing...) | por mudança |
| `alert` | problemas críticos (rollback-failed, storage-missing) | imediato |

## Regras de honestidade do progresso (P11)

1. `total` só é reportado quando conhecido de verdade (bytes do Content-Length, itens do plano); senão `total: null` e a UI mostra etapa+contador — **proibido progresso sintético/percentual inventado**.
2. `stage` vem do pipeline transacional (scan/plan/backup/stage/apply/verify/activate/test) — o usuário vê em que fase real está.
3. Cancelamento: `job.cancel` → evento `job.state: cancelling` imediato + `cancelled` quando o ponto de segurança foi atingido; a UI mostra "cancelando com segurança…" nesse intervalo.
4. Pausa/retomada emitem eventos com causa (`user`, `battery`, `network`, `gameplay`).
5. Jobs longos emitem `checkpoint` (para resume) — visível como "progresso persistido".
6. Eventos de sessão carregam apenas `sessionId`, `gameId` e estado; comando e ambiente
   do jogo nunca entram no log ou no contrato público.
7. O reconciliador não emite evento por percentual de bateria, espaço livre ou timestamp;
   somente topologia/capacidade material produz uma nova sequência.
8. `session.resume` compara `CLOCK_BOOTTIME` com `CLOCK_MONOTONIC`. É evidência
   pós-resume; não equivale a um hook pré-suspend nem promete flush anterior.
9. O produtor persiste todo progresso mais recente no job, mas limita eventos
   `job.progress` a no máximo 4/s por job; transições de estado nunca são
   descartadas.
