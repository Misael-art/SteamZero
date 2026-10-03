# THEME-ENGINE-AND-STUDIO — plataforma de criatividade declarativa

## 1. Propósito e regra de verdade

Esta é a especificação normativa da **Theme Engine** e do **Theme Studio** do
SteamZero. Ela complementa `AURA-SURFACES.md` e atualiza a dimensão de produto do
framework incremental preservado em `docs/expansion/FRAMEWORK TEMA/`.

Filosofia central: **renderize, não edite**.

- um asset-fonte pode produzir infinitas variações por receita;
- derivados não são distribuídos como cópias pré-editadas;
- efeitos e composições são não destrutivos;
- GPU realiza a renderização; CPU faz validação, planejamento, decodificação e
  tarefas assíncronas adequadas;
- criatividade usa contratos declarativos, não código arbitrário.

Se o designer precisa abrir Photoshop/GIMP para criar uma variação que a engine
promete — recolor, silhueta, contorno, glow, máscara, composição ou transição — a
capacidade correspondente ainda não está concluída.

## 2. Estado atual honesto

Já existem fundações parciais:

- manifestos, tokens, herança, resolver e fallback de temas;
- temas builtin, catálogo, instalação/importação e preferência;
- preview e edição de tokens/metadados com exportação de pacote;
- contratos parciais de scene graph e projeção QML;
- effect stack allowlisted em `MediaEffectLayer.qml`, incluindo blur, cor,
  saturação, brilho, contraste, sombra, glow, opacidade, máscara, vignette e
  reflexão;
- testes unitários, integração e harness QML para partes dessas capacidades.

Isso torna a **Theme Engine parcial** e o **Theme Studio parcial**. Ainda não
existem, como produto concluído, scene graph livre consumido ponta a ponta, grafo
visual de efeitos, timeline, transformações completas de logo, extração dinâmica
de cores, cache GPU com orçamento, canvas de autoria ou certificação física.

## 3. Arquitetura e fronteiras

```text
Launcher/AURA UI ── dados e ações semânticas versionadas
        │
Theme Engine ───── scene graph + layout + bindings + efeitos + animação
        │
Qt Quick/RHI ───── Vulkan/OpenGL conforme o host Linux

Theme Studio ───── autoria/preview/validação ──► pacote declarativo
```

- AURA UI é um consumidor e tema builtin.
- AURA Launcher é um produto consumidor do runtime.
- Theme Engine renderiza e protege a execução.
- Theme Studio cria pacotes; não é requisito para o runtime carregar um pacote
  válido.
- Captura de save, sessão de jogo, scraping, achievements e cloud pertencem aos
  seus domínios; a engine apenas renderiza contratos publicados por eles.

## 4. Scene graph e layout

O contrato versionado deve oferecer:

- hierarquia arbitrária dentro de limites explícitos;
- IDs estáveis e componentes reutilizáveis;
- posicionamento absoluto e relativo;
- anchors e constraints;
- row, column, grid, stack, flow e overlay;
- z-index, clipping, máscaras e área de hit separada da área visual;
- translate, scale, rotate, skew, origem e perspectiva 3D limitada;
- repetidores para coleção, lista, grid, carousel, wheel e offset converter;
- slots semânticos `home`, `library`, `gameDetail`, `search`, `collections`,
  `saveStates`, `quickMenu`, `osd`, `empty`, `loading`, `error` e `offline`;
- breakpoints por largura, altura, proporção, densidade, handheld/dock e tier;
- layouts para 1280×800, 949×593, Full HD, ultrawide e escala fracionária;
- fallback determinístico quando constraint, asset ou dado não resolver.

O pacote não referencia tabela interna, path privado ou classe QML. Consome um
read model público, versionado e sanitizado.

## 5. Pipeline de imagens

### 5.1 Formatos

Runtime obrigatório: PNG, JPEG, WebP, AVIF e SVG estático sanitizado. GIF/WebP
animado é opcional por capability. BMP, TGA, ICO, TIFF e PSD entram pelo importador
do Studio e são convertidos no staging; PSD não é dependência do runtime.

### 5.2 Ajuste e amostragem

