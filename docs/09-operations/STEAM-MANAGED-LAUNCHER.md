# Launcher Steam gerenciado

## Contrato de uso

Nas propriedades do jogo na Steam, a Launch Option é:

```text
steamzero-launch --appid <APP_ID> -- %command%
```

O separador `--` é obrigatório. O launcher nunca usa shell, não reinterpreta metacaracteres
e não persiste a linha de comando nem o ambiente do jogo.

## Resolução de política

1. Perfil `game` para o AppID.
2. Perfil `portable` ou `dock`, conforme conectores DRM observados em modo read-only.
3. Perfil `global`.

Ausência de política bloqueia o lançamento gerenciado com erro explícito; não inicia o jogo
sem o perfil solicitado nem inventa estado aplicado.

## Composição allowlisted

- **Gamescope:** `-r <30|40|60>` e `-F fsr` somente para a opção Gamescope FSR.
- **Feral GameMode:** prefixo `gamemoderun`.
- **MangoHud:** prefixo `mangohud` fora de Gamescope; dentro dele exige MangoApp e usa
  `gamescope --mangoapp`, conforme a documentação oficial.
- **LSFG-VK:** `LSFG_LEGACY`, `LSFG_DLL_PATH`, `LSFG_MULTIPLIER`, `LSFG_FLOW_SCALE` e
  `LSFG_PERFORMANCE_MODE`; exige manifesto regular e `Lossless.dll` real na biblioteca.

Referências primárias: [Gamescope](https://github.com/ValveSoftware/gamescope),
[GameMode](https://github.com/FeralInteractive/gamemode),
[MangoHud](https://github.com/flightlessmango/MangoHud) e
[configuração LSFG-VK](https://github.com/PancakeTAS/lsfg-vk/wiki/Configuring-lsfg%E2%80%90vk).

FSR2 interno, TDP e clock manual da GPU não possuem aplicação genérica segura neste marco;
ficam em `deferredEffects` e não contam como observados.

## Estados e recuperação

| Estado | Significado |
|---|---|
| `desired` | política salva, sem jogo observado |
| `observed` | PID vivo, marcadores de ambiente válidos e digest atual |
| `stale` | sessão interrompida ou perfil alterado durante o jogo |
| `degraded` | falha no último spawn/lifecycle |

O launcher encaminha SIGTERM/SIGINT ao filho, aguarda seu encerramento e grava apenas
AppID, PID, digest, efeitos sem segredo, timestamps e exit code. Após SIGKILL do wrapper,
PID morto produz `recoveryRequired`; a recuperação marca a sessão como `interrupted`.

## Limite atual

O SteamZero fornece e exibe a Launch Option exata, mas ainda não altera automaticamente o
`localconfig.vdf`. Essa mutação exigirá Steam parada, parser VDF preservador, snapshot,
plano/confirmToken, verify e rollback byte-idêntico antes de ser habilitada.
