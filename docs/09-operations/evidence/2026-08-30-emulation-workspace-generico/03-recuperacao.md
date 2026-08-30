# Recuperação — rollback disponível

Release ativa após o update: `2.0.0rc1-af49819e1326` (sourceCommit
`af49819e1326af014b8e93102baea522ce52c292`, wheel SHA-256
`58afe75a69403437eed90aee2d1ffc73847fd801525a2612482baf30149a4bd0`).

## Rollback preservado

- Release anterior `2.0.0rc1-a897f8ffcfed` permanece presente em
  `/opt/steamzero/releases/`, imutável, com o marcador de ownership SteamZero.
  O `install_host.py rollback --release 2.0.0rc1-a897f8ffcfed` é o caminho
  governado de retorno.
- O instalador valida o alvo de rollback (`_require_rollback`) antes de
  ativar; a ativação registra `previousRelease` no manifest (schemaVersion 4) e
  o daemon confirma a release ativa antes de declarar convergência.

## Verificação de convergência pós-instalação

- `doctor --json`: `runtime.provenance` = `2.0.0rc1-af49819e1326`,
  `service.generation` = `daemon na release ativada`, `state.db.integrity` =
  `ok`, `recovery.pending` = `0`, `pendingOperations` = `0`, `blockers` = `[]`.
- `service` e `socket`: `active`.
- Convergência do daemon: `first` (1 tentativa) e `idempotent` (0 tentativas)
  ambos `converged`, PID 2940873, `sourceDirty: false`.

## Estados `degraded` pré-existentes (não introduzidos por esta release)

- `staging.orphan: 1` e `backup.orphan: 1` — árvores órfãs de operações
  anteriores, sem operação no banco.
- `boot.direct: unknown` — "Sem permissão para inspecionar a configuração de
  boot" (`permissionDenied`); observação read-only do Game Mode, não regressão.
- `qml.exitCode 124` no smoke — janela QML offscreen com windowSeconds=5;
  estado `started`, não-fatal.

Estes três já existiam antes do update e são estados observados do host, não
defeito introduzido por `2.0.0rc1-af49819e1326`.
