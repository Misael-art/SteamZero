# ADR-0018 — Estratégia Game Mode vs Desktop Mode

**Status:** aceito

## Contexto
§11/§12. Game Mode (gamescope) restringe: janelas únicas, sem tray, teclado virtual do Steam, foco por gamepad. Desktop Mode é KDE completo. PhaseZero já separa modos com scripts dedicados e detecção (`detect-mode.sh`, `display-session.sh`).

## Alternativas
1. **Duas experiências dedicadas sobre o mesmo daemon: Game Mode UI empacotada como app não-Steam (roda dentro do gamescope) + Desktop UI; QAM opcional** (escolhida).
2. Uma UI única responsiva — contras: compromissos de densidade e input degradam ambos os públicos (lição: Configurator RetroDECK serve Game Mode, zenity não).
3. Game Mode via web no navegador do Deck — contras: UX de navegador em gamescope é hostil.

## Decisão
Game Mode UI adicionada como shortcut Steam (pelo nosso adapter de shortcuts, com launch options controladas — precedente `pz steamdeck launch-options`); detecção de contexto (gamescope vs desktop) escolhe defaults de escala/layout; mesmas ações, mesmos contratos; Desktop UI cobre o superset administrativo.

## Consequências
Session/Mode Manager único serve as duas; testes UI nas duas resoluções/contextos.

## Riscos
Mudanças do gamescope entre versões SteamOS (R-03) — cobertas pela Compat Matrix e fallback de display (FM-18).

## Revisão
Fase 5 com protótipo ADR-0002.
