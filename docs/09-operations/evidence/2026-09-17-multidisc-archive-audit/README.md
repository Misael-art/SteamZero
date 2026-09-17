# Auditoria física read-only de archives multidisco

Executada em 2026-09-17 contra o acervo real em `/home/misael/emulation/roms`,
com `ArchiveAwareMultiDiscResolver` da árvore `origin/main` no merge
`153d3da8`. Nenhum ZIP foi extraído, renomeado, convertido ou sobrescrito.

O ZIP X68000 `Garou Densetsu I+II+Special (1993)(Magical Company).zip`
(SHA-256 `2a0196b8efa2a5beb11a6cb7415463b7d757a6d6541b8a7b51aca4f8598ff68b`)
foi particionado em três jogos lógicos:

- Garou Densetsu — 4 discos, A–D;
- Garou Densetsu 2 — 6 discos, A–F;
- Garou Densetsu Special — 9 discos, A–I.

Cada membro DIM recebeu hash próprio. Os três conjuntos ficaram em
`needs-platform-contract`, pois o manifesto ainda não comprova M3U no PX68K;
nenhuma playlist foi publicada.

No Amiga, a varredura dos oito ZIPs de Super Street Fighter II reconheceu os
sete discos e os membros ADF, mas classificou o conjunto como `conflict` por
variantes incompatíveis (`[h PDY]`, `[t +18 HF]` e a duplicata `(1)`). Isso
confirma a política de não escolher pelo sufixo e de não gerar M3U antes da
revisão/extração gerenciada.

Resultado: a decomposição archive-aware está comprovada em mídia real; o
próximo bloqueio é o contrato PUAE/PX68K e a operação plan/apply/verify, não o
parser de nomes.

## Regressão focada e estado de instalação

As regressões focadas da cadeia relacionada passaram na árvore auditada:

```text
tests/unit/test_session_peripherals.py
tests/unit/test_session_overlay.py
tests/unit/test_session_overlay_adapter.py
tests/unit/test_launcher_media.py
tests/integration/test_media.py                         39 passed

tests/unit/test_multidisc.py
tests/unit/test_multidisc_archive.py
tests/unit/test_multidisc_artifacts.py
tests/unit/test_library_rom_classify.py                   88 passed
```

O bundle governado `2.0.0rc1-153d3da8b80b` continua em espera no diálogo
`pkexec`; `/opt/steamzero/current` ainda resolve para
`2.0.0rc1-d70a80f83aae`. Portanto, esta auditoria não promove captura física
de troca de disco nem afirma a release nova como instalada.
