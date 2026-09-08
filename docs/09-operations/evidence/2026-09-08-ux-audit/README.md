# Auditoria UX consultiva — release instalada

Data: 2026-09-08 (America/Sao_Paulo)

Esta auditoria observa a experiência da release que já estava instalada. Não
houve `install`, `rollback`, `theme apply`, `frontends apply`, reboot, logout ou
encerramento da sessão KDE durante a coleta.

## Identidade da prova

- pacote: `2.0.0rc1`
- release ativa: `2.0.0rc1-435f9108eeb7`
- commit de origem: `435f9108eeb7b4adf1d84b87d9d2e70c692eead1`
- daemon: PID `807844`, convergente, sem restart nesta auditoria
- `steamzero doctor --json`: `ok=true`, `status=degraded`, `pendingOperations=0`,
  `staleJobs=0`, `orphanStaging=1`, `orphanBackups=0`, `orphanJournals=0`,
  `bootDirect=unknown` por permissão
- tela: 1280×800 capturada pelo compositor; o host reporta painel eDP-1
  800×1280, escala 1,35 e rotação do display
- contagem de status: 56 JSON no catálogo, 44 não agregados e 12 agregados.
  O prompt de origem dizia 43 não agregados; a diferença foi preservada como
  achado, não escondida.

Toda captura abaixo foi feita com `spectacle -b -n -o <arquivo>` após ativar a
janela pelo PID indicado. As capturas da Central foram coletadas em janela QML
com PID `1200476`, salvo onde indicado. O PID não é inferido pelo título da
janela.

## Evidência visual

| Arquivo | PID | Observação verificável |
|---|---:|---|
| [01-central-overview-1280x800.png](01-central-overview-1280x800.png) | 1200476 | Visão geral real; catálogo assíncrono chega a 1.131 jogos. |
| [02-central-menu-1280x800.png](02-central-menu-1280x800.png) | 1200476 | Drawer aberto com Space injetado; foco do teclado é visível. |
| [03-emulation-1280x800.png](03-emulation-1280x800.png) | 1200476 | Emulação: 62 plataformas, 63 destinos editoriais, 155 experiências históricas. |
| [04-steam-1280x800.png](04-steam-1280x800.png) | 1200476 | Steam: prontidão, perfil e lançamento gerenciado aguardando. |
| [05-perfis-1280x800.png](05-perfis-1280x800.png) | 1200476 | Contradição visível: cartão aplicado e banner de contexto desatualizado. |
| [06-sync-1280x800.png](06-sync-1280x800.png) | 1200476 | Estado vazio de sync; sem provedor, fila, retry ou resolução de conflito. |
| [07-cast-1280x800.png](07-cast-1280x800.png) | 1200476 | Casting LAN disponível, mas pede configurar o serviço no host. |
| [08-system-1280x800.png](08-system-1280x800.png) | 1200476 | Diagnóstico com estados de runtime/proveniência; conteúdo inferior corta. |
| [09-library-1280x800.png](09-library-1280x800.png) | 1200476 | Biblioteca com Steam e Switch; cobertura visual desigual entre sistemas. |
| [10-themes-catalog-1280x800.png](10-themes-catalog-1280x800.png) | 1651425 | Temas real: abas, 567,3 MB/4.125 arquivos e dois temas instalados. |
| [11-launcher-before-1280x800.png](11-launcher-before-1280x800.png) | 1702338 | AURA Launcher: 8.016 arquivos, 1.131 jogos, foco no primeiro cartão. |
| [12-launcher-after-30-right-1280x800.png](12-launcher-after-30-right-1280x800.png) | 1702338 | Após 30 setas para direita, o foco permaneceu no primeiro cartão. |
| [13-launcher-detail-1280x800.png](13-launcher-detail-1280x800.png) | 1622407 | Return abriu a página real de jogo com ação Jogar focada. |
| [14-game-launched-1280x800.png](14-game-launched-1280x800.png) | 1629538 | RetroArch/Mesen abriu a ROM real. |
| [15-game-survives-launcher-1280x800.png](15-game-survives-launcher-1280x800.png) | 1642503 | Jogo continuou vivo após encerrar o Launcher. |

As imagens 11 e 12 têm hashes, respectivamente,
`26182390d56a1152435e3eb51d119050e39b2b8338bb311413ddd75a8721a566` e
`3b32904681ad3f1467ac73d41ea8c002475efac76aacaf66c47b81231f54f19f`.
O teste de 30 setas é adicional ao ciclo de lançamento; a diferença visual
entre os arquivos não prova movimento, pois a grade permaneceu no primeiro
cartão. Isso é precisamente o resultado negativo registrado.

