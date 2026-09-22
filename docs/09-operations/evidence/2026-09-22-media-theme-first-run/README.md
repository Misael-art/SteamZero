# Complemento de diagnóstico — mídia, first-run e Theme Studio

Data da execução: 2026-09-22  
Release observada no host: `2.0.0rc1-504d10b14485`  
Commit do código auditado: `504d10b144851b70eab99d1fad7110ae34e88f84`

Este documento complementa, sem substituir, o [diagnóstico de jornada UX e ROM](../2026-09-22-ux-deep-dive/README.md) e o [relatório completo de validação do host](../2026-09-22-full-host-validation/README.md).

## Veredito executivo

| Frente | Resultado real | Diagnóstico |
|---|---|---|
| Login SteamGridDB | passou | Cofre disponível; teste remoto autenticou; estado persistido como `validated`. |
| Login ScreenScraper | falhou de forma explícita | Campos obrigatórios estão presentes, mas o servidor rejeitou a credencial. A UI não deve tratar como “não configurado”. |
| Busca individual | passou com degradação | 19 candidatos para um jogo Switch; ScreenScraper falhou, SteamGridDB respondeu. |
| Download/aplicação individual | passou | Candidato 0 foi baixado, validado, canonicalizado e ficou `confirmed`; arquivo PNG existe. |
| Lote assíncrono | passou com degradação | 15 jogos: 9 processados, 6 pulados, 0 falhas de aplicação; job devolveu `jobId` antes de terminar. |
| Organização/otimização | passou parcialmente | 0 masters órfãos; 112 PNGs em dimensões exatas. Não existe medição perceptual de “melhor mídia”. |
| Theme Studio — autoria | passou parcialmente | Metadados, tokens, preview, save, export e layout funcionam. Efeitos são observáveis, não editáveis pelo inspector. |
| First-run | lacuna crítica | DuckStation abre wizard e bloqueia a jornada; melonDS não tem config detectável; Dolphin abre aviso/estado sem jogos. PCSX2 está além do wizard, mas tem path de BIOS/portal frágil. |
| Frontends/temas externos | degradado | ES-DE/SRM não estão presentes como frontend ativo; quatro temas ES-DE locais são inválidos no schema; não há pacote RetroFE instalado para lançamento físico. |

## 1. Mídia e scraping

### 1.1 Fontes e autenticação

O registro de providers expõe estes caminhos:

- `steamgriddb`: API key; grids, heroes, logos e ícones; plataformas Switch/PC/Steam.
- `screenscraper`: `devid`/`devpassword` obrigatórios e `ssid`/`sspassword` opcionais; boxart, screenshot e manual.
- `steam-local`: publicação local de artes otimizadas; não usa login.
- `igdb` e `steam-web-api`: declarados, porém desabilitados/não implementados no build.

Resultado no host, sem imprimir nenhum segredo:

```text
Secret store: disponível
SteamGridDB: configured=true, antes stored; test -> valid=true, state=validated
ScreenScraper: configured=true, antes stored; test -> valid=false,
              E-SCRAPE-CREDENTIAL-REJECTED, state=rejected
IGDB/Twitch: unavailable, adaptador não implementado
Steam local: local/ready
Steam Web API: unavailable, nenhum recurso atual depende dela
```

O estado rejeitado ficou persistido com `lastValidatedAt`; isso prova que a interface distingue “credencial existente, mas inválida” de “campo vazio”. A causa operacional de ScreenScraper exige correção da credencial/conta do operador ou confirmação do contrato de autenticação pelo upstream. Não foi mascarada como quota.

Não existe no código um provider identificado literalmente como “Steam Deck API”. A capacidade funcional observada como método remoto de arte no host é a integração SteamGridDB; se “API do Steam Deck” for um endpoint adicional esperado, ele ainda não está exposto como adapter nomeado e precisa ser especificado/implementado como lacuna própria.

### 1.2 Jornada individual real

Jogo usado: `Demon Slayer Kimetsu no Yaiba the Hinokami Chronicles 2`  
ID canônico: `0fd1b7954e6eaf474f5e8c8c`  
Title ID: `0100AD80208A8000`  
Plataforma: `switch`

1. A busca `game.media.search` foi planejada e aplicada pela mesma fachada usada pela UI.
2. O job interativo terminou como `candidates-found`.
3. Resultado: 19 candidatos; `provider_errors = {screenscraper: E-SCRAPE-CREDENTIAL-REJECTED}`.
4. O candidato de índice 0 foi selecionado e baixado.
5. A validação de assinatura passou; a mídia foi persistida como fonte `scraper`, estado `confirmed`.
6. O master ficou em `media/masters/switch/box2d/<sha256>.png`.
7. A otimização produziu os destinos de Steam portrait e landscape.

