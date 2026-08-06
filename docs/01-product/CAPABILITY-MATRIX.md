<!-- GERADO POR tools/capability_matrix.py — NÃO EDITE À MÃO. -->
<!-- Regrave com: python tools/capability_matrix.py --write -->

# CAPABILITY-MATRIX — o que o código declara, e o que ele recusa

Derivada dos manifestos empacotados, do roteamento de lifecycle e do catálogo de
contratos de UI. **Nada aqui é lido do host**: o documento é idêntico em qualquer
máquina, e o gate `--check` reprova quando o código muda sem regravá-lo.

Esta matriz responde "o produto consegue oferecer isto?", **não** "isto funciona".
Capacidade declarada é promessa do manifesto; execução real exige evidência de
host, que vive nos relatórios de certificação.

## Resumo

| dimensão | valor |
|---|---|
| adapters declarados | 16 |
| adapters instaláveis pelo lifecycle | 16 de 16 |
| plataformas declaradas | 36 |
| plataformas com bloqueio | 21 de 36 |
| cores libretro exigidos | 17 |
| adapters que entregam core | 0 |
| ações de UI publicadas | 116 |
| ações declaradas indisponíveis | 6 |

## Adapters e roteamento de lifecycle

Capacidade declarada no manifesto não implica execução verificada: a coluna
`instalável` é o que `lifecycle.route_for` aceita **antes** de tentar.

| adapter | kind | fonte | EOL | executor | instalável | capacidades declaradas | motivo da recusa |
|---|---|---|---|---|---|---|---|
| azahar | emulator | flatpak | não | flatpak | sim | 10 | — |
| cemu | emulator | flatpak | não | flatpak | sim | 10 | — |
| citron | emulator | appimage | não | engine | sim | 10 | — |
| dolphin | emulator | flatpak | não | flatpak | sim | 10 | — |
| duckstation | emulator | appimage | não | engine | sim | 10 | — |
| eden | emulator | appimage | não | engine | sim | 10 | — |
| flycast | emulator | flatpak | não | flatpak | sim | 10 | — |
| melonds | emulator | flatpak | não | flatpak | sim | 10 | — |
| pcsx2 | emulator | flatpak | não | flatpak | sim | 10 | — |
| ppsspp | emulator | flatpak | não | flatpak | sim | 10 | — |
| retroarch | emulator | flatpak | não | flatpak | sim | 10 | — |
| rpcs3 | emulator | flatpak | não | flatpak | sim | 10 | — |
| ryubing | emulator | appimage | não | engine | sim | 10 | — |
| sunshine | tool | native | não | engine | sim | 2 | — |
| xemu | emulator | flatpak | não | flatpak | sim | 10 | — |
| xenia-canary | emulator | appimage | não | engine | sim | 10 | — |

## Lifecycle por emulador e por ação

Uma linha por emulador `kind=emulator`, uma coluna por ação do contrato.
O gate reprova quando um emulador **ativo** não declara capacidade
obrigatória, fica sem executor ou mantém fonte EOL.

| emulador | suporte | executor | detect | status | install | update | verify | repair | uninstall | rollback/recovery | stop | open-config | EOL | motivo da recusa |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| azahar | ativo | flatpak | sim | sim | sim | sim | sim | sim | sim | sim | n/d | **não** | não | — |
| cemu | ativo | flatpak | sim | sim | sim | sim | sim | sim | sim | sim | n/d | **não** | não | — |
| citron | ativo | engine | sim | sim | sim | sim | sim | sim | sim | sim | sim | **não** | não | — |
| dolphin | ativo | flatpak | sim | sim | sim | sim | sim | sim | sim | sim | n/d | **não** | não | — |
| duckstation | ativo | engine | sim | sim | sim | sim | sim | sim | sim | sim | sim | **não** | não | — |
| eden | ativo | engine | sim | sim | sim | sim | sim | sim | sim | sim | sim | **não** | não | — |
| flycast | ativo | flatpak | sim | sim | sim | sim | sim | sim | sim | sim | n/d | **não** | não | — |
| melonds | ativo | flatpak | sim | sim | sim | sim | sim | sim | sim | sim | n/d | **não** | não | — |
| pcsx2 | ativo | flatpak | sim | sim | sim | sim | sim | sim | sim | sim | n/d | **não** | não | — |
| ppsspp | ativo | flatpak | sim | sim | sim | sim | sim | sim | sim | sim | n/d | **não** | não | — |
| retroarch | ativo | flatpak | sim | sim | sim | sim | sim | sim | sim | sim | n/d | **não** | não | — |
| rpcs3 | ativo | flatpak | sim | sim | sim | sim | sim | sim | sim | sim | n/d | **não** | não | — |
| ryubing | ativo | engine | sim | sim | sim | sim | sim | sim | sim | sim | sim | **não** | não | — |
| xemu | ativo | flatpak | sim | sim | sim | sim | sim | sim | sim | sim | n/d | **não** | não | — |
| xenia-canary | ativo | engine | sim | sim | sim | sim | sim | sim | sim | sim | sim | **não** | não | — |

**15 emuladores ativos** · obrigatórias: detect, status, install, update, verify, repair, uninstall · `open-config` declarado em **0 de 15**.

`open-config` não é obrigatório ainda porque nenhum manifesto declara o argv: emuladores não compartilham forma de abrir configuração, e inventar um produziria botão que abre a coisa errada. A lacuna fica contada aqui até que o argv de cada upstream seja verificado.

