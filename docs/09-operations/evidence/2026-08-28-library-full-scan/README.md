# Varredura completa do acervo real — 2026-08-28

Item: `SZ-LIBRARY-CANONICAL`. Branch `codex/library-full-scan` (base `23b13b6`).
Raiz: `/home/misael/emulation/roms`. Medição **somente leitura** com
`PlatformDirectoryInventory.from_registry(PlatformRegistry.bundled())`,
comparada com a medição de 2026-08-24 (`2026-08-24-library-198-directories`).

## O que mudou no código

1. **Amostragem removida.** `PlatformDirectoryInventory.inventory()` não tem
   mais `max_games_per_platform`: `selected_games` carrega TODOS os jogos
   únicos. A amostragem era o que reduzia 375 jogos a 75 na fonte canônica —
   300 jogos existentes ficavam invisíveis para Biblioteca/Emulação.
2. **7 aliases ES-DE de plataformas já suportadas** (mesma plataforma, outra
   grafia — nunca plataforma diferente):
   `gc`→nintendo-console, `megadrivejp`→mega-drive,
   `megacd`/`megacdjp`/`sega32xjp`/`sega32xna`→sega-cd-32x, `msx1`→msx.
3. **3 diretórios de serviço classificados não-jogo** (mesma natureza de
   `bios`, já excluído): `emulators`, `generic-applications`, `kodi`.

## Medição na árvore nova (somente leitura)

| Métrica | 2026-08-24 | 2026-08-28 |
|---|---|---|
| matched | 59 | **66** |
| unmatched | 138 | **128** |
| excluded | 1 | **4** |
| Jogos únicos detectados | 375 | 375 |
| Jogos que ENTRAM na fonte canônica | 75 (amostragem) | **375** |
| Symlinks pulados | 61 | 61 |

Tabela por diretório (todos com `selected == count`, sem amostragem):
`switch` 178, `mastersystem` 51, `psx` 49, `famicom` 33, `gb` 30, `n3ds` 19,
`ps2` 6, `dreamcast` 5, `wiiu` 2, `ps3` 1, `wii` 1 — 375 no total.

## Decisões explícitas para os 128 unmatched restantes

Convenção: plataforma SEM manifesto no projeto ou atribuição ambígua fica
`unmatched` (visível, com diagnóstico) até decisão de produto — extensão não
adivinha plataforma. Os três grupos abaixo particionam a medição de hoje
(110 + 12 + 6 = 128, verificação por script):

- **Plataforma real sem manifesto — 110 (decisão: suportar exige MANIFESTO
  NOVO, que é decisão de produto, não alias)**: `adam`, `ags`, `amstradcpc`,
  `android`, `apple2`, `apple2gs`, `arcadia`, `archimedes`, `arduboy`,
  `astrocde`, `atarist`, `atarixe`, `atomiswave`, `bbcmicro`, `c16`,
  `cavestory`, `cdimono1`, `cdtv`, `chailove`, `channelf`, `coco`,
  `consolearcade`, `crvision`, `daphne`, `doom`, `dos`, `dragon32`, `easyrpg`,
  `electron`, `fba`, `fbneo`, `flash`, `fm7`, `fmtowns`, `gamate`,
  `gameandwatch`, `gamecom`, `gmaster`, `gx4000`, `j2me`, `laserdisc`,
  `lcdgames`, `lowresnx`, `lutro`, `macintosh`, `mame-advmame`,
  `mame-mame4all`, `mark3`, `megaduck`, `mess`, `model2`, `model3`, `moto`,
  `mugen`, `multivision`, `naomi`, `naomi2`, `naomigd`, `odyssey2`, `openbor`,
  `oric`, `palm`, `pc`, `pc88`, `pc98`, `pcfx`, `pico8`, `plus4`, `pokemini`,
  `portmaster`, `ports`, `primehack`, `primehacks`, `ps4`, `psvita`, `pv1000`,
  `quake`, `samcoupe`, `saturn`, `saturnjp`, `scummvm`, `scv`, `sg-1000`,
  `solarus`, `spectravideo`, `stratagus`, `stv`, `supergrafx`, `supervision`,
  `supracan`, `symbian`, `tanodragon`, `ti99`, `tic80`, `to8`, `triforce`,
  `trs-80`, `uzebox`, `vectrex`, `vic20`, `videopac`, `vircon32`, `vsmile`,
  `wasm4`, `windows3x`, `windows9x`, `x1`, `x68000`, `zmachine`, `zx81`.
- **Variantes/famílias de plataforma JÁ suportada, atribuição ambígua — 12
  (decisão: permanecem unmatched; virar alias exigiria decidir extensões e
  fronteiras de mídia — produto)**: `atarijaguarcd`, `fds`, `genesiswide`,
  `msxturbor`, `n64dd`, `neogeocd`, `neogeocdjp`, `satellaview`, `sgb`,
  `sneshd`, `snesna`, `sufami`.
- **Serviços/gerenciadores com atalhos de jogo, não diretórios de ROM de uma
  plataforma — 6 (decisão: unmatched até haver contrato de atalhos)**: `cloud`,
  `desktop`, `epic`, `lutris`, `moonlight`, `remoteplay`.

## Consequência honesta para o transporte (não medida aqui, medida em 2026-08-27)

O workspace de emulação já media **1.513.479 bytes contra o cap de 1.048.576**
COM a amostragem de 75 jogos (evidência `E-API-RESPONSE-TOO-LARGE`,
WORKLOG 2026-08-27). A varredura completa acrescenta ~300 linhas de jogo ao
read model (~1,3 KB/linha na ordem de grandeza) — o cap do transporte
continua estourado e passa a ser o próximo passo obrigatório do item:
**paginar o workspace** (a central in-process não passa pelo cap; o caminho
CLI/daemon sim). A variante paginada prometida na `manualAction` do erro ainda
não existe.

## Provas

- `tests/unit/test_library_rom_classify.py` (50) — inclui o teste novo dos
  aliases ES-DE e não-jogo, com prova negativa: remover o alias `gc` derruba
  o teste (mutação executada e revertida nesta sessão).
- `tests/unit/test_emulation_controller.py::test_library_scan_indexes_known_platform_directories_without_scanning_bios`
  — contrato do scan atualizado: 12 jogos criados, `selectedCount == gameCount`.
