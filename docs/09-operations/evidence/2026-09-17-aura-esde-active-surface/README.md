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
- `25-current-osd.png`: nova sessão real na mesma release, com o jogo
  `\'89 Dennou Kyuusei Uranai (Japan)`, foco em `Galeria de saves` e `Trocar
  disco` corretamente indisponível para conteúdo single-disc.
- `26-save-gallery.png`: galeria física de save-state, com slot nativo, foco,
  timestamp e fallback explícito `SEM CAPTURA`.
- `perf-installed-b396aaed.json` e `perf-installed-b396aaed-rerun.json`:
  sondas Wayland reais da release instalada, com startup, frame time/p95, RSS e
  VRAM. As duas primeiras amostras ficaram acima do orçamento de p95; a
  terceira amostra em `perf-installed-b396aaed-third.json` passou em todos os
  limites na superfície real `948x593`: startup `1130 ms`, p95 `16,181 ms` e
  VRAM `99468 KiB`. O gap específico da superfície de referência `1280x800`
  permanece aberto.
- `session-osd-real.json`: observação autenticada da sessão RetroArch real;
  save-state, pausa/retomada e fallback de troca de disco foram exercitados
  pelo contrato. O bezel visual raster ainda aguarda a nova release após o
  merge da compatibilidade PNG.

As capturas foram recortadas à janela AURA para não persistir o desktop do
operador. A captura do emulador com a dock foi descartada e não é usada como
prova de bezel.