## Veredito por área (1–10)

As notas são consultivas, não promoção de estado técnico.

| Área | Nota | Veredito |
|---|---:|---|
| Central — visão geral | 6 | Hierarquia clara e catálogo vivo, mas densidade/clipping e drawer dependente de Space. |
| Central — Emulação | 5 | Read model honesto e rico; ações de ciclo completo não foram provadas. |
| Central — Steam/Perfis | 5 | Bom diagnóstico de prontidão, porém banner/card de perfil contraditórios. |
| Central — Saves/Sync | 4 | Estado vazio honesto, mas sem caminho de configuração/retry/conflito. |
| Central — Sistema | 5 | Causa aparece; recuperação acionável ainda é limitada. |
| Central — Biblioteca | 5 | Inventário legível; artwork/placeholder não fecha a promessa editorial. |
| Launcher/BigPicture | 4 | Home bonita e launch real provado; foco/setas, busca e Big Picture não fecham. |
| Tema | 5 | Catálogo e metadados existem; abas/ações cortam em 1280×800 e troca não foi mutada. |
| Theme Studio | 4 | Modelo/canvas read-only é coerente, mas não acessível por input nesta sessão. |
| Emulação/ciclo de vida | 5 | Switch/RetroArch real abriu e sobreviveu ao Launcher; matriz restante não. |
| Armazenamento | 3 | Não há prova física das ações de destino, compressão e preservação de dados. |
| Mídia | 3 | Pipeline e filtros existem, mas clareza de scraping/progresso não foi fechada. |
| Frontends/integração | 2 | SRM/ES-DE estão ausentes no host; LaunchBox/RetroFE não foram alcançados. |
| Diagnóstico | 6 | Proveniência e causa são bons; `degraded`/órfão ainda pede decisão ao usuário. |
| Casting | 3 | Orquestrador LAN disponível; nenhum receptor/latência/recuperação foi provado. |
| Acessibilidade | 5 | Foco visível em várias telas e alvos grandes; mouse não foi confiável e editor não foi alcançado. |
| Host/operação | 7 | Convergência e rollback disponível estão claros; doctor segue degraded. |

## H1–H15

| Hipótese | Veredito | Evidência da release |
|---|---|---|
| H1 Launcher: foco/ativação | parcial | Return abriu jogo e retorno foi provado em sessões anteriores desta release; 30 setas e F não moveram/abriram busca na sessão atual. |
| H2 teclado funciona, mouse não | confirmada | Space/Tab/Return funcionaram em rotas reais; ponteiro injetado não foi confiável. |
| H3 cena ES-DE só preview | confirmada | `SceneEsdeView.qml` renderiza, mas não possui handler de foco/teclas/movimento; o gap permanece. |
| H4 Theme Studio read-only | confirmada/parcial | QML declara `readOnly: true` por padrão e esconde edição quando read-only; canvas físico da aba não foi alcançado. |
| H5 RetroFE sem entrada visual | refutada | A release instalada tem entrada QML e diálogo de inspeção RetroFE; a cena ainda não é ativada automaticamente. |
| H6 staging órfão em instalação nova | não validada | Doctor observou 1 órfão, mas a regra da auditoria proibia instalar tema para obter before/after causal. |
| H7 quatro gaps da UI | parcial | Live-launcher permanece aberto; banner/perfil contraditório e clipping foram vistos; medição de contraste/gate de órfão não foram reexecutados como sonda pixel. |
| H8 ciclo físico só Switch | confirmada | Só o ciclo RetroArch/ROM observado foi provado; as demais plataformas ficaram não validadas. |
| H9 storage incompleto | confirmada | A UI observada não ofereceu destino de mover, compressão em lote ou desinstalação com dados. |
| H10 adapters/firmware ausentes | confirmada | Status/itens mantêm PS4/Vita ausentes e firmware/store restritos; não houve linha de lançamento falsa. |
| H11 catálogo/capas incompletos | confirmada | Launcher usa placeholders alfanuméricos; Biblioteca não mostra artwork equivalente para todos os sistemas. |
| H12 mídia pouco clara | parcial | Estados de mídia aparecem, mas scraping/progresso/causa não foram demonstrados em operação real. |
| H13 diagnóstico sem recuperação QML | confirmada | Sistema mostra diagnóstico/exportação; não apareceu recuperação contextual para cada falha. |
| H14 casting LAN degraded | confirmada | Tela diz que o orquestrador está disponível, mas pede configuração e não há receptor para validar. |
| H15 título não identifica release | confirmada | PIDs diferentes produziram janelas com o mesmo título; README registra PID e release para cada prova. |