A busca, portanto, não aborta por uma fonte remota indisponível: mantém fallback/resultado de outra fonte e registra o erro. A lacuna é a recuperação guiada para ScreenScraper e a confirmação visual de que o ranking remoto escolheu a melhor arte, não apenas o candidato de maior confiança declarada.

### 1.3 Jornada em lote e assíncrona

Foi executada a operação `media.global.search-missing` com escopo `switch`.

```text
jobId: 01M34K02HCVQNE5AVG41050YZ1
operationId: 01M34K02GKFD7CEWFP838JME5M
total: 15
processed: 9
skipped: 6
updated: 0
failures: 0
no_candidates: 0
outcome: degraded
provider_details: screenscraper / E-SCRAPE-CREDENTIAL-REJECTED / 9 jogos
```

O `apply` devolveu o `jobId` antes da conclusão. O progresso foi observado em estados de provider e de jogo (`12/15` e `15/15`), e o job encerrou em `completed/succeeded`. Os seis pulados correspondem à política `search-missing`, que não reprocessa jogos que já possuem master remoto.

A operação testada é o lote de busca; ela não é “download em lote” por si só. O modo `overwrite` é o que aplica candidatos e otimiza em lote, mas não foi usado contra toda a biblioteca para não substituir arte existente sem uma decisão explícita por jogo. A arquitetura prevê o caminho; a qualidade em lote continua sem aceite perceptual.

### 1.4 Organização, integridade e qualidade

Foi executado `media.audit` no escopo Switch:

```text
masterFiles: 51
optimizedFiles: 112
viewLinks: 0
orphanMasters: 0
registryEntries: 56
```

Inspeção física dos 112 arquivos otimizados:

```text
steam-portrait: 56 arquivos, 600x900, PNG
steam-landscape: 56 arquivos, 920x430, PNG
dimensões divergentes: 0
tamanho mínimo: 10.223 bytes
tamanho máximo: 1.276.993 bytes
```

A organização é determinística e segura: masters por plataforma/tipo/hash; derivados por plataforma/perfil. O auditador não encontrou órfãos. Porém:

- apenas portrait e landscape foram efetivamente materializados nessa coleção; hero, logo, icon, screenshot, vídeo e manual não têm cobertura equivalente nesse audit;
- o sistema valida magic bytes, limite de download, tamanho e dimensões do perfil, mas não mede nitidez, composição, legibilidade, duplicação semântica ou qualidade perceptual;
- o ranking usa confiança declarada, região e ordem de provider; não há score visual comparativo;
- `viewLinks=0` significa que a mídia otimizada ainda não foi publicada em links gerenciados para a Steam nessa rodada;
- licença e atribuição são carregadas no candidato/registro, mas não há gate operacional que escolha “melhor” arte por licença além de rejeitar metadado incompatível.

### 1.5 Outros métodos de mídia

O pipeline também cobre mídia customizada, extraída da ROM/NCA, cache de emulador, mídia remota e fallback de ícone de plataforma. Os testes automatizados de integração cobrem canonicalização, quarantine/rollback, magic bytes, limite de tamanho, links gerenciados, escopo por plataforma e falhas de provider. Nesta rodada, a suíte combinada executou **202 testes aprovados**.

O ponto ainda não fechado é a jornada operacional completa por cada tipo de mídia: selecionar uma screenshot, hero, logo, icon, manual e vídeo reais; medir o resultado visual em cada frontend; e confirmar publicação/rollback por conta Steam. O host atual só comprovou aplicação real de boxart e seus dois derivados.

## 2. First-run e resiliência dos emuladores

### 2.1 Estado observado

