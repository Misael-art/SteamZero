# DESKTOP-MODE-UI — Qt/QML adaptativo para KDE

Tecnologia: Qt Quick/QML (ADR-0002). A UI é opcional e consome os mesmos contratos da
CLI/API; ausência do runtime Qt não afeta status, plano, apply ou recovery do backend.

## Perfil portátil (Steam Deck em Desktop Mode)

- Layout de uma coluna abaixo de 820 px; alvos interativos com no mínimo 48 px.
- Escala padrão 135%, respeitando valores existentes entre 125% e 150%.
- Toque e controle completos, foco visível, primeiro botão previsível e sem focus trap.
- Janelas normais maximizadas; diálogos e utilitários ficam isentos.
- Application Dashboard e Overview do Plasma; nenhum launcher/switcher próprio no M10-H.
- Seções: Visão geral, Emuladores, Steam, Perfis, Saves e Sync e Sistema.
- Nenhum fluxo comum exige terminal. A CLI permanece rota break-glass e de automação.

## Central System Studio

A janela principal segue o padrão de gerenciamento selecionado: navegação persistente,
contexto do dispositivo no cabeçalho, lista operacional no centro e detalhe da seleção à
direita quando houver largura. Em telas estreitas o detalhe vira progressão natural após
a lista, sem reduzir alvos ou esconder ações essenciais.

- **Header de estado:** resume Deck, displays e modo Desktop. Conflitos de ownership usam
  banner âmbar persistente, código do erro e ação imediata para revisar a liberação.
- **Emuladores:** filtros Todos/Atenção/Instalados, logos reais, estado proveniente do
  executor Flatpak, sistemas suportados e ação contextual. Install/update sempre abre um
  plano confirmado; fonte EOL aparece como indisponível, nunca como instalável.
- **Steam:** área dedicada com a mesma hierarquia de lista/detalhe dos emuladores. Expõe
  cliente, biblioteca, Steam Input e teclado Steam, usando somente URIs/ações allowlisted
  e capacidade detectada no host.
- **Steam / Gameplay:** usa a direção visual "Prontidão do jogo": biblioteca local,
  escopo global/por jogo/portátil/dock, perfil recomendado, FPS segmentado, TDP contínuo
  somente quando os limites do Deck foram observados, GPU automática/manual, Gamescope,
  Feral GameMode, MangoHud e upscaling. SteamZero, Steam e Sistema têm responsabilidades
  visuais distintas; componente ausente oferece apenas **Abrir Sistema**.
- **Verdade do perfil Steam:** revisão e aplicação usam plano efêmero confirmado e
  revalidam biblioteca, capacidades e owner Desktop. `truthState=desired` representa a
  política persistida para o lançamento gerenciado; TDP/GPU não são declarados aplicados
  nem observados antes da existência do executor de runtime correspondente.
- **Perfis:** seleção, preview e confirmação dos perfis auto/handheld/dock/safe.
- **Saves e Sync:** fila, conflitos e estado da sincronização; indisponibilidade remota
  degrada somente esta área.
- **Sistema:** doctor, logs, checks e recuperação. Quick Reset continua disponível como
  ação global e aplica apenas um plano `safe` confirmado.

Logos de emuladores e Steam são assets reais com atribuição; a marca SteamZero é um asset
gerado próprio. Ícones de ações e navegação vêm do tema KDE para permanecer coerentes com
o Desktop e responder ao esquema do sistema.

### Conflito com watcher legado

- O botão de aplicar permanece bloqueado, mas nunca silencioso: um card âmbar explica
  que outro serviço controla display/input, identifica a unidade e preserva modo observador.
- Para `phasezero-steamdeck-mode-watcher.service`, a UI oferece **Revisar desativação do
  watcher antigo**. Um diálogo mostra os argv exatos, impacto e rollback antes de confirmar.
- No BigLinux verificado, a unidade é `user` (`~/.config/systemd/user`), portanto os
  comandos corretos são `systemctl --user stop ...` e `systemctl --user disable ...`;
  `sudo systemctl ...` consultaria o escopo errado e não desativaria esse watcher.
- Se `stop` passar e `disable` falhar, o adapter tenta restaurar enable/start. A UI mantém
  o card e mostra `E-DESKTOP-CONFLICT-RELEASE`, sem liberar apply prematuramente.
- Install/update de componentes também revalida o conflito no backend imediatamente antes
  da mutação, evitando contornar o bloqueio por status obsoleto na interface.

### Recuperação de emergência

Quando `recoveryRequired` é verdadeiro, a central abre antes do uso normal um diálogo
modal: **Alteração incompleta detectada**. Há uma única ação primária — **Restaurar último
estado seguro** — ligada a `desktop recover`. O aviso volta em refresh enquanto o journal
continuar não terminal; falha HTTP, timeout ou bridge ausente produz feedback visível e
preserva o estado, sem fechar silenciosamente o diálogo.

## Perfil dock

- Troca automática somente com tela externa ou dock físico estável por três segundos.
- Teclado/mouse externos ajustam affordances, mas não trocam sozinhos todo o perfil.
- Escala e política de janelas são armazenadas separadamente do perfil portátil.
- Override manual persiste até reset explícito para `auto`.

## Administração avançada

Em telas largas a região de detalhe permanece simultaneamente visível; em telas limitadas
ao painel interno do Deck a lista ocupa a largura útil e mantém rolagem, foco e footer de
controle. Capacidades futuras para lote, diff de presets, logs por correlationId, journal,
armazenamento e quarentena entram na mesma arquitetura; não existe uma UI separada que
sacrifique a ergonomia portátil.

## Regras de segurança

1. UI nunca executa shell nem possui poderes adicionais; solicita ações allowlisted.
2. Toda mutação apresenta plano, riscos, `confirmToken` e garantia G-STATE/G-FULL.
3. Estado de conflito ou recovery é sempre visível e bloqueia efeitos concorrentes.
4. Provider ausente degrada a capacidade correspondente, nunca fecha a central.
5. QML declara nomes acessíveis e grafo de foco; `qmllint` e testes estáticos fazem parte do gate.
6. A bridge converte também falhas inesperadas em erro HTTP estruturado; nunca fecha a
   conexão sem feedback para o botão que originou a ação.
