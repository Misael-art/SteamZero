# GameMode — leitura somente leitura — 2026-09-22

## Comando

```text
/usr/local/bin/steamzero desktop gamemode-status --json
```

## Estado observado no host

- `binaryState=present`: `gamemoderun` está disponível;
- `daemonState=unknown`: a consulta a `gamemoded` não foi conclusiva;
- `authorizationState=unknown`;
- `capabilityState=unknown` e `state=unknown`;
- `activityState=idle`;
- efeitos `governor`, `splitLock` e `ioprio`: `unknown`.

O plano administrativo retornado é apenas declarativo e informa
`executesHostChanges=false`; nenhum serviço, grupo, governor ou configuração
foi alterado. A saída não foi promovida a `ready` apenas pela presença do
binário.

## Canonical

O probe separa binário, daemon, autorização, atividade e efeitos, degrada
falhas de observação para `unknown` e publica remediação sem expor stdout,
argv, paths privados ou segredos. A suíte focada passou com **81 passed** e
45 testes não selecionados; o state home real permaneceu idêntico antes e
depois.