| Emulador | Evidência do host | Impacto de first-run | Diagnóstico |
|---|---|---|---|
| DuckStation | `~/.config/duckstation/settings.ini` ausente; wizard físico observado com Language, BIOS, Game Directories, Controller, Graphics, RetroAchievements, Interface, View e Complete | bloqueia lançamento direto | P0: launcher precisa detectar ausência de config e abrir uma jornada assistida, ou semear configuração mínima/selecionar BIOS e diretório antes de tentar o jogo. |
| PCSX2 | `PCSX2.ini` existe e `SetupWizardIncomplete=false`; UI nativa abriu biblioteca com 6 jogos | wizard já superado | P1: BIOS aponta para portal `run/user/1000/doc/...`; o lançamento governado de CHD falhou porque o caminho pedido não existe dentro do sandbox Flatpak. Resiliência de path/portal ainda é necessária. |
| Dolphin | `Dolphin.ini` existe; UI mostrou aviso de saúde/segurança e “no GameCube/Wii ISOs/WADs” | primeiro uso não é jogo direto | P1: tratar aviso inicial e diretório vazio explicitamente; não deixar o usuário interpretar ausência de jogos como falha silenciosa. |
| melonDS | config canônico `~/.config/melonDS/melonDS.ini` ausente; pacote instalado | risco não exercitado no build atual | P1: abrir em sandbox descartável, capturar primeiro diálogo e declarar se seed/config é necessário. |
| RetroArch | `retroarch.cfg` existe | first-run provável superado | P2: o core é um segundo nível de configuração; ainda falta comprovar a primeira abertura de cada core e o overlay de pausa no caminho físico. |
| PPSSPP | `ppsspp.ini` existe e `FirstRun=False` | first-run superado | P2: estado de configuração comprovado, mas o overlay de pausa/save-state físico deve permanecer na matriz de jornada. |
| Azahar | `qt-config.ini` existe com NAND/SDMC | first-run superado | P2: falta confirmação visual de BIOS/keys/diretórios em instalação limpa. |
| Flycast | `emu.cfg` existe | first-run provavelmente superado | P2: caminho físico de jogo e eventual aviso de BIOS ainda precisam de captura dedicada. |
| Cemu | `settings.xml` existe, mas `GamePaths` vazio | biblioteca sem diretório | P1: onboarding precisa pedir diretório e não abrir uma tela vazia sem explicação. |
| Ryujinx | `Config.json` existe, `game_dirs` presente; UI mostrou 32/32 jogos carregados | first-run superado | passou no inventário/UI; continuar cobrindo pausa e retorno. |
| Eden | configuração e perfis customizados existem | first-run superado | passou no inventário; a rota governada precisa manter a mesma resiliência de paths. |
| SharpEmu | `configFormat=none`; UI mostrou biblioteca vazia | sem wizard conhecido, mas sem conteúdo | P1: estado experimental deve ser apresentado como “sem biblioteca/sem dump”, não como falha do launcher. |
| shadPS4 | contrato declara `configFormat=none`; sem config editável pelo SteamZero | first-run não governado pelo produto | P1: lançamento deve verificar display/compatibilidade e explicar que config upstream não é editada pelo produto. |

A constatação central é que “já configurado” não pode ser o único caminho suportado: a primeira execução precisa ser idempotente, detectável e retornável. O SteamZero deve reconhecer wizard, aviso de saúde, biblioteca vazia, BIOS/keys ausentes e sandbox sem caminho, oferecendo ação de correção e nunca deixando um processo aberto bloqueando a jornada.

## 3. Theme Studio e efeitos

### 3.1 O que foi exercitado

Backend real em XDG temporário, sem alterar o tema ativo do host:

1. criar tema derivado de `org.steamzero.default`;
2. editar autoria e token de cor;
3. gerar preview resolvido;
4. salvar o manifesto em tema de usuário;
5. exportar ZIP;
6. verificar manifesto dentro de `<theme-id>/theme.json`;
7. cancelar a sessão.

Resultado: **passou**. O preview refletiu `accent=#ff00aa`, o tema foi salvo, o ZIP foi gerado e o cancelamento encerrou a sessão.

Suítes QML/integração executadas:

```text
126 passed — editor, efeitos, asset recipes, studio graph, extends, catalog routes e QML asset recipes
check_theme_editor_aura.qml: PASS
check_theme_editor_asset_recipes.qml: PASS
check_theme_studio_canvas.qml: PASS
check_theme_editor_import.qml: PASS
check_media_effect_layer.qml: PASS
check_theme_scene_preview.qml: timeout em 20s (RC 124)
```

O timeout do scene preview não foi convertido em falso sucesso: permanece uma lacuna de harness/runtime QML a investigar.

### 3.2 Maturidade real do editor

Implementado e demonstrado:

- edição de metadados, cores, geometria, tipografia e movimento;
- preview resolvido pela mesma cadeia declarativa da interface;
- herança `extends` com diagnóstico de ciclo/base ausente/profundidade;
- save transacional de tema de usuário;
- exportação ZIP com confirmação na UI;
- importação/inspeção de pacote, ES-DE e RetroFE por rotas protegidas;
- canvas, árvore, inspector, constraints, timeline e grafo de efeitos;
- edição declarativa de layout: colunas, gap, largura e altura do item;
- temas builtin em modo somente leitura;
- asset recipes, paleta dinâmica, glass, motion e superfícies possuem contratos e previews cobertos por testes.

