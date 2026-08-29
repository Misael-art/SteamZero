# Lote 1 de manifestos de plataforma — 2026-08-28

Item: `SZ-LIBRARY-CANONICAL` (etapa "os 110 diretorios que exigem manifesto").
Branch `codex/library-full-scan`. **25 manifestos novos** + alias `atarixe`
na `atari-classics` + sancao de core por plataforma em `launch_profile.py`.

## O que entrou

Plataformas com caminho real de emulacao declarado (adapter `retroarch` +
core libretro upstream existente; sancao em `PLATFORM_CORES` seguindo o
precedente de `swanstation`/`dolphin`/`pcsx2`, cujos cores/adapters tambem
nao estao no lock — sancao e contrato da plataforma; instalabilidade e
camada separada com recusa honesta de "Jogar" enquanto o core nao chegar
ao lock):

| Manifesto | Sistemas (dirs cobertos) | Core |
|---|---|---|
| sega-saturn | saturn, saturnjp | mednafen_saturn |
| sg-1000 | sg-1000 | genesis_plus_gx |
| neo-geo-cd | neogeocd, neogeocdjp | neocd |
| vectrex | vectrex | vecx |
| odyssey2 | odyssey2, videopac | o2em |
| channelf | channelf | freechaf |
| pc-engine-supergrafx | supergrafx | beetle_sgx |
| atari-st | atarist | hatari |
| apple2 | apple2 | applewin |
| bbc-micro | bbcmicro | beebem |
| coco | coco, dragon32 | xroar |
| ti99 | ti99 | ti99 |
| zx81 | zx81 | 81 |
| thomson | to8, moto | theodore |
| x68000 | x68000 | px68k |
| pc88 | pc88 | quasi88 |
| pc98 | pc98 | np2kai |
| gameandwatch | gameandwatch | gw |
| supervision | supervision | potator |
| megaduck | megaduck | sameduck |
| doom | doom | prboom |
| quake | quake | tyrquake |
| pico8 | pico8 | fake08 |
| tic80 | tic80 | tic80 |
| wasm4 | wasm4 | wasm4 |
| (alias) atarixe -> atari-classics | atarixe | stella |

**31 diretorios do acervo real deixaram de ser unmatched.**

## Medicao no acervo real (somente leitura, pos-lote)

| Metrica | antes do lote | depois |
|---|---|---|
| matched | 66 | **97** |
| unmatched | 128 | **97** |
| excluded | 4 | 4 |
| jogos unicos selecionados | 375 | **394** (+19: arquivos reais nos diretorios novos, antes invisiveis) |

O read model continua com os jogos VERDADEIROS apos a dedup com o scanner
do Switch (212; ver `2026-08-28-transport-compression/README.md`).

## Provas

- `tests/unit/test_platforms.py` (32 passed): lista de ids do bundle
  atualizada (contrato); classe nova `TestLote1CoberturaDosSemManifesto`
  — cada diretorio da tabela casa com a plataforma declarada e a extensao
  de referencia classifica como base.
- **Prova negativa**: remover `39-sega-saturn.platform.json` derruba o
  teste do lote (mutacao executada e revertida).
- `make update-capability-matrix` + `make capability-matrix`: matriz
  regenerada e sancionada — e o gate que PEGOU o lote sem sancao
  (`mednafen_saturn nao e sancionado para sega-saturn`), provando que a
  sancao e gateada e nao decorativa.

## Restantes (97 unmatched) — decisao explicita, em aberto

- **Sem caminho de emulacao declaravel hoje** (exigiria MAME standalone ou
  cores sem certeza de contrato — nao invento): `adam`, `ags`, `amstradcpc`,
  `android`, `apple2gs`, `arcadia`, `archimedes`, `arduboy`*, `astrocde`,
  `atarijaguarcd`, `atomiswave`, `c16`, `cavestory`, `cdimono1`, `cdtv`,
  `consolearcade`, `crvision`, `daphne`, `dos`, `easyrpg`, `electron`*,
  `fba`, `fbneo`, `fds`, `flash`, `fm7`, `fmtowns`, `gamate`, `gamecom`,
  `genesiswide`, `gmaster`, `gx4000`, `j2me`, `laserdisc`, `lcdgames`,
  `lowresnx`, `lutro`, `macintosh`, `mame-advmame`, `mame-mame4all`,
  `mark3`, `mess`, `model2`, `model3`, `msxturbor`, `mugen`, `multivision`,
  `n64dd`, `naomi`, `naomi2`, `naomigd`, `openbor`, `pcfx`, `plus4`,
  `pokemini`, `pv1000`, `samcoupe`, `satellaview`, `scv`, `sgb`, `sneshd`,
  `snesna`, `solarus`, `spectravideo`, `stratagus`, `stv`, `sufami`,
  `supracan`, `symbian`, `tanodragon`, `triforce`, `trs-80`, `uzebox`,
  `vic20`, `vircon32`, `vsmile`, `windows3x`, `windows9x`, `x1`, `zmachine`
  (*arduboy/electron: cores upstream existem (arduous/elkjs) — entram no
  lote 2 apos conferencia de extensao).
- **Variants ambiguas (mantidas unmatched por decisao)**: `atarijaguarcd`,
  `fds`, `genesiswide`, `msxturbor`, `n64dd`, `satellaview`, `sgb`,
  `sneshd`, `snesna`, `sufami`.
- **Servicos de atalho (nao e diretorio de ROM de plataforma)**: `cloud`,
  `desktop`, `epic`, `lutris`, `moonlight`, `remoteplay`, `portmaster`,
  `ports`, `primehack`, `primehacks`.
- **Requerem adapter proprio hoje inexistente no acervo de adapters
  renderizaveis**: `pc` (DOS/Windows), `ps4`, `psvita`, `scummvm`.

Lote 2 planejado: `arduboy`, `electron`, `samcoupe`, `pcfx`, `pokemini`,
`vic20`, `plus4`, `x1` — pendente conferencia de core/extensao com a mesma
barra de certeza deste lote.
