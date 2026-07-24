# FEAT-PLAYTIME-V1 — playtime, recentes e continuar jogando

## Fonte de verdade

`game_session` continua sendo a única fonte de lifecycle. A migração v13
acrescenta `played_seconds` e `duration_source`; não existe contador paralelo em
QML, no launcher ou em arquivo de configuração.

Origens de duração:

| Valor | Significado |
|---|---|
| `observed-monotonic` | medido no processo que acompanhou a sessão |
| `recovered-wall-clock` | aproximação transparente durante recovery pós-crash |
| `legacy-wall-clock` | backfill v12 por `finished_at - started_at` |
| `unavailable` | duração ainda não observada |

O Session Manager acumula somente intervalos `running`, excluindo suspensão. O
wrapper Steam e o watcher de emulação gravam o total ao chegar a
`closed|failed`. Nenhum timestamp de parede é apresentado como medição
monotônica.

## Read model

`feat-playtime-v1` agrega por `gameId`:

- segundos e quantidade de sessões;
- última sessão, estado e origem da duração;
- ordenação recente estável e cursor keyset opaco;
- origem segura do launcher (`steam`, `emulation` ou `unknown`);
- ação de continuar, recuperar ou explicar indisponibilidade.

Sessão legada sem origem nunca ganha botão executável. PID não aparece no
contrato e, isoladamente, não prova que o jogo continua em execução.

## Sessões interrompidas

Uma sessão Steam ativa só vira “interrompida” no Desktop quando o launcher
confirma `recoveryRequired` com identidade de processo ausente ou divergente. O
primeiro gesto executa apenas recovery; após o registro chegar a `failed` com
`E-SESSION-INTERRUPTED`, a atualização oferece “Continuar”. Emulação acompanhada
por watcher registra falha interrompida se `waitpid` deixa de observar o filho.

## Superfícies

- CLI: `playtime list [--limit N --cursor C]` e
  `playtime show --game-id ID`;
- JSON-RPC: `playtime.list` e `playtime.show`;
- Desktop: `dashboard.playtime`, ações allowlisted de continuar e recovery;
- Home QML: até quatro itens recentes, tempo total e estado textual.

O contrato é read-only. Lançamento e recovery permanecem nos serviços de
emulação e sessão Steam existentes.
