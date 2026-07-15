# ADR-0002 — Godot 4 para Game Mode UI; Desktop UI decidida por protótipo (Qt/QML × web local)

**Status:** proposto (exige protótipos com critérios antes da Fase 5 — §12.10)

## Contexto
RetroDECK já entrega Configurator em Godot para Game Mode (evidência: `godot-configurator.sh` no manifest de componentes) — precedente real no domínio. PhaseZero usa WPF+contrato JSON no Windows e páginas web em `linux/ui`. LinuxToys usa GTK.

## Problema
Game Mode exige: 60fps, gamepad-first, glyphs, escala TV, tema console. Desktop exige densidade, tabelas, diff viewers.

## Alternativas (Game Mode)
1. **Godot 4** (proposta) — prós: input de gamepad de primeira classe, render performático, precedente RetroDECK, MIT; contras: acessibilidade/screen reader imaturos (G10), i18n manual; riscos: R-04.
2. Qt Quick — prós: acessibilidade melhor, maduro; contras: gamepad nav manual, licenciamento LGPL cuidados em Flatpak; 3. Web local (gamepad API) — prós: velocidade de dev; contras: runtime pesado no Deck, latência de input.

## Decisão
Godot 4 para Game Mode **condicionado** a protótipo (gate da Fase 5) medindo: (a) navegação por foco 100% controle sem hacks; (b) 60fps no Deck com biblioteca 10k virtualizada; (c) escala 100–TV sem quebra; (d) labels acessíveis exportáveis; (e) glyphs dinâmicos. Falhou ⇒ Qt/QML assume (plano B orçado). Desktop UI: decidir no mesmo ciclo entre Qt/QML e web local com critérios (tabelas 10k, diff viewer, esforço de manutenção compartilhando i18n/design tokens). Zenity: **apenas fallback** de emergência (nunca fluxo principal). CLI JSON permanece o contrato estável independente da escolha.

## Consequências
UI desacoplada por contrato (a troca de toolkit não toca o núcleo); design tokens/i18n em formato neutro.

## Revisão futura
Protótipos avaliados no fim da Fase 1; resultado anexado a este ADR com números.
