# FEATURE-CATALOG — catálogo de funcionalidades

Colunas: origem conceitual (de qual projeto vem a melhor referência), fase do roadmap.

> Visão técnica de proveniência (262 funções, incluindo internas do núcleo, classificadas em Inspiração/Adaptação/Aprimoramento/Novo com evidência `arquivo:linha`): [FUNCTION-PROVENANCE-MATRIX](../02-research/FUNCTION-PROVENANCE-MATRIX.md).

## Ciclo de vida de componentes

| ID | Funcionalidade | Origem conceitual | Fase |
|---|---|---|---|
| F-LC-01 | Instalar emulador/frontend/ferramenta por manifesto (Flatpak/AppImage/nativo) | RetroDECK components + LinuxToys metadados + PhaseZero staging | 4 |
| F-LC-02 | Atualizar com pin de versão, checksum e canal (stable/beta/dev) | RetroDECK recipe + PhaseZero verify | 4 |
| F-LC-03 | Desinstalar com inventário e preservação de dados do usuário | PhaseZero rollback manifest | 4 |
| F-LC-04 | Reparar (verify → repair só da camada quebrada) | PhaseZero `-Audit -Repair`; EmuDeck `autofix.sh` | 4 |
| F-LC-05 | Rollback de qualquer operação de ciclo de vida | PhaseZero | 1 |
| F-LC-06 | Matriz de compatibilidade por distro (pacman/dnf/apt/rpm-ostree/flatpak) | LinuxToys `is_*` + `pkg_install`/`pkg_flat` | 4 |

## Configuração

| F-CF-01 | Parsers estruturados INI/JSON/XML/YAML com escrita atômica e diff | PhaseZero `pz_write_managed_file` + biblioteca nova | 1 |
| F-CF-02 | Presets e configuração por jogo | RetroDECK presets.sh; EmuDeck configEmuAI | 4 |
| F-CF-03 | Migrações versionadas de config com preservação de comentários | novo (lacuna em todos) | 3 |
| F-CF-04 | Restore defaults por seção | RetroDECK | 4 |

## Biblioteca e ROMs

| F-LB-01 | Scan incremental read-only com hash e classificação | PhaseZero `library scan` (`linux/emulation/library/scan.py`) | 3 |
| F-LB-02 | Plan/preview/apply/verify/rollback de organização | PhaseZero `library/{plan,apply}.py` (confirmToken) | 3 |
| F-LB-03 | Conversões CHD/RVZ/CSO/NSZ com staging, espaço reservado, timeout, original até commit | PhaseZero `rom-optimize` + EmuDeck cobertura de formatos | 3 |
| F-LB-04 | Dedupe, multi-disco (M3U), incompletos, órfãos, quarentena | RetroDECK M3U validator; PhaseZero media clean | 3 |
| F-LB-05 | Migração SSD↔microSD por UUID com bloqueio de escrita em remoção | PhaseZero removable + RetroDECK move_folder | 3 |
| F-LB-06 | Proteções: zip bomb, path traversal, symlink inseguro | PhaseZero `library/safezip.py` | 1 |

## BIOS/Firmware/Keys

| F-BI-01 | Store central com hashes, região, versão, compatibilidade por emulador | RetroDECK BIOS checker + EmuDeck checkBIOS.sh + PhaseZero bios.sh | 3 |
| F-BI-02 | Links seguros para os emuladores consumidores | PhaseZero shared-content.sh | 3 |
| F-BI-03 | Importação local, auditoria, nunca em logs | política nova | 3 |

## Saves e sync

| F-SV-01 | Store central de saves/states com backups incrementais e linha do tempo | novo (lacuna em todos; EmuDeck faz só cloud) | 3 |
| F-SV-02 | Checkpoint pré-suspensão e flush pré-desligamento | novo, sobre PhaseZero session hooks | 2 |
| F-SV-03 | Cloud sync com fila offline, criptografia opcional e conflito não-destrutivo | EmuDeck cloudServicesManager (referência de provedores; comportamento reimplementado) | 3 |

## Mídia e metadados

| F-MD-01 | Scraping multi-provedor com cache, retry, rate limit, licença registrada | EmuDeck generateGameLists + RetroDECK ES-DE scraper | 3 |
| F-MD-02 | Índice incremental, associação por hash, órfãos, quarentena | PhaseZero media-index.py | 3 |

## Desempenho

| F-PF-01 | Perfis GameMode/Gamescope/MangoHUD/TDP por jogo/dispositivo/energia | PhaseZero performance.sh/tuning + EmuDeck advanced settings | 2/4 |
| F-PF-02 | LCD/OLED, portátil/dock, meta de FPS, upscaling, frame gen (LSFG) | PhaseZero `performance prepare-lsfg` | 4 |
| F-PF-03 | Restauração do estado ao sair | PhaseZero windows-vm optimize (padrão restore) | 2 |

