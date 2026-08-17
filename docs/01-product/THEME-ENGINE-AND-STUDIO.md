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
3. grid, list, wheel e cover flow são declarativos;
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
