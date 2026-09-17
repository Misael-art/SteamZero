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
