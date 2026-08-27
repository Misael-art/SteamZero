# Drift de commit tornava emulador são inexecutável

Host Valve Jupiter, release ativa `2.0.0rc1-3b296a949316`, 2026-08-27.

Sem captura de tela: a correção não tem superfície gráfica entregue. A release
instalada segue com o mapeamento antigo, então nada do que este documento
descreve é observável na central hoje. Uma captura aqui seria decorativa.

## Como apareceu

O operador relatou: "retroarch está como reparar e vários outros emuladores
também não executaram".

## Medido no host

`steamzero component list` — 33 componentes:

| estado | quantidade |
|---|---|
| installed | 11 |
| missing | 20 |
| degraded | 2 (`retroarch`, `dolphin`) |

Detalhe publicado pelos dois degradados: `commit instalado X difere da fonte
fixada Y`. Commits conferidos:

| componente | instalado | fixado no manifesto |
|---|---|---|
| retroarch | `1f766799d9ff…` | `d8644a97df3d…` |
| dolphin | `1b150924d321…` | `377c3e63506e…` |

`flatpak info org.libretro.RetroArch` confirma **RetroArch 1.22.2 íntegro e
executável**. O host rodou `flatpak update`; os manifestos fixam commits
anteriores. Não há corrupção de artefato.

## Causa raiz

`FlatpakExecutor.status` mapeava **qualquer** divergência de commit para
`degraded`. `ComponentLifecycle.launch` recusa todo estado fora de
`{installed, outdated}` com `E-COMPONENT-DEGRADED`.

A taxonomia em `lifecycle.py` já distinguia os dois casos:

- `outdated` — "íntegro, porém a fonte fixada avançou"
- `degraded` — "artefato ou metadados não conferem"

O mapeamento contrariava a própria taxonomia do projeto. O gate estava correto.

Consequência para o usuário: uma divergência de contabilidade tornava
inutilizável um emulador que funcionava, e o único caminho oferecido na tela era
"reparar" — na prática, downgrade para o commit fixado.

## Defeito adicional, exposto pela correção

`status()` e `_persist()` duplicavam o mapeamento. Corrigir apenas `status()`
fez a store gravar `degraded` para um deployment que a observação já chamava de
`outdated`. O teste `test_scenario_14_rollback_is_auditable_and_preserves_configuration[flatpak]`
reprovou exatamente nessa divergência — a duplicação era a causa original de os
dois lados poderem discordar. Extraído `_deployment_state` como fonte única.

## O que NÃO foi provado

A correção está provada por teste, **não** por observação no artefato instalado.
Publicar e instalar release exige autorização explícita, não concedida nesta
sessão. Até lá, `retroarch` e `dolphin` continuam `degraded` e sem launch no
host.

## Preservado de propósito

Drift de `manifestHash` no executor engine continua `degraded`: ali os metadados
realmente não conferem. `outdated` segue em `_REPAIRABLE_STATES`, então a ação
de reparo permanece disponível para quem quiser convergir ao pin — o que sai é
o bloqueio, não a opção.
