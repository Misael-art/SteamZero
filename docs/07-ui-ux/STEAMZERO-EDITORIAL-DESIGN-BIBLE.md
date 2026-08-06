# SteamZero Editorial — Design Bible v1

## Intenção

SteamZero Editorial usa uma base **mineral mist** legível e uma única mídia do
usuário como matéria contextual. A composição não reproduz temas de terceiros:
retém apenas os princípios úteis observados nas referências — foco central,
vizinhos silenciosos, espaço negativo, título expressivo e dados junto à ação.
Nenhum asset, fonte, logo, imagem de jogo ou nome de ROM de referência entra no
pacote.

## Hierarquia e grid

- O foco principal é único: item, sistema ou ação `Jogar`.
- Biblioteca editorial: capa focal em cor plena; vizinhas com saturação/opacidade
  reduzidas; título, metadados e índice alfabético perto do foco.
- Dossiê: capa e ação na primeira camada; descrição e compatibilidade na segunda;
  screenshots, controles, saves e diagnóstico em painéis progressivos.
- Home organiza continuar, recentes, favoritos, coleções, sistemas e pendências
  reais. Estados futuros usam `planned` e não ações falsas.
- Margens e colunas derivam do viewport; alvos mínimos são 48 px. Em retrato, a
  capa sobe antes da descrição; em TV/ultrawide, o espaço extra vira respiro, não
  linhas excessivamente largas.

## Tokens, tipo e movimento

Papéis tipográficos: `display`, `heading`, `title`, `body`, `metadata`, `badge`,
`caption`, `controlHint`, `diagnostic`. A fonte padrão continua a do sistema
enquanto não houver uma fonte distribuível com licença registrada. Escalas 100,
135, 150 e 200% refluem; truncamento sempre conserva acesso ao texto integral.
Os tamanhos desses papéis são tokens versionados de `typography` e a Home e a
Biblioteca os consomem pelo `ThemeBridge`; a composição não depende mais de
tamanhos literais espalhados nessas superfícies.

Foco responde em 120 ms; item muda em 180 ms; vista muda em 300 ms. O movimento
reduzido elimina zoom/parallax/reflexo e preserva a informação com corte ou fade
curto. Alto contraste remove tratamento de mídia que reduza legibilidade.

## Pilha de efeitos

`theme.json.effects` é versionado separadamente (`schemaVersion: 1`) e contém
apenas efeitos allowlisted: blur, saturation, brightness, contrast, colorize,
opacity, shadow, glow, reflection, gradientMask e vignette. Cada efeito é
validado no schema e no domínio, possui valores padrão, limites, capability,
custo e fallback determinístico. Temas não carregam QML, JavaScript ou shaders.

O renderer captura a source uma vez e reaproveita essa textura em
`QtQuick.Effects.MultiEffect`, `ReflectionLayer` e `VignetteLayer`. Reflexo
espelhado, máscara alpha gradiente e vinheta são primitives locais confiáveis;
por isso `graphics.effect.reflection` e `graphics.mask.gradient` são anunciadas
somente no runtime que as implementa. Cada uma continua negociada por
capability e produz diagnóstico/fallback determinístico quando indisponível,
sem quebrar a cena ou alegar fidelidade completa. `cinematic` usa a pilha inteira
suportada; `balanced` reduz parâmetros caros; `economy` remove
blur/glow/reflection/vignette; `accessible` remove tratamento visual para
priorizar contraste.

Além de cor/geometria/tipo/movimento, `tokens` publica namespaces fechados de
`stateVariants`, `interaction`, `accessibility` e `performance`. Eles definem
escala de foco, opacidade periférica, alvo mínimo, precedência obrigatória do
sistema e tier padrão. Um tema não pode esconder foco, reduzir o alvo abaixo de
48 px ou negar alto contraste/movimento reduzido. O builtin `1.1.0` aplica a
base mineral mist também fora da biblioteca editorial.

## Mídia, estados e performance

Seleção contextual determinística: hero/fanart, boxart, screenshot, banner,
arte de plataforma, composição geométrica. `EditorialLibrary` já preserva e
prioriza hero/fanart → capa → screenshot → banner quando esses campos chegam no
read model; quando não chegam, não tenta varrer o disco. A mesma mídia fonte alimenta fundo,
foco e reflexo; derivados só podem ser caches limitados e invalidados pelo hash
do master. Sem mídia, o ícone da origem e a composição mineral mantêm título,
foco e ação sem fingir que existe arte.

Não há pré-processamento de imagens para representar estado visual. O carrossel
usa `ListView` horizontal virtualizado, com reutilização de delegates e cache
de duas capas: uma biblioteca grande não cria um item QML por jogo. As telas
operacionais usam a mesma linguagem, com menos dramaticidade e dados reais.

## Navegação e honestidade operacional

Intents semânticas governam D-pad, analógicos, A/B, touch, mouse e teclado. O
retorno restaura seleção e contexto; nenhuma ação essencial depende de hover.
Recursos sem contrato recebem estrutura e estado `planned`/`unavailable`, ficam
desabilitados e descrevem a limitação sem fabricar dados ou confirmação.

