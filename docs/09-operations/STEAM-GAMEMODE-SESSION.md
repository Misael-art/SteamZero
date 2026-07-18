# SteamZero Game Mode Session

`steamzero-gamemode-session` é uma sessão SDDM independente. Ela verifica Steam, Gamescope
e um launcher Plasma antes de iniciar. O argv do compositor é fechado:

```text
gamescope --steam -- steam -steamos3 -gamepadui
```

Ao sair, falhar ou receber um destino desconhecido, o Session Manager executa o fallback
Plasma disponível (`startkde-biglinux wayland`, `startplasma-wayland` ou X11). Três falhas
consecutivas nunca viram loop de login. `steamos-session-select` aceita apenas desktop,
plasma, steam, gamepadui, reboot e shutdown; o alvo fica no runtime XDG 0700 e a Steam é
encerrada sem shell.

O launcher recusa ser iniciado sobre um Desktop existente, salvo no modo de teste
explicitamente opt-in. A entrada instalada é **SteamZero Game Mode** e aponta apenas para a
release ativa em `/opt/steamzero/current`; nenhum caminho ou serviço PhaseZero é consultado.

## Ambiente observado

Antes de qualquer reconciliador ou mutação, o estado real pode ser auditado com:

```text
steamzero session environment --json
```

O snapshot combina DMI com presença do painel interno, sessão gráfica, bateria/AC, rede,
conectores DRM e volumes montados associados a `/dev/disk/by-uuid`. A leitura usa apenas
procfs/sysfs/mountinfo e links de dispositivo; não monta volumes, não aplica modos e não
altera a sessão. No Deck, `mmcblk` identifica o leitor microSD mesmo quando o kernel anuncia
`removable=0`.

O daemon reconcilia esse snapshot a cada cinco segundos. A migração v5 mantém somente o
último estado material e emite `session.environment` quando device, sessão, AC, rede,
displays ou volumes mudam. Percentual de bateria, espaço livre e timestamp são deliberadamente
ignorados pelo digest para evitar crescimento por polling. Nesta etapa o reconciliador
somente observa e registra; ele ainda não aplica modo nem executa recovery.

Retomadas são detectadas sem privilégio pela diferença entre `CLOCK_BOOTTIME`, que
avança durante o suspend, e `CLOCK_MONOTONIC`, que fica congelado. O evento persistente
`session.resume` habilita recuperação pós-resume. Flush e checkpoint antes de dormir
continuam condicionados ao hook systemd/logind da fronteira R3; o evento não inventa
uma garantia pré-suspend que o processo user-scoped ainda não possui.

## Boot direto

Uma sessão gráfica é escolhida pelo display manager, não pelo GRUB. A entrada
**SteamZero Game Mode** apenas acrescenta `steamzero.gamemode=1` ao kernel; o oneshot
`steamzero-gamemode-boot.service`, executado antes do display manager, valida a sessão e
publica uma seleção SDDM com `Relogin=false`. Sessão ausente remove o autologin gerenciado e
volta ao greeter. Steam/Gamescope ausente ou três falhas consecutivas entregam o controle ao
Plasma.

Ativação e remoção são explícitas, root-only e regeneram o GRUB:

```text
bigsudo /usr/local/libexec/steamzero-gamemode-boot enable --user USUARIO
/usr/local/libexec/steamzero-gamemode-boot status
bigsudo /usr/local/libexec/steamzero-gamemode-boot disable
```

O ativador deriva kernel, initramfs, UUID e subvolume do boot corrente, exige que os
artefatos existam, usa escrita atômica, preserva o `grub.cfg` anterior durante a transação e
recusa arquivos sem marcador de ownership. O marcador legado
`phasezero.steamos=1` é aceito somente para migração da entrada já existente; o runtime,
serviço e sessão selecionada são exclusivamente do SteamZero. O serviço legado é desativado
depois que a nova entrada e o fallback foram verificados.

O Gamescope upstream se descreve como compositor da sessão SteamOS e documenta o modo
embedded; a composição completa da sessão fora do SteamOS exige validação específica da
distribuição e do hardware. Fonte primária:
[ValveSoftware/gamescope](https://github.com/ValveSoftware/gamescope).
