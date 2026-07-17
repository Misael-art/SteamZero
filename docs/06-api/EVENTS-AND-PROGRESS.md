# EVENTS-AND-PROGRESS — eventos e progresso

## Canal

- API: notificações JSON-RPC após `events.subscribe {jobIds?|kinds?|entities?}`.
- CLI: `--follow` emite NDJSON (um evento por linha, schema `event-v1`).
- UI que reconecta: re-hidrata do State Store (`job.get` + `event_log` desde `seq`) — eventos têm `seq` monotônico por job; sem perda ao reconectar.

## Tipos

| kind | Conteúdo | Frequência |
|---|---|---|
| `job.state` | transições da máquina de JOB-LIFECYCLE | por transição |
| `session.state` | lifecycle canônico do jogo (`launching`…`failed`) | por transição |
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
