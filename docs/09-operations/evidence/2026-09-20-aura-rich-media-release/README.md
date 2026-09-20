# AURA — mídia rica e desempenho na release instalada

Release observada: `2.0.0rc1-3acc2104dd5a`, commit de origem
`3acc2104dd5af8862b0ee2a21065fa387acd7720`, Wayland/OpenGL.

O fluxo governado ativou a release e confirmou serviço ativo/Doctor convergente,
mas o pós-check do instalador registrou a incompatibilidade de schema do bundle
(`host=22`, `alvo=20`). Esse diagnóstico não foi ocultado; a release efetiva e
o commit de origem foram conferidos read-only depois da ativação.

O importador RetroFE executou plan-first e aplicou somente 79 decisões seguras
na raiz gerenciada de mídia. Houve 3 ambiguidades e 165 itens sem correspondência;
nenhum foi escolhido ou sobrescrito automaticamente. As origens permaneceram
intactas e cinco assignments anteriores foram preservados.

As capturas mostram duas projeções reais no Launcher instalado:

- `01-fanart-fullscreen.png`: fanart de Mega Man 8 como fundo cinematográfico,
  com vignette/blur e fallback de capa legível.
- `02-cover-fullscreen.png`: capa de Blaster Master no card central.

`03-performance.json` registra startup de 840 ms, 375 amostras, p95 de
16,167 ms e VRAM medida de 58.736 KiB; todos os limites foram atendidos.

O assignment antigo de Astyanax declarava `platformId: switch`, embora o jogo
fosse `nes-famicom`; o bridge rejeitou a entrada e manteve fallback, provando
que a ingestão não vaza mídia entre plataformas.

Nenhum reboot, encerramento do KDE ou mutação das origens foi realizado.
