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
PID morto produz `recoveryRequired`; a recuperação encerra a sessão como `failed` com
o código estável `E-SESSION-INTERRUPTED`.

Desde o schema v4, `game_session` é a fonte de verdade: o mesmo vocabulário
`idle→launching→running→…→closed|failed` serve o domínio F-SD-01 e o launcher real.
Um índice parcial por owner recusa uma segunda sessão ativa de forma atômica. Cada
transição e seu evento `session.state` são gravados juntos; comando e ambiente nunca são
persistidos. Estados M11 antigos (`active/exited/interrupted`) continuam legíveis durante
a migração, mas novos launches não reutilizam o perfil legado.

Diagnóstico e recovery também estão disponíveis sem UI:

```text
steamzero session status --game-id <APP_ID> --json
steamzero session recover --game-id <APP_ID>
```

## Configuração automática e recuperação

A tela Steam pode registrar a linha no `localconfig.vdf` do jogo selecionado. A ação é
separada do salvamento do perfil e sempre passa por uma revisão explícita, especialmente
quando já existe uma Launch Option que será substituída.

As proteções são obrigatórias:

- a Steam precisa estar completamente fechada no planejamento, no apply e no rollback;
- arquivos, diretórios de conta e `config` não podem ser symlinks, e o alvo precisa
  permanecer contido na conta observada;
- com múltiplas contas, somente `MostRecent=1` de `loginusers.vdf` resolve a conta ativa;
- o parser aceita o formato KeyValues citado e comentários, rejeita estrutura ambígua e
  altera somente `apps/<appid>/LaunchOptions`, sem reserializar o restante do arquivo;
- o arquivo possui limite de 16 MiB; mudança concorrente invalida o plano;
- plano, `confirmToken`, fingerprint, destino exato e conteúdo esperado são revalidados;
- o apply verifica a folha gravada e o journal fornece rollback **G-FULL** byte-idêntico.

O botão **Desfazer configuração** restaura a última operação da sessão. Se a aplicação
for interrompida, o recovery transacional geral continua sendo a fonte de verdade.

## Limite operacional atual

O fluxo está coberto por arquivos Steam sintéticos e o host real foi consultado somente
em modo read-only. O ciclo físico configurar → abrir Steam → lançar jogo → fechar →
desfazer permanece pendente para uma bancada descartável com snapshot.

Manutenção de cache, pacote de mídia e a sessão Game Mode independente são descritos em
`STEAM-MAINTENANCE-AND-MEDIA.md` e `STEAM-GAMEMODE-SESSION.md`. Eles não ampliam o launcher
com acesso a GRUB, compatdata ou shell.
