# AURA — revalidação física da release instalada

Release observada: `2.0.0rc1-c3b14a040b7c`.

`performance.json` foi produzido por `tools/launcher_perf_probe.py` sobre a
janela Wayland real. A amostra tem 375 frames, startup de 1191 ms, p95 de
16,163 ms e VRAM observada de 13.664 KiB; passou os três orçamentos definidos.

`01-installed-surface.png` é uma captura da janela AURA ativa, em 1280×801.
Ela comprova a superfície instalada e o carousel/foco; não certifica ingestão
de fanart ou vídeo, que continuam fallback/pendentes nesta release.
