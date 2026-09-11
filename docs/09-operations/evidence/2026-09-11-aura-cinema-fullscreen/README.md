# AURA Cinema fullscreen — prova física instalada

Data: 2026-09-11  
Release ativa: `2.0.0rc1-9caa2c223cfb`  
Source commit: `9caa2c223cfb9f901e8c4dde74ed534a396c9bba`  
Wheelhouse CI: run `34585110023`  
Rollback disponível: `2.0.0rc1-172c020e03b6`

## Jornada provada

1. O Launcher instalado abriu em fullscreen e resolveu a ponte `/cinema` para o foco inicial.
2. A cena exibiu o cover-flow com capa central, vizinhas reduzidas e fallback legível sem arte.
3. `Right` moveu o foco horizontal para outro jogo sem mouse.
4. `Enter` abriu a página de detalhes do jogo focado, com capa fallback, plataforma, descrição fallback, ação `Jogar` focada e rodapé de controles.

Capturas:

- `01-cinema-fullscreen.png` — Cinema após a resolução assíncrona da ponte.
- `02-carousel-navigation.png` — foco após navegação horizontal.
- `03-details-fallback.png` — detalhes e fallback sem mídia.

## Desempenho

`04-performance.json` foi medido no host real apontando para `/opt/steamzero/current/venv/lib/python3.14/site-packages/steamzero/ui/qml`, em 1280x800, com 10 s de amostragem e 2 s de warm-up:

- 625 frames do render loop;
- média 15,999 ms;
- p50 15,866 ms;
- p95 16,735 ms;
- startup 77 ms;
- pico RSS 57.616 KiB;
- VRAM não medida pela API disponível.

As repetições `05-performance-repeat-2.json` e `06-performance-repeat-3.json` ficaram em p95 de 16,718 ms e 16,708 ms. Portanto, o p95 observado (16,708–16,735 ms) ainda excede marginalmente a meta de 16,7 ms e permanece aberto para otimização. O valor de frame time vem do render loop da sonda e não é afirmado como FPS apresentado na tela.

## Limites observados

O catálogo instalado resolveu vários jogos sem mídia de capa/fanart; a cena permaneceu acionável e legível pelo fallback. A prova desta etapa cobre a cadeia mecânica `bridge → catálogo → Theme Engine/Cinema → carousel → detalhes`. Pause/OSD, save-state, troca de disco, bezels por jogo e execução de um jogo real continuam dependentes dos adapters de sessão e permanecem fora desta captura.
