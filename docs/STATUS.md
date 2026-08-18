# STATUS — SteamZero

<!-- Gerado por tools/project_status.py; nao editar manualmente. -->

Esta e a visao atual do projeto. A fonte de verdade sao os arquivos em `docs/status/items/`; WORKLOG, diagnosticos e relatorios sao evidencias historicas.

| ID | Capacidade | Estagio | Implementacao | Integracao | Verificacao | Operacao | Distribuicao | Proxima acao |
|---|---|---|---|---|---|---|---|---|
| SZ-AGG-ADAPTERS | Adapters: integracoes externas sem item proprio | partial | partial | integrated | none | unknown | installed | Promover a itens proprios os adapters com ciclo transacional e evidencia dedicada. |
| SZ-AGG-ASSETS | Conteudo empacotado: experiencias, i18n e catalogos | partial | partial | integrated | none | unknown | installed | Amarrar cada catalogo empacotado ao item da capacidade que o consome. |
| SZ-AGG-CORE | Nucleo: paths, erros, transacao e migracoes | partial | partial | integrated | none | unknown | installed | Separar migracoes de estado em item proprio, com prova de round-trip por versao. |
| SZ-AGG-DOMAIN | Dominio: regras de negocio sem item proprio | partial | partial | integrated | none | unknown | installed | Promover a itens proprios os recortes de dominio com contrato e teste dedicados. |
| SZ-AGG-INPUT-PROFILES | Perfis de controle empacotados | partial | partial | integrated | none | unknown | installed | Provar que um perfil aplicado tem efeito observavel antes de declarar a capacidade. |
| SZ-AGG-JOBS | Jobs em segundo plano e recovery | partial | partial | integrated | none | unknown | installed | Cobrir recovery de job interrompido por teste dedicado. |
| SZ-AGG-PLATFORM-MANIFESTS | Manifests de plataforma empacotados | partial | partial | integrated | none | unknown | installed | Cobrir a curadoria dos manifests por um item de catalogo de plataformas. |
| SZ-AGG-PRIVILEGED | Superficie privilegiada e helpers de host | partial | partial | integrated | none | unknown | installed | Cobrir cada helper privilegiado por teste de recusa e por checagem de ownership. |
| SZ-AGG-SCHEMAS | Schemas versionados do runtime | partial | partial | integrated | none | unknown | installed | Amarrar cada schema ao item da capacidade que o produz ou consome. |
| SZ-AGG-SERVICE-API | Daemon e superficie de API | partial | partial | integrated | none | unknown | installed | Separar o contrato JSON-RPC em item proprio com fixtures de envelope. |
| SZ-AGG-TESTS | Suite de testes sem item proprio | partial | partial | integrated | none | unknown | installed | Amarrar cada arquivo de teste ao item da capacidade que ele prova, comecando pelos que sustentam evidencia declarada. |
| SZ-AGG-TOOLS | Ferramentas de repositorio e harnesses | partial | partial | integrated | none | unknown | installed | Separar o harness de VM e o instalador de host em itens proprios, que ja tem contrato e consequencia de host. |
| SZ-AURA-LAUNCHER | AURA Launcher — biblioteca fullscreen e lancamento | planned | planned | isolated | none | unknown | not-packaged | Definir o vertical slice home-biblioteca-jogo-retorno e implementa-lo com baseline e evidencia fisica separados da AURA UI. |
| SZ-AURA-UI | AURA UI — sistema visual da central | implemented | complete | integrated | unit | degraded | installed | Validar visualmente AURA UI na central real, sem confundir essa prova com o AURA Launcher. |
| SZ-CAST-INTERNET | Partilha de ecra pela internet | planned | planned | isolated | none | unknown | not-packaged | Implementar cast internet apenas apos prova LAN estavel e decisao de relay, respeitando remote-cast-session-v1. |
| SZ-CAST-LAN | Partilha de ecra em rede local | implemented | complete | integrated | unit | degraded | installed | Exercitar pareamento e transmissao contra um receptor real (operador): a descoberta voltou a responder, o caminho seguinte nunca foi percorrido em producao. |
| SZ-EMULATION-M10 | Ciclo transacional de emuladores Flatpak | verified-vm | partial | feature-branch | vm | degraded | installed | Escrever o autoconfig gerenciado do RetroArch a partir da traducao RetroPad (resolver indice contra o pad real, arquivo com marcador, nunca editar o retroarch.cfg do usuario) e provar install/verify/rollback de um emulador no host. |
| SZ-FRONTEND-ESDE | Importacao de temas ES-DE | implemented | complete | integrated | unit | ready | not-packaged | Ligar o importador a uma rota de UI (G42): hoje ele so e alcancavel por linha de comando, o que nao serve ao usuario que quer trazer um tema ES-DE. |
| SZ-FRONTEND-ESDE-SYSTEMS | Custom systems do ES-DE idempotentes | implemented | complete | integrated | unit | unknown | not-packaged | Validar contra uma instalacao real do ES-DE no host (operador). |
| SZ-FRONTEND-LAUNCHBOX | Compatibilidade de importacao LaunchBox | planned | planned | isolated | none | unknown | not-packaged | Criar ADR e fixtures antes de prometer compatibilidade LaunchBox. |
| SZ-FRONTEND-M11-SURFACE | Superficie M11: comando frontends na CLI e no daemon | implemented | complete | integrated | unit | unknown | not-packaged | Cobrir cli/main.py e service/methods.py por itens agregadores de diretorio na etapa de catalogo; este item responde apenas pela superficie frontends dentro deles. |
| SZ-FRONTEND-RETROFE | Vertical slice e declaracoes RetroFE | verified-dev | complete | integrated | dev | ready | not-packaged | Conectar o RetroFE aos adapters M11 (SZ-FRONTEND-SRM, SZ-FRONTEND-ESDE-SYSTEMS, SZ-FRONTEND-STEAM-SHORTCUTS) sem alegar suporte a LaunchBox antes de um adapter proprio. |
| SZ-FRONTEND-SRM | Manifests do Steam ROM Manager idempotentes | implemented | complete | integrated | unit | unknown | not-packaged | Validar contra uma instalacao real do Steam ROM Manager no host (operador). |
| SZ-FRONTEND-STEAM-SHORTCUTS | Atalhos do Steam (shortcuts.vdf) transacionais | implemented | complete | integrated | unit | unknown | not-packaged | Expor a marcacao do atalho de interface na UI e validar contra um shortcuts.vdf real do operador antes de promover a verificacao integrada. |
| SZ-GOVERNANCE-STATUS | Estado verificavel e coordenacao de trabalho | verified-dev | complete | feature-branch | dev | ready | not-packaged | Manter status-check e WORKLOG append-only verdes apos harmonizacao a45. |
| SZ-MEDIA-SCRAPING | Metadados e midia por scraping controlado | implemented | complete | integrated | unit | degraded | installed | Mostrar o estado vaultVolatile na UI com texto acionavel (o cofre perdeu o valor, nao voce esqueceu) e fechar a G40 (systemeid do ScreenScraper). |
| SZ-ONLINE-P2P | Jogo online ponto a ponto | planned | planned | isolated | none | unknown | not-packaged | Implementar runtime P2P apenas apos escolha de transporte e emuladores, respeitando o contrato netplay-session-v1. |
| SZ-RETROACHIEVEMENTS | RetroAchievements e modo offline | planned | planned | isolated | none | unknown | not-packaged | Implementar adapter RetroAchievements apenas apos hardening de keyring e outbox, respeitando achievement-event-v1. |
| SZ-THEME-ENGINE | Theme Engine — cenas e efeitos declarativos | partial | partial | integrated | unit | degraded | installed | Avançar carousel declarativo. Medição física permanece na release instalada identificada. |
| SZ-THEME-STUDIO | Theme Studio — autoria visual de temas | partial | partial | integrated | unit | degraded | installed | Capturar evidência física do canvas na próxima release instalada. |
| SZ-UI-DESKTOP-AUDIT | UI Desktop — auditoria visual e jornadas P0/P1 | verified-dev | partial | feature-branch | dev | degraded | not-packaged | Integrar em main e validar fisicamente no Deck. |

Consulte `docs/ACTIVE-WORK.md` antes de criar uma branch ou editar arquivos compartilhados.
