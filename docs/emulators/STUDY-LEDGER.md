# STUDY-LEDGER — ciclo de estudo por sistema

Um sistema por vez. O estudo **propõe**, a `EMULATOR-PORTING-DIRECTIVE` decide, o
WI executa. Nenhuma linha de código de produto sai deste ciclo.

Status: `pendente` · `em-curso` · `revisão` · `verde` · `descoberta`.

## Ondas

| Onda | Slug | Sistema | Status | Commit | Pendências |
|---|---|---|---|---|---|
| 0 | `switch` | Nintendo Switch | **revisão** | — | **Não fecha em `verde`:** o §7 exige licença e manutenção verificadas com fonte e data — a licença do Citron não é declarada no manifesto e o estado upstream dos três não foi reverificado (D4). Resolver no WI-S0 |
| 1 | `nes` | NES / Famicom | **verde** | — | Checklist §7 completo. Docs oficiais consultadas são da linha 0.9.9 (2020) e a aplicabilidade ao MesenCE 2.2.1 está marcada `[validar no spike]` em cada uso |
| 1 | `snes` | SNES | pendente | — | — |
| 1 | `gb-gbc` | Game Boy / Color | pendente | — | MesenCE 2.2.0 anuncia link cable entre dois GB/GBC — gancho P3 forte |
| 1 | `gba` | Game Boy Advance | pendente | — | — |
| 1 | `mega-drive` | Mega Drive / 32X / CD | pendente | — | — |
| 1 | `master-system` | Master System / Game Gear | pendente | — | — |
| 1 | `ps1` | PlayStation | pendente | — | Adapter `duckstation` já existe |
| 1 | `arcade-mame` | Arcade (MAME) | pendente | — | — |
| 1 | `arcade-fbneo` | Arcade (FBNeo) | pendente | — | — |
| 1 | `pc-engine` | PC Engine / TG16 | pendente | — | — |
| 1 | `neo-geo` | Neo Geo | pendente | — | — |
| 2 | `n64` `gamecube-wii` `dreamcast` `saturn` `ps2` `psp` `nds` `3ds` | — | pendente | — | Adapter `dolphin` já existe |
| 3 | `ps3` `xbox` `xbox360` `wiiu` `psvita` | — | pendente | — | — |
| 4 | `dos` `scummvm` `c64` `amiga` `zx-spectrum` `msx` + engines + nichos | — | pendente | — | — |

## Divergências entre o diretivo de estudo e o repositório

Registradas em 2026-07-24, corrigidas conforme decisão do operador.

| # | Divergência | Resolução aplicada |
|---|---|---|
| D1 | O diretivo manda propor `FM-62+`; o maior FM do repositório é **FM-26** (`docs/03-architecture/FAILURE-MODES.md`) | Dossiês propõem **FM-27+**. A citação de `FM-22` no diretivo confere e existe |
| D2 | Onda 0 diz "revisar dossiê existente" de Switch; `docs/emulators/` não existia e não há dossiê | Onda 0 tratada como **criação**, consolidando `EMULATOR-PORTING-DIRECTIVE.md`, `ADR-0021`, `SWITCH-MEDIA-PROVIDER-PLAN.md` e os manifestos já commitados |
| D3 | Cinco leituras obrigatórias do §1 não existem: `IMPLEMENTATION-REPORT.md`, `COOP-ONLINE`, `THEME-RUNTIME`, `DESKTOP-EXPERIENCE`, `EXPANSION-SUPER-PROMPT` | Registradas como pendência. **Não foram inventadas** — o §9 do diretivo proíbe redesenhar arquitetura neste ciclo. Onde um dossiê dependeria delas, a lacuna está marcada no próprio dossiê |
| D4 | O diretivo assume pesquisa web livre | `WebSearch` e `WebFetch` falham neste ambiente (modelo `cc/claude-haiku-4-5-20251001` indisponível; um 403 e um 429 adicionais). Pesquisa feita pelo **navegador**, que funciona. Mais lenta: afeta o ritmo das ondas seguintes |

## Descobertas fora de escopo

Entram aqui, nunca mudam a fila no improviso.

| # | Descoberta | Onde impacta |
|---|---|---|
| DESC-1 | `SourMesen/Mesen2` foi **arquivado em 2026-06-04**; o desenvolvimento migrou para `nesdev-org/MesenCE` (fork comunitário, 255 commits à frente, stable 2.2.1). Consultado 2026-07-24 | NES, SNES, GB/GBC, GBA, PC Engine, Master System/GG — seis sistemas da Onda 1 dependem desta escolha |
| DESC-2 | MesenCE 2.2.0 adicionou **link cable entre dois GB/GBC** e melhorou **MSU-1** no SNES | Ganchos P3 (GB/GBC) e P6 (SNES); avaliar nos dossiês respectivos |
| DESC-3 | Upstream do Mesen documenta que os popups da UI Avalonia **não renderizam sob Gamescope** — menus de configuração inacessíveis em Game Mode | Reforça a tese do produto: config por arquivo torna a GUI dispensável. Vale para todos os sistemas cobertos pelo Mesen |
| DESC-4 | Config por jogo endereçada por **serial** já existe em DuckStation, PCSX2 e Dolphin (`GameSettings/<serial>.ini`) | `ps1` e `gamecube-wii` consomem contrato conhecido em vez de pesquisar do zero. Ver `RESEARCH-INPUT-LEGACY-SCRIPTS.md` C1 |
| DESC-5 | Emuladores de dois ecrãs podem rotear para dois monitores físicos, mas **só em Desktop Mode** — o compositor de Game Mode é single-output/single-focus | Momento mágico quase pronto para `wiiu` (GamePad na tela do Deck, jogo na TV) e `3ds`. Ver C2 |
| DESC-6 | Somando DESC-3 e DESC-5: a restrição do compositor de Game Mode é **transversal**, não por emulador | Promover a capability de plataforma + FM próprio, em vez de redescobrir sistema a sistema |
| DESC-7 | O giroscópio é **descartado** pelos scripts de referência (filtro explícito de IMU) | O mapa gyro→pistola de luz não tem precedente para portar: spike exploratório, risco declarado. Ver C3 |

## Decisões do operador

| Data | Decisão |
|---|---|
| 2026-07-24 | **Citron fica** como terceiro adapter, mesmo pinado em nightly. A lacuna de licença vira item do WI-S0 (bloco B3 do briefing de pesquisa), não motivo de remoção |
