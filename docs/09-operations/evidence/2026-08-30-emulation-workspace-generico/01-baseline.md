# Baseline — roteamento por plataforma antes da migração

Item: `SZ-LIBRARY-CANONICAL`. Release instalada no host antes do update:
`2.0.0rc1-a897f8ffcfed` (sourceCommit `a897f8ffcfed`).

Sintoma reproduzido (registrado no `library-canonical.json` e na a37):

- O workspace despejava a lista INTEIRA de jogos na superfície do Switch. Um
  disco de PSX aparecia dentro do Switch, as plataformas próprias ficavam
  vazias e o serial `SLUS_005.55` era validado contra o padrão de title id do
  Switch — a biblioteca mista real do operador reprovava o contrato do
  workspace.
- `truthState` vinha `unverified` porque o read model era composto sem o estado
  do host (a a37 registrou 36 plataformas zeradas no host real).

## Como ler o defeito

A fonte canônica já gravava `platform` em cada entrada, mas `build_switch_workspace`
despejava os jogos inteiros no Switch. A projeção não respeitava a plataforma
declarada: uma raiz mista virava uma biblioteca "só de Switch" com as demais
plataformas vazias.

## Consequência para o transporte

A a37/a38 mediram o workspace estourado no cap de 1.048.576 bytes; a varredura
completa (~375 jogos) ampliou o read model.
