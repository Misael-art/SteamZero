# AURA Cinema — evidência física 2026-09-17

Release instalada: `2.0.0rc1-41f56fffa17a`  
Commit: `41f56fffa17a9e861bfa64e57153cb792ee47f4b`  
Rollback: `2.0.0rc1-7a7e96f8e4fd`

## Evidência

- `05-entrega-funcional.png`: central desktop instalada, tema aplicado e sem
  operação pendente.
- `06-launcher-aura-cinema.png`: Launcher Cinema instalado com biblioteca real;
  registra o fallback de capa quando a mídia não existe.
- `07-rich-cinema.png`: Launcher Cinema instalado com fixture local de validação;
  comprova capa central, vizinhas, fanart, paleta e metadados ricos.
- `performance-final-2.0.0rc1-41f56fffa17a.json`: sonda Wayland real, startup,
  frame time/p95, RSS e VRAM.
- `session-osd-real.json`: observação autenticada da sessão RetroArch real;
  save-state, pausa/retomada, bezel e fade foram exercitados pelo contrato.

As imagens `08` e `09` foram descartadas: o compositor não expôs a janela do
RetroArch e as capturas apontavam para outra janela ativa. Não são evidência.
