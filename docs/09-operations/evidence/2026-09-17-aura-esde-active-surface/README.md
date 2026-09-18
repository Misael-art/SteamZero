# AURA Cinema — evidência física 2026-09-18

Release instalada: `2.0.0rc1-b396aaedcc64`  
Commit: `b396aaedcc64df1eeae68a9143fdb1dfa6345f6e`  
Rollback: `2.0.0rc1-7a7e96f8e4fd`

## Evidência

- `05-entrega-funcional.png`: central desktop instalada, tema aplicado e sem
  operação pendente.
- `06-launcher-aura-cinema.png`: Launcher Cinema instalado com biblioteca real;
  registra o fallback de capa quando a mídia não existe.
- `07-rich-cinema.png`: Launcher Cinema instalado com fixture local de validação;
  comprova capa central, vizinhas, fanart, paleta e metadados ricos.
- `08-amiga-multidisc-catalog.png`: catálogo AURA com fixture real derivada de
  quatro ZIPs ADF do Amiga; prova o read model rico sem promover o conjunto a
  lançamento válido.
- `24-aura-osd-fixed.png`: jogo NES real em execução na release instalada;
  OSD AURA focado, com save-state e troca de disco como capacidades declaradas,
  sem vazamento da página subjacente.
- `perf-installed-b396aaed.json` e `perf-installed-b396aaed-rerun.json`:
  sondas Wayland reais da release instalada, com startup, frame time/p95, RSS e
  VRAM. Startup e VRAM passaram; p95 observado foi `16,918–16,959 ms` contra o
  orçamento de `16,7 ms`, então o gap de performance permanece aberto.
- `session-osd-real.json`: observação autenticada da sessão RetroArch real;
  save-state, pausa/retomada, bezel e fade foram exercitados pelo contrato.

As capturas intermediárias da sessão foram descartadas; somente a imagem `24`
foi mantida como prova física pós-instalação. O PNG foi recortado à janela AURA
para não persistir o desktop do operador.