- `contain`, `cover`, `fill`, `crop` e dimensões explícitas;
- aspect ratio protegido por padrão e desligável por elemento;
- crop por centro, ponto focal ou região de interesse declarada/detectada;
- nearest neighbor para pixel art;
- bicubic/Catmull-Rom e Lanczos3 para capa/fanart;
- Scale2x/xBRZ como nodes opcionais de alto custo, nunca pressupostos;
- mipmaps, texture atlas quando benéfico e compressão suportada pelo backend;
- lazy loading, carregamento preditivo e cancelamento quando o item sai da cena;
- placeholder/fonte reduzida enquanto a textura final carrega.

### 5.3 Cache

- chave por hash de conteúdo + receita + tamanho + tier;
- LRU adaptativo em RAM/VRAM;
- teto padrão de 512 MB de VRAM, sem reservar esse valor antecipadamente;
- invalidação quando fonte, receita, escala ou capability mudar;
- derivados são cache descartável, nunca assets duplicados no pacote.

## 6. Effect graph nativo

Nodes combináveis e allowlisted:

- cor: grayscale, sepia, invert, hue rotate, saturation, brightness, contrast,
  duotone, threshold e matrix 4×5;
- blur: Gaussian e box; motion, radial, tilt-shift e bokeh entram por tiers;
- borda: stroke sólido/tracejado, inner/outer shadow, inner/outer glow e rounded
  corners;
- composição: opacity, blend modes, tint, gradient overlay, masks e clipping;
- transformação: mirror, zoom, pixelate, wave/distortion limitada e reflection;
- retro: scanlines, CRT, curvature, bloom, vignette, VHS, grain e light leak;
- avançados: chromatic aberration, depth of field, noise, parallax, neon,
  hologram, Ken Burns e particles com orçamento explícito.

Cada node declara custo, capabilities, limites e fallback. Um node indisponível
produz diagnóstico e degradação conhecida; nunca desaparece silenciosamente nem
derruba a cena.

Shaders arbitrários de terceiros permanecem proibidos. Novos efeitos entram como
nodes builtin revisados; uma futura extensão isolada exige ADR, sandbox, limites,
timeout e cadeia de confiança próprios.

## 7. Transformação de logos por um único asset

A receita trabalha prioritariamente sobre alpha/máscara ou signed distance field:

- versão colorida original;
- grayscale;
- silhueta preta/branca;
- inversão RGB/luminância;
- color shift por hue;
- recolor sólido/gradiente;
- contorno fino/grosso, interno/externo/centralizado;
- dilatação e erosão;
- Sobel/Canny opcional para casos sem alpha;
- preenchimento, glow e shadow combináveis.

Gate obrigatório: um asset sintético/licenciado produz ao menos as variantes
colorida, preta, branca, contorno branco fino/grosso e contorno preto fino/grosso.
Os logos de referência anexados à solicitação não são incorporados ao repositório
sem licença de redistribuição.

## 8. Extração e uso dinâmico de cores

A análise assíncrona, cacheada pelo hash da arte, publica:

- dominant;
- vibrant/lightVibrant/darkVibrant;
- muted/lightMuted/darkMuted;
- complementary/accent;
- background e contrastText acessível.

Algoritmos elegíveis: K-Means, Median Cut e seleção por famílias vibrant/muted.
A extração nunca roda por frame. Falha usa paleta determinística do tema. Bindings
como `{game.colors.vibrant}` são sanitizados; contraste pode promover uma variante
segura antes da renderização de texto essencial.

## 9. Glassmorphism

O node de vidro realiza:

1. captura restrita da região atrás do elemento;
2. blur offscreen;
3. tint por cor fixa ou extraída;
4. blend/opacidade;
5. borda semitransparente;
6. highlight em gradiente;
7. shadow;
8. fallback sem backbuffer blur.

O tier reduz raio, resolução do buffer ou desliga o blur antes de comprometer
foco, texto ou frame budget.

## 10. Estados, animação e transições

Estados nativos: normal, focused, selected, pressed, disabled, loading, missing,
error, offline, playing, idle e menuOpen.

- timeline, keyframes, delay, duration, repeat, sequence e parallel;
- easing linear, in/out, quad, cubic, quart, quint, expo, circ, back, elastic,
  bounce e Bézier cúbico;
- entrada: fade, slide, scale, bounce, elastic, curtain, ripple, pixelate, glitch,
  typewriter, flip, spin, zoom blur, blinds, peel, mosaic, spiral e heartbeat;
- troca de cena: crossfade, wipe, dissolve, cover flow, accordion, flip clock,
  cube e page curl quando o tier permitir;
