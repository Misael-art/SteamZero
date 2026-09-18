# AURA Cinema — bezel e performance na release instalada

Data: 2026-09-18  
Release ativa: `2.0.0rc1-a71c2b5e17cd`  
Source commit: `a71c2b5e17cd753164f746dbef2281d14b064a60`  
CI push: `35340802160`  
PR do contrato do bezel: `#211`, merge `a71c2b5e17cd753164f746dbef2281d14b064a60`  
PR da saída por Escape: `#212`, merge `1bd29f17fa9f2c85e784baa66d653f07eb87e9f4`

## Resultado

O Launcher instalado abriu em fullscreen com catálogo AURA Cinema. O jogo real
`'89 Dennou Kyuusei Uranai (Japan).zip` foi lançado pelo Mesen e a captura
`02-game-bezel.png` mostra a imagem em execução dentro da moldura AURA ciano e
roxa, sem barra de título ou dock. A configuração gerenciada do RetroArch
declara `overlays = "1"`, que era a condição ausente que impedia a camada de
bezel de aparecer.

Também foi validado o caminho de saída por controle: na home, `Esc` emite
`exitRequested` e a cena raiz chama `Qt.quit()`; na página de jogo, `Esc`
continua voltando para a home. O harness QML fechou com 34 passed e 14
deselected.

## Arquivos

| Arquivo | Evidência |
|---|---|
| `01-launcher-installed.png` | Launcher fullscreen na release ativa, 1280x801 |
| `02-game-bezel.png` | Jogo real em execução com bezel AURA visível, 1187x972 |
| `03-performance-installed.json` | Probe Wayland/OpenGL da release instalada |

## Medição

`launcher_perf_probe.py --launcher /usr/local/bin/steamzero-launcher --backend opengl --timeout 30 --strict-budget`

| Métrica | Observado | Orçamento | Resultado |
|---|---:|---:|---|
| Startup | 724 ms | 2000 ms | passou |
| Frame time p95 | 16,515 ms | 16,7 ms | passou |
| Frames | 375 | mínimo 120 | passou |
| RSS máximo | 348612 KiB | informativo | registrado |
| VRAM máxima | 103692 KiB | 524288 KiB | passou |

Nota: frame time é do render loop `FrameAnimation`, não uma inferência de
frames apresentados pelo compositor.

## Integridade

```text
70a826da1585d7c3372d7db565b8e6331a18899c0588fde55b0c26fc2476415e  01-launcher-installed.png
192f773849c7c3e1fddf39276272a285700a8d9bec55a72c70d9c8e2b0be5dea  02-game-bezel.png
74dcc13720b22699affdfaf6ae1b6f2a130a59d692ae129a196ad16a390b2d51  03-performance-installed.json
```

Nenhum reboot, restart do KDE ou edição manual de `/opt` foi executado.
