# AURA Launcher — medição física válida

Execução em 2026-09-16 contra a janela Wayland real do host, sem `offscreen`,
na release ativa `2.0.0rc1-d1cbb03a3b66` (`d1cbb03a3b66930e3df4b46f880716eed0eca40f`).
O KDE não foi reiniciado nem finalizado.

Captura visual física realizada na mesma release e na janela Wayland real
fullscreen (1280x800): `01-baseline.png` registra o fallback legível sem arte;
`02-entrega-funcional.png` registra o ciclo visual rico com capa central
ampliada, vizinhas com escala/opacidade, foco ciano, marca AURA/CINEMA,
sistema, estado online, relógio e ações de controle. O acervo temporário de
captura usou três registros reais do catálogo e capas locais já publicadas;
nenhuma arte foi inventada. A captura não promove OSD, save-state, troca de
disco, bezel ou fade de sessão, que continuam exigindo prova funcional própria.

Comando repetido duas vezes:

```text
tools/launcher_perf_probe.py --launcher /usr/local/bin/steamzero-launcher --backend opengl --timeout 30 --strict-budget
```

As duas execuções finais observaram a superfície real `948x593`, startup abaixo de 2 s,
mais de 120 amostras, p95 do render loop abaixo de 16,7 ms e VRAM observada por
DRM fdinfo agrupado por `drm-client-id`. Os resultados são válidos para a
superfície instalada medida; não afirmam FPS apresentado pelo compositor.

Na primeira execução final: startup `695 ms`, p95 `16,180 ms` e VRAM `97.548 KiB`.
Na segunda: startup `691 ms`, p95 `16,243 ms` e VRAM `38.172 KiB`.
Ambas passaram os três orçamentos na release final instalada.

`performance-final-1.json` e `performance-final-2.json` preservam as duas
amostras da release final; os arquivos `performance-valid-1.json` e
`performance-valid-2.json` mantêm o baseline anterior. A validação automatizada
agora separa `valid` de `meetsBudget` e
recusa ausência de VRAM ou de amostras suficientes como certificação.

## Ciclo físico de sessão — baseline do defeito terminal

Na mesma release `2.0.0rc1-d1cbb03a3b66`, o jogo real NES `'<89 Dennou Kyuusei
Uranai (Japan)` foi lançado pelo catálogo e observado no RetroArch/Mesen. As
capturas `03-session-game.png`, `04-session-overlay-running.png`,
`05-session-paused.png` e `06-save-state-gallery.png` provam, respectivamente,
o jogo, o OSD sobre o jogo, pausa e a galeria de save-state com fallback
`SEM CAPTURA`. As operações bridge→sessão→adapter de pausa, retomada,
save-state e load-state retornaram `accepted=true`.

Esta execução também reproduziu e isolou o defeito que motivou o commit
`82799f5`: ao terminar a sessão enquanto a galeria estava aberta, a superfície
modal permanecia sobre o catálogo. A captura é, portanto, baseline físico do
ciclo e não prova da correção; a confirmação pós-instalação será registrada em
uma sessão posterior, na mesma pasta.
