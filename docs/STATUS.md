# STATUS — SteamZero

<!-- Gerado por tools/project_status.py; nao editar manualmente. -->

Esta e a visao atual do projeto. A fonte de verdade sao os arquivos em `docs/status/items/`; WORKLOG, diagnosticos e relatorios sao evidencias historicas.

| ID | Capacidade | Estagio | Implementacao | Integracao | Verificacao | Proxima acao |
|---|---|---|---|---|---|---|
| SZ-CAST-INTERNET | Partilha de ecra pela internet | planned | planned | isolated | none | Escrever ADR de NAT, relay, privacidade e limite de banda. |
| SZ-CAST-LAN | Partilha de ecra em rede local | partial | partial | integrated | unit | Fechar a flakiness IPC G32 e executar prova em dois dispositivos LAN. |
| SZ-EMULATION-M10 | Ciclo transacional de emuladores Flatpak | blocked | partial | feature-branch | vm | Repetir somente RetroArch/minimal apos r35 e registrar o payload se a rede falhar. |
| SZ-FRONTEND-ESDE | Importacao de temas ES-DE | implemented | complete | integrated | unit | Promover a verificacao integrada somente junto do frontend que consome o tema. |
| SZ-FRONTEND-LAUNCHBOX | Compatibilidade de importacao LaunchBox | planned | planned | isolated | none | Criar ADR e fixtures antes de prometer compatibilidade LaunchBox. |
| SZ-FRONTEND-RETROFE | Vertical slice e declaracoes RetroFE | verified-dev | complete | integrated | dev | Conectar o frontend M11 sem alegar suporte a LaunchBox antes de um adapter proprio. |
| SZ-GOVERNANCE-STATUS | Estado verificavel e coordenacao de trabalho | verified-dev | complete | feature-branch | dev | Integrar este catalogo antes de abrir a proxima frente paralela. |
| SZ-MEDIA-SCRAPING | Metadados e midia por scraping controlado | partial | partial | integrated | unit | Executar validacao real de providers em ambiente controlado sem promover scraping a dado confiavel por padrao. |
| SZ-ONLINE-P2P | Jogo online ponto a ponto | planned | planned | isolated | none | Definir ADR de transporte, identidade, abuso e compatibilidade de emuladores. |
| SZ-RETROACHIEVEMENTS | RetroAchievements e modo offline | planned | planned | isolated | none | Definir contrato de credenciais, cache e modo hardcore antes de integrar API externa. |
| SZ-THEME-AURA | Tema nativo AURA | partial | partial | integrated | unit | Definir o baseline visual AURA e validar o fluxo completo em QML. |
| SZ-THEME-EDITOR | Editor e marketplace de temas | partial | partial | integrated | unit | Cobrir preview, importacao e rollback em uma vertical integrada de UI. |

Consulte `docs/ACTIVE-WORK.md` antes de criar uma branch ou editar arquivos compartilhados.
