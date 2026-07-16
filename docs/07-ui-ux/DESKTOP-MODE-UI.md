# DESKTOP-MODE-UI — Qt/QML adaptativo para KDE

Tecnologia: Qt Quick/QML (ADR-0002). A UI é opcional e consome os mesmos contratos da
CLI/API; ausência do runtime Qt não afeta status, plano, apply ou recovery do backend.

## Perfil portátil (Steam Deck em Desktop Mode)

- Layout de uma coluna abaixo de 820 px; alvos interativos com no mínimo 48 px.
- Escala padrão 135%, respeitando valores existentes entre 125% e 150%.
- Toque e controle completos, foco visível, primeiro botão previsível e sem focus trap.
- Janelas normais maximizadas; diálogos e utilitários ficam isentos.
- Application Dashboard e Overview do Plasma; nenhum launcher/switcher próprio no M10-H.
- Seções: Modo, Controles/Teclado, Display/Janelas e Diagnóstico/Recuperação.
- Nenhum fluxo comum exige terminal. A CLI permanece rota break-glass e de automação.

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

## Perfil dock

- Troca automática somente com tela externa ou dock físico estável por três segundos.
- Teclado/mouse externos ajustam affordances, mas não trocam sozinhos todo o perfil.
- Escala e política de janelas são armazenadas separadamente do perfil portátil.
- Override manual persiste até reset explícito para `auto`.

## Administração avançada

Em telas largas permanecem as capacidades para P2/P3: lote, diff de presets, logs por
correlationId, journal, armazenamento e quarentena. A densidade cresce responsivamente;
não existe uma UI separada que sacrifique a ergonomia portátil.

## Regras de segurança

1. UI nunca executa shell nem possui poderes adicionais; solicita ações allowlisted.
2. Toda mutação apresenta plano, riscos, `confirmToken` e garantia G-STATE/G-FULL.
3. Estado de conflito ou recovery é sempre visível e bloqueia efeitos concorrentes.
4. Provider ausente degrada a capacidade correspondente, nunca fecha a central.
5. QML declara nomes acessíveis e grafo de foco; `qmllint` e testes estáticos fazem parte do gate.
6. A bridge converte também falhas inesperadas em erro HTTP estruturado; nunca fecha a
   conexão sem feedback para o botão que originou a ação.
