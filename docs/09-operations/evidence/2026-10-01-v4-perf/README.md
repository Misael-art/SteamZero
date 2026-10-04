# V4 — medição de desempenho (instrumento canônico `tools/theme_perf_probe.py`)

**Nível de prova: ensaio no checkout (branch `codex/v1-v3-theme-journey-2026-10-01`), não release instalada.**
Hardware: AMD Custom APU 0405 (VanGogh), Wayland, Qt 6.11.2, superfície 1280x800, 7 layouts de cena,
6 s de medição + 2 s de aquecimento, 3 repetições por cenário, offscreen não usado (janela real do `qml6`).

## Cenários
- `base`: tema criado a partir da demonstração de receitas, sem edições.
- `edited`: o mesmo tema depois de editar pela API do Studio: pilhas `focusedCover` (+shadow, +glow, +blur), `peripheralCover` (+vignette), keyframe `focused.scale=1.2`, timeline `entrada` com clip e binding `previewTitles.text ← item.genre`.
- Ambos com `--effect-layers 6 --cover-image tests/fixtures/themes/esde-mini/fundo.png`: seis capas renderizadas por `MediaEffectLayer` com a pilha `focusedCover` do cenário (a sonda anterior não renderizava efeitos; a extensão está em `tools/theme_perf_probe.py`).

| Cenário | efeitos na pilha | frame p95 (3 corridas, ms) | frame máx (ms) | VRAM de pico (kB) | startup (ms) | RSS de pico (kB) |
|---|---|---|---|---|---|---|
| base | shadow, glow | 14,306 / 14,489 / 14,404 | 26,92 / 17,19 / 16,32 | 69 840 / 74 340 / 74 340 | 225 / 189 / 195 | ~170 000 |
| edited | shadow, glow, shadow, glow, blur | 14,023 / 14,375 / 14,564 | 15,77 / 15,38 / 16,42 | 69 832 / 70 620 / 72 296 | 191 / 189 / 197 | ~170 500 |

Meta V4: p95 ≤ 16,7 ms e VRAM ≤ 512 MB — **atendidas neste cenário e hardware** (p95 máx. 14,6 ms; VRAM máx. 74 MB).
Referência sem camada de efeitos (corrida anterior): p95 14,5 ms, VRAM 58 MB.

## Limites
- frame p95 é do render loop (`FrameAnimation`), **não** FPS apresentado; sem instrumento de compositor.
- Não é a release instalada: repetir com `--qml-dir /opt/steamzero/current` na release autorizada.
- A sonda renderiza efeitos sobre uma capa de gradiente; não mede movimento/timelines nem bindings (esses não alteram a pintura da sonda).
- Os efeitos dos tiers/`reducedMotion` não foram variados; sem VRAM de tier economy.
- Dados brutos: `probe-{base,edited}-effects-{1,2,3}.json`.