## Controles

| F-CT-01 | Perfis Steam Input por emulador/plataforma/jogo | EmuDeck templates de controle + RetroDECK controller layouts | 4 |
| F-CT-02 | Ações semânticas universais (sair, save/load state, pausa, FF, disco, tela, captura, menu desempenho) | RetroDECK hotkeys + PhaseZero hotkey-actions.sh | 4 |
| F-CT-03 | Hot-swap, recuperação pós-suspensão, gyro, trackpads, traseiros, radiais, conflitos, teste de eixos | PhaseZero controllers.sh | 2/4 |

## Frontends

| F-FE-01 | Adapters Steam/SRM/ES-DE/RetroArch/RetroDECK/Heroic (LaunchBox se viável) | PhaseZero srm.sh, frontends.py, launchbox_import.py; EmuDeck runSRM | 4 |
| F-FE-02 | Shortcuts Steam com arte, sem duplicação | PhaseZero steam-shortcut.py | 4 |

## Deck / sessão

| F-SD-01 | Session Manager (launching…failed) | novo, sobre PhaseZero display-session.sh | 2 |
| F-SD-02 | Máquina de modos handheld/docked-tv/docked-monitor/desktop/unknown + fallback de display | PhaseZero apply-handheld/docked-*/detect-mode/mode-watcher | 2 |
| F-SD-03 | microSD: UUID, monitor de montagem, erro I/O, relatório de integridade | PhaseZero install-removable-mount.sh | 2 |
| F-SD-04 | Offline-first e fila de operações remotas | novo | 2 |
| F-SD-05 | Matriz de compat SteamOS/Steam Client/plugins | novo | 2 |

## Handheld Desktop

| F-HD-01 | Perfis KDE handheld/dock/safe com contexto, estabilidade e override | SteamZero | 4 |
| F-HD-02 | Ownership exclusivo e providers de input/teclado por capability | SteamZero | 4 |
| F-HD-03 | Snapshot G-STATE, verify, rollback e recovery de efeitos Desktop | SteamZero | 4 |
| F-HD-04 | Central Qt/QML touch+controle, bridge efêmera allowlisted | SteamZero | 4/5 |
| F-HD-05 | Runtime independente e importador legado offline separado | SteamZero | contínuo |

## Plataforma

| F-PL-01 | Núcleo transacional + journal + locks + quarentena | PhaseZero (generalização do library pipeline) | 1 |
| F-PL-02 | Job Manager (fila, prioridade, pausa, resume, cancel, pós-reboot, limites CPU/IO, bateria, bloqueio durante jogo) | novo | 1 |
| F-PL-03 | State Store SQLite + export/import legível | novo (ADR-0005) | 1 |
| F-PL-04 | Serviço local UI/API com allowlist e schemas | PhaseZero UI contract (conceito) | 1 |
| F-PL-05 | Helper privilegiado com allowlist | PhaseZero admin bridge + install-privileged-controls.sh | 1 |
| F-PL-06 | CLI JSON estável | PhaseZero json-envelope.sh | 1 |
| F-PL-07 | Doctor/diagnóstico + pacote de suporte revisável | PhaseZero -Doctor; RetroDECK logger/support | 1/5 |
| F-PL-08 | Updates da própria plataforma com canais e rollback | RetroDECK cooker/main + PhaseZero updates/ | 6 |

## UI

| F-UI-01 | AURA Launcher fullscreen (home, biblioteca, jogo, busca, coleções, launch/return) | categoria Big Picture/ES-DE/RetroFE/BigBox; implementação própria | 5 |
| F-UI-02 | AURA UI da central de gerenciamento (dashboard, BIOS, jobs, saves, configurações, lote, logs e migrações) | SteamZero | 4/5 |
| F-UI-03 | QAM adapter opcional via Decky | PhaseZero decky-ws-client.py | 5 |
| F-UI-04 | Acessibilidade (escala, contraste, redução de movimento, remap, glyphs) | novo | 5 |
| F-UI-05 | Theme Engine declarativa: scene graph, layouts, assets, bindings, effect graph e animações GPU-first | SteamZero | 5 |
| F-UI-06 | Theme Studio visual: canvas, árvore, inspector, nodes, timeline, preview, validação e pacote reproduzível | SteamZero | 5/6 |

`F-UI-02` estar tematizada, instalada ou visível **não** implementa `F-UI-01`.
O Launcher pode consumir tokens da AURA UI, mas exige shell, navegação, modelo de
biblioteca, ciclo de lançamento e certificação física próprios.
Theme Engine e Theme Studio também mantêm status independentes: runtime parcial
não prova ferramenta visual, e editor de tokens não prova autoria livre de cenas.
