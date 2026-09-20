# Validação de dumps reais — 2026-09-19/20

## Escopo e baseline

Esta sessão foi executada na release efetivamente ativa `2.0.0rc1-c3b14a040b7c`, sem instalação, rollback ou alteração manual do host. A árvore original `/home/misael/emulation/roms/` permaneceu somente leitura; nenhum arquivo foi extraído, movido, apagado ou sobrescrito.

Comando de inventário somente leitura:

```text
find /home/misael/emulation/roms ...
```

O scanner canônico foi executado pelo controlador da release ativa (`library.scan`). Resultado persistido pelo próprio SteamZero:

```text
jobId=01M2YC2CFA9X8AZH1HAV127ERQ
status=scanned games=1156 filesFound=15706 updates=20 dlcs=144 unidentified=0 errors=0
incompatible=1350 archive-platform-unknown=1316 archive-unclassified=34
ignored=13036 unsupported-format=13036 roots=2
```

Distribuição observada: `nes-famicom=258`, `nintendo-3ds=20`, `master-system=204`, `nintendo-handheld=296`, `snes=109`, `mega-drive=81`, `sega-saturn=18`, `game-gear=41`, `playstation=53`, `x68000=14`, `playstation-2=6`, `dreamcast=5`, `nintendo-ds=14`, `zx-spectrum=1`, `switch=15`, `xbox-360=1`, `nintendo-console=2`, `wii-u=2`, `xbox=1`, `playstation-vita=5`, `playstation-4=2`, `playstation-3=1`, `neo-geo-cd=1`, `amiga=5`, `three-do=1`.

Archives permaneceram em `unsupported-content`/`needs-review` quando não houve associação segura. Não houve extração ou conversão; os 1.350 itens incompatíveis são um próximo subitem de revisão, não um motivo para interromper os sistemas já classificáveis.

## Sistemas fechados nesta etapa

