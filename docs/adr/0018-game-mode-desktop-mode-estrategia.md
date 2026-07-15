# ADR-0018 — Estratégia Game Mode vs Desktop Mode

**Status:** aceito

## Contexto
§11/§12. Game Mode (gamescope) restringe: janelas únicas, sem tray, teclado virtual do
Steam, foco por gamepad. Desktop Mode é KDE completo, mas no painel de 7" também exige
uma experiência portátil própria. A solução não pode depender de scripts externos.

## Alternativas
1. **Duas experiências dedicadas sobre o mesmo daemon: Game Mode UI empacotada como app não-Steam (roda dentro do gamescope) + Desktop UI; QAM opcional** (escolhida).
2. Uma UI única responsiva — contras: compromissos de densidade e input degradam ambos os públicos (lição: Configurator RetroDECK serve Game Mode, zenity não).
3. Game Mode via web no navegador do Deck — contras: UX de navegador em gamescope é hostil.

## Decisão
Game Mode UI será adicionada como shortcut Steam pelo adapter próprio. Na sessão KDE,
o Desktop Experience Coordinator escolhe `handheld-desktop` ou `docked-desktop` por
capabilities e sinais locais; teclado/mouse isolados não trocam o perfil. O shell usa
Overview/Application Dashboard do Plasma. Mesmas ações e contratos servem ambas as UIs.

## Consequências
Session/Mode Manager único serve as duas; testes UI nas duas resoluções/contextos.

## Riscos
Mudanças do gamescope entre versões SteamOS (R-03) — cobertas pela Compat Matrix e fallback de display (FM-18).

## Revisão
Fase 5 com protótipo ADR-0002.
