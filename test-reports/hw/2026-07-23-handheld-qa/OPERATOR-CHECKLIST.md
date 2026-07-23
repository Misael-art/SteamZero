# Checklist físico — handheld QA

Data-alvo: 2026-07-23  
Branch: `codex/handheld-qa-layout-foco`  
Base: `33e95ed01b1ae5e044cd6f61cabb63f6fd08fc5a`

Este documento é um gate exclusivo do operador humano. Os testes offscreen,
`ydotool`, teclado, mouse, compositor virtual ou qualquer outra automação não
contam como evidência física.

## Regras da execução

- [ ] **PENDING** — Executar em hardware handheld real, anotando modelo,
  resolução física, escala, sessão gráfica e versão instalada.
- [ ] **PENDING** — Não confirmar instalação, remoção, sincronização, limpeza,
  lançamento, restauração, publicação Steam ou aplicação de perfil.
- [ ] **PENDING** — Usar apenas dados descartáveis/sintéticos quando a tela
  exigir conteúdo para inspeção.
- [ ] **PENDING** — Registrar foto ou vídeo de cada falha, com seção, escopo,
  área, controle focado e dimensão do viewport.

## Viewports e rodapé

- [ ] **PENDING** — Em 949×593 lógico, confirmar cabeçalho e rodapé visíveis,
  sem conteúdo sob o rodapé.
- [ ] **PENDING** — Em 1280×800 físico, confirmar cabeçalho e rodapé visíveis,
  sem conteúdo sob o rodapé.
- [ ] **PENDING** — Em cada seção principal, rolar até o fim e confirmar que o
  último controle inteiro fica acima do rodapé.
- [ ] **PENDING** — Confirmar ausência de rolagem horizontal, cortes laterais e
  conteúdo inalcançável nas duas dimensões.

## Emulação

- [ ] **PENDING** — Percorrer os escopos Global, Emulador, Por jogo, Portátil e
  Dock com D-pad/controle físico.
- [ ] **PENDING** — Em cada escopo, percorrer Visão geral, Keys e firmware,
  Updates e DLC, Mods e cheats, Gráficos e fluidez, Controles, Saves,
  Shader cache, Mídia, Armazenamento e Avançado.
- [ ] **PENDING** — Confirmar que avisos/progresso de Global, ação necessária de
  Emulador e conteúdo de Portátil/Dock permanecem roláveis e legíveis.
- [ ] **PENDING** — Medir por amostragem os seletores de plataforma, escopo e
  área; todos os alvos interativos devem ter pelo menos 48×48 px.
- [ ] **PENDING** — Confirmar que Saves e Shader cache são alcançáveis por
  controle físico e que o foco acompanha a rolagem.

## Biblioteca compacta por jogo

- [ ] **PENDING** — Confirmar cards verticais, sem reutilização visual da tabela
  desktop e sem rolagem horizontal.
- [ ] **PENDING** — No primeiro card, confirmar nome, Title ID, capa/fallback,
  emulador, requisitos e ações antes do rodapé.
- [ ] **PENDING** — Confirmar que a apresentação desktop da biblioteca não
  regrediu em viewport desktop.
- [ ] **PENDING** — Abrir Ajustes por toque e pelo botão A; confirmar foco
  inicial em Fechar e alvo de Fechar com pelo menos 48×48 px.
- [ ] **PENDING** — Rolar o drawer até o último controle e confirmar que ele
  fica inteiro acima do rodapé.
- [ ] **PENDING** — Fechar o drawer e confirmar que o foco retorna ao botão
  Ajustes/item que o abriu, nunca ao menu principal.

## Busca e teclado virtual

- [ ] **PENDING** — Focar a busca por toque, D-pad, botão A e Enter.
- [ ] **PENDING** — Confirmar que o teclado virtual do sistema aparece somente
  quando o campo editável recebe foco.
- [ ] **PENDING** — Buscar por nome e por Title ID; fechar o teclado virtual e
  confirmar preservação do texto e do foco.
- [ ] **PENDING** — Continuar a navegação direcional depois de fechar o teclado,
  sem salto para menu, rodapé ou outro painel.

## Steam e Modo Desktop

- [ ] **PENDING** — Percorrer os quatro escopos Steam e as áreas Desempenho e
  LSFG, Controles, Biblioteca e Modo Desktop.
- [ ] **PENDING** — Confirmar que 30/40/60 FPS ficam visíveis, focáveis e com
  alvos de pelo menos 48×48 px.
- [ ] **PENDING** — Confirmar os quatro perfis revisáveis do Modo Desktop e a
  restauração de foco ao fechar a revisão.
- [ ] **PENDING** — Abrir e fechar diálogos somente leitura; confirmar retorno
  do foco ao invocador.

## Saves e Sync

- [ ] **PENDING** — Confirmar que o card Provider não é cortado em 949×593 nem
  em 1280×800.
- [ ] **PENDING** — Rolar itens pendentes/conflitados até Atualizar status e
  confirmar que o botão fica inteiro acima do rodapé.
- [ ] **PENDING** — Não confirmar qualquer mutação de sincronização.

## Movimento reduzido e encerramento

- [ ] **PENDING** — Com movimento reduzido ativo no host, confirmar ausência de
  animação no menu, Central de tarefas e transições do drawer.
- [ ] **PENDING** — Confirmar retorno de foco ao fechar menu principal e Central
  de tarefas.
- [ ] **PENDING** — Registrar resultado final como PASS ou FAIL somente após
  executar todos os itens acima em hardware real.

Resultado físico: **PENDING**
