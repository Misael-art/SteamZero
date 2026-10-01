# V4 — medição de desempenho (instrumento canônico `tools/theme_perf_probe.py`)

**Nível de prova: ensaio no checkout (commit `8fa24bb7`), não release instalada.** Hardware: AMD Custom APU 0405 (VanGogh), Wayland, superfície 1280x800, 7 cenas, tema padrão, 6 s + 2 s de aquecimento.

| Métrica | Medido | Meta V4 | Observação |
|---|---|---|---|
| frame p95 (render loop) | 14,499 ms | ≤ 16,7 ms | ritmo do render loop; **não** prova FPS apresentado |
| frame médio / máx | 13,335 / 19,259 ms | — | 360 frames |
| startup | 174 ms | — | |
| RSS de pico | 153 888 kB | — | |
| VRAM de pico | 58 324 kB | ≤ 512 MB | drm fdinfo por client-id |

Limites: sem release identificada, sem cena com efeitos/timeline editados nem tier por resolução; uma única corrida (sem variância). Para atender ao DoD de V4, repetir com `--qml-dir /opt/steamzero/current` na release autorizada e com o `--preview-json` de um tema que use os efeitos e timelines do Studio.
Dados brutos: `probe-checkout.json`.
