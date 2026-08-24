# Matriz dos 198 diretórios do acervo real

Data: 2026-08-24  
Raiz: `/home/misael/emulation/roms`  
Medição **somente leitura**, sem abrir estado e sem tocar nas ROMs do usuário.  
Ferramenta: `PlatformDirectoryInventory.from_registry(PlatformRegistry.bundled())`.

## Totais

| Métrica | Valor |
|---|---|
| Diretórios inventariados | 198 |
| Com plataforma reconhecida (`matched`) | 59 |
| Sem plataforma reconhecida (`unmatched`) | 138 |
| Excluídos por serem diretórios de apoio | 1 |
| Diretórios que realmente contêm jogos | 11 |
| Jogos detectados | 375 |
| Jogos que a amostragem selecionaria | 75 |
| Symlinks pulados | 61 |

## O que estes números dizem

1. **O acervo tem 375 jogos, concentrados em 11 diretórios.** Os outros 187 estão
   vazios ou não têm plataforma reconhecida. "Cobrir 198 diretórios" não significa
   198 bibliotecas: significa varrer os 198 e não perder nenhum dos 375 jogos.
2. **138 diretórios não têm manifesto de plataforma.** O projeto empacota 37
   manifestos e o acervo segue a nomenclatura do ES-DE, bem mais larga. Nenhum jogo
   foi encontrado neles nesta medição, mas um jogo colocado ali hoje ficaria invisível.
3. **A amostragem do caminho de fallback reduziria 375 jogos a 75.**
   `max_games_per_platform=10` serve a um relatório de inventário, não a uma biblioteca.
4. **61 symlinks foram pulados**, o que é o comportamento correto: symlink não vira jogo.

## Diretórios com jogos

| Diretório | Plataforma | Jogos | Amostra |
|---|---|---|---|
| `switch` | switch | 178 | 10 |
| `mastersystem` | master-system | 51 | 10 |
| `psx` | playstation | 49 | 10 |
| `famicom` | nes-famicom | 33 | 10 |
| `gb` | nintendo-handheld | 30 | 10 |
| `n3ds` | nintendo-3ds | 19 | 10 |
| `ps2` | playstation-2 | 6 | 6 |
| `dreamcast` | dreamcast | 5 | 5 |
| `wiiu` | wii-u | 2 | 2 |
| `ps3` | playstation-3 | 1 | 1 |
| `wii` | nintendo-console | 1 | 1 |

## Diretórios com plataforma reconhecida e sem jogos (48)

`3do`, `amiga`, `amiga1200`, `amiga600`, `amigacd32`, `arcade`, `atari2600`, `atari5200`, `atari7800`, `atari800`, `atarijaguar`, `atarilynx`, `c64`, `colecovision`, `cps`, `cps1`, `cps2`, `cps3`, `gamegear`, `gba`, `gbc`, `genesis`, `intellivision`, `mame`, `megadrive`, `msx`, `msx2`, `n64`, `nds`, `neogeo`, `nes`, `ngp`, `ngpc`, `pcengine`, `pcenginecd`, `psp`, `sega32x`, `segacd`, `sfc`, `snes`, `tg-cd`, `tg16`, `virtualboy`, `wonderswan`, `wonderswancolor`, `xbox`, `xbox360`, `zxspectrum`

## Diretórios sem plataforma reconhecida (138)

Estes são o trabalho restante do item: cada um precisa de manifesto ou de uma
decisão explícita de que não será suportado.

`adam`, `ags`, `amstradcpc`, `android`, `apple2`, `apple2gs`, `arcadia`, `archimedes`, `arduboy`, `astrocde`, `atarijaguarcd`, `atarist`, `atarixe`, `atomiswave`, `bbcmicro`, `c16`, `cavestory`, `cdimono1`, `cdtv`, `chailove`, `channelf`, `cloud`, `coco`, `consolearcade`, `crvision`, `daphne`, `desktop`, `doom`, `dos`, `dragon32`, `easyrpg`, `electron`, `emulators`, `epic`, `fba`, `fbneo`, `fds`, `flash`, `fm7`, `fmtowns`, `gamate`, `gameandwatch`, `gamecom`, `gc`, `generic-applications`, `genesiswide`, `gmaster`, `gx4000`, `j2me`, `kodi`, `laserdisc`, `lcdgames`, `lowresnx`, `lutris`, `lutro`, `macintosh`, `mame-advmame`, `mame-mame4all`, `mark3`, `megacd`, `megacdjp`, `megadrivejp`, `megaduck`, `mess`, `model2`, `model3`, `moonlight`, `moto`, `msx1`, `msxturbor`, `mugen`, `multivision`, `n64dd`, `naomi`, `naomi2`, `naomigd`, `neogeocd`, `neogeocdjp`, `odyssey2`, `openbor`, `oric`, `palm`, `pc`, `pc88`, `pc98`, `pcfx`, `pico8`, `plus4`, `pokemini`, `portmaster`, `ports`, `primehack`, `primehacks`, `ps4`, `psvita`, `pv1000`, `quake`, `remoteplay`, `samcoupe`, `satellaview`, `saturn`, `saturnjp`, `scummvm`, `scv`, `sega32xjp`, `sega32xna`, `sg-1000`, `sgb`, `sneshd`, `snesna`, `solarus`, `spectravideo`, `stratagus`, `stv`, `sufami`, `supergrafx`, `supervision`, `supracan`, `symbian`, `tanodragon`, `ti99`, `tic80`, `to8`, `triforce`, `trs-80`, `uzebox`, `vectrex`, `vic20`, `videopac`, `vircon32`, `vsmile`, `wasm4`, `windows3x`, `windows9x`, `x1`, `x68000`, `zmachine`, `zx81`

## Excluídos (1)

`bios`
