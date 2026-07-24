# SteamZero Expansion Ledger

Fonte de governança: prompt mestre de expansão recebido diretamente do operador
em 2026-07-23. A base é `c94d249`, tip limpo de
`codex/correcao-midia-credenciais-diretorios` e descendente de `6b10db5`.

Rótulos permitidos: `pending`, `in-progress`, `verified-dev`, `verified-offscreen`,
`verified-vm`, `verified-hw`, `PENDING-HUMAN`, `blocked` e `backlog-protected`.
Nenhum gate offscreen promove experiência física ou sensorial a `verified-hw`.

| WI | Escopo | Contrato principal | Estado | Evidência/relatório |
|---|---|---|---|---|
| F0 | Saneamento da baseline de qualidade | error-v1 | verified-dev | `docs/expansion/WI-F0.md` |
| F1 | `core.net` seguro, limitado, cancelável e fake | core.net | verified-dev | `docs/expansion/WI-F1.md` |
| F2 | `core.crypto`, checksum, assinatura e envelopes | core.crypto | verified-dev | `docs/expansion/WI-F2.md` |
| F3 | jobs/operações paginados e `--follow` | event-v1 | verified-dev | `docs/expansion/WI-F3.md` |
| F4 | daemon persistente e compatibilidade CLI | local API | verified-dev | `docs/expansion/WI-F4.md` |
| F5 | registry declarativo de plataformas/capacidades | platform-manifest-v1 | pending | — |
| F6 | perfis versionados e reversíveis de input | retro-input-profile-v1 | pending | — |
| A1 | Playtime, sessões interrompidas e continuar jogando | feat-playtime-v1 | pending | — |
| A2 | Histórico operacional e rollback contextual | feat-operation-history-v1 | pending | — |
| A3 | Tags, favoritos e coleções inteligentes | feat-collection-v1 | pending | — |
| A4 | Anti-bitrot limitado, re-hash e estado suspect | feat-bitrot-v1 | pending | — |
| A5 | Plataformas cloud declarativas e atalhos reversíveis | platform-manifest-v1 | pending | — |
| A6 | Sessões co-op por QR atrás de feature flag | co-op-session-v1 | pending | — |
| A7 | MediaHub canônico masters → optimized → views | media-registry-v1 | pending | — |
| A8 | Patches IPS/BPS/xdelta sobre cópia imutável | patch-operation-v1 | pending | — |
| A9 | RetroAchievements, keyring, offline e hardcore | achievement-v1 | pending | — |
| A10 | Reserva compatível do catálogo de produto | capability payload | pending | — |
| A11 | Ports/homebrew open-source reproduzíveis | port-catalog-v1 | pending | — |
| A12 | Scraper hash-first/DAT/fuzzy/cache/seed | media-registry-v1 | pending | — |
| G0 | Evidência automatizada HUD 1280×800 | gtool-hud-v1 | pending | — |
| G1 | MangoHud por jogo, diff e rollback | gtool-hud-v1 | pending | — |
| G2 | Compositor puro de ambiente de lançamento | gtool-launch-environment-v1 | pending | — |
| G3 | vkBasalt por jogo, custo e desligamento completo | gtool-launch-environment-v1 | pending | — |
| G4 | Frame generation LSFG/OptiScaler com fallback | gtool-framegen-v1 | pending | — |
| G5 | Captura e galeria com orçamento de performance | media-registry-v1 | pending | — |
| G6 | Benchmark local reproduzível por jogo/perfil | benchmark-v1 | pending | — |
| R0 | Tabela integer normativa e sharp-bilinear | retro-experience-v1 | pending | — |
| R1 | Presets Como era/Equilibrado/Melhorado | retro-experience-v1 | pending | — |
| R2 | Vídeo: integer, PAR, cores, shaders e RF→RGB | retro-experience-v1 | pending | — |
| R3 | Timing, DRC, PAL/NTSC, slowdown e overclock | retro-experience-v1 | pending | — |
| R4 | TATE transacional, recovery e janela alternativa | retro-experience-v1 | pending | — |
| R5 | Áudio por dispositivo, chips, EQ e dock/handheld | retro-experience-v1 | pending | — |
| R6 | Perfis automáticos de controles especializados | retro-input-profile-v1 | pending | — |
| R7 | Latência/torneio, netplay e melhorias 3D | retro-experience-v1 | pending | — |
| R8 | Registry compartilhado de shaders/bezels | media-registry-v1 | pending | — |
| B0 | Web UI LAN, família/kiosk, comunidade, pareamento | nenhum (protegido) | backlog-protected | — |

## Diagnóstico de emulação incorporado

Fonte: catálogo de inspeção `2026-07-23-catalogo-falhas-emulacao.md`, lido na
worktree `codex/desktop-ergonomia-d0` (`43ec946`). A comparação autoritativa é
feita contra esta linha consolidada; código presente aqui não será reconstruído.

| ID | Achado do diagnóstico | Destino no ciclo | Estado | Evidência |
|---|---|---|---|---|
| D1 | Emulador principal + fallback visual por plataforma | correção transversal/F5 | verified-dev | `docs/expansion/WI-D1.md` |
| D2 | DLC/update no scan e projeção para emuladores | F5, A4, A8 | pending | `docs/expansion/DIAGNOSTIC-EMULATION-RESOLUTION.md` |
| D3 | Fiação de catálogos, mods e cheats existentes | A12 + composição | verified-dev | `docs/expansion/WI-D3.md` |
| D4 | Gráficos e performance | G1, G3, G4, G6, R0–R2 | pending | `docs/expansion/DIAGNOSTIC-EMULATION-RESOLUTION.md` |
| D5 | Controles editáveis e perfis | F6, R6 | pending | `docs/expansion/DIAGNOSTIC-EMULATION-RESOLUTION.md` |
| D6 | vSaves, playtime, captura e lançamento | A1, G5 | pending | `docs/expansion/DIAGNOSTIC-EMULATION-RESOLUTION.md` |
| D7 | Scraping/download e fallback de artwork | F1, A7, A12 | in-progress | `docs/expansion/WI-D1.md` |
| D8 | Artwork e conversão de ROM | A7, A8 | in-progress | conversão: `docs/expansion/WI-D3.md`; artwork: A7 |
| D9 | Armazenamento e exclusão linkada | A4, A7 | pending | `docs/expansion/DIAGNOSTIC-EMULATION-RESOLUTION.md` |
| D10 | Leitura de DLC, shader, firmware e região | F5, A4, A12 | pending | `docs/expansion/DIAGNOSTIC-EMULATION-RESOLUTION.md` |

## Auditorias por lote

- A cada quatro WIs: suíte completa, ledger × commits × relatórios e dependências
  com destino explícito.
- Ao fim de cada track: matriz requisito → WI → contrato → teste → evidência.
- Instalação e release somente após todos os gates finais e preflights do
  instalador canônico.