## Rotas A–N

- **A/B Launcher:** home e detalhe foram abertos; Return lançou uma ROM real,
  RetroArch foi fechado e o jogo sobreviveu ao encerramento do Launcher. A
  grade é horizontalmente cortada em 1280×800. Busca, Coleções, 60+ movimentos
  efetivos e biblioteca vazia acionável ficaram não validados; setas/F falharam
  por input observado.
- **C Mídia:** nenhum `media.plan/apply` foi executado. Os estados da Central
  não explicam uma operação real de provider, bytes, quota ou recorrência.
- **D Central:** Visão geral, Emulação, Steam, Perfis, Saves/Sync, Casting,
  Sistema, Biblioteca e Temas foram percorridos. Há clipping inferior/ações
  fora da viewport em 1280×800 e contraste sem medição pixel nesta sessão.
- **E Funções:** doctor, service status, jobs/operations e listas foram lidos;
  não foram aplicados componentes, perfis, coleções, firmware ou temas.
- **F Storage:** status e read model foram consultados; mover destino,
  compressão e remoção preservando dados ficaram não validados.
- **G Frontends:** `frontends status --json` retornou SRM `missing` e ES-DE
  `missing`; `frontends verify --json` sem spec foi recusado por schema antes de
  qualquer efeito. Não há prova de destino externo.
- **H Host:** `service status`, `steamzero-host converge`, doctor, jobs e
  operations foram read-only; daemon convergiu sem restart. O host não foi
  reiniciado.
- **I Casting:** a tela LAN foi alcançada; descoberta, conexão, latência e
  perda do par não foram possíveis sem receptor/configuração.
- **J Acessibilidade:** foco visível em Central/Launcher e tamanho mínimo
  aparente são pontos positivos; mouse não confiável e editor inacessível por
  input permanecem fricções.
- **K Tema:** quatro temas builtin aparecem no `theme list`; o catálogo físico
  mostra Iconic/PlayStation-X instalados e metadados. A aba de edição/canvas não
  foi obtida por gesto físico, e nenhuma troca foi mutada.
- **L BigPicture:** não validado: não houve prova de atalho SteamZero acionável
  no Big Picture, retorno ao Big Picture ou comparação operacional com ES-DE/
  RetroFE. O status de frontends ausentes impede promover a integração.
- **M Integração:** loopback/daemon/read models e proveniência foram confirmados;
  a cadeia quebra nos frontends ausentes, na navegação física do Launcher e em
  ações de tema/storage não exercitadas.
- **N Fluidez:** startup e render foram observados qualitativamente; não se
  afirma FPS/jank/VRAM nesta auditoria. A grade de 1.131 jogos abre, mas a
  cobertura de LOD/performance em rolagem não foi medida no compositor.

## Matriz dos itens não agregados

O catálogo atual tem 44 itens não agregados. “Parcial/não validado” significa
que o item ou parte do critério não foi promovido por esta prova; não transforma
teste unitário/offscreen em prova de usuário.