Não implementado como autoria visual completa:

- não há controles no `ThemeEditorPanel` para criar/remover/reordenar `EffectSpec`;
- não há edição de parâmetros de blur, glow, shadow, saturation, colorize, reflection, vignette etc. no inspector;
- o efeito selecionado mostra propriedades e `THEME-STUDIO-COST-001`, explicitamente “o inspector só observa, não executa”;
- o profiler informa custo declarado e `withinBudget`, mas `measured=false`: não mede frame time, memória, GPU/RHI ou custo no Steam Deck;
- o canvas não desenha uma cena própria para efeito, motion ou binding; informa que o nó não tem cena própria;
- a edição de layout é a única mutação física do inspector demonstrada no QML.

Conclusão de maturidade: **editor de tokens/layout e empacotamento em estágio funcional; Theme Studio completo de efeitos ainda parcial, aproximadamente nível de inspector/preview declarativo, não de compositor visual WYSIWYG**.

### 3.3 Temas presentes no host

- Builtin disponíveis: `org.steamzero.default`, `org.steamzero.aura`, `org.steamzero.steamdeck` e `org.steamzero.asset-recipes-demo`.
- Tema de usuário ativo: `org.steamzero.01m2qznd` — `AURA ES-DE Physical`, válido e com tokens/effects/mediaRecipes resolvidos.
- Temas ES-DE importados como `org.esde.iconic`, `org.esde.nso-menu`, `org.esde.playstation-x` e `org.esde.xmb-menu`: **inválidos**, rejeitados por ausência de `compatibility` no schema SteamZero.
- `frontends status`: SRM ausente (`diretório de manifests ausente`) e ES-DE ausente (`es_systems.xml ausente`). Logo, não há prova de lançamento físico de temas ES-DE/SRM neste host nesta rodada.
- Nenhum pacote RetroFE instalado foi localizado para lançamento real; as rotas e testes do importador existem, mas a prova operacional depende de uma cena RetroFE real.

No tema ativo, os aspectos fixos (tokens, efeitos e receitas de mídia) resolvem; `dynamicPalette`, `glass`, `sceneMotion`, `sceneSurfaces` e `sceneContainers` estão nulos. Os aspectos dinâmicos são demonstrados pelo tema fixture `asset-recipes-demo` nos harnesses, não pelo tema ativo.

## 4. Lacunas priorizadas

### P0

1. Resiliência de first-run DuckStation: detectar wizard, seed/assistir configuração e voltar ao jogo.
2. Repetir a mesma política para qualquer emulador sem config (`melonDS`) e para biblioteca/diretório vazio (`Dolphin`, `Cemu`, `SharpEmu`).
3. Corrigir handoff de paths para Flatpak PCSX2, especialmente BIOS via document portal e CHD fora do sandbox.

### P1

4. Recuperar ScreenScraper com credencial válida e registrar quota/limite de conta sem mascarar rejeição.
5. Implementar/identificar o provider chamado “Steam Deck API”; o nome não existe como adapter na release auditada.
6. Fazer download/aplicação real por kind (`hero`, `logo`, `icon`, `screenshot`, `manual`, vídeo), com preview e rollback por item.
7. Criar score de qualidade/seleção: dimensões, proporção, nitidez, duplicata, licença, região e confiança precisam resultar em uma decisão auditável.
8. Fechar o suporte físico de ES-DE, SRM e RetroFE com artefatos reais, incluindo ativação, lançamento e rollback.
9. Adicionar edição de EffectSpec ao Theme Studio e fazer o preview atualizar os parâmetros, preservando allowlist e fallback.

### P2

10. Medir profiler em hardware/RHI: frame time, memória, decode, blur e tier cinematic/balanced/economy.
11. Reexecutar a matriz de pause/save-state/multi-disk e fade-in/fade-out após a correção do onboarding; os processos não podem permanecer abertos.
12. Corrigir o timeout de `check_theme_scene_preview.qml` e transformar a captura em gate de release.

## 5. Limpeza e encerramento

No encerramento da rodada:

```text
jobs ativos: []
wmctrl -lG: vazio
emuladores/QML/launcher de teste: nenhum processo correspondente
```

Um `library.scan` abandonado por um probe interrompido foi reconhecido e cancelado; os jobs de busca em lote e auditoria de mídia terminaram normalmente. Nenhum emulador ou Theme Studio permaneceu aberto.

