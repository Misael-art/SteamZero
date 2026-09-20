# Remediação de runtimes — 2026-09-20

## Diagnóstico registrado

- X68000: 14 ROMs. O inventário encontra os archives e a reconciliação
  `archive-multidisc-*`, mas o cache de launch reclassificava o `.zip` como
  `archive-needs-extraction` e o removia antes do spawn, resultando em
  `E-TX-STALE-PLAN`.
- Amiga: 5 ROMs. O mesmo caminho de perda de candidatos afeta os conjuntos
  `.zip`; PUAE está instalado, mas não deve receber um container não extraído
  como se fosse uma mídia diretamente lançável.
- RPCS3: o ISO alcançou a tela de firmware. O preflight anterior só validava
  keys/firmware do Switch; falta um bloqueio explícito para `PS3UPDAT.PUP` e
  uma orientação de primeira execução. Firmware oficial deve ser obtido da
  Sony com confirmação explícita, nunca de fonte de terceiros ou de forma
  silenciosa.
- PCSX2: a release instalada recusou `--fullscreen` antes do spawn; o
  manifesto deve ser alinhado à sintaxe real, mas a expectativa no teste
  compartilhado pertence ao workstream de catálogo de erros.
- Multidisco/save: o adapter RetroArch já possui M3U, listagem/troca de disco,
  save-state, load-state e backup de slot. A prova física de troca de disco
  ainda requer um conjunto multidisco legal completo. A inspeção read-only de
  `/home/misael/emulation/roms` encontrou zero `.m3u` e apenas discos isolados
  ou archives; os archives Amiga/X68000 permanecem somente leitura até a
  conversão governada.

## Estado e próxima ação

Esta frente registra o diagnóstico e corrige a perda de candidatos no cache e o
preflight de firmware. Não houve instalação, rollback, download de firmware,
push ou reboot. O handoff de PCSX2 e as provas físicas continuam abertos como
SOFT-COORDINATION/ação do operador, não como parada da frente.

## Provas automatizadas

- `test_emulation_runtime_remediation.py`: 4 passed.
- `test_library_rom_classify.py` + `test_launch_e2e.py`: 78 passed.
- `test_emulation_controller.py`: 141 passed em 8m04s.
- `test_keys_firmware.py`: 17 passed.
- Ruff check/format nos arquivos alterados: passed.

Fonte oficial para o firmware do PS3: <https://www.playstation.com/pt-br/support/hardware/ps3/system-software/>.
