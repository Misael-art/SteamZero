# Radiografia consultiva priorizada

## 1. Veredito executivo

O SteamZero tem um núcleo operacional honesto e um AURA Launcher já capaz de
buscar, abrir e recuperar um jogo real por teclado. A experiência, porém, ainda
parece uma central administrativa em estado de diagnóstico, não uma plataforma
de jogos pronta: o acervo fullscreen não tem artwork suficiente, a central
mostra perfil desatualizado com contraste fraco, e a aba Temas perde o catálogo
na bridge embora a CLI conheça os temas.

| Área | Nota | Evidência e leitura UX |
|---|---:|---|
| Central / Visão geral | 5 | Hierarquia limpa e vazio acionável; alerta persistente e baixo contraste. |
| Central / Emulação | 5 | Contratos ricos, mas estados visuais atuais chegam vazios/aguardando backend. |
| Central / Steam | 5 | Escopos e dependências são claros; pouca confirmação física no host. |
| Central / Perfis | 4 | Perfil recomendado existe, mas “não aplicado” domina a tela e os controles são discretos. |
| Central / Saves e Sync | 5 | Estado read-only honesto; sem provider não há jornada. |
| Central / Transmissão | 4 | Ações existem, mas orquestrador não configurado torna a superfície parecida com protótipo. |
| Central / Sistema | 6 | Diagnóstico explica causa e impacto; recuperação QML é limitada. |
| Central / Biblioteca | 5 | Contagens e estados úteis, mas cobertura de arte irregular. |
| AURA Launcher / Big Picture | 6 | Busca, jogo Steam e retorno provados; catálogo e atalho Big Picture não. |
| Tema / Theme Engine | 6 | Engine declarativa e degradação são fortes; ativação na central não converge. |
| Theme Studio | 4 | Canvas/árvore/inspector existem em contrato; autoria direta continua ausente. |
| Emulação / ciclo de vida | 6 | Switch tem ciclo físico; demais plataformas não têm a mesma prova. |
| Armazenamento | 3 | Read model é promissor, mas mover/comprimir/desinstalar permanece sem UX ponta a ponta. |
| Mídia / Biblioteca | 4 | Quota é diagnosticada no job, mas a UI não traduz o pipeline em próximos passos. |
| Frontends / integração | 3 | Contratos idempotentes, nenhum SRM/ES-DE real detectado no host. |
| Diagnóstico / operação | 6 | CLI fornece causa, orphan staging e convergência; ação recuperável pela QML falta. |
| Casting | 3 | LAN degradado/não configurado; internet planejada. |
| Acessibilidade | 4 | Foco e targets aparecem nos contratos, mas alerta, rodapé e estados disabled falham em contraste. |

## 2. Itens implementados: critérios e gaps

Legenda: `C` confirmado no host/release; `P` parcialmente confirmado por
contrato/teste ou por evidência incompleta; `R` refutado pela observação atual;
`N` não validado por falta de alvo físico, provider ou dependência. `c1..cn`
referem-se, na ordem, aos `acceptanceCriteria` do JSON do item; os textos
canônicos permanecem na fonte de verdade. Gaps são explicitamente confirmados
quando a observação reproduziu a condição, e “N” quando não houve rota segura.

