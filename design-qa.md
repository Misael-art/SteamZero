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

## Iteração Área Modo Desktop — 2026-07-17

**Referência vencedora:**
`/home/misael/.codex/generated_images/019f66dd-1834-72b3-b44a-4e06b4a64b8c/exec-f662d739-150f-4aaf-b6d6-8f269e8685d9.png`

**Implementação consolidada:** `/tmp/steamzero-desktop-a33-final.png`

**Comparação combinada na mesma escala:** `/tmp/steamzero-desktop-a33-comparison.png`

**Viewport lógico:** 1600×1000; captura física 1200×750 com `QT_SCALE_FACTOR=0.75`.

- O seletor contextual da seção Steam agora oferece **Modo Desktop** ao lado de
  Desempenho e LSFG, Controles e Biblioteca, sem criar uma navegação paralela.
- A tela reutiliza a direção visual Prontidão aprovada, os tokens do `Main.qml`, ícones
  KDE e os componentes existentes. A hierarquia separa verdade do perfil, input,
  display/dock, sessão/recuperação e preparação do Sistema.
- Plano, apply, reset, resolução de conflito, recovery e teclado chamam handlers reais;
  preparação KVM/libvirt e drivers permanecem ações de Sistema, não instalações fingidas
  dentro da Steam.
- A comparação combinada confirma tema, tipografia, hierarquia e densidade da direção
  Prontidão, sem texto cortado, sobreposição ou alvo primário menor que 48 px. A tela não
  replica o conteúdo de Gameplay: reutiliza a linguagem aprovada para perfil Desktop,
  entrada, display/hotplug e sessão/resiliência.
- Estados técnicos foram localizados (`não aplicado`, `degradado`, `desatualizado`) e
  continuam semanticamente distinguíveis por cor e texto. O banner de atenção não depende
  apenas de cor.
- O focus graph cobre navegação vertical por D-pad em Gameplay e Modo Desktop; o seletor
  discreto de perfil também possui navegação esquerda/direita, sem interceptar sliders ou
  listboxes. `Accessible.name` e os alvos de ação permanecem explícitos.
- `qmllint` passou para `Main.qml`, `SteamGameplay.qml` e `SteamDesktop.qml`; o gate completo
  passou com **590 testes** e **85,46%** de cobertura. O host continua reportando divergência
  Desktop como `degraded`, em vez de exibir sucesso incorreto.

Nenhuma diferença acionável P0/P1/P2 permanece.

final result: passed

## Iteração Launcher Steam observável — 2026-07-17

**Implementação:** `/tmp/steamzero-launcher-runtime.png`

**Viewport lógico:** 1600×1000, capturado no Steam Deck com `QT_SCALE_FACTOR=0.75`.

- A faixa **Lançamento gerenciado** fica entre seleção/escopo e prontidão, refletindo a
  ordem mental jogo → política → runtime → ajustes.
- Estado e Launch Option são legíveis e selecionáveis sem competir com o CTA principal.
  A recuperação só aparece para sessão interrompida; execução observada usa verde e
  divergência/falha usa âmbar.
- O texto explica que o perfil somente vira observado durante uma execução real, evitando
  confundir política salva com hardware efetivamente alterado.
- Nenhuma diferença P0/P1/P2, truncamento ou controle menor que o padrão foi observado.

final result: passed

## Iteração Launch Options automática — 2026-07-17

**Implementação:** `/tmp/steamzero-launch-options-auto.png`

**Viewport físico:** 1280×800 no Steam Deck, KDE com escala 1,35.

- A configuração permanece dentro de **Lançamento gerenciado**, sem competir com a
  criação do perfil nem aparentar ser uma instalação de Sistema.
- O estado diferencia configuração ausente, valor externo, Steam em execução e wrapper
  já gerenciado. Substituição de valor externo exige diálogo de revisão e informa o
  rollback G-FULL antes da confirmação.
- O primeiro QA revelou truncamento da ação no breakpoint real. O rótulo compacto
  **Configurar** mantém o alvo acessível; o nome completo para tecnologia assistiva
  é **Configurar Launch Options automaticamente na Steam**.
- Nenhuma diferença P0/P1/P2 permanece na faixa gerenciada. O conteúdo avançado segue
  rolável sob a barra fixa de ações, como definido na direção visual aprovada.

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

---

# Responsive Design QA — SteamZero

## Evidence

- Source visual truth:
  - `/run/user/1000/codex-desktop/tmp/codex-clipboard-7fbfe836-1604-48c8-813c-4899f44ed4ec.png`
  - `/run/user/1000/codex-desktop/tmp/codex-clipboard-e57c7577-f337-4615-a5e1-0fe763760f92.png`
  - `/run/user/1000/codex-desktop/tmp/codex-clipboard-5d797c2a-67de-4668-97d0-b799e13ca450.png`