| Sistema | Emulador/core | Conteúdo | Instalação/verify | Gameplay | Retorno |
|---|---|---|---|---|---|
| 3DO | RetroArch / `opera` (`libretro-opera`) | `/home/misael/emulation/roms/3do/Yu Yu Hakusho (Japan).chd`, SHA-256 `9b0cd9f84e389ce815472813b35ab62a5ec6d71ed81e7a42a3708afa278ed7d9` | `installed`, `1.22.2`, `verified=true` | `installed-not-played`; `panafz1.bin` ausente | Pendente de BIOS legítima do operador (`HARD-EXTERNAL-SUBITEM`) |
| Famicom/NES | RetroArch / `mesen` (`libretro-mesen`) | `/home/misael/emulation/roms/famicom/AV Bishoujo Senshi Girl Fighting (Bootleg).nes`, game-id `10388314f46fea7a3ab66e3d`, SHA-256 `e19ba32210de5abb6148708612b48bacac691b80b0b418b484118e14fd750b0f` | `installed`, `1.22.2`, `verified=true` | `gameplay-proven`: launch real iniciou PID 254019 e mostrou a partida | `listPeripherals`, `pause` e `resume` aceitos; Alt+F4 encerrou o processo e não restou sessão ativa |
| Master System | RetroArch / `genesis_plus_gx` (`libretro-genesis-plus-gx`) | `/home/misael/emulation/roms/mastersystem/1969 (Homebrew) (SMS).sms`, game-id `ae18c7e53583298461a0edea`, SHA-256 `6e4a6d9a2e8b68d071e0d3d7f77f56ca9967073bc6a1f8b66119db0828025e32` | `installed`, `1.22.2`, `verified=true` | `gameplay-proven`: launch real iniciou PID 489473 e mostrou a partida | `listPeripherals`, `pause` e `resume` aceitos; Alt+F4 encerrou o processo e não restou sessão ativa |
| Dreamcast | Flycast primário (`flycast`); RetroArch/`flycast` fallback | `/home/misael/emulation/roms/dreamcast/Ikaruga (Japan).chd`, game-id `0a8cf6f98371340cd0af6ea4`, SHA-256 `f66b6d83c6003dff2a104de2b169b3d3e6e5f012c2c725fc203b141765948b07` | `installed`, commit Flatpak `5bb79aad...`, `verified=true` | `installed-not-played`: boot real em Flycast e tela inicial; entrada não alcançou a janela para iniciar a partida | `pause`/`resume` aceitos; `listPeripherals` recusado pelo adapter; encerramento e lifecycle sem sessão ativa |
| Nintendo 3DS | Azahar (`azahar`) | `/home/misael/emulation/roms/n3ds/Dragon Ball Z - Extreme Butoden (USA).3ds`, game-id `41d513d86c8925e67afd0af6`, 512 MiB | `installed`, commit Flatpak `fd0b3050...`, `verified=true` | `installed-not-played`: boot real e tela do jogo/SAVE observados; entrada interativa não foi comprovada | `pause`/`resume` aceitos; `listPeripherals` recusado; SIGTERM governado ao grupo do PID encerrou e deixou lifecycle vazio |
| PlayStation 2 | PCSX2 primário (`pcsx2`); RetroArch/`pcsx2` fallback | `/home/misael/emulation/roms/ps2/Black (USA) (Translated PtBr).chd`, game-id `7e55ff7c9e416c915fe24acf`, 1,026,426,508 bytes | `installed`, commit Flatpak `31307c3e...`, `verified=true` | `installed-not-played`: a release ativa passou `--fullscreen`, rejeitado pelo PCSX2 (`Unknown parameter`); correção depende de handoff no arquivo compartilhado | grupo PS2 encerrado e lifecycle vazio; repetir fisicamente somente após integração/release governada |
| PlayStation 3 | RPCS3 (`rpcs3`) | `/home/misael/emulation/roms/ps3/Ratchet & Clank - A Crack in Time (Europe) (En,Fr,De,Es,It,Nl).iso`, game-id `d020a6e215c4af8dd862b978`, 24,772,083,712 bytes | `installed`, commit Flatpak `27d554ca...`, `verified=true` | `missing-runtime`: RPCS3 abriu a tela inicial exigindo firmware do PlayStation 3; não houve gameplay | grupo RPCS3 encerrado por SIGTERM no PGID do launch e lifecycle vazio; requer firmware legítimo do operador (`HARD-EXTERNAL-SUBITEM`) |
| GameCube | Dolphin (`dolphin`) | `/home/misael/emulation/roms/gc/Legend of Zelda, The - Twilight Princess (USA).iso`, game-id `487f4ba69cad1a5bbc9c7b4c`, 1,459,978,240 bytes | `installed`, commit Flatpak `377c3e63...`, `verified=true` | `installed-not-played`: tela de segurança e sequência de abertura renderizadas; entrada interativa não foi comprovada | grupo Dolphin encerrado por SIGTERM no PGID do launch e lifecycle vazio; `listPeripherals` não estava disponível no socket após o processo gráfico iniciar |
| Xbox | xemu (`xemu`) | `/home/misael/emulation/roms/xbox/Outrun 2006 Coast 2 Coast - [Pal Multi 5] Xbox.iso`, game-id `34975ae97b0069663218efea`, 870,580,224 bytes | `installed`, commit Flatpak `2f8b8889...`, `verified=true` | `missing-runtime`: xemu abriu “Configure machine settings to get started”; o ISO não alcançou boot | grupo xemu encerrado por SIGTERM no PGID do launch e lifecycle vazio; configuração/firmware legítimos da máquina permanecem `HARD-EXTERNAL-SUBITEM` |
| Wii | Dolphin (`dolphin`) | `/home/misael/emulation/roms/wii/Tatsunoko vs. Capcom - Ultimate All-Stars (Europe).rvz`, game-id `992a9f0bbc72fd95ca9667b3`, 1,503,399,964 bytes | `installed`, commit Flatpak `377c3e63...`, `verified=true` | `needs-review`: aviso Wii Remote renderizado; ao avançar, o jogo recusou o arranjo de controles (“You cannot use other Controllers with a Nintendo GameCube Controller connected to Controller Socket 1”), sem gameplay | grupo Dolphin encerrado por SIGTERM no PGID do launch e lifecycle vazio; configuração de controles/periférico é `HARD-EXTERNAL-SUBITEM` |
| Wii U | Cemu (`cemu`) | `/home/misael/emulation/roms/wiiu/Nano Assault Neo (US).wua`, game-id `25e7f2c23311057f22000a2d`, 63,042,182 bytes | `installed`, commit Flatpak `cbadbaba...`, `verified=true` | `installed-not-played`: título real do jogo e tela de seleção de lutador foram visíveis, mas não houve prova de partida interativa | grupo Cemu encerrado por SIGTERM no PGID do launch e lifecycle vazio; controle respondeu apenas com recusa controlada `AURA-SESSION-CONTROL-REQUEST-002` |
| Nintendo Switch | Eden primário (`eden`), Citron/Ryubing fallback | `/home/misael/emulation/roms/switch/Nintendo World Championships NES Edition [0100AD10185F8000][v0].nsp`, game-id `4ea1c08e1db356ae5989c7a2`, 322,257,168 bytes | `installed`, Eden `0.2.1-steamdeck`, Citron/Ryubing verificados | `installed-not-played`: NSP abriu o título/menu real; controle retornou recusa de requisição e não houve gameplay interativo | grupo Eden encerrado por SIGTERM no PGID do launch e lifecycle vazio; nenhum runtime fallback foi necessário |
| Super Nintendo (SNES) | RetroArch / `snes9x` (`libretro-snes9x`) | `/home/misael/emulation/roms/snes/Chrono Trigger (USA).zip`, game-id `3a2da000bdeaceb29abe6f42`, 3,017,740 bytes | `installed`, `1.22.2`, `verified=true` | `gameplay-proven` visual: a tela interna “Battle Mode / Active / Wait” foi renderizada; o contrato de controle devolveu recusa controlada | grupo RetroArch encerrado por SIGTERM no PGID do launch e lifecycle vazio |
| Game Boy | RetroArch / `mgba` (`libretro-mgba`) | `/home/misael/emulation/roms/gb/Metroid II - Return of Samus (World) (Translated PtBr).gb`, game-id `cc403fee83e8a600bf868845`, 1,048,576 bytes | `installed`, `1.22.2`, `verified=true` | `installed-not-played`: tela real de título renderizada; avanço e controle interativo não foram comprovados | grupo RetroArch encerrado por SIGTERM no PGID do launch e lifecycle vazio; pedidos de controle receberam recusa controlada |