| Item | Estado observado nesta release | Gaps/critério relevante |
|---|---|---|
| SZ-AURA-LAUNCHER | parcial; launch/return provados, navegação física falhou | REAL-CATALOG-PHYSICAL; RETURN-FADES-PHYSICAL |
| SZ-AURA-UI | unit; telas reais confirmam a superfície, não o Launcher | prova visual integral não promovida |
| SZ-CAST-INTERNET | planejado; não disponível | sem artefato/pacote |
| SZ-CAST-LAN | unit/degraded; tela disponível | receptor/latência/recuperação não validados |
| SZ-COMPONENT-LIFECYCLE | unit/hw; sem operação nesta sessão | matriz de instalação/rollback física não reexecutada |
| SZ-CONTROLS-INPUT-PROFILES | hw parcial; card de Perfis visível | chegada do perfil ao jogo não validada |
| SZ-EMULATION-LONG-OPERATIONS | hw parcial; fila/estado observados | operação longa real não executada |
| SZ-EMULATION-M10 | VM/degraded; fora do host | DEBT-A7; GAP-G45 |
| SZ-EMULATION-PLATFORM-CONTEXT | unit/degraded; contexto visível | REQUIREMENT-CARD-FALLBACK; EMULATION-PHYSICAL-LAUNCH |
| SZ-EMULATION-PLATFORM-SCOPE | unit/degraded; escopo editorial visível | EMULATION-PHYSICAL-LAUNCH; REQUIREMENT-CARD-FALLBACK |
| SZ-EMULATION-STORAGE-MANAGEMENT | unit/degraded; sem ação mutável | STORAGE-MOVE-UI-DESTINATION; EMULATION-PHYSICAL-LAUNCH |
| SZ-EMULATION-STORAGE-PLATFORM-SCOPE | unit/degraded; sem ação mutável | MOVE-UI-DESTINATION; BATCH-COMPRESSION; EMULATION-PHYSICAL-LAUNCH |
| SZ-EMULATION-STORAGE-READMODEL | unit/degraded; read model sem ciclo | MOVE-DIRECTORY; ROM-COMPRESSION; EMULATION-PHYSICAL-LAUNCH |
| SZ-EMULATION-ENHANCEMENTS | unit/unknown; não promovido fisicamente | estado de host desconhecido |
| SZ-FRONTEND-ESDE-SYSTEMS | unit/unknown; host sem ES-DE | ES-DE ausente no status |
| SZ-FRONTEND-ESDE | unit/ready; destino não presente | integração física não validada |
| SZ-FRONTEND-LAUNCHBOX | planejado | LEDGER-A10 |
| SZ-FRONTEND-M11-SURFACE | unit/unknown | sem prova de superfície instalada |
| SZ-FRONTEND-RETROFE | dev/ready; entrada RetroFE instalada | publicação em frontend alvo não validada |
| SZ-FRONTEND-SRM | unit/unknown; SRM missing | manifests ausentes no host |
| SZ-FRONTEND-STEAM-SHORTCUTS | unit/unknown | BigPicture/shortcut não validado |
| SZ-GOVERNANCE-STATUS | dev/ready | DEBT-CI-VISUAL-IMAGE-SEM-SVG |
| SZ-HOST-UPDATE-TRANSACTIONAL | hw/ready; converge OK | boot físico continua do operador |
| SZ-LIBRARY-CANONICAL | dev/unknown; 1.131 jogos chega à home | LIBRARY-PHYSICAL-CATALOG-COVERAGE |
| SZ-LIBRARY-CONVERSION-CONTRACT | unit/unknown | sem jornada física de conversão |
| SZ-MEDIA-AUDIT-PLATFORM-SCOPE | unit/degraded; não executado | MEDIA-UI-PIPELINE-CLARITY; EMULATION-PHYSICAL-LAUNCH |
| SZ-MEDIA-PIPELINE-PLATFORM-SCOPE | unit/degraded; não executado | MEDIA-UI-PIPELINE-CLARITY; EMULATION-PHYSICAL-LAUNCH |
| SZ-MEDIA-PROVIDER-PLATFORM-FILTER | unit/degraded; filtro não exercitado | status de provider não demonstrado |
| SZ-MEDIA-SCRAPING | unit/degraded; sem plan/apply | GAP-G44; LEDGER-A12; LEDGER-A7 |
| SZ-ONLINE-P2P | planejado | LEDGER-A6 |
| SZ-PLATFORM-CORE-PER-SYSTEM | unit/unknown; matriz não lançada | PHYSICAL-RELEASE; ADAPTER-COVERAGE |
| SZ-PLATFORM-REQUIREMENT-SCOPE | unit/unknown; status honesto | FIRMWARE-PS3-STORE-NOT-WIRED; PSVITA-ABSENT; QML-GLOBAL-REQUIREMENT-ROW-OWNED-BY-V2 |
| SZ-PLATFORM-VITA-CATALOG | unit/unknown; sem adapter/store | VITA-ADAPTER-ABSENT; FIRMWARE-VITA-STORE-NOT-WIRED |
| SZ-RETROACHIEVEMENTS | planejado | LEDGER-A9 |
| SZ-SYSTEM-DIAGNOSTICS-GUIDANCE | unit/degraded; doctor orienta, não recupera | SYSTEM-DIAGNOSTICS-QML-RECOVERY; EMULATION-PHYSICAL-LAUNCH |
| SZ-THEME-ENGINE | hw/degraded; catálogo/status resolvido | staging órfão observado; troca/fallback físico não reexecutados |
| SZ-THEME-ESDE-SCENE-RENDER | hw/degraded; preview separado | THEME-ESDE-SCENE-NOT-RENDERED |
| SZ-THEME-IMPORT-ESDE-LAYOUT | hw/degraded; não ativado | THEME-ESDE-SCENE-NOT-RENDERED |
| SZ-THEME-IMPORT-RETROFE | hw/ready; entrada visual instalada | cena não é ativada automaticamente |
| SZ-THEME-IMPORT-SURFACE | unit/degraded; catálogo alcançado | THEME-STUDIO-PHYSICAL-CANVAS |
| SZ-THEME-STUDIO | hw/degraded; canvas físico desta release não alcançado | THEME-STUDIO-PHYSICAL-CANVAS; edição direta permanece read-only |
| SZ-UI-DESKTOP-AUDIT | físico parcial; oito rotas reais percorridas | UI-LIVE-LAUNCHER-ROUTING; contraste pixel e mouse ficam sem prova |
| SZ-UI-PACKAGED-ICONS | unit/packaged; não é promoção de cobertura visual | LIBRETRO-CORES-SEM-LOGO; PLATAFORMAS-EM-FALLBACK; SEM-EVIDENCIA-VISUAL |
| SZ-V2-HARMONIZED-FUNCTIONAL-RELEASE | partial/unknown; release ativa convergiu | matriz final de integração permanece fora deste ciclo |