## Componentes e corte vertical implementados

`EditorialHome.qml` projeta continuar, recentes, favoritos, coleções, sistemas e pendências a partir
de playtime, coleções, Steam e emulação. Coleções publicadas abrem a Biblioteca
com o filtro de membros preservado; sem coleção não há ação fictícia. Uma retomada só é primária se o read
model já publicar uma ação segura; caso contrário, a Home abre a biblioteca.
Emuladores, saves e sync, saúde de biblioteca e diagnóstico aparecem como
cartões de manutenção discretos e levam às seções operacionais existentes; não
recebem tratamento cinematográfico nem ações próprias.

`OperationalMetricCard.qml` aplica a mesma hierarquia factual às telas de
manutenção. A primeira adoção é Saves e Sync: pendentes, conflitos preservados
e concluídos são uma grade responsiva com estado explícito, enquanto provider,
detalhes e rollback continuam nas rotas operacionais já existentes.

`EditorialLibrary.qml` implementa **Sistemas → Sistema → Biblioteca → Dossiê →
Preparar para jogar** com `steamGameplay.games` e o índice canônico
`emulation.editorialPlatforms` (com fallback para `emulation.platforms`). A
vista de sistema mostra estado e ação real;
subsistemas/regiões/variantes permanecem em posição `planned` até que a fonte os
publique. Steam publica IDs numéricos e usa o contrato `steam.game.launch`; o
botão abre a revisão e não muda opções de lançamento. Jogos emulados sem
launcher seguro publicado mostram `Lançamento indisponível`, com a razão real,
e não imitam uma ação disponível.

BIOS, keys e firmware formam uma camada própria da vista de Sistema. Keys e
firmware usam o requirement publicado; BIOS sem contrato continua “não
publicado”, e nunca é rotulado falsamente como ausente ou pronto.

A biblioteca oferece carrossel focal, grade e lista virtualizadas sobre a mesma
fonte filtrada por sistema, coleção e alfabeto. Recentes e favoritos entram pela
Home e pelas coleções publicadas. Gênero, ano e desenvolvedor já têm posições
estruturais: filtram somente os valores recebidos em cada jogo; se a fonte não
publicar o campo, o controle fica explicitamente indisponível e explica o
limite, sem gerar categorias artificiais.

O dossiê expõe plataforma, origem, mídia, gênero, ano, desenvolvedor, tempo,
sessões e última sessão quando publicados. A revisão acrescenta perfil, FPS, resolução, controles e sync quando
o read model os contém; ano, gênero, desenvolvedor, vídeo e compatibilidade
detalhada continuam indisponíveis até receberem contrato verdadeiro.

`ScreenshotRail.qml` mantém a galeria de capturas como uma `ListView`
virtualizada, com no máximo 24 fontes publicadas e deduplicadas. Sem screenshot,
ou no alto contraste, ela comunica o estado sem renderizar uma imagem substituta;
vídeo continua fora da UI até haver um contrato de reprodução segura.

A árvore visível é pequena e reutilizável: `EditorialHome` e
`EditorialLibrary` consomem `MediaEffectLayer`, `ReflectionLayer`,
`VignetteLayer`, `NavigationIcon` e os tokens resolvidos pelo `ThemeBridge`.
`EditorialLibrary.handleNavigationIntent()` recebe intents semânticos de
movimento, confirmação e retorno; adaptadores de controle, touch, mouse e
teclado ficam fora do tema. A biblioteca é a última seção da navegação sem
mudar os índices das áreas operacionais existentes. Os harnesses QML percorrem
os dois caminhos de origem, retrato 800×1280, 4K lógico a 200%, alto contraste,
movimento reduzido e uma fixture de 1.200 títulos virtualizada.

Para revisão visual manual, `check_editorial_library.qml` também captura as
etapas `systems`, `system`, `library` e `dossier`; a captura da etapa Sistema verifica no
compositor o contraste de BIOS/keys/firmware antes de qualquer decisão de
produto.

## Proveniência

As seis imagens e layouts externos foram somente auditados como referência
visual read-only. Decisões mantidas: uma capa focal, vizinhos com peso visual
reduzido, metadados próximos à seleção, espaço negativo que separa navegação de
detalhe e trilho alfabético. Decisões descartadas: marcas de terceiros,
relógio/data decorativos, ilustrações de controle, marcas d'água de sistema,
texturas de fundo e qualquer arte/mídia de jogo presente nas referências.

Esses princípios aparecem na composição mineral e nos componentes próprios do
SteamZero, não como reprodução de uma tela de referência. A implementação atual
não adiciona assets. A mídia permanece do usuário, gerenciada pelo store
existente; fixtures sintéticas continuam restritas aos testes. Qualquer asset
futuro exige registro de autor, licença, atribuição e transformação antes de
entrar no tema builtin.