O conteúdo Famicom é um dump real presente no host; a proveniência legal não foi inferida pelo scanner e não deve ser promovida a `verified-hw` sem a confirmação do operador.

## Evidência física

- [03-gameplay-famicom.png](/mnt/sdcard/Projects/Port_Steam-emulation-validation/docs/09-operations/evidence/2026-09-19-real-dump-inventory/03-gameplay-famicom.png): janela RetroArch/Mesen visível com a partida carregada.
- [04-recovery-famicom.png](/mnt/sdcard/Projects/Port_Steam-emulation-validation/docs/09-operations/evidence/2026-09-19-real-dump-inventory/04-recovery-famicom.png): janela do emulador encerrada; a consulta ao lifecycle retornou lista de sessões ativas vazia.
- [05-gameplay-mastersystem.png](/mnt/sdcard/Projects/Port_Steam-emulation-validation/docs/09-operations/evidence/2026-09-19-real-dump-inventory/05-gameplay-mastersystem.png): janela RetroArch/Genesis Plus GX visível com a partida carregada.
- [06-recovery-mastersystem.png](/mnt/sdcard/Projects/Port_Steam-emulation-validation/docs/09-operations/evidence/2026-09-19-real-dump-inventory/06-recovery-mastersystem.png): janela do emulador encerrada; a consulta ao lifecycle retornou lista de sessões ativas vazia.
- [07-gameplay-dreamcast.png](/mnt/sdcard/Projects/Port_Steam-emulation-validation/docs/09-operations/evidence/2026-09-19-real-dump-inventory/07-gameplay-dreamcast.png): boot Flycast real de Ikaruga; não é declarado como gameplay.
- [10-recovery-dreamcast.png](/mnt/sdcard/Projects/Port_Steam-emulation-validation/docs/09-operations/evidence/2026-09-19-real-dump-inventory/10-recovery-dreamcast.png): Flycast encerrado e lifecycle vazio.
- [11-gameplay-3ds.png](/mnt/sdcard/Projects/Port_Steam-emulation-validation/docs/09-operations/evidence/2026-09-19-real-dump-inventory/11-gameplay-3ds.png): boot Azahar real e tela do jogo; não é declarado como gameplay interativo.
- [12-recovery-3ds.png](/mnt/sdcard/Projects/Port_Steam-emulation-validation/docs/09-operations/evidence/2026-09-19-real-dump-inventory/12-recovery-3ds.png): Azahar encerrado por SIGTERM no grupo identificado e lifecycle vazio.
- [13-gameplay-ps2.png](/mnt/sdcard/Projects/Port_Steam-emulation-validation/docs/09-operations/evidence/2026-09-19-real-dump-inventory/13-gameplay-ps2.png): erro controlado da release ativa (`Unknown parameter: "fullscreen"`), sem promoção a gameplay.
- [14-recovery-ps2.png](/mnt/sdcard/Projects/Port_Steam-emulation-validation/docs/09-operations/evidence/2026-09-19-real-dump-inventory/14-recovery-ps2.png): grupo PCSX2 encerrado e lifecycle vazio.
- [15-gameplay-ps3.png](/mnt/sdcard/Projects/Port_Steam-emulation-validation/docs/09-operations/evidence/2026-09-19-real-dump-inventory/15-gameplay-ps3.png): RPCS3 visível com o dump ISO aberto e a tela controlada de exigência de firmware; não é declarado como gameplay.
- [16-recovery-ps3.png](/mnt/sdcard/Projects/Port_Steam-emulation-validation/docs/09-operations/evidence/2026-09-19-real-dump-inventory/16-recovery-ps3.png): grupo RPCS3 encerrado e lifecycle vazio.
- [17-gameplay-gamecube.png](/mnt/sdcard/Projects/Port_Steam-emulation-validation/docs/09-operations/evidence/2026-09-19-real-dump-inventory/17-gameplay-gamecube.png): Dolphin visível na tela real de saúde e segurança do GameCube.
- [18-gameplay-gamecube.png](/mnt/sdcard/Projects/Port_Steam-emulation-validation/docs/09-operations/evidence/2026-09-19-real-dump-inventory/18-gameplay-gamecube.png): sequência de abertura real de Twilight Princess renderizada; não é declarada como gameplay interativo.
- [19-recovery-gamecube.png](/mnt/sdcard/Projects/Port_Steam-emulation-validation/docs/09-operations/evidence/2026-09-19-real-dump-inventory/19-recovery-gamecube.png): grupo Dolphin encerrado e lifecycle vazio.
- [20-gameplay-xbox.png](/mnt/sdcard/Projects/Port_Steam-emulation-validation/docs/09-operations/evidence/2026-09-19-real-dump-inventory/20-gameplay-xbox.png): xemu visível na tela controlada de configuração de máquina; não é declarado como boot/gameplay.
- [21-recovery-xbox.png](/mnt/sdcard/Projects/Port_Steam-emulation-validation/docs/09-operations/evidence/2026-09-19-real-dump-inventory/21-recovery-xbox.png): grupo xemu encerrado e lifecycle vazio.
- [22-gameplay-wii.png](/mnt/sdcard/Projects/Port_Steam-emulation-validation/docs/09-operations/evidence/2026-09-19-real-dump-inventory/22-gameplay-wii.png): Dolphin visível no aviso real de segurança do Wii Remote.
- [23-gameplay-wii.png](/mnt/sdcard/Projects/Port_Steam-emulation-validation/docs/09-operations/evidence/2026-09-19-real-dump-inventory/23-gameplay-wii.png): erro controlado de configuração de controles do Wii; não é declarado como gameplay.
- [24-recovery-wii.png](/mnt/sdcard/Projects/Port_Steam-emulation-validation/docs/09-operations/evidence/2026-09-19-real-dump-inventory/24-recovery-wii.png): grupo Dolphin encerrado e lifecycle vazio.
- [25-gameplay-wiiu.png](/mnt/sdcard/Projects/Port_Steam-emulation-validation/docs/09-operations/evidence/2026-09-19-real-dump-inventory/25-gameplay-wiiu.png): Cemu visível com o título real de Nano Assault Neo.
- [26-gameplay-wiiu.png](/mnt/sdcard/Projects/Port_Steam-emulation-validation/docs/09-operations/evidence/2026-09-19-real-dump-inventory/26-gameplay-wiiu.png): tela real de seleção após a tentativa de avanço; não é declarada como gameplay interativo.
- [27-recovery-wiiu.png](/mnt/sdcard/Projects/Port_Steam-emulation-validation/docs/09-operations/evidence/2026-09-19-real-dump-inventory/27-recovery-wiiu.png): grupo Cemu encerrado e lifecycle vazio.
- [28-gameplay-switch.png](/mnt/sdcard/Projects/Port_Steam-emulation-validation/docs/09-operations/evidence/2026-09-19-real-dump-inventory/28-gameplay-switch.png): Eden visível no título/menu real de Nintendo World Championships NES Edition.
- [30-recovery-switch.png](/mnt/sdcard/Projects/Port_Steam-emulation-validation/docs/09-operations/evidence/2026-09-19-real-dump-inventory/30-recovery-switch.png): grupo Eden encerrado e lifecycle vazio.
- [31-gameplay-snes.png](/mnt/sdcard/Projects/Port_Steam-emulation-validation/docs/09-operations/evidence/2026-09-19-real-dump-inventory/31-gameplay-snes.png): RetroArch/Snes9x visível em tela interna real de Chrono Trigger.
- [32-recovery-snes.png](/mnt/sdcard/Projects/Port_Steam-emulation-validation/docs/09-operations/evidence/2026-09-19-real-dump-inventory/32-recovery-snes.png): grupo RetroArch encerrado e lifecycle vazio.
- [33-gameplay-gameboy.png](/mnt/sdcard/Projects/Port_Steam-emulation-validation/docs/09-operations/evidence/2026-09-19-real-dump-inventory/33-gameplay-gameboy.png): RetroArch/mGBA visível na tela real de título de Metroid II.
- [34-gameplay-gameboy.png](/mnt/sdcard/Projects/Port_Steam-emulation-validation/docs/09-operations/evidence/2026-09-19-real-dump-inventory/34-gameplay-gameboy.png): tentativa de avanço permaneceu na tela de título; não é declarada como gameplay.
- [35-recovery-gameboy.png](/mnt/sdcard/Projects/Port_Steam-emulation-validation/docs/09-operations/evidence/2026-09-19-real-dump-inventory/35-recovery-gameboy.png): grupo RetroArch encerrado e lifecycle vazio.

A captura cobre o resultado visual real e a recuperação do jogo. O retorno ao AURA Launcher não foi declarado: a sessão foi iniciada no desktop disponível desta validação, portanto a prova de foco do Launcher permanece separada.

## Próxima ação segura

Registrar agora PS4/PS5 como `unsupported-content`/`needs-review` somente em leitura: as pastas têm metadata e artefatos `.rar`/`.exfat`, mas os manifestos ativos aceitam `pkg`/`elf`/`bin` e não há dump lançável. Nenhuma extração é permitida; a próxima frente independente pode seguir para outro sistema com formato/runtime suportados. `HARD-EXTERNAL-SUBITEM` continua restrito a runtime/BIOS/entrada física quando aplicável e à confirmação de proveniência legal.