## Priorização consultiva

### P0 — bloqueios de experiência

1. Corrigir e provar o contrato de input do Launcher na mesma janela viva:
   direcional, busca, Coleções e 60+ movimentos, com foco que nunca some.
2. Fechar a promessa de frontend: o atalho SteamZero no Big Picture e o
   caminho ES-DE/SRM precisam existir ou declarar explicitamente “não instalado”
   com próximo passo acionável.
3. Tornar Tema uma transação compreensível: aba de edição alcançável, preview
   visível, apply/rollback e erro de staging apresentados na mesma superfície.

### P1 — ganhos rápidos

- Reservar viewport inferior para não cortar botões/abas em 1280×800.
- Unificar banner de perfil com os valores aplicado/observado para eliminar a
  contradição “aplicado” versus “contexto desatualizado”.
- Transformar estados vazios de Sync, Cast e Media em CTA com diagnóstico,
  pré-requisito e recuperação, não só texto.
- Mostrar badge “placeholder sem artwork” e a origem/estado da mídia no card.
- Exibir sempre release/PID em uma tela de diagnóstico exportável, sem colocar
  tokens na UI.
- Garantir foco inicial e foco de retorno após fechar o jogo; não depender do
  mouse para recuperar uma janela.
- Para Theme Studio, manter a separação declarativa, mas oferecer um modo de
  edição permitido apenas para cópia de usuário e marcar builtin como read-only.
- Medir contraste pelo pixel renderizado por tema e repetir com alto contraste/
  reduced motion herdados do host.

### Melhorias estruturais

1. Contrato único de input/identidade de janela entre daemon, Launcher e QML,
   com telemetria de foco e motivo quando um gesto é ignorado.
2. Read model transversal de catálogo/mídia/tema com estados `missing`,
   `degraded`, `ready` e `permissionDenied` visualmente equivalentes em todas
   as superfícies.
3. Frontend bridge idempotente com verificação concreta do destino e captura
   de segunda execução sem duplicação.
4. Pipeline de Theme Engine que materializa cena preview e navegação como
   capacidades independentes; preview bonito sem interação deve ser rotulado
   como preview, não parecer uma skin ativa.
5. Evidência física automatizada por release com PID, versão, hash before/after
   e uma captura funcional por etapa; harness continua complemento.

## Comparativo de mercado

- Steam Deck: SteamZero está atrás em foco/input e retorno de Big Picture; fica
  à frente em explicitar diagnósticos de proveniência e contratos de estado.
- PS5 UI: está atrás em transições, densidade controlada e recuperação contextual;
  empata na clareza de estados quando a tela já tem o read model.
- Playnite/LaunchBox: está atrás em catálogo visual, busca e coleção pronta;
  à frente em separar operações transacionais e gaps de plataforma.
- ES-DE/RetroFE: está atrás em profundidade de frontend instalado e cena
  navegável; à frente em governança de importação/licença e não executar tema
  arbitrário.

## Próxima onda recomendada

Primeiro fechar input/foco do Launcher e o atalho BigPicture, em uma única prova
física de release. Em paralelo, reabrir SZ-THEME-STUDIO somente para tornar a
edição declarativa de cópia de usuário alcançável, mantendo builtin read-only.
Depois disso, priorizar cenas ES-DE interativas (textList/carousel/helpSystem)
antes de adicionar mais efeitos: a superfície atual já consegue parecer bonita,
mas sem navegação a promessa emocional fica incompleta.

## Limites e ações do operador

- Não foi feito reboot; o teste físico de boot direto permanece exclusivamente
  do operador.
- Não foi possível provar BigPicture, receptor de casting, ações de storage,
  instalação nova de tema, input de mouse confiável ou mutação do Theme Studio.
- O rollback disponível antes da auditoria permanece `2.0.0rc1-b09908a58261`;
  nenhum rollback foi acionado nesta sessão.
