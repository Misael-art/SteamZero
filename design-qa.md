# Design QA — System Studio Desktop

**Source visual truth path:**
`/home/misael/.codex/generated_images/019f66dd-1834-72b3-b44a-4e06b4a64b8c/exec-ad2311d9-147d-4dbf-88c2-8c1efccf717e.png`

**Implementation screenshot path:** `/tmp/steamzero-redesign-pass6.png`

**Additional rendered states:**

- `/tmp/steamzero-steam-section.png` — área Steam dedicada;
- `/tmp/steamzero-recovery.png` — recuperação de emergência;
- `/tmp/steamzero-installed-clean.png` — wheel instalado, painel interno do Deck a 135%.

**Viewport:** comparação normalizada em 1586×992; implementação original em janela
1280×800 logical, capturada a 1841×1193 no KDE/Wayland a 135%. A validação no painel
interno foi capturada em 1393×859 físicos, com o compositor limitando a largura lógica.

**State:** modo Desktop no Steam Deck LCD; comparação principal com conflito
`E-DESKTOP-OWNER-CONFLICT`. Os dados de componentes diferem intencionalmente: o mock
mostra instalações ilustrativas, enquanto a implementação mostra a verdade do host
(Dolphin/RetroArch ausentes e fonte DuckStation EOL).

## Full-view comparison evidence

Comparação conjunta: `/tmp/steamzero-design-qa-combined.png`. Fonte e implementação
foram colocadas no mesmo canvas após remover a moldura externa e normalizar o conteúdo.
A composição preserva sidebar, banner de conflito, título/filtros, lista central,
painel de detalhe e footer de controle. A cópia instalada também foi aberta diretamente
de `/opt/steamzero/current`, confirmando a variação responsiva sem sobreposição.

## Focused region comparison evidence

Comparação conjunta focada: `/tmp/steamzero-design-qa-focused.png`. O recorte cobre
banner, filtros, densidade das três linhas, estados, ações e painel de detalhe. Foi usado
porque tipografia pequena, alinhamento dos logos e tratamentos de disabled não eram
legíveis com confiança apenas na visão completa.

## Findings

- Nenhum achado P0, P1 ou P2 permaneceu na comparação final.
- [P3] Os ícones monocromáticos da navegação variam levemente conforme o tema KDE.
  Isso preserva integração nativa e não altera hierarquia, leitura ou affordance.
- [P3] A implementação usa dados reais ausentes/EOL, reduzindo a densidade de metadados
  frente ao mock. A diferença é funcional e evita apresentar instalações inexistentes.

### Required fidelity surfaces

- **Fonts and typography:** família nativa Qt/KDE, pesos e escala preservam a hierarquia
  do alvo; títulos, labels e texto auxiliar não colidem nem truncam no viewport comparado.
- **Spacing and layout rhythm:** tracks principais, margens, seleção ciano, bordas,
  padding e footer correspondem ao conceito. A lista ganha largura quando o painel de
  detalhe é ocultado no viewport real do Deck.
- **Colors and visual tokens:** fundo azul-preto, superfícies elevadas, ciano de foco,
  âmbar semântico, verde de pronto e estados disabled possuem contraste consistente.
- **Image quality and asset fidelity:** Dolphin, DuckStation, RetroArch e Steam usam SVGs
  reais licenciados; a marca SteamZero usa PNG próprio com transparência limpa. Não há
  emoji, placeholder, SVG inline artesanal ou desenho CSS substituindo assets visíveis.
- **Copy and content:** rótulos são autônomos, acionáveis e contextualizados em pt-BR;
  conflito e recuperação explicam impacto e próximo passo sem exigir terminal.
- **Behavior and accessibility:** navegação, filtros, seleção, planos confirmados, Steam,
  Quick Reset, doctor e recuperação possuem handlers reais; foco ciano, alvos mínimos e
  grafo de teclado/controle foram preservados. Timeout/erro da bridge gera feedback.

## Comparison history

1. **Primeira renderização — bloqueada:** P2 em logos genéricos, botões nativos claros
   sobre tema escuro e proporções não normalizadas. Correções: assets SVG reais, marca
   própria, `DarkButton.qml`, tokens disabled e captura no mesmo viewport.
2. **Renderização intermediária — bloqueada:** P2 em legibilidade de ações e falta de
   equivalência visual para Steam. Correções: lista/detalhe Steam com quatro capacidades,
   estados reais, botões escuros e deep-link de seção para inspeção.
3. **Pass 6 — aprovada:** as comparações full-view e focada não apresentam diferença
   P0/P1/P2 acionável. Estados adversos adicionais foram renderizados e a cópia instalada
   confirmou a resposta no viewport físico do Deck.

## Implementation checklist

- [x] Header contextual e conflito acionável.
- [x] Gerenciamento real de emuladores em lista/detalhe.
- [x] Área Steam equivalente e funcional.
- [x] Recuperação de emergência em um clique.
- [x] Layout adaptativo, foco por controle e feedback de erro.
- [x] Wheel instalado e renderizado no host.

## Follow-up polish

- P3 opcional: empacotar uma família própria de ícones monocromáticos caso a consistência
  entre temas KDE passe a ter prioridade sobre integração visual nativa.

final result: passed
