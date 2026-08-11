# STATUS — SteamZero

<!-- Gerado por tools/project_status.py; nao editar manualmente. -->

Esta e a visao atual do projeto. A fonte de verdade sao os arquivos em `docs/status/items/`; WORKLOG, diagnosticos e relatorios sao evidencias historicas.

| ID | Capacidade | Estagio | Implementacao | Integracao | Verificacao | Proxima acao |
|---|---|---|---|---|---|---|
| SZ-CAST-INTERNET | Partilha de ecra pela internet | planned | planned | isolated | none | Implementar cast internet apenas apos prova LAN estavel e decisao de relay, respeitando remote-cast-session-v1. |
| SZ-CAST-LAN | Partilha de ecra em rede local | implemented | complete | integrated | unit | Prova fim a fim em dois dispositivos LAN reais (operador) e certificacao de hardware. |
| SZ-EMULATION-M10 | Ciclo transacional de emuladores Flatpak | blocked | partial | feature-branch | vm | Repetir somente RetroArch/minimal apos r35 e registrar o payload se a rede falhar. |
| SZ-FRONTEND-ESDE | Importacao de temas ES-DE | implemented | complete | integrated | unit | Promover a verificacao integrada somente junto do frontend que consome o tema. |
| SZ-FRONTEND-LAUNCHBOX | Compatibilidade de importacao LaunchBox | planned | planned | isolated | none | Criar ADR e fixtures antes de prometer compatibilidade LaunchBox. |
| SZ-FRONTEND-RETROFE | Vertical slice e declaracoes RetroFE | verified-dev | complete | integrated | dev | Conectar o frontend M11 sem alegar suporte a LaunchBox antes de um adapter proprio. |
| SZ-GOVERNANCE-STATUS | Estado verificavel e coordenacao de trabalho | verified-dev | complete | feature-branch | dev | Manter status-check e WORKLOG append-only verdes apos harmonizacao a45. |
| SZ-MEDIA-SCRAPING | Metadados e midia por scraping controlado | implemented | complete | integrated | unit | Executar validacao real de providers em ambiente controlado (operador, com credenciais) sem promover scraping a dado confiavel por padrao. |
| SZ-ONLINE-P2P | Jogo online ponto a ponto | planned | planned | isolated | none | Implementar runtime P2P apenas apos escolha de transporte e emuladores, respeitando o contrato netplay-session-v1. |
| SZ-RETROACHIEVEMENTS | RetroAchievements e modo offline | planned | planned | isolated | none | Implementar adapter RetroAchievements apenas apos hardening de keyring e outbox, respeitando achievement-event-v1. |
| SZ-THEME-AURA | Tema nativo AURA | implemented | complete | integrated | unit | Validacao visual e operacional no host (operador): aplicar AURA, preview e rollback no boot direto. |
| SZ-THEME-EDITOR | Editor e marketplace de temas | partial | partial | integrated | unit | Fechar a G39 (cadeia extends acima de MAX_EXTENDS_DEPTH degrada para a paleta padrao sem diagnostico) e cobrir importacao/rollback em uma vertical integrada de UI. |
| SZ-UI-DESKTOP-AUDIT | UI Desktop — auditoria visual e jornadas P0/P1 | verified-dev | partial | feature-branch | dev | Integrar em main e validar fisicamente no Deck. |

Consulte `docs/ACTIVE-WORK.md` antes de criar uma branch ou editar arquivos compartilhados.
