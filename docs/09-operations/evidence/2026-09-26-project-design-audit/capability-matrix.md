# Quadro de capacidades do catálogo

Fotografia do catálogo em 2026-09-26. Fonte: 78 itens individuais e 12 itens agregadores em docs/status/items/*.json. A classificação abaixo preserva os campos publicados no catálogo; ela não transforma implementation=complete em prova de integração, distribuição ou validação física.

## Resumo por domínio

| Domínio | Itens | Completo | Parcial | Planejado | Integrado ao main | Feature branch | Isolado | Released |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| casting | 2 | 1 | 0 | 1 | 1 | 0 | 1 | 0 |
| distribution | 2 | 0 | 2 | 0 | 0 | 2 | 0 | 0 |
| emulation | 14 | 2 | 12 | 0 | 1 | 13 | 0 | 0 |
| frontends | 8 | 6 | 1 | 1 | 6 | 0 | 2 | 0 |
| governance | 6 | 4 | 1 | 1 | 4 | 0 | 2 | 0 |
| media | 6 | 5 | 1 | 0 | 5 | 1 | 0 | 0 |
| online | 2 | 0 | 0 | 2 | 0 | 0 | 2 | 0 |
| platform | 11 | 4 | 7 | 0 | 3 | 8 | 0 | 0 |
| themes | 9 | 3 | 6 | 0 | 7 | 2 | 0 | 0 |
| ui | 18 | 6 | 12 | 0 | 12 | 3 | 1 | 2 |

## Totais e leitura

- Implementação: 31 complete, 42 partial, 5 planned.
- Integração: 39 integrated, 29 feature-branch, 8 isolated, 2 released.
- Operação declarada: 11 ready, 40 degraded, 27 unknown.
- Distribuição declarada: 1 packaged, 33 installed, 44 not-packaged.
- Verificação declarada no catálogo: 31 unit, 13 dev, 27 hw, 1 vm, 6 none.
- Os campos implementation, integration, operation, verification e distribution são eixos distintos. “Completo” não quer dizer integrado, empacotado ou comprovado na release ativa.
- As colunas de evidências e lacunas contam registros no item, não medem qualidade nem atualidade. Os critérios e notas detalhados permanecem no JSON de cada capacidade.

## Itens agregadores

| ID | Camada | Item do catálogo |
|---|---|---|
| SZ-AGG-ADAPTERS | platform | Adapters: integracoes externas sem item proprio |
| SZ-AGG-ASSETS | media | Conteudo empacotado: experiencias, i18n e catalogos |
| SZ-AGG-CORE | governance | Nucleo: paths, erros, transacao e migracoes |
| SZ-AGG-DOMAIN | governance | Dominio: regras de negocio sem item proprio |
| SZ-AGG-INPUT-PROFILES | platform | Perfis de controle empacotados |
| SZ-AGG-JOBS | governance | Jobs em segundo plano e recovery |
| SZ-AGG-PLATFORM-MANIFESTS | platform | Manifests de plataforma empacotados |
| SZ-AGG-PRIVILEGED | distribution | Superficie privilegiada e helpers de host |
| SZ-AGG-SCHEMAS | governance | Schemas versionados do runtime |
| SZ-AGG-SERVICE-API | governance | Daemon e superficie de API |
| SZ-AGG-TESTS | governance | Suite de testes sem item proprio |
| SZ-AGG-TOOLS | governance | Ferramentas de repositorio e harnesses |

## Inventário de cada capacidade individual

| Domínio | Capacidade | Implementação | Integração | Operação | Verificação | Distribuição | Evidências registradas | Lacunas registradas | Critérios de aceite |
|---|---|---|---|---|---|---|---:|---:|---:|
| themes | [Fronteira de confiança do asset-fonte SVG (frente A2)](../../../status/items/aura-asset-sanitizacao.json) | complete | integrated | unknown | unit | not-packaged | 1 | 1 | 5 |
| ui | [AURA Cinema — periféricos de sessão e composição fullscreen](../../../status/items/aura-cinema-completion.json) | partial | integrated | degraded | hw | installed | 29 | 3 | 5 |
| governance | [Contratos canônicos da plataforma AURA (GameRecord, MediaRole, Provenance, EnhancementEntry)](../../../status/items/aura-contracts.json) | complete | isolated | unknown | unit | installed | 3 | 1 | 5 |
| ui | [AURA — evidência física da release instalada](../../../status/items/aura-current-release-evidence-2026-09-20.json) | complete | integrated | ready | hw | installed | 4 | 1 | 5 |
| themes | [Tema ES-DE como superfície ativa da AURA UI](../../../status/items/aura-esde-active-surface-2026-09-17.json) | partial | feature-branch | unknown | dev | not-packaged | 3 | 3 | 5 |
| ui | [Theme Engine — ponte catálogo/mídia real para cena ES-DE](../../../status/items/aura-esde-runtime-bridge-2026-09-20.json) | partial | feature-branch | degraded | unit | installed | 6 | 3 | 6 |
| ui | [AURA Launcher — saída explícita por controle](../../../status/items/aura-launcher-exit.json) | complete | feature-branch | unknown | dev | not-packaged | 1 | 1 | 3 |
| ui | [AURA Launcher — biblioteca fullscreen e lancamento](../../../status/items/aura-launcher.json) | partial | isolated | degraded | hw | installed | 60 | 8 | 6 |
| frontends | [Modelo canônico GameRecord e importadores de metadados (frente A1)](../../../status/items/aura-metadata.json) | partial | isolated | unknown | unit | not-packaged | 10 | 2 | 9 |
| ui | [AURA Launcher — medição física válida de desempenho](../../../status/items/aura-performance-validation-2026-09-16.json) | partial | integrated | degraded | hw | installed | 10 | 2 | 5 |
| governance | [Plano de execução AURA fullscreen e plataforma integrada](../../../status/items/aura-platform-execution-plan.json) | planned | isolated | unknown | none | not-packaged | 1 | 4 | 6 |
| media | [AURA — projeção de mídia com escopo de plataforma](../../../status/items/aura-platform-media-scope-2026-09-20.json) | partial | feature-branch | ready | unit | not-packaged | 2 | 1 | 4 |
| ui | [AURA — ingestão segura de mídia local RetroFE](../../../status/items/aura-retrofe-media-ingestion-2026-09-20.json) | complete | integrated | ready | hw | installed | 4 | 0 | 5 |
| ui | [AURA — projeção determinística de mídia rica](../../../status/items/aura-rich-media-projection-2026-09-16.json) | partial | released | degraded | hw | installed | 5 | 4 | 4 |
| ui | [AURA save-state gallery e contrato de slots](../../../status/items/aura-save-state-gallery.json) | partial | released | degraded | hw | installed | 9 | 0 | 5 |
| media | [Contrato de busca harmonizada do catálogo e mídia](../../../status/items/aura-search-contract-2026-09-16.json) | complete | integrated | ready | dev | not-packaged | 5 | 1 | 5 |
| ui | [AURA Pause, OSD e contrato de sessão](../../../status/items/aura-session-osd.json) | partial | integrated | degraded | hw | installed | 7 | 2 | 5 |
| themes | [AURA UI — sistema visual da central](../../../status/items/aura-ui.json) | complete | integrated | degraded | unit | installed | 5 | 0 | 3 |
| ui | [AURA Cinema — fechamento visual e medição na release instalada](../../../status/items/aura-visual-completion-2026-09-15.json) | partial | integrated | degraded | hw | installed | 14 | 5 | 4 |
| ui | [AURA Cinema — superfície rica integrada e validação física](../../../status/items/aura-visual-rich-surface-2026-09-17.json) | partial | integrated | ready | hw | installed | 9 | 2 | 5 |
| casting | [Partilha de ecra pela internet](../../../status/items/cast-internet.json) | planned | isolated | unknown | none | not-packaged | 2 | 0 | 2 |
| casting | [Partilha de ecra em rede local](../../../status/items/cast-lan.json) | complete | integrated | degraded | unit | installed | 3 | 0 | 2 |
| platform | [Ciclo funcional assincrono de componentes](../../../status/items/component-lifecycle.json) | complete | integrated | degraded | hw | installed | 16 | 0 | 7 |
| emulation | [Perfis de controle e autoconfig gerenciado](../../../status/items/controls-input-profiles.json) | partial | feature-branch | unknown | hw | not-packaged | 8 | 0 | 5 |
| emulation | [Operações longas de emulação com acompanhamento](../../../status/items/emulation-long-operations.json) | partial | feature-branch | ready | hw | installed | 18 | 0 | 6 |
| emulation | [Ciclo transacional de emuladores Flatpak](../../../status/items/emulation-m10.json) | partial | feature-branch | degraded | vm | installed | 3 | 2 | 3 |
| emulation | [Contexto de emulação por plataforma](../../../status/items/emulation-platform-context.json) | partial | feature-branch | degraded | unit | not-packaged | 4 | 2 | 5 |
| emulation | [Isolamento de saves e mídia por plataforma](../../../status/items/emulation-platform-scope.json) | partial | feature-branch | degraded | unit | not-packaged | 5 | 2 | 5 |
| emulation | [Validação sistema a sistema de dumps reais no host](../../../status/items/emulation-real-dump-validation-2026-09-19.json) | partial | integrated | degraded | hw | installed | 42 | 9 | 5 |
| emulation | [Remediação resiliente de runtimes, firmware, multidisco e saves](../../../status/items/emulation-runtime-remediation-2026-09-20.json) | partial | feature-branch | unknown | unit | not-packaged | 5 | 3 | 5 |
| emulation | [Contratos de gestão de armazenamento da emulação](../../../status/items/emulation-storage-management.json) | partial | feature-branch | degraded | unit | not-packaged | 3 | 2 | 6 |
| emulation | [Estatísticas de armazenamento por plataforma](../../../status/items/emulation-storage-platform-scope.json) | partial | feature-branch | degraded | unit | not-packaged | 3 | 3 | 4 |
| emulation | [Read model de armazenamento da emulação](../../../status/items/emulation-storage-readmodel.json) | partial | feature-branch | degraded | unit | not-packaged | 6 | 3 | 5 |
| emulation | [Melhorias por jogo agnósticas de plataforma](../../../status/items/emulator-enhancements.json) | complete | feature-branch | unknown | unit | not-packaged | 9 | 0 | 6 |
| frontends | [Custom systems do ES-DE idempotentes](../../../status/items/frontend-esde-systems.json) | complete | integrated | unknown | unit | not-packaged | 1 | 0 | 4 |
| frontends | [Importacao de temas ES-DE](../../../status/items/frontend-esde.json) | complete | integrated | degraded | unit | not-packaged | 5 | 1 | 3 |
| frontends | [Compatibilidade de importacao LaunchBox](../../../status/items/frontend-launchbox.json) | planned | isolated | unknown | none | not-packaged | 0 | 1 | 2 |
| frontends | [Superficie M11: comando frontends na CLI e no daemon](../../../status/items/frontend-m11-surface.json) | complete | integrated | unknown | unit | not-packaged | 2 | 0 | 3 |
| frontends | [Vertical slice e declaracoes RetroFE](../../../status/items/frontend-retrofe.json) | complete | integrated | degraded | dev | not-packaged | 3 | 1 | 2 |
| frontends | [Manifests do Steam ROM Manager idempotentes](../../../status/items/frontend-srm.json) | complete | integrated | unknown | unit | not-packaged | 1 | 0 | 4 |
| frontends | [Atalhos do Steam (shortcuts.vdf) transacionais](../../../status/items/frontend-steam-shortcuts.json) | complete | integrated | unknown | unit | not-packaged | 1 | 0 | 4 |
| ui | [Prontidão honesta do Feral GameMode](../../../status/items/gamemode-readiness-g29.json) | complete | integrated | degraded | hw | installed | 2 | 1 | 5 |
| governance | [Estado verificavel e coordenacao de trabalho](../../../status/items/governance-status.json) | complete | integrated | degraded | dev | installed | 14 | 0 | 4 |
| emulation | [Prontidão resiliente de PS4, PS5, X68000 e Xbox](../../../status/items/high-end-runtime-readiness-2026-09-20.json) | partial | feature-branch | degraded | unit | not-packaged | 4 | 5 | 6 |
| distribution | [Update e rollback transacionais do host](../../../status/items/host-update-transactional.json) | partial | feature-branch | ready | hw | installed | 12 | 1 | 10 |
| governance | [Recovery de jobs, auditoria e cleanup recuperável](../../../status/items/job-recovery-doctor-g25.json) | complete | integrated | degraded | dev | installed | 3 | 0 | 5 |
| platform | [Biblioteca canonica unica](../../../status/items/library-canonical.json) | partial | integrated | degraded | hw | installed | 21 | 7 | 9 |
| platform | [Conversão de biblioteca por contrato de plataforma](../../../status/items/library-conversion-contract.json) | complete | feature-branch | unknown | unit | not-packaged | 2 | 0 | 4 |
| governance | [Reconciliação seletiva de worktrees com a main](../../../status/items/main-reconciliation-2026-09-26.json) | partial | integrated | degraded | dev | installed | 8 | 4 | 6 |
| media | [Auditoria do pipeline de mídia por plataforma](../../../status/items/media-audit-platform-scope.json) | complete | integrated | degraded | hw | installed | 4 | 3 | 4 |
| media | [Estatísticas do pipeline de mídia por plataforma](../../../status/items/media-pipeline-platform-scope.json) | complete | integrated | degraded | hw | installed | 7 | 3 | 4 |
| media | [Filtro de provedores de mídia por plataforma](../../../status/items/media-provider-platform-filter.json) | complete | integrated | degraded | unit | not-packaged | 2 | 0 | 3 |
| media | [Metadados e midia por scraping controlado](../../../status/items/media-scraping.json) | complete | integrated | degraded | hw | installed | 8 | 4 | 4 |
| platform | [Reconciliação de descritor multidisco](../../../status/items/multidisc-descriptor-reconciliation.json) | partial | feature-branch | unknown | dev | not-packaged | 13 | 3 | 9 |
| emulation | [Materialização transacional de multidisco e ingestão de archives](../../../status/items/multidisc-materialization-ingestion-2026-09-20.json) | partial | feature-branch | unknown | unit | not-packaged | 4 | 3 | 6 |
| ui | [AURA — identidade estável no descritor e na troca de disco](../../../status/items/multidisc-session-disc-identity.json) | partial | integrated | ready | hw | not-packaged | 3 | 1 | 5 |
| online | [Jogo online ponto a ponto](../../../status/items/online-p2p.json) | planned | isolated | unknown | none | not-packaged | 2 | 1 | 2 |
| platform | [Core por sistema em plataformas agrupadas](../../../status/items/platform-core-per-system.json) | partial | feature-branch | unknown | unit | not-packaged | 4 | 2 | 5 |
| platform | [Catálogo de plataforma PlayStation 4 (shadPS4)](../../../status/items/platform-ps4-catalog.json) | partial | feature-branch | unknown | unit | not-packaged | 3 | 1 | 6 |
| platform | [Instalação física do shadPS4 e lançamento PS4](../../../status/items/platform-ps4-physical-install.json) | partial | feature-branch | degraded | dev | not-packaged | 3 | 1 | 5 |
| platform | [Catálogo experimental de plataforma PlayStation 5 (SharpEmu)](../../../status/items/platform-ps5-catalog.json) | partial | feature-branch | unknown | unit | not-packaged | 19 | 1 | 7 |
| platform | [Escopo de requisitos por plataforma](../../../status/items/platform-requirement-scope.json) | complete | feature-branch | unknown | unit | not-packaged | 3 | 3 | 4 |
| platform | [Catálogo de plataforma PlayStation Vita](../../../status/items/platform-vita-catalog.json) | partial | integrated | degraded | hw | installed | 8 | 2 | 4 |
| emulation | [Download assistido do firmware oficial do PS3](../../../status/items/ps3-official-firmware-download.json) | complete | feature-branch | unknown | unit | not-packaged | 2 | 2 | 7 |
| ui | [Atribuição de recursos e probe QML confiável](../../../status/items/resource-qml-probe-g30-g31.json) | complete | integrated | degraded | dev | installed | 2 | 2 | 5 |
| online | [RetroAchievements e modo offline](../../../status/items/retroachievements.json) | planned | isolated | unknown | none | not-packaged | 2 | 1 | 2 |
| platform | [Contrato de verificação do componente SharpEmu](../../../status/items/sharpemu-component-smoke-contract.json) | complete | feature-branch | ready | unit | not-packaged | 1 | 1 | 3 |
| ui | [Diagnóstico do sistema orientado à recuperação](../../../status/items/system-diagnostics-guidance.json) | complete | integrated | degraded | dev | not-packaged | 5 | 1 | 4 |
| governance | [Isolamento de estado e diretório temporário da suíte](../../../status/items/test-state-isolation-g26.json) | complete | integrated | ready | dev | not-packaged | 4 | 0 | 4 |
| themes | [Theme Engine — cenas e efeitos declarativos](../../../status/items/theme-engine.json) | partial | integrated | degraded | hw | installed | 49 | 1 | 6 |
| themes | [Temas ES-DE: renderizacao da cena compilada](../../../status/items/theme-esde-scene-render.json) | partial | integrated | degraded | hw | installed | 11 | 3 | 12 |
| themes | [Temas ES-DE: compilacao de layout, aquisicao e instalacao transacional](../../../status/items/theme-import-esde-layout.json) | partial | integrated | degraded | hw | not-packaged | 10 | 2 | 12 |
| themes | [Importação segura de cenas RetroFE](../../../status/items/theme-import-retrofe.json) | complete | integrated | ready | hw | installed | 10 | 1 | 5 |
| themes | [Importação de temas acessível pela área Temas](../../../status/items/theme-import-surface.json) | partial | feature-branch | degraded | unit | not-packaged | 8 | 1 | 5 |
| themes | [Theme Studio — autoria visual de temas](../../../status/items/theme-studio.json) | partial | integrated | degraded | hw | installed | 19 | 3 | 8 |
| ui | [UI Desktop — auditoria visual e jornadas P0/P1](../../../status/items/ui-desktop-audit.json) | partial | feature-branch | degraded | dev | not-packaged | 49 | 2 | 19 |
| ui | [Ícones oficiais empacotados de emuladores, serviços e plataformas](../../../status/items/ui-packaged-icons.json) | partial | integrated | unknown | unit | packaged | 4 | 3 | 4 |
| distribution | [Release funcional 2.0 harmonizada](../../../status/items/v2-harmonized-functional-release.json) | partial | feature-branch | unknown | none | not-packaged | 1 | 0 | 7 |
