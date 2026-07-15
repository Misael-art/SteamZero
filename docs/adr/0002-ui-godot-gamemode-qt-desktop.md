# ADR-0002 — Godot 4 candidato no Game Mode; Qt/QML no Desktop

**Status:** aceito parcialmente (Qt/QML Desktop aceito no M10-H; Game Mode mantém gate)

## Contexto
RetroDECK já entrega Configurator em Godot para Game Mode. No Desktop, o painel de 7"
também exige toque, foco por controle, alvos grandes e layout adaptativo; em monitor,
precisa preservar densidade e ferramentas administrativas.

## Problema
Game Mode exige: 60fps, gamepad-first, glyphs, escala TV, tema console. Desktop exige densidade, tabelas, diff viewers.

## Alternativas (Game Mode)
1. **Godot 4** (proposta) — prós: input de gamepad de primeira classe, render performático, precedente RetroDECK, MIT; contras: acessibilidade/screen reader imaturos (G10), i18n manual; riscos: R-04.
2. Qt Quick — prós: acessibilidade melhor, maduro; contras: gamepad nav manual, licenciamento LGPL cuidados em Flatpak; 3. Web local (gamepad API) — prós: velocidade de dev; contras: runtime pesado no Deck, latência de input.

## Decisão
Godot 4 para Game Mode permanece **condicionado** ao protótipo original. A Desktop UI
usa Qt Quick/QML: integração nativa com KDE, acessibilidade, Wayland e layout adaptativo
pesam mais que a reutilização de uma stack web. O QML é opcional no pacote; sem runtime
Qt o backend/CLI continuam operantes. Zenity permanece apenas fallback de emergência.
CLI/API JSON continuam sendo o contrato estável independente do toolkit.

## Consequências
UI desacoplada por contrato (a troca de toolkit não toca o núcleo); design tokens/i18n em formato neutro.

## Revisão futura
Reavaliar Game Mode no M12; reavaliar a central Desktop após testes visuais e de foco em
949×593 lógico, monitor 1080p e escala 150%.