| Item | Critérios de aceite observados | Gaps / veredito |
|---|---|---|
| SZ-AURA-LAUNCHER | `C` home, busca, página, launch/return; `N` catálogo integral, foco por 60+ movimentos e fade | `GAP-LAUNCHER-REAL-CATALOG-PHYSICAL` confirmado visualmente; `GAP-LAUNCHER-RETURN-FADES-PHYSICAL` N |
| SZ-AURA-UI | `C` identidade/tokens versionados e testes; `P` aplicação visual atual | sem gap declarado; perfil desatualizado e contraste observados |
| SZ-CAST-INTERNET | `N` todos | planejado, não empacotado |
| SZ-CAST-LAN | `P` contratos/testes; `R` jornada real | UI/CLI sem orquestrador configurado |
| SZ-COMPONENT-LIFECYCLE | `C` jobs, cancelamento e rollback em histórico; `N` nova matriz completa | `P`, estado do host tem 31/34 instalados |
| SZ-CONTROLS-INPUT-PROFILES | `P` contrato/autoconfig; `N` confirmação no jogo real | não empacotado; prova física pendente |
| SZ-EMULATION-ENHANCEMENTS | `P` contrato/testes; `N` impacto físico por jogo | implementação completa, sem promoção física |
| SZ-EMULATION-LONG-OPERATIONS | `C` jobs concluídos/cancelados/recuperados; `P` UI em execução | `P`, sem nova operação mutável nesta auditoria |
| SZ-EMULATION-M10 | `P` VM/transação; `N` matriz física | `DEBT-A7`, `GAP-G45` confirmados como estado parcial |
| SZ-EMULATION-PLATFORM-CONTEXT | `C` contexto Switch/62 plataformas no CLI; `N` fallback físico sem backend | gaps de card/físico confirmados |
| SZ-EMULATION-PLATFORM-SCOPE | `P` isolamento por contrato; `N` ciclo físico fora Switch | gaps de card/físico confirmados |
| SZ-EMULATION-STORAGE-MANAGEMENT | `P` contrato; `N` mover/comprimir/desinstalar pela UI | `GAP-STORAGE-MOVE-UI-DESTINATION` confirmado como ausência de jornada |
| SZ-EMULATION-STORAGE-PLATFORM-SCOPE | `P` estatísticas no read model; `N` ações físicas | destino, batch e ciclo físico não validados |
| SZ-EMULATION-STORAGE-READMODEL | `P` read model expõe raízes/contagens; `N` mover/comprimir/desinstalar | gaps de armazenamento confirmados por status |
| SZ-FRONTEND-ESDE | `P` importador/testes; `N` ES-DE real | host reporta `es_systems.xml ausente` |
| SZ-FRONTEND-ESDE-SYSTEMS | `P` idempotência em testes; `N` segunda execução no alvo real | host sem ES-DE |
| SZ-FRONTEND-LAUNCHBOX | `N` | planejado; `LEDGER-A10` |
| SZ-FRONTEND-M11-SURFACE | `P` CLI/contrato; `N` efeito no frontend real | não empacotado |
| SZ-FRONTEND-RETROFE | `P` slice determinístico; `R` jornada visual | não há rota RetroFE na central |
| SZ-FRONTEND-SRM | `P` codec/idempotência em testes; `N` alvo real | host reporta manifests ausentes |
| SZ-FRONTEND-STEAM-SHORTCUTS | `P` VDF/ownership em testes; `N` atalho SteamZero no Big Picture | não empacotado; alcance Big Picture não validado |
| SZ-GOVERNANCE-STATUS | `C` catálogo, workstreams e fontes verificáveis; `P` discrepância 43×44 documentada | `DEBT-CI-VISUAL-IMAGE-SEM-SVG` permanece |
| SZ-HOST-UPDATE-TRANSACTIONAL | `C` release ativa, convergência e rollback/roll-forward registrados; `N` nova mutação | operacionalmente pronto, sem alterar nesta auditoria |
| SZ-LIBRARY-CANONICAL | `C` scan real reporta 231 jogos; `P` leitura fullscreen; `R` cobertura visual uniforme | `GAP-LIBRARY-PHYSICAL-CATALOG-COVERAGE` confirmado por placeholders |
| SZ-LIBRARY-CONVERSION-CONTRACT | `P` contratos/testes; `N` conversão real no host | não validado fisicamente |
| SZ-MEDIA-AUDIT-PLATFORM-SCOPE | `P` auditoria/job; `N` clareza UI | `GAP-MEDIA-UI-PIPELINE-CLARITY` confirmado |
| SZ-MEDIA-PIPELINE-PLATFORM-SCOPE | `P` contagem/job e quota; `N` UI completa | `GAP-MEDIA-UI-PIPELINE-CLARITY` confirmado |
| SZ-MEDIA-PROVIDER-PLATFORM-FILTER | `P` filtros em teste; `N` provider real | não validado |
| SZ-MEDIA-SCRAPING | `C` quota classificada e jobs terminalizados; `N` nova mídia física | `GAP-G44`, `LEDGER-A12`, `LEDGER-A7` permanecem |
| SZ-ONLINE-P2P | `N` | planejado; `LEDGER-A6` |
| SZ-PLATFORM-CORE-PER-SYSTEM | `P` matriz no read model; `N` cobertura física | gaps de release/adapter confirmados |
| SZ-PLATFORM-REQUIREMENT-SCOPE | `C` Switch declara keys/firmware; `P` ausência PS3/Vita | `GAP-FIRMWARE-PS3-STORE-NOT-WIRED`, `GAP-PLATFORM-PSVITA-ABSENT` confirmados |
| SZ-PLATFORM-VITA-CATALOG | `C` Vita3K ausente é reportado; `N` catálogo jogável | gaps de adapter/store confirmados |
| SZ-RETROACHIEVEMENTS | `N` | planejado; `LEDGER-A9` |
| SZ-SYSTEM-DIAGNOSTICS-GUIDANCE | `C` CLI dá causa/orientação; `R` QML não oferece recuperação equivalente | `GAP-SYSTEM-DIAGNOSTICS-QML-RECOVERY` confirmado |
| SZ-THEME-ENGINE | `C` CLI expõe tema ativo e receita diagnóstica; `P` cena/performance física | parcial; engine não promove Theme Studio/AURA Launcher |
| SZ-THEME-ESDE-SCENE-RENDER | `C` compilação/render de preview histórico; `R` navegação integrada à central | `GAP-THEME-ESDE-SCENE-NOT-RENDERED` confirmado |
| SZ-THEME-IMPORT-ESDE-LAYOUT | `P` compilação/validação; `N` aquisição/instalação nesta sessão | gap de ativação permanece |
| SZ-THEME-IMPORT-RETROFE | `P` inspeção segura backend; `R` entrada visual/asset copy | `GAP-THEME-RETROFE-QML-ENTRY` e asset copy confirmados |
| SZ-THEME-IMPORT-SURFACE | `P` contratos; `R` catálogo da aba Temas ausente | `GAP-THEME-STUDIO-PHYSICAL-CANVAS` confirmado |
| SZ-THEME-STUDIO | `P` canvas/árvore/inspector em contratos e evidência anterior; `R` edição direta | gaps físico/direct editing confirmados |
| SZ-UI-DESKTOP-AUDIT | `C` central real aberta e alertas observados; `R` integração tema/bridge e contraste | quatro gaps confirmados visualmente/operacionalmente |
| SZ-UI-PACKAGED-ICONS | `P` allowlist/testes; `N` cobertura visual por plataforma | gaps de logos/fallback/evidência permanecem |
| SZ-V2-HARMONIZED-FUNCTIONAL-RELEASE | `P` release canônica instalada/convergida; `N` jornada completa de todos os itens | não empacotado como item independente |