- interrupção/reversão preserva estado e foco;
- `reducedMotion` substitui ou zera toda animação não essencial.

## 11. Componentes nativos e modos de view

- progress bar linear, circular, segmentada e dotted;
- progresso ligado a valores reais, inclusive `{current}/{total}` filtrado;
- grid, list, wall, wheel, cover flow, carousel 2D/3D, mosaic, timeline e map;
- offset converter com scale, opacity, blur, rotation, translation e z-index por
  distância do selecionado;
- highlight central e tratamento de adjacentes;
- transparência por idle, navegação, foco e menu;
- panels, cards, modals, drawers, badges, tooltips, labels e glyphs semânticos;
- clock, system monitor, recently played, favorites, random game, search, filters
  e statistics como widgets allowlisted;
- weather e integrações remotas somente por provider externo com consentimento,
  cache e estado offline; tema nunca acessa a rede.

## 12. Save-state gallery e OSD

A engine recebe contratos, não controla o emulador:

- thumbnail por slot, timestamp, playtime, compatibilidade e estado;
- grid/carousel de saves com fallback sem captura;
- OSD para volume, mute, brilho, screenshot, save/load state, fast-forward,
  rewind, pause, controle, achievement e rede;
- ícone, texto e progress bar temáveis;
- OSD não pode ocultar erro crítico nem falsificar sucesso.

Captura automática de save-state pertence ao adapter/session manager e exige
prova separada de compatibilidade e preservação.

## 13. Metadados e bindings

Campos públicos possíveis: título, ano, desenvolvedora, publicadora, gênero,
descrição, rating, classificação etária, jogadores, playtime, controles, mods,
links allowlisted, IDs externos, região, idioma, série e franquia.

Expressões seguras permitem condição, formatação, aritmética limitada,
interpolação, filtros e variáveis locais. São proibidos eval, reflexão, filesystem,
rede, processo, shell, Python, JavaScript e QML fornecido pelo pacote.

## 14. Theme Studio

O Studio completo oferece:

- canvas visual com zoom, guides, snap e seleção;
- árvore da cena e componentes reutilizáveis;
- inspector de propriedades e constraints;
- grafo de efeitos por nodes;
- timeline/keyframes/easing;
- editor de breakpoints, states e variantes;
- data bindings assistidos e dados de demonstração sem segredos;
- preview ao vivo e hot reload;
- preview simultâneo Deck/Full HD/ultrawide e tiers;
- simulação de controle, foco, offline, vazio, erro e jogo ativo;
- undo/redo, copy/paste, histórico e comparação antes/depois;
- profiler de FPS, frame time, memória, textura e draw calls;
- validadores de schema, assets, licença, foco, contraste, alvo, reduced motion,
  limites e orçamento;
- criar, salvar, exportar, importar, sobrescrever com confirmação e reabrir sem
  perda;
- pacote e digest reproduzíveis.

O editor atual de tokens, metadados e preview é fundação parcial, não evidência de
canvas, effect graph ou timeline.

### 14.1. Ergonomia de autoria para artwork heterogêneo

O backlog do Studio deve tornar o ajuste de capas e demais artes declarativo,
reversível e aplicável por objeto, sem exigir edição destrutiva dos arquivos-fonte
nem cópias pré-rotacionadas. Em especial:

- **orientação automática**: oferecer `none`, `auto`, `portrait` e `landscape`,
  comparando a orientação da imagem com a orientação do slot/moldura e permitindo
  regras condicionais por sistema, região, categoria de mídia ou variante. `auto`
  deve ser determinístico, explicável no inspector e sempre permitir override;
- **enquadramento e preenchimento**: expor visualmente `contain`, `cover`, `fill`
  e `crop`, além de alinhamento horizontal/vertical (`left|center|right` e
  `top|center|bottom`) e ponto focal. O editor deve deixar claro quando a imagem
  será recortada, distorcida ou terá letterbox;
- **regras por slot, não por asset**: uma mesma categoria de objeto pode declarar
  receitas diferentes para arte japonesa, americana, retrato, paisagem ou mídia
  ausente. A engine continua responsável por renderizar e cachear a variação; o
  pacote não deve acumular assets derivados apenas para resolver orientação ou
  enquadramento;
