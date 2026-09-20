# AURA — evidência física da release ativa

Data: 2026-09-20  
Release ativa: `2.0.0rc1-c3b14a040b7c`  
Sessão: Wayland real, sem reinício do KDE

## Resultado

O Launcher AURA abriu na superfície fullscreen física. A captura mostra o
carousel Cinema com foco, navegação horizontal, cabeçalho de sistema/estado da
conexão, relógio e rodapé de ações. A imagem selecionada é publicada quando
existe; as demais posições permanecem em fallback legível quando não há mídia.

| Arquivo | Conteúdo |
|---|---|
| `01-launcher-fullscreen.png` | Captura da janela AURA ativa, 1280x800 |
| `02-performance.json` | Sonda Wayland/OpenGL da release instalada |

## Desempenho

`tools/launcher_perf_probe.py --launcher /usr/local/bin/steamzero-launcher --backend opengl --timeout 45`

| Métrica | Observado | Orçamento | Resultado |
|---|---:|---:|---|
| Startup | 1096 ms | 2000 ms | passou |
| Frame time p95 | 16,169 ms | 16,7 ms | passou |
| Frames | 375 | mínimo 120 | passou |
| VRAM máxima | 13460 KiB | 524288 KiB | passou |
| RSS máximo | 368672 KiB | informativo | registrado |

Nota: o frame time é do `FrameAnimation` do render loop, não uma inferência
dos frames apresentados pelo compositor.

## Limites da prova

Esta captura comprova a superfície física instalada e o fallback seguro. Ela
não promove, sozinha, ingestão remota de fanart, OSD de jogo real, save-state,
troca de disco ou bezel/fade durante uma sessão; essas capacidades continuam
dependentes de seus adapters e das capturas específicas correspondentes.

## Integridade

```text
47a0e45a476aaeb1881b89ba817674b9e189c178f125fa0c0c1f936884b6c44b  01-launcher-fullscreen.png
6daabd61b1ff4516be4e5c42d958e793850c937d07f0e5f1e5483a00144d9453  02-performance.json
```