## 3. Hipóteses H1–H15

| Hipótese | Veredito | Evidência |
|---|---|---|
| H1 | Parcial | Busca/launch/return por teclado foram provados na release `085169f4`; catálogo físico e fade continuam sem prova. |
| H2 | Confirmada | Validação canônica registra teclado via `ydotoold`, 0 cliques; mouse não foi usado como prova. |
| H3 | Confirmada | `SceneEsdeView.qml` renderiza IR; não há handler de foco/tecla/movimento. |
| H4 | Confirmada | Canvas é preview/inspector; edição direta não existe como persistência segura. |
| H5 | Confirmada | RetroFE existe em domain/CLI; não há rota visual no desktop. |
| H6 | Confirmada | `doctor`/`state audit` reportam a árvore órfã `01M1MVR99JYX492AC41HAES91A`. |
| H7 | Confirmada | Central atual mostra “Perfil do Desktop desatualizado” em baixo contraste; Temas mostra bridge sem catálogo. |
| H8 | Confirmada | Só o ciclo Switch/Steam possui evidência física canônica; demais sessões têm falhas/orphans no histórico. |
| H9 | Confirmada | Read model declara gaps de destino, compressão, diretório e uninstall. |
| H10 | Confirmada | `vita3k` está `missing`; PS4/Vita não aparecem como adapters jogáveis. |
| H11 | Confirmada | Launcher e Biblioteca exibem placeholders tipográficos para grande parte do acervo. |
| H12 | Confirmada | Job registra quota/sem candidatos, mas a UI não apresenta a cadeia do que foi feito/falta. |
| H13 | Confirmada | Sistema oferece diagnóstico textual, mas não a recuperação QML correspondente ao doctor. |
| H14 | Parcial | Cast LAN está instalado no item, porém host/UI estão sem orquestrador; internet permanece planejada. |
| H15 | Confirmada | PID `507008` e release `085169f4` foram anotados; evidência anterior usa PID/release diferentes. |