- **polimento seguro**: preview simultâneo em low/balanced/cinematic, fallback
  legível, high contrast, escala de texto e `reducedMotion` devem prevalecer sobre
  a estética. Toda regra precisa sobreviver a exportar/importar/reabrir sem perda.

Esses controles são requisitos futuros de autoria do Theme Studio e não promovem
por si só o estado do runtime ou do AURA Launcher.

## 15. Pacote, compatibilidade e segurança

O pacote declara schema, API mínima/máxima, autoria, licença SPDX, assets-fonte,
scenes, components, recipes e capabilities. Instalação usa staging, limites,
sanitização, digest, publicação atômica, verify e rollback.

- sem path absoluto, traversal, symlink, arquivo especial ou URL de asset;
- SVG sem script, evento, `foreignObject` ou referência externa;
- limites de arquivo, pixels, profundidade, nodes, efeitos, texturas e animações;
- tema inválido não bloqueia catálogo/startup;
- fallback para builtin seguro;
- migração de schema explícita e reversível;
- tema não substitui texto operacional, código de erro, glyph de controle ou ação
  semântica de segurança;
- assets exigem licença/atribuição; material protegido não é redistribuído como
  fixture de teste.

## 16. Acessibilidade

- alvo interativo ≥48 px;
- foco sempre visível e focus graph sem becos;
- contraste essencial ≥7:1 ou política aprovada equivalente;
- escala de texto realmente consumida;
- high contrast e reduced motion prevalecem sobre o tema;
- modos de daltonismo deuteranopia/protanopia/tritanopia;
- leitor de tela recebe nome, papel, estado e ação;
- cor não é o único canal;
- tema que não consegue adaptar degrada para apresentação segura.

## 17. Desempenho e backends

Alvo do projeto Linux: Qt Quick/RHI com Vulkan ou OpenGL suportado pelo host. O
contrato do tema é backend-neutral; DirectX/Metal não são promessa da 1.0.

Cena física de referência:

- 60 FPS estáveis em 1280×800;
- frame p95 dentro de 16,7 ms;
- home utilizável em até 2 s com cache aquecido;
- VRAM ≤512 MB e orçamento adaptativo;
- decodificação, cor e I/O fora da thread de render;
- batch/atlas/occlusion/lazy/predictive loading medidos, não presumidos;
- tiers `low`, `balanced` e `cinematic` com degradação determinística;
- nenhum efeito pesado causa tela preta, OOM ou perda de input.

FPS, tempo e memória só recebem resultado `passed` com medição na release e no
hardware identificados. Harness offscreen prova contrato, não performance física.

## 18. Integrações futuras

RetroAchievements, providers de mídia, vídeo, presença social, saves em nuvem e
streaming publicam dados por adapters próprios. A Theme Engine pode apresentar
esses dados quando existirem, mas não os implementa e não acessa seus serviços.

## 19. Ondas de entrega

1. consolidar contrato versionado de scene/effect/image e fixtures sintéticas;
2. fechar transformações de asset único e cache de derivados;
3. layouts/repeaters/bindings e breakpoints;
4. extração de cores, glass e effect nodes por tiers;
5. states, timeline e transições;
6. componentes Launcher, OSD e save gallery por contratos;
7. Studio: canvas/árvore/inspector;
8. Studio: effect graph/timeline/bindings/profiler;
9. hardening, acessibilidade, import/export e migrações;
10. release instalada, matriz física, evidência e certificação.

Cada onda segue reprodução/baseline, implementação mínima completa, teste focado,
validação física proporcional, gates integrais no fechamento, commit isolado e
evidência. Não se declara a onda completa a partir de mock ou screenshot estático.

## 20. Definition of Done

Theme Engine só vira `complete` quando:

1. um único asset gera todas as variantes de logo exigidas sem derivados no pacote;
2. scene graph, layouts, repeaters, bindings, efeitos e animações funcionam ponta
   a ponta em pacote externo seguro;
3. grid, list, wheel, cover flow, carousel, flow e stack são declarativos;
4. cor dinâmica, glass, cache e tiers possuem fallback e diagnóstico;
5. múltiplas resoluções, controle e acessibilidade passam;
6. pacote inválido/pesado volta ao tema seguro;
7. metas de FPS, frame time, startup e VRAM são medidas no Deck;
8. instalação, reexecução, atualização, rollback e remoção preservam dados;
9. release instalada possui capturas e métricas ligadas ao commit.

