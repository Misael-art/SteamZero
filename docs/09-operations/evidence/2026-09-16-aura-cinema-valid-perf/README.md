# AURA Launcher — medição física válida

Execução em 2026-09-16 contra a janela Wayland real do host, sem `offscreen`,
na release ativa `2.0.0rc1-a5f3ed144f3d` (`a5f3ed144f3d44adbf89f4979268e4ec58e35193`).
O KDE não foi reiniciado nem finalizado.

Comando repetido duas vezes:

```text
tools/launcher_perf_probe.py --launcher /usr/local/bin/steamzero-launcher --backend opengl --timeout 20
```

As duas execuções observaram a superfície real `948x593`, startup abaixo de 2 s,
mais de 120 amostras, p95 do render loop abaixo de 16,7 ms e VRAM observada por
DRM fdinfo agrupado por `drm-client-id`. Os resultados são válidos para a
superfície instalada medida; não afirmam FPS apresentado pelo compositor.

`performance-valid-1.json` e `performance-valid-2.json` preservam as duas
amostras. A validação automatizada agora separa `valid` de `meetsBudget` e
recusa ausência de VRAM ou de amostras suficientes como certificação.