## 4. Ganhos rápidos

1. Corrigir a publicação `theme.catalog.list` na bridge; a aba Temas deve mostrar
   os quatro builtins que a CLI já lista, com ativo/compatível/instalado.
2. Trocar o alerta marrom quase preto por token com contraste medido e manter o
   foco visível nos botões “Revisar perfil” e “Dispensar”.
3. Na home do Launcher, usar card de fallback consistente: logo/plataforma,
   estado “arte indisponível” e título com elipse, sem letras isoladas enormes.
4. Exibir no launcher “231 jogos / N plataformas / arte X/Y” em vez de uma
   contagem que mistura arquivos, updates e itens para revisão.
5. Adicionar CTA “Ver motivo” aos jogos sem keys/BIOS/adapter e CTA de retry ao
   job de mídia degradado/quota.
6. No retorno do jogo, registrar visualmente “Voltando para [seção]” e preservar
   o mesmo cartão; medir o fade só depois da transição ser observável.
7. Na aba Sistema, converter `orphan staging` em ação segura de quarentena com
   tamanho, idade e rollback relacionado, sem botão mudo.
8. Diferenciar sempre `não publicado`, `não configurado`, `não verificado` e
   `indisponível`; hoje esses estados parecem visualmente semelhantes.

## 5. Estruturais e pontos de fricção

### P0 — bloqueios de experiência

- A ponte UI não publica o catálogo de temas: o usuário vê zero temas e não
  consegue ativar o tema que o runtime/CLI declara ativo.
- O catálogo fullscreen sem artwork torna uma biblioteca moderna indistinguível
  de uma lista de arquivos; isso atinge a promessa de AURA Launcher.
- Big Picture não foi fisicamente provado: sem atalho real/visível da própria
  central, o usuário não tem porta de entrada comparável a ES-DE/Playnite.

### P1/P2 — reprodução

| Prioridade | Passo | Dor |
|---|---|---|
| P1 | Abrir central → Visão geral/Perfis | alerta persistente “desatualizado”, texto e botões com contraste insuficiente; não fica claro se revisar é obrigatório. |
| P1 | Abrir Temas | CLI lista temas, UI mostra “catálogo não publicado”; confiança quebrada e nenhum próximo passo útil. |
| P1 | Abrir Launcher → percorrer acervo | placeholders `!`, `A`, `1`, `2`, nomes longos e corte de cartões; hierarquia não comunica plataforma/arte ausente. |
| P1 | Abrir Sistema | “Nenhum check do doctor publicado ainda” contradiz o doctor CLI recém-executado; recuperação exige sair da UI. |
| P2 | Abrir Transmissão | há ações de descobrir/iniciar/parar, mas “orquestrador não configurado” não diz como habilitar. |
| P2 | Abrir Saves e Sync | modo somente leitura é honesto, porém sem CTA de autenticação/provider. |
| P2 | Tentar ES-DE/RetroFE | backend/preview existem, mas não há uma jornada visual de importação/uso. |

## 6. Comparativo de categoria

| Referência | SteamZero | Veredito |
|---|---|---|
| Steam Deck / Big Picture | Controle, retorno e estados declarativos são bons; descoberta visual e atalho próprio não provados | ATRÁS em acabamento e integração |
| Playnite | Modelo de biblioteca e metadados são promissores; cobertura visual e filtros são rasos | ATRÁS |
| LaunchBox | Contratos de importação e arte não equivalem a catálogo utilizável | ATRÁS |
| ES-DE | Cena compilada é interessante, mas não navega nem substitui a central | ATRÁS na experiência, à frente apenas na explicitação de limites |
| RetroFE | Slice declarativo existe; sem entrada visual, instalação e lançamento reais | ATRÁS |

## 7. Recomendação final

Primeiro, fechar a cadeia **bridge → catálogo → ativação → renderização** e,
em paralelo, transformar a falta de artwork em um estado visual projetado. Isso
destrava confiança no tema e uma home que parece biblioteca, não diagnóstico.
Depois, fazer a entrada Big Picture e o retorno jogo→launcher terem prova física
completa. Só então vale ampliar Theme Studio para edição direta e ES-DE para
carousel/textList/video/helpSystem navegáveis; um preview bonito sem uso real
cria expectativa maior que a capacidade entregue.