- Implementation screenshots:
  - `/home/misael/.codex/visualizations/2026/07/22/019f8a30-4b0d-7c71-90af-47eea14605f7/responsive-qa/steamzero-responsive-1280x800-shell.png`
  - `/home/misael/.codex/visualizations/2026/07/22/019f8a30-4b0d-7c71-90af-47eea14605f7/responsive-qa/steamzero-responsive-1280x800-emulation.png`
  - `/home/misael/.codex/visualizations/2026/07/22/019f8a30-4b0d-7c71-90af-47eea14605f7/responsive-qa/steamzero-responsive-1280x800-steam.png`
  - `/home/misael/.codex/visualizations/2026/07/22/019f8a30-4b0d-7c71-90af-47eea14605f7/responsive-qa/steamzero-responsive-1920x1080-emulation.png`
  - `/home/misael/.codex/visualizations/2026/07/22/019f8a30-4b0d-7c71-90af-47eea14605f7/responsive-qa/steamzero-responsive-2560x1080-shell.png`
- Combined comparisons:
  - `/home/misael/.codex/visualizations/2026/07/22/019f8a30-4b0d-7c71-90af-47eea14605f7/responsive-qa/compare-deck-emulation.png`
  - `/home/misael/.codex/visualizations/2026/07/22/019f8a30-4b0d-7c71-90af-47eea14605f7/responsive-qa/compare-deck-steam.png`
  - `/home/misael/.codex/visualizations/2026/07/22/019f8a30-4b0d-7c71-90af-47eea14605f7/responsive-qa/compare-ultrawide-emulation.png`

The source screenshots include native window chrome. Implementation captures contain the
application-owned QML content only. All captures use device scale factor 1. The component
captures normalize the inner application viewport after the global sidebar/banner/footer:
1208×696 for Deck, 1656×954 for Full HD, and 2296×954 for ultrawide.

## State and interactions checked

- Compact global navigation and tooltip-backed icon-only mode.
- Compact Emulation area selector replacing the static sub-sidebar.
- Global, emulator, game, handheld, and dock scope controls.
- Sticky primary action in Emulation and sticky review/apply controls in Steam Gameplay.
- One-column compact content and desktop/ultrawide contextual panels.
- Full HD standard navigation, two-column card grid, and context panel.
- Ultrawide 1400 px content cap with a separate context/status column.

## Full-view comparison

The compact implementation removes the two simultaneous text sidebars visible in the
source, reduces top chrome, keeps the scope/area controls above the fold, and reserves the
bottom edge for the active CTA. No horizontal overflow or hidden CTA is visible at the Deck
viewport. The ultrawide implementation preserves the original hierarchy while preventing
forms and cards from stretching across the full 21:9 canvas.

## Focused-region comparison

Focused comparison was performed on the navigation/header/action regions and the Steam
Gameplay settings/footer region. Icons continue to use the existing theme and supplied
SteamZero/Switch assets; no placeholder or generated imagery was introduced. The action
regions remain keyboard controls with accessible names and visible focus borders.

## Required fidelity surfaces

- Fonts and typography: existing font family and weights are preserved; compact titles step
  down without truncating the screen title. Secondary copy uses elision only where the same
  context remains available through the selected area or accessible description.
- Spacing and layout rhythm: compact gutters are 12 px, desktop gutters are 20–28 px, cards
  stack at compact size, and ultrawide content is capped at 1400 px.
- Colors and visual tokens: existing background, surface, cyan, green, amber, red, border,
  and focus tokens are unchanged.
- Image quality and asset fidelity: existing raster/vector assets are reused at their native
  aspect ratio. No image was stretched or replaced.
- Copy and content: application copy is unchanged except for responsive presentation.
- Accessibility: primary tap targets remain at least 40 px; global compact navigation exposes
  its text through accessible names and hover/focus tooltips.

## Comparison history

1. First compact capture found a P1: hiding the context panel also hid Emulation's primary
   action. Fix: added a compact sticky action footer bound to `primaryAction()`.
2. Second compact capture found a P2: secondary system buttons rendered truncated text in the
   72 px sidebar. Fix: removed those duplicate shortcuts from compact mode; their destinations
   remain available in the primary navigation.
3. Post-fix captures show the primary action continuously visible, no clipped sidebar labels,
   no horizontal overflow, and contained ultrawide controls.

## Findings

No actionable P0, P1, or P2 findings remain for the requested responsive breakpoints.

## Follow-up polish

- P3: verify the exact system icon glyphs under the production KDE icon theme; the offscreen
  software renderer uses its fallback theme for capture.

final result: passed
