# Design QA — Steam Gameplay / Prontidão do jogo

**Source visual truth:**
`/home/misael/.codex/generated_images/019f66dd-1834-72b3-b44a-4e06b4a64b8c/exec-f662d739-150f-4aaf-b6d6-8f269e8685d9.png`

**Implementation screenshot:** `/tmp/steamzero-gameplay-final-v4.png`

**Viewport:** 1600×1000, sem moldura de dispositivo.

**State:** Deck LCD, bateria 74%, Modo Desktop, Cyberpunk 2077 selecionado,
escopo Por jogo, perfil Equilibrado 40 FPS proposto, vkBasalt opcional ausente.

**Full-view comparison evidence:** `/tmp/steamzero-gameplay-comparison-final.png`

**Focused comparison evidence:** `/tmp/steamzero-gameplay-controls-comparison.png` compara
perfil, FPS, TDP, clock de GPU, MangoHud, upscaling e integrações na mesma escala. O
recorte foi necessário porque a densidade dos controles não é legível no comparativo
de 3200 px.

## Findings

- Nenhuma diferença P0/P1/P2 permanece. A composição conserva jogo → escopo → prontidão
  → ambiente/capacidade/ajustes/impacto → confirmação. Todos os controles obrigatórios
  estão visíveis e a ação de Sistema não é confundida com instalação dentro da Steam.
- [P3] O mockup usa um medidor circular adicional para 85%; a implementação usa número
  grande e `ProgressBar` nativa. A semântica, contraste e leitura por acessibilidade são
  preservados, sem introduzir desenho QML artesanal.
- [P3] A tipografia da implementação é um pouco mais compacta que a imagem gerada. Isso
  mantém os alvos essenciais e as três zonas simultâneas também no layout 1280×800; não
  há texto cortado no viewport comparado.
- [P3] O CTA fica acima de uma área de respiro maior em 1600×1000. A decisão evita uma
  altura fixa que quebrou a renderização responsiva durante a segunda iteração.

## Required fidelity surfaces

- **Fonts and typography:** mesma hierarquia de título, seção, label e estado; pesos e
  contraste coerentes com o QML existente. Sem truncamento nos controles principais.
- **Spacing and layout rhythm:** sidebar, banner, três zonas e footer correspondem ao
  mockup. Margens, divisores, raios e densidade são consistentes com o design atual.
- **Colors and visual tokens:** azul-preto, ciano, verde e âmbar reutilizam os tokens do
  `Main.qml`; não há gradiente ou neon novo.
- **Image quality and assets:** marca SteamZero e logo Steam usam assets reais existentes;
  a capa vem da biblioteca/cache Steam (URL oficial apenas na fixture visual). Ícones de
  ação usam o tema KDE, sem emoji, SVG artesanal ou placeholder.
- **Copy and content:** responsabilidades SteamZero/Steam/Sistema, limites 3–15 W,
  200–1600 MHz, perfis, FPS, MangoHud, upscaling, impacto e CTAs correspondem ao brief.
- **Behavior and accessibility:** alvos principais ≥48 px, nomes acessíveis, escolhas
  discretas segmentadas, TDP como único slider contínuo, revisão confirmada, bloqueios
  de componente e owner, e plano obsoleto cobertos.

## Comparison history

1. A primeira captura (`/tmp/steamzero-gameplay-implementation.png`) revelou ação
   **Abrir Sistema** encoberta, perfil atual selecionado em vez do recomendado e ausência
   do subitem Gameplay na sidebar. Foram ampliadas a zona Ambiente, separada a seleção
   recomendada do perfil salvo e adicionada a hierarquia Steam → Gameplay.
2. A tentativa de empurrar o CTA ao footer com altura derivada produziu deslocamento e
   renderização incompleta. A altura artificial foi removida; a captura pós-correção
   `/tmp/steamzero-gameplay-final-v4.png` confirma frame completo e estável.
3. O comparativo final e o recorte focado não mostram diferenças acionáveis P0/P1/P2.

## Verification

- 377 testes passaram, incluindo leitura de manifest real, plano/confirm token,
  persistência, runtime ausente, mudança de biblioteca e conflito de owner no apply.
- `qmllint` passou para `Main.qml`, `DarkButton.qml` e `SteamGameplay.qml`.
- Ruff, mypy estrito, lint de fronteiras e independência de PhaseZero passaram.
- A execução Qt/QML usada na captura não emitiu erros de console.

## Follow-up polish

- Validar foco físico e legibilidade no painel 1280×800 do Deck antes de remover o status
  de validação visual em hardware.

## Iteração LSFG e Steam Input — 2026-07-17

**Implementação — desempenho:** `/tmp/steamzero-lsfg-fixed-actions.png`

**Implementação — controles:** `/tmp/steamzero-controls-1600-scaled.png`

**Comparação combinada:** `/tmp/steamzero-lsfg-comparison.png`

**Viewport lógico:** 1600×1000, capturado no Steam Deck com `QT_SCALE_FACTOR=0.75`
para caber no painel físico sem alterar a geometria lógica do mockup.

- O subgrupo **Desempenho e LSFG / Controles** mantém jogo, escopo e prontidão como
  contexto persistente. A troca de área não cria uma nova rota nem perde o perfil em edição.
- LSFG usa listbox discreta Desligado/2×/3×/4×, mostra a propriedade Sistema e bloqueia
  a revisão quando a camada Vulkan não foi observada. Não existe instalação simulada.
- Controles usa listbox por jogo, status Steam Input e ação allowlisted **Editar no Steam**.
  A política de controles é persistida separadamente da política de desempenho.
- A primeira captura no painel reduzido mostrou a aba Controles cortada e a ação principal
  abaixo da dobra. As áreas foram movidas para uma linha própria, Ambiente ganhou diálogo
  compacto em larguras menores e as ações passaram a uma barra fixa.
- A comparação com a referência mantém tema, tipografia, estados, hierarquia e densidade.
  Nenhuma diferença P0/P1/P2 permanece; Ambiente/Capacidade passa para diálogo apenas no
  breakpoint compacto, preservando acesso sem comprimir Ajustes essenciais.
- `qmllint` passou e a execução Qt/QML das duas áreas não emitiu erros de console.

final result: passed

## Iteração Sistema / LSFG-VK — 2026-07-17

**Implementação:** `/tmp/steamzero-system-lsfg.png`

**Viewport lógico:** 1600×1000, capturado no Steam Deck com `QT_SCALE_FACTOR=0.75`.

- O componente foi posicionado em Sistema, distinguindo claramente a responsabilidade
  do SteamZero (preparar a camada livre) da Steam (fornecer o aplicativo proprietário).
- Status, origem, dependência e ações usam a mesma linguagem visual de prontidão do mockup
  escolhido. Sem Lossless Scaling, a única ação é **Abrir biblioteca**; não há instalação
  simulada nem elevação de privilégio.
- A revisão prévia expõe versão, garantia G-FULL, caminhos alterados, hash completo e a
  restrição de propriedade antes de habilitar **Instalar e verificar**.
- Nenhuma diferença P0/P1/P2, texto cortado ou erro de console foi observado; `qmllint`
  e os testes de contrato da UI passaram.

final result: passed
