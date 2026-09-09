# ADR-0028 — Tema default AURA Cinema para a experiência fullscreen

**Status:** aceito

## Contexto

O plano de execução da plataforma fullscreen
(`docs/12-roadmap/AURA-FULLSCREEN-PLATFORM-EXECUTION-PLAN.md`, frente A0) exige um
tema default para o shell fullscreen AURA. A direção visual de referência são os
conceitos que Aura original, RetroFE e BigBox compartilham: arte do jogo como
protagonista, fundo discreto, navegação horizontal com destaque seletivo e
metadados discretos.

Três restrições vêm antes da estética:

1. **Independência (ADR-0019):** nenhum código, asset, layout proprietário, marca,
   XML específico ou pacote de terceiros é copiado. A referência estética é uma
   direção, não uma dependência operacional.
2. **"Renderize, não edite"** (`docs/01-product/THEME-ENGINE-AND-STUDIO.md`): o tema
   guarda asset-fonte e receita declarativa; variações são produzidas pela Theme
   Engine e apenas cacheadas.
3. **Fronteira de confiança (AGENTS.md §10):** tema de terceiros não executa QML,
   JavaScript, Python, shell, binário, biblioteca ou shader arbitrário — somente
   scene graph, bindings, componentes e effect nodes allowlisted.

O tema default é uma implementação independente do SteamZero, empacotada como
tema do projeto e construída sobre o scene graph e as receitas declarativas
próprios.

## Decisão

O tema default da experiência fullscreen chama-se **AURA Cinema** e segue a
composição abaixo. Cada região tem fallback obrigatório: o tema **nunca** deixa o
usuário sem foco, sem ação de retorno ou em tela preta.

| Região | Conteúdo | Fallback obrigatório |
|---|---|---|
| Fundo | fanart blur, vignette e cor extraída | fundo sólido por tier e tema seguro |
| Centro | cover, logo derivado e foco | ícone de sistema + título |
| Laterais | capas adjacentes com escala/opacidade/blur | cards tipográficos |
| Rodapé | ano, gênero, jogadores, rating, playtime | somente campos disponíveis |
| Cabeçalho | marca, coleção, relógio e estado de conexão | cabeçalho estático mínimo |
| Detalhe | screenshots, descrição, ações e requisitos | página textual navegável |
| Overlay | pause, saves, controles, manual e estado | menu sem mídia e sem processo auxiliar |

### Tiers de renderização

- **low:** sem vídeo, sem glass pesado, sem partículas; blur reduzido; imagens
  pré-dimensionadas; foco de alta legibilidade.
- **balanced:** blur, paleta dinâmica, parallax leve, transições e screenshots.
- **cinematic:** efeitos avançados allowlisted, vídeo quando medido no hardware
  indicado, reflexo e composição multicamada.

Precedência normativa: `reducedMotion`, `highContrast`, escala de texto e falha do
backend **prevalecem sobre qualquer escolha estética**. A degradação entre tiers
nunca remove foco, navegação ou ação de retorno.

### Budget de desempenho

Aprovado para o tier balanced, medido no hardware e na release indicados — nunca
inferido de teste offscreen:

- startup até **2 s** com cache quente;
- **60 FPS** em 1280×800;
- p95 de frame time até **16,7 ms**;
- VRAM até **512 MB**.

### Contratos de dados associados

- `src/steamzero/schemas/game-record-v1.schema.json` — GameRecord canônico com
  MediaRole (`cover`, `fanart`, `screenshot`, `marquee`, `video`, `icon`) e
  Provenance (origem, timestamp, confiança, política de conflito).
- `src/steamzero/schemas/enhancement-entry-v1.schema.json` — EnhancementEntry do
  registry de melhorias por jogo.

Campos desconhecidos no GameRecord são tolerados e preservados: o modelo canônico
evolui por versão de schema, não por descarte silencioso de dados.

## Consequências

- O importador de metadados nunca apaga informação mais rica por causa de um
  formato mais pobre; conflito vira estado explícito (provenance + warnings).
- Ausência de arte, vídeo, GPU ou plugin Qt produz o fallback da tabela, com
  legibilidade e jogabilidade preservadas — não tela vazia.
- Qualquer alegação de FPS, memória ou fidelidade visual do tema exige medição no
  hardware e na release indicados.
- A implementação visual do AURA Cinema pertence à frente A4 (shell) e à Theme
  Engine; este ADR não declara nenhuma delas implementada.
