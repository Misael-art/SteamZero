# STUDY-LEDGER — ciclo de estudo por sistema

> **Leia junto:** [`STUDY-DIRECTIVE-ADDENDUM.md`](STUDY-DIRECTIVE-ADDENDUM.md)
> corrige quatro pontos do direcionador de estudo e registra os achados
> transversais que não devem ser redescobertos sistema a sistema.

Um sistema por vez. O estudo **propõe**, a `EMULATOR-PORTING-DIRECTIVE` decide, o
WI executa. Nenhuma linha de código de produto sai deste ciclo.

Status: `pendente` · `em-curso` · `revisão` · `verde` · `descoberta`.

## Ondas

| Onda | Slug | Sistema | Status | Commit | Pendências |
|---|---|---|---|---|---|
| 0 | `switch` | Nintendo Switch | **verde** | — | Fechado em 2026-07-25: licenças dos três confirmadas (Eden GPLv3, Ryubing MIT, Citron GPL-3.0) e projetos ativos. WI-S0 agora tem entregáveis concretos: repinar Citron na estável, reconferir hash do Ryubing, declarar licença |
| 1 | `nes` | NES / Famicom | **verde** | — | Revisado em 2026-07-25 com a coleta externa. Três afirmações anteriores estavam erradas e foram corrigidas (ver CORR-1..3). Riscos abertos declarados no dossiê: gyro sem precedente, HD Packs sem verificação em Linux, netplay sem doc |
| — | `retroarch` | Frontend multi-sistema (transversal) | revisão | — | Dossiê de infraestrutura, não de sistema. Fecha em `verde` quando o WI-R0 responder se o core Mesen no libretro carrega a base de dados interna |
| 1 | `snes` | SNES | **bloqueado** | — | Aguarda o **WI-R0**: a escolha MesenCE × RetroArch decide seis dossiês de uma vez. Estudar SNES antes seria escrever a §2 duas vezes |
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
| DESC-8 | **O rename No-Intro do WI-5 órfã a config por jogo de emuladores que a endereçam por nome de arquivo** — silenciosamente, sem erro | O achado de maior impacto do ciclo. Impõe requisito novo ao WI-5 (mover o sidecar na mesma transação) e vira **FM-29**. Ver `nes.md` §4 |
| DESC-9 | Gyro-como-mouse do Steam Input é **relativo**; pistola de luz precisa de **absoluto**. Nenhum precedente publicado de gyro→lightgun | O momento mágico do NES fica com dois veículos possíveis (gyro ou trackpad) e o spike vira "provar que é possível", com resultado negativo aceitável |
| DESC-10 | **Nenhum** dos quatro emuladores estudados publica SHA-256 (MesenCE, Eden, Ryubing, Citron) | O hash é sempre calculado localmente no primeiro download. Isso precisa virar **política declarada** no `ADAPTER-MODEL.md`, não prática implícita |
| DESC-11 | Assets do Ryubing 1.3.3 foram **recriados em 2026-03-30** (migração GitLab→Forgejo) sem mudar a versão | Hash pinado antes disso pode não bater. Classe de risco nova: *release imutável que não é imutável* |
| DESC-12 | **O RetroArch é imune ao FM-27** — desenha o próprio menu dentro da janela, sem popups de toolkit | Reabre a decisão primária do NES e, por arrasto, dos seis sistemas do MesenCE. Ver `retroarch.md` e o WI-R0 |
| DESC-13 | Netplay do RetroArch é **rollback documentado**; o do MesenCE é lockstep inferido | Se multiplayer online entrar na fila, a diferença é decisiva e não deve ser nivelada por baixo |
| DESC-14 | **O RetroArch não lê giroscópio em Linux desktop** — a API libretro prevê os eixos, mas só os drivers `android`/`cocoa`/`vita`/`switch` os passam | Endurece DESC-9: a ponte gyro→absoluto teria de nascer *fora* do RetroArch, como componente próprio. Eleva o valor do plano B (trackpad) |
| DESC-15 | FM-29 se aplica ao RetroArch **ampliado**: override `.cfg`, remap `.rmp`, opções `.opt` e preset de shader — quatro classes de sidecar, todas por nome de arquivo | O requisito do WI-5 passa a ser mover *conjunto* de sidecars, não arquivo único |
| DESC-16 | Um integrador all-in-one em Flatpak monolítico é o "produto acabado" mais próximo do nosso — mas **não permite trocar builds individuais** | Colide com pinning fino por emulador, que é a nossa premissa. Validação de conceito, não caminho |

## Correções — o que a coleta de 2026-07-25 derrubou

Registro do que este ciclo **afirmou errado** e corrigiu. Existe para que o
padrão fique visível, não só o resultado.

| # | Eu afirmei | Na verdade | Origem do erro |
|---|---|---|---|
| CORR-1 | "AppImage das releases do MesenCE, pinado por SHA-256" | A estável **não tem AppImage** (só `.zip`), o AppImage é nightly, e o projeto **não publica hash nenhum** | Assumi que o padrão dos manifestos de Switch valia para outro projeto. Analogia, não verificação |
| CORR-2 | melonDS "não tem" modo de duas janelas | **Tem desde a 1.0** — multi-janela com top/bottom independentes | Copiei o comentário de um script de referência sem datar. O script foi escrito antes da 1.0 e envelheceu em silêncio |
| CORR-3 | Azahar usa `layout_option=5` para Separate Windows | O valor é **`4`**; `5` é HybridScreen | Mesma fonte, mesmo erro de método |
| CORR-4 | Config por jogo do MesenCE: formato desconhecido | JSON, `GameConfig/<nome-da-ROM>.json`, **endereçada por nome de arquivo** — e isso colide com o WI-5 (ver DESC-8) | Não era erro, era lacuna; a coleta fechou |

**Lição de método, aplicável ao resto das ondas:** comentário em script de
referência é *hipótese datada*, não fato. Dos quatro itens acima, dois vieram de
confiar num comentário sem verificar a data. Todo dossiê seguinte trata a
árvore de scripts legados como pista a confirmar, nunca como fonte.

## WIs propostos e seu estado

| WI | Origem | Estado | Bloqueia |
|---|---|---|---|
| **WI-S0** | `switch.md` §14 | **prompt fechado** em `docs/expansion/WI-S0.md`, pronto para um agente implementador | os demais WIs de Switch |
| **WI-R0** | `retroarch.md` §14 | proposto, é **pesquisa** e não implementação | `nes.md`, `snes` e mais quatro dossiês do MesenCE |
| **WI-N1** | `nes.md` §14 | proposto, **bloqueado** pelo WI-R0 | — |

## Decisões do operador

| Data | Decisão |
|---|---|
| 2026-07-24 | **Citron fica** como terceiro adapter, mesmo pinado em nightly. A lacuna de licença vira item do WI-S0 (bloco B3 do briefing de pesquisa), não motivo de remoção |
