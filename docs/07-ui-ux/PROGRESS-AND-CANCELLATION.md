# PROGRESS-AND-CANCELLATION — progresso e cancelamento (§12.7)

## Apresentação por duração

| Duração esperada | Padrão |
|---|---|
| <1s | resultado direto |
| 1–10s | indicador inline (etapa + spinner) |
| >10s | job com card de progresso completo, cancelável/pausável |

## Card de job (campos obrigatórios quando aplicáveis)

Etapa do pipeline real · barra (só com total real — P11) · item atual (arquivo) · velocidade · espaço usado/necessário · concluídos/pendentes · avisos acumulados · botões Pausar/Retomar/Cancelar.

## Cancelamento

- Sempre disponível; sempre **seguro** (unwind da etapa, staging descartado, nada meio-ativado — JOB-LIFECYCLE).
- Feedback em duas fases: "cancelando com segurança…" → "cancelado" (com o que foi/não foi feito).
- Cancelar ≠ reverter: se etapas já commitadas existem (saga), a UI oferece explicitamente "desfazer o que já foi feito" como operação própria.

## Pausa

- Automática (bateria, jogo iniciado, rede caiu) com causa exibida; manual a qualquer momento; retomada preserva progresso (checkpoints).

## Regras anti-mentira

1. Sem porcentagem inventada; sem barra "quase cheia parada".
2. ETA só quando a taxa é estável (janela móvel); senão omitir.
3. Conclusão só após `verify` — a barra não "termina" no fim do download (o pipeline continua e o card mostra as etapas restantes).