## Plataformas e bloqueios de jogabilidade

| plataforma | emulador primário | executor | core exigido | BIOS declarada | bloqueio |
|---|---|---|---|---|---|
| switch | eden | engine | — | — | nenhum |
| nintendo-handheld | retroarch | flatpak | mgba | — | core `mgba` sem instalador |
| nes-famicom | retroarch | flatpak | mesen | — | core `mesen` sem instalador |
| snes | retroarch | flatpak | snes9x | — | core `snes9x` sem instalador |
| mega-drive | retroarch | flatpak | genesis_plus_gx | — | core `genesis_plus_gx` sem instalador |
| arcade | retroarch | flatpak | fbneo | — | core `fbneo` sem instalador |
| playstation | duckstation | engine | — | — | nenhum |
| geforce-now | serviço cloud | browser | — | — | nenhum |
| xbox-cloud-gaming | serviço cloud | browser | — | — | nenhum |
| amazon-luna | serviço cloud | browser | — | — | nenhum |
| nintendo-console | dolphin | flatpak | — | — | nenhum |
| master-system | retroarch | flatpak | genesis_plus_gx | — | core `genesis_plus_gx` sem instalador |
| game-gear | retroarch | flatpak | genesis_plus_gx | — | core `genesis_plus_gx` sem instalador |
| pc-engine-turbografx | retroarch | flatpak | mednafen_pce | — | core `mednafen_pce` sem instalador |
| atari-classics | retroarch | flatpak | stella | — | core `stella` sem instalador |
| neo-geo-pocket | retroarch | flatpak | mednafen_ngp | — | core `mednafen_ngp` sem instalador |
| wonderswan | retroarch | flatpak | mednafen_wswan | — | core `mednafen_wswan` sem instalador |
| msx | retroarch | flatpak | bluemsx | — | core `bluemsx` sem instalador |
| zx-spectrum | retroarch | flatpak | fuse | — | core `fuse` sem instalador |
| commodore-64 | retroarch | flatpak | vice_x64 | — | core `vice_x64` sem instalador |
| amiga | retroarch | flatpak | puae | kick34005.A500, kick40068.A1200 | core `puae` sem instalador |
| colecovision | retroarch | flatpak | bluemsx | — | core `bluemsx` sem instalador |
| intellivision | retroarch | flatpak | freeintv | — | core `freeintv` sem instalador |
| virtual-boy | retroarch | flatpak | mednafen_vb | — | core `mednafen_vb` sem instalador |
| three-do | retroarch | flatpak | opera | panafz1.bin | core `opera` sem instalador |
| sega-cd-32x | retroarch | flatpak | genesis_plus_gx | bios_CD_E.bin, bios_CD_U.bin, bios_CD_J.bin | core `genesis_plus_gx` sem instalador |
| nintendo-64 | retroarch | flatpak | mupen64plus_next | — | core `mupen64plus_next` sem instalador |
| playstation-2 | pcsx2 | flatpak | — | — | nenhum |
| playstation-portable | ppsspp | flatpak | — | — | nenhum |
| dreamcast | flycast | flatpak | — | — | nenhum |
| nintendo-ds | melonds | flatpak | — | — | nenhum |
| nintendo-3ds | azahar | flatpak | — | — | nenhum |
| wii-u | cemu | flatpak | — | — | nenhum |
| playstation-3 | rpcs3 | flatpak | — | — | nenhum |
| xbox | xemu | flatpak | — | — | nenhum |
| xbox-360 | xenia-canary | engine | — | — | nenhum |

## Cores libretro exigidos

17 cores são exigidos pelos perfis de lançamento e 0 adapter(s) declaram `kind: core`. Enquanto esse número for zero, nenhuma plataforma que dependa de core é jogável pelo produto: o core precisa ser instalado por fora.

`bluemsx`, `fbneo`, `freeintv`, `fuse`, `genesis_plus_gx`, `mednafen_ngp`, `mednafen_pce`, `mednafen_vb`, `mednafen_wswan`, `mesen`, `mgba`, `mupen64plus_next`, `opera`, `puae`, `snes9x`, `stella`, `vice_x64`

## Ações de UI declaradas indisponíveis

A bridge publica estas ações com o motivo, em vez de escondê-las — a UI as
mostra desabilitadas com a causa. Ausência aqui não significa funcionamento
verificado, apenas que o contrato não se declara indisponível.

| ação | endpoint | aplicabilidade | motivo declarado |
|---|---|---|---|
| component.open-config | — | not-applicable | Nenhum emulador ativo possui argumento oficial comprovado para abrir diretamente a configuração; consulte a matriz e abra a UI principal. |
| component.rollback | — | not-applicable | Use o fluxo de revisão e confirmação de rollback do componente. |
| component.recover | — | not-applicable | Use Inspecionar recuperação, depois Revisar recovery e Confirmar recovery. |
| sync.status | — | not-applicable | A fila é somente leitura no snapshot atual; retry/cancel ainda não possuem rota da bridge. |
| profiles.history | — | not-applicable | A UI revisa diferenças antes de aplicar e oferece recovery, mas o store não publica uma linha do tempo de perfis pela bridge. |
| session.recovery | — | not-applicable | A recuperação de sessão pertence ao daemon e ainda não possui contrato Desktop. |
