# STATUS — SteamZero

<!-- Gerado por tools/project_status.py; nao editar manualmente. -->

Esta e a visao atual do projeto. A fonte de verdade sao os arquivos em `docs/status/items/`; WORKLOG, diagnosticos e relatorios sao evidencias historicas.

| ID | Capacidade | Estagio | Implementacao | Integracao | Verificacao | Operacao | Distribuicao | Proxima acao |
|---|---|---|---|---|---|---|---|---|
| SZ-CAST-INTERNET | Partilha de ecra pela internet | planned | planned | isolated | none | unknown | not-packaged | Implementar cast internet apenas apos prova LAN estavel e decisao de relay, respeitando remote-cast-session-v1. |
| SZ-CAST-LAN | Partilha de ecra em rede local | implemented | complete | integrated | unit | degraded | installed | Prova fim a fim em dois dispositivos LAN reais (operador) e certificacao de hardware. |
| SZ-EMULATION-M10 | Ciclo transacional de emuladores Flatpak | verified-vm | partial | feature-branch | vm | degraded | installed | Repetir somente RetroArch/minimal apos r35 e registrar o payload se a rede falhar. |
| SZ-FRONTEND-ESDE | Importacao de temas ES-DE | implemented | complete | integrated | unit | ready | not-packaged | Promover a verificacao integrada somente junto do frontend que consome o tema. |
| SZ-FRONTEND-ESDE-SYSTEMS | Custom systems do ES-DE idempotentes | implemented | complete | feature-branch | unit | unknown | not-packaged | Validar contra uma instalacao real do ES-DE no host (operador). |
| SZ-FRONTEND-LAUNCHBOX | Compatibilidade de importacao LaunchBox | planned | planned | isolated | none | unknown | not-packaged | Criar ADR e fixtures antes de prometer compatibilidade LaunchBox. |
| SZ-FRONTEND-M11-SURFACE | Superficie M11: comando frontends na CLI e no daemon | implemented | complete | feature-branch | unit | unknown | not-packaged | Cobrir cli/main.py e service/methods.py por itens agregadores de diretorio na etapa de catalogo; este item responde apenas pela superficie frontends dentro deles. |
| SZ-FRONTEND-RETROFE | Vertical slice e declaracoes RetroFE | verified-dev | complete | integrated | dev | ready | not-packaged | Conectar o RetroFE aos adapters M11 (SZ-FRONTEND-SRM, SZ-FRONTEND-ESDE-SYSTEMS, SZ-FRONTEND-STEAM-SHORTCUTS) sem alegar suporte a LaunchBox antes de um adapter proprio. |
| SZ-FRONTEND-SRM | Manifests do Steam ROM Manager idempotentes | implemented | complete | feature-branch | unit | unknown | not-packaged | Validar contra uma instalacao real do Steam ROM Manager no host (operador). |
| SZ-FRONTEND-STEAM-SHORTCUTS | Atalhos do Steam (shortcuts.vdf) transacionais | implemented | complete | feature-branch | unit | unknown | not-packaged | Exercitar contra um shortcuts.vdf real do operador antes de promover a verificacao integrada. |
| SZ-GOVERNANCE-STATUS | Estado verificavel e coordenacao de trabalho | verified-dev | complete | feature-branch | dev | ready | not-packaged | Manter status-check e WORKLOG append-only verdes apos harmonizacao a45. |
| SZ-MEDIA-SCRAPING | Metadados e midia por scraping controlado | implemented | complete | integrated | unit | degraded | installed | Executar validacao real de providers em ambiente controlado (operador, com credenciais) sem promover scraping a dado confiavel por padrao. |
| SZ-ONLINE-P2P | Jogo online ponto a ponto | planned | planned | isolated | none | unknown | not-packaged | Implementar runtime P2P apenas apos escolha de transporte e emuladores, respeitando o contrato netplay-session-v1. |
| SZ-RETROACHIEVEMENTS | RetroAchievements e modo offline | planned | planned | isolated | none | unknown | not-packaged | Implementar adapter RetroAchievements apenas apos hardening de keyring e outbox, respeitando achievement-event-v1. |
| SZ-THEME-AURA | Tema nativo AURA | implemented | complete | integrated | unit | degraded | installed | Validacao visual e operacional no host (operador): aplicar AURA, preview e rollback no boot direto. |
| SZ-THEME-EDITOR | Editor e marketplace de temas | partial | partial | integrated | unit | degraded | installed | Fechar a G39 (cadeia extends acima de MAX_EXTENDS_DEPTH degrada para a paleta padrao sem diagnostico) e cobrir importacao/rollback em uma vertical integrada de UI. |
| SZ-UI-DESKTOP-AUDIT | UI Desktop — auditoria visual e jornadas P0/P1 | verified-dev | partial | feature-branch | dev | degraded | not-packaged | Integrar em main e validar fisicamente no Deck. |

Consulte `docs/ACTIVE-WORK.md` antes de criar uma branch ou editar arquivos compartilhados.
