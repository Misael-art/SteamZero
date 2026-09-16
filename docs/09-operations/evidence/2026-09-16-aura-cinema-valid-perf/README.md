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