Theme Studio só vira `complete` quando:

1. canvas, árvore, inspector, constraints, effect graph e timeline existem;
2. designer cria as variantes previstas sem editor externo ou terminal;
3. preview cobre resoluções, states, dados e acessibilidade;
4. undo/redo e recuperação preservam o documento;
5. criar→salvar→exportar→importar→reabrir é byte/semanticamente estável;
6. validadores bloqueiam pacote inseguro, incompatível ou acima do orçamento;
7. o pacote produzido roda na Theme Engine instalada;
8. evidência física e relatório mostram o fluxo real de autoria e consumo.

Conclusão da Theme Engine ou do Studio não promove automaticamente AURA UI nem
AURA Launcher. Os quatro itens mantêm estados e provas independentes.

## 21. Jornadas de experiência, menus e etapas

A navegação completa da experiência é um documento sidecar versionado
`experience-journey-v2`; leitores também migram documentos v1 para v2. Ela não é
uma extensão informal do manifesto `theme-manifest-v1`, que continua rejeitando
propriedades desconhecidas. Os contratos estão em
`src/steamzero/schemas/experience-journey-v1.schema.json` e
`src/steamzero/schemas/experience-journey-v2.schema.json`.

- O documento separa a organização visual da árvore do grafo de conexões. Links
  apontam para IDs estáveis de menus/etapas, e várias origens podem apontar para
  o mesmo menu sem copiar sua cena ou seus assets.
- A implementação inicial publica limites de proteção de **4 MiB por documento
  serializado**, **4.096 menus**, **16.384 conexões**, **8.192 posições de
  organização**, **64 filtros por menu** e **512 contextos de voltar**. São
  limites de recursos do contrato, não um limite de profundidade. Ao se aproximar
  deles, a UI/runtime deve avisar e oferecer diagnóstico; listas grandes usam
  virtualização. Complexidade de validação e roteamento é O(V+E) em menus e
  conexões. Estes tetos não substituem medição de memória/tempo do Engine e do
  Launcher em hardware/release identificados.
- Ciclos iniciados por input explícito são válidos. Ciclos só automáticos são
  diagnosticados para impedir execução sem saída. Referências ausentes não são
  corrigidas silenciosamente.
- Fontes, campos, tipos e valores vêm de read models públicos versionados. Filtros
  combinam como AND, são tipados e allowlisted; ordenação usa os mesmos campos.
  A v2 acrescenta agrupamento por campo publicado e bindings declarativos entre
  menus, que só acrescentam filtros AND no destino.
  SQL, eval, script, QML, shell e acesso a tabelas internas não fazem parte do
  contrato. Dados desconhecidos, zero resultados e fonte indisponível têm
  estados e recuperação distintos.
- O contexto de navegação preserva menu de origem, seleção, filtros, rolagem e
  foco. Respostas de ações antigas são descartadas depois de uma rota mais nova.
  Ao voltar da sessão, o destino é o contexto capturado, não uma Home presumida.
- Cada menu e etapa visual pode declarar tema próprio. A omissão herda AURA com
  motivo `not-customized`; escolha explícita de AURA tem motivo separado. Tema
  inexistente e recurso visual incompatível têm diagnósticos próprios e fallback
  por trecho. Cobertura é calculada apenas para etapas usadas. Origem visual e
  capability operacional são resultados independentes.
- Launch, pausa, retomada, save/load e exit são ações semânticas governadas pelo
  domínio/adapters. Uma animação de fade não confirma uma operação. A etapa
  seguinte observa sucesso/falha/timeout publicados pela sessão; herança visual
  nunca habilita uma operação indisponível.
- O mesmo documento salvo/reaberto deve alimentar Studio Preview, Theme Engine e
  Launcher/AURA Cinema. O caminho de aceitação inclui três ou mais menus,
  facetas diferentes que compartilham destinos, temas por etapa, aviso de
  herança, round-trip/export/import, retorno contextual e erros recuperáveis.

### Matriz de superfície e operação

