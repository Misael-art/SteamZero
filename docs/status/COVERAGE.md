# COVERAGE — SteamZero

<!-- Gerado por tools/project_status.py; nao editar manualmente. -->

Visao complementar ao STATUS: quanto codigo cada capacidade responde e
onde uma alegacao nao tem evidencia que a sustente.

| ID | Arquivos no escopo | Evidencias | Aprovadas | Verificacao | Observacao |
|---|---|---|---|---|---|
| SZ-AGG-ADAPTERS | 113 | 0 | 0 | none | custodia declarada; nenhuma capacidade provada |
| SZ-AGG-ASSETS | 10 | 0 | 0 | none | custodia declarada; nenhuma capacidade provada |
| SZ-AGG-CORE | 41 | 1 | 1 | none | custodia declarada; nenhuma capacidade provada |
| SZ-AGG-DOMAIN | 108 | 0 | 0 | none | custodia declarada; nenhuma capacidade provada |
| SZ-AGG-INPUT-PROFILES | 20 | 0 | 0 | none | custodia declarada; nenhuma capacidade provada |
| SZ-AGG-JOBS | 3 | 0 | 0 | none | custodia declarada; nenhuma capacidade provada |
| SZ-AGG-PLATFORM-MANIFESTS | 63 | 0 | 0 | none | custodia declarada; nenhuma capacidade provada |
| SZ-AGG-PRIVILEGED | 7 | 0 | 0 | none | custodia declarada; nenhuma capacidade provada |
| SZ-AGG-SCHEMAS | 51 | 0 | 0 | none | custodia declarada; nenhuma capacidade provada |
| SZ-AGG-SERVICE-API | 11 | 0 | 0 | none | custodia declarada; nenhuma capacidade provada |
| SZ-AGG-TESTS | 447 | 0 | 0 | none | custodia declarada; nenhuma capacidade provada |
| SZ-AGG-TOOLS | 39 | 0 | 0 | none | custodia declarada; nenhuma capacidade provada |
| SZ-AURA-ASSET-SANITIZACAO | 2 | 1 | 1 | unit |  |
| SZ-AURA-CONTRACTS | 38 | 3 | 3 | unit |  |
| SZ-AURA-LAUNCHER | 204 | 35 | 27 | hw |  |
| SZ-AURA-METADATA | 18 | 8 | 8 | unit |  |
| SZ-AURA-PLATFORM-EXECUTION-PLAN | 5 | 1 | 0 | none |  |
| SZ-AURA-UI | 16 | 5 | 4 | unit |  |
| SZ-CAST-INTERNET | 44 | 2 | 1 | none |  |
| SZ-CAST-LAN | 6 | 2 | 2 | unit |  |
| SZ-COMPONENT-LIFECYCLE | 23 | 12 | 10 | hw |  |
| SZ-CONTROLS-INPUT-PROFILES | 16 | 8 | 4 | hw |  |
| SZ-EMULATION-ENHANCEMENTS | 24 | 9 | 9 | unit |  |
| SZ-EMULATION-LONG-OPERATIONS | 28 | 18 | 12 | hw |  |
| SZ-EMULATION-M10 | 6 | 3 | 2 | vm |  |
| SZ-EMULATION-PLATFORM-CONTEXT | 3 | 4 | 2 | unit |  |
| SZ-EMULATION-PLATFORM-SCOPE | 2 | 5 | 4 | unit |  |
| SZ-EMULATION-STORAGE-MANAGEMENT | 2 | 3 | 2 | unit |  |
| SZ-EMULATION-STORAGE-PLATFORM-SCOPE | 5 | 3 | 2 | unit |  |
| SZ-EMULATION-STORAGE-READMODEL | 6 | 6 | 5 | unit |  |
| SZ-FRONTEND-ESDE | 2 | 5 | 2 | unit |  |
| SZ-FRONTEND-ESDE-SYSTEMS | 3 | 1 | 1 | unit |  |
| SZ-FRONTEND-LAUNCHBOX | 1 | 0 | 0 | none | sem evidencia registrada |
| SZ-FRONTEND-M11-SURFACE | 5 | 2 | 2 | unit |  |
| SZ-FRONTEND-RETROFE | 5 | 2 | 1 | dev |  |
| SZ-FRONTEND-SRM | 3 | 1 | 1 | unit |  |
| SZ-FRONTEND-STEAM-SHORTCUTS | 2 | 1 | 1 | unit |  |
| SZ-GOVERNANCE-STATUS | 22 | 7 | 5 | dev |  |
| SZ-HOST-UPDATE-TRANSACTIONAL | 18 | 12 | 9 | hw |  |
| SZ-LIBRARY-CANONICAL | 89 | 10 | 7 | dev |  |
| SZ-LIBRARY-CONVERSION-CONTRACT | 4 | 2 | 2 | unit |  |
| SZ-MEDIA-AUDIT-PLATFORM-SCOPE | 4 | 3 | 2 | unit |  |
| SZ-MEDIA-PIPELINE-PLATFORM-SCOPE | 2 | 3 | 2 | unit |  |
| SZ-MEDIA-PROVIDER-PLATFORM-FILTER | 10 | 2 | 2 | unit |  |
| SZ-MEDIA-SCRAPING | 29 | 6 | 6 | unit |  |
| SZ-ONLINE-P2P | 37 | 2 | 1 | none |  |
| SZ-PLATFORM-CORE-PER-SYSTEM | 78 | 4 | 3 | unit |  |
| SZ-PLATFORM-REQUIREMENT-SCOPE | 7 | 3 | 2 | unit |  |
| SZ-PLATFORM-VITA-CATALOG | 5 | 3 | 2 | unit |  |
| SZ-RETROACHIEVEMENTS | 41 | 2 | 1 | none |  |
| SZ-SYSTEM-DIAGNOSTICS-GUIDANCE | 2 | 3 | 2 | unit |  |
| SZ-THEME-ENGINE | 78 | 37 | 34 | hw |  |
| SZ-THEME-ESDE-SCENE-RENDER | 18 | 8 | 7 | hw |  |
| SZ-THEME-IMPORT-ESDE-LAYOUT | 32 | 10 | 10 | hw |  |
| SZ-THEME-IMPORT-RETROFE | 10 | 10 | 9 | hw |  |
| SZ-THEME-IMPORT-SURFACE | 4 | 8 | 7 | unit |  |
| SZ-THEME-STUDIO | 85 | 18 | 15 | hw |  |
| SZ-UI-DESKTOP-AUDIT | 388 | 41 | 26 | dev |  |
| SZ-UI-PACKAGED-ICONS | 51 | 4 | 2 | unit |  |
| SZ-V2-HARMONIZED-FUNCTIONAL-RELEASE | 2 | 1 | 0 | none |  |

Arquivos em `src/`: **563**. Sob agregador apenas, sem item de capacidade: **287** (50%). Esse numero e o tamanho real do runtime que tem dono declarado e nenhuma capacidade provada; ele deve cair conforme recortes viram itens proprios, e subir e sinal de codigo novo entrando sem capacidade declarada.
