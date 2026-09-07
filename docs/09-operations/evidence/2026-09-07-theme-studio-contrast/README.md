# Evidência física — contraste do inspector do Theme Studio

Data: 2026-09-07 (America/Sao_Paulo)

Release observada: `2.0.0rc1-b09908a58261` (`2.0.0rc1`, commit de origem
`b09908a5826174b8ff8d02fbf09f7dcef288edd9`). A release foi ativada pelo fluxo
governado após o CI pós-merge `34142341383` concluir os oito gates verdes.

## Provas

- `01-baseline.png`: canvas instalado da release anterior
  `2.0.0rc1-c1419ddbdddb`, em que os textos do inspector usavam cores fixas
  inadequadas para o painel claro.
- `02-entrega-funcional.png`: canvas instalado da release atual, com a cena
  `layout.previewTitles`, árvore, SpinBoxes e inspector legíveis; o cabeçalho
  da captura identifica a release ativa.

O preview foi materializado a partir do tema builtin
`org.steamzero.asset-recipes-demo` via bridge live. O painel claro mostra
labels, valores declarativos, constraints e estado do profiler com a paleta
derivada do tema.

## Saúde e segurança da sessão

`install_host.py status` confirmou a release, commit, wheel e wheelhouse
esperados. `steamzero-host converge --expect-release
2.0.0rc1-b09908a58261` confirmou convergência idempotente (`attempts=0`, sem
restart adicional); `steamzero --version` retornou `2.0.0rc1`.

Não houve reboot, logout, encerramento do KDE ou toque no launcher
pré-existente. A alteração de valores dos SpinBoxes não foi declarada como
prova física: o host não dispõe de injetor de input Wayland utilizável nesta
sessão. A lacuna `GAP-THEME-STUDIO-PHYSICAL-CANVAS` permanece aberta para a
prova de interação, embora a superfície visual instalada esteja comprovada.

## Checksums

- `01-baseline.png`: `54e034ec2c55afb35dbd4814cd7c6b2aa697520f9c12e6eb4a81b6a3d1d3f854`
- `02-entrega-funcional.png`: `817e20ae74d3f61e7a153d1a6777052be26f59d8e86a1efe26029112d2d47d55`