| Etapa/superfície | Fonte e navegação | Dono operacional | Prova necessária |
|---|---|---|---|
| Plataformas, gêneros, anos, fabricante, hardware, emulador e outras facetas | Campos/tipos/valores de read model público; filtros combinados seguem no contexto | Read model + runtime do Launcher | Campos novos aparecem sem tela codificada por campo; vazio, unknown e fonte indisponível têm contagem/recuperação |
| Menu de jogos compartilhado | Várias origens usam o mesmo ID; conexão e filtros não copiam cena | Navegação do Launcher | Entrar por plataforma e outra faceta; Voltar restaura filtros, jogo, rolagem e foco de cada origem |
| Fade de entrada | Aparência própria ou AURA; limitado e interrompível | Resultado de launch do adapter/sessão | Mostrar sucesso, falha, retry e timeout; fade nunca é o oráculo de que o jogo abriu |
| Jogo e bezel | Composição da etapa mais dados publicados da sessão | Adapter de launch/sessão e capability de bezel | Jogo ativo, bezel suportado/ausente, erro e saída observados separadamente |
| Pausa e retomada | Menu compartilhável com aparência própria ou AURA | Capabilities pause/resume do adapter | Só entrar após confirmação; retomar ou falhar sem perder a origem |
| Saves | Fonte publicada do domínio de saves; save comum e save-state não se confundem | Domínio/adapters de saves | Listar, carregar, cancelar, falhar e voltar; preservar o estado real publicado pelo adapter |
| Fade de saída e retorno | Aparência por etapa; destino é o contexto de jogo salvo | Resultado de exit do adapter/sessão | Saída confirmada ou falha governada; voltar ao mesmo jogo/filtros/foco e depois à faceta anterior |
| OSD, loading, vazio, erro e offline | Estado/mensagem/ações de recuperação publicados | Domínio responsável pela operação | Mensagem e ação reais, timeout/retry e foco utilizável; sem tela morta |

Antes de aplicar, a matriz de cobertura mostra origem e versão de cada etapa
usada. A etiqueta de herança conta apenas omissões ou escolhas explícitas de
AURA; referências ausentes e incompatibilidades aparecem em linhas próprias,
mesmo quando seu fallback visual também usa AURA. A lista de capabilities do
adapter não deriva da aparência escolhida.

O estado atual é **parcial**. A branch de continuidade contém o schema v2, o
serviço transacional e o painel de Jornadas anexado ao Theme Studio, com árvore,
conexões, filtros, bindings, agrupamento, temas por menu/etapa, aviso de
herança, histórico e operações de arquivo. A bridge autenticada de loopback
publica `journey.studio.*` sobre `JourneyStudioService` e os read models
públicos do Desktop. O teste QML da bridge cria e edita menus pela interface,
salva/reabre a mesma jornada e usa a composição da etapa selecionada.

`journey.studio.engine-preview` consulta os resultados filtrados no servidor,
limita bindings ao catálogo de campos públicos, resolve a cobertura da etapa e
passa `preview.items` ao `DesktopDashboard.editor_preview`/`ThemeEditorManager`.
O resolver native materializa os `sceneLayouts` declarados, e o QML reutiliza
`ThemeStudioCanvas`. Um teste de bridge confirma que o documento reaberto com o
tema `org.steamzero.asset-recipes-demo` produz somente o título filtrado da
Jornada, sem a amostra estática Axiom Verge. Referência de tema ausente ou slot
incompatível cai explicitamente em AURA e devolve a causa; high contrast e
reduced motion usam os probes do dashboard na execução normal. A cena XML
continua usando o renderer ES-DE já existente e recebe a projeção filtrada do
componente, mas não foi exercitada nesse round-trip da bridge.

Outro teste edita `maxItems` no tema filho de `asset-recipes-demo`, salva e
reabre o pacote, e confirma que o Theme Engine mantém a edição na prévia da
Jornada: dos três registros filtrados, só os dois primeiros chegam à cena. A
cobertura também usa `sceneSurfaces` herdado da cadeia `extends`, sem declarar
incompatibilidade falsa. Isso verifica o consumo nativo do documento salvo no
Theme Engine neste checkout, com fixtures e registros sintéticos isolados.

O resultado não prova a janela Main instalada, pixels/tempo de uma release, nem
consumo pelo AURA Launcher/Cinema. A cena XML ainda não foi exercitada nesse
round-trip. Capabilities de launch, pause/resume, saves, bezel e exit continuam
`unknown` quando o adapter da sessão não as publica; a aparência resolvida
nunca as habilita. Não houve integração de sessão ou input físico nesta etapa.
Theme Studio, Theme Engine, AURA UI, AURA Launcher e os adapters de sessão
continuam com critérios e provas independentes.
