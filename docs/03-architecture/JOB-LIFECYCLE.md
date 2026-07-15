# JOB-LIFECYCLE — ciclo de vida de jobs

## Máquina de estados

```
created ─► queued ─► running ─► completed
              │         ├─► paused ─► running (resume)
              │         ├─► cancelling ─► cancelled (cancel seguro: só em pontos de segurança)
              │         └─► failed ─► (auto) rolling-back ─► rolled-back | rollback-failed
              └─► blocked (dependência/lock/rede/bateria) ─► queued
Após reboot/crash do daemon: running ─► interrupted ─► (recovery) queued|rolling-back
```

Estados terminais: `completed`, `cancelled`, `rolled-back`, `rollback-failed` (este exige intervenção e aparece como problema crítico no dashboard).

## Propriedades do job (persistidas no State Store)

`id (ULID)`, `type`, `params (validados por schema)`, `priority`, `state`, `progress {stage, current, total, unit, bytesPerSec}`, `operationId` (liga ao journal transacional), `correlationId`, `createdBy (ui|cli|qam|scheduler)`, `constraints {requiresNetwork, requiresAC, requiresStorage[], cpuLimit, ioLimit, forbiddenDuringGameplay}`, `checkpoints[]`, `result | error{code}`.

## Políticas

- **Fila e prioridade:** interativo (usuário esperando) > manutenção > background. Preempção só em pontos de segurança.
- **Pausa/retomada:** todo job longo declara pontos de segurança (fim de item/arquivo). Pausa = parar no próximo ponto; estado persistido (padrão do checkpoint/resume do PhaseZero Windows, generalizado).
- **Cancelamento:** cancel ≠ kill. Cancel executa a rotina de unwind da etapa corrente (ex.: apagar staging parcial) e nunca deixa estado intermediário ativado.
- **Recuperação pós-reboot:** na subida, o Job Manager varre jobs `running` → `interrupted`; se a transação subjacente não passou de `apply`, faz rollback automático; se passou de `activate`+`verify`, tenta completar o commit (roll-forward). Decisão registrada no journal.
- **Limites de recursos:** jobs background com `nice`/`ionice` (ou cgroup slice quando disponível); em bateria < limiar, jobs `requiresAC` ficam `blocked`.
- **Bloqueio durante jogo:** SessionManager em `running` bloqueia jobs marcados `forbiddenDuringGameplay` (conversões, scans pesados) — herdando a intenção do "pause during gameplay" do EmuDeck cloud sync, mas por política central.
- **Histórico:** jobs terminais retidos N dias (config), exportáveis; visíveis na UI de Jobs.

## Concorrência

- 1 job mutável por **recurso** (lock por recurso no núcleo: componente X, biblioteca da plataforma Y, store de saves do jogo Z).
- Locks são leases com heartbeat + dono (pid, jobId) — lock órfão expira e é registrado (§13.3 exige teste de lock abandonado).
- Jobs read-only (scan, status) são ilimitados, mas cedem I/O a interativos.
