# Índice canônico — Evidências de certificação M10 (VM descartável)

Gerado em 2026-08-11 a partir dos arquivos `docs/diagnostics/*m10-vm-evidence*.md`.

Cada evidência registra commit de origem (hash completo no arquivo), protocolo, veredito e
resultado por etapa; o run-id (`rNN`) é o nome da VM descartável (`steamzero-m10-rNN`).

Artefatos de VM (qcow2, overlays, seed, chaves) não são versionados; os overlays de falha
preservados em `.zcode/vm-harness/` são referenciados aqui pelos hashes das evidências.

## Certificação canônica do Item 4 (r25–r46)

| run | data | emulador | protocolo | veredito | commit | evidência (sha256[16]) |
|---|---|---|---|---|---|---|
| r25 | 2026-08-10 | pcsx2 | minimal | APROVADO | 19d8b9548a3e | `2026-08-10-m10-vm-evidence-125944.md` `229582743c54d10f` |
| r26 | 2026-08-10 | pcsx2 | full | APROVADO | 19d8b9548a3e | `2026-08-10-m10-vm-evidence-134406.md` `8be32841e2b3ac2c` |
| r27 | 2026-08-10 | pcsx2 | full | APROVADO | 19d8b9548a3e | `2026-08-10-m10-vm-evidence-140812.md` `5d1942c67223018a` |
| r28 | 2026-08-10 | pcsx2 | full | APROVADO | 19d8b9548a3e | `2026-08-10-m10-vm-evidence-143121.md` `f5d9d888433d8ce3` |
| r39 | 2026-08-11 | pcsx2 | minimal | APROVADO | 586ed7cb8642 | `2026-08-11-m10-vm-evidence-042012.md` `26745cf8dfe075cc` |
| r40 | 2026-08-11 | pcsx2 | full | APROVADO | 586ed7cb8642 | `2026-08-11-m10-vm-evidence-043652.md` `ae9c0b06cab92400` |
| r41 | 2026-08-11 | pcsx2 | full | APROVADO | 586ed7cb8642 | `2026-08-11-m10-vm-evidence-045545.md` `ef2ba0ff1c085cfa` |
| r42 | 2026-08-11 | pcsx2 | full | APROVADO | 586ed7cb8642 | `2026-08-11-m10-vm-evidence-051404.md` `f7ddc90a3d3e0df4` |
| r29 | 2026-08-10 | ppsspp | minimal | REPROVADO | 19d8b9548a3e | `2026-08-10-m10-vm-evidence-145001.md` `1353aa6d6e9c58ec` |
| r30 | 2026-08-10 | ppsspp | minimal | APROVADO | 2d134e2651f8 | `2026-08-10-m10-vm-evidence-153706.md` `d21ffd468909da7e` |
| r31 | 2026-08-10 | ppsspp | full | REPROVADO | 2d134e2651f8 | `2026-08-10-m10-vm-evidence-155113.md` `3b7ed8cb83b1f7be` |
| r31b | 2026-08-10 | ppsspp | full | APROVADO | 223d087a5070 | `2026-08-10-m10-vm-evidence-170031.md` `77c882ffc45e3b3e` |
| r32 | 2026-08-10 | ppsspp | full | APROVADO | 223d087a5070 | `2026-08-10-m10-vm-evidence-172803.md` `4e7f58fe2ff5c4e8` |
| r33 | 2026-08-10 | ppsspp | full | REPROVADO | 223d087a5070 | `2026-08-10-m10-vm-evidence-174746.md` `05052fcf8c188a1f` |
| r33b | 2026-08-10 | ppsspp | full | REPROVADO | 6a76f04dcffd | `2026-08-10-m10-vm-evidence-182744.md` `1db292e22f758202` |
| r34 | 2026-08-10 | ppsspp | full | APROVADO | 6a76f04dcffd | `2026-08-10-m10-vm-evidence-185712.md` `8babb68d8838989f` |
| r43 | 2026-08-11 | ppsspp | minimal | APROVADO | 586ed7cb8642 | `2026-08-11-m10-vm-evidence-053150.md` `5198fffe54811512` |
| r44 | 2026-08-11 | ppsspp | full | APROVADO | 586ed7cb8642 | `2026-08-11-m10-vm-evidence-054616.md` `aa3bb45d7d125980` |
| r45 | 2026-08-11 | ppsspp | full | APROVADO | 586ed7cb8642 | `2026-08-11-m10-vm-evidence-060546.md` `78eb6fd452eb88e7` |
| r46 | 2026-08-11 | ppsspp | full | APROVADO | 586ed7cb8642 | `2026-08-11-m10-vm-evidence-062338.md` `1c24de67f24f3bc4` |
| r35 | 2026-08-10 | retroarch | minimal | REPROVADO | 6a76f04dcffd | `2026-08-10-m10-vm-evidence-194927.md` `6bfbc70ee4cadc99` |
| r35a | 2026-08-10 | retroarch | minimal | REPROVADO | 6a76f04dcffd | `2026-08-10-m10-vm-evidence-191453.md` `d5f8eca99b96eca0` |
| r35b | 2026-08-10 | retroarch | minimal | REPROVADO | e1e2c73d26b8 | `2026-08-10-m10-vm-evidence-205604.md` `34331c9e8302f132` |
| r35c | 2026-08-11 | retroarch | minimal | APROVADO | 10704a795fdc | `2026-08-11-m10-vm-evidence.md` `649d338322b511f5` |
| r36 | 2026-08-11 | retroarch | full | APROVADO | 10704a795fdc | `2026-08-11-m10-vm-evidence-020748.md` `c9b8cf1a76af6636` |
| r37 | 2026-08-11 | retroarch | full | APROVADO | 10704a795fdc | `2026-08-11-m10-vm-evidence-024646.md` `91656bb145550179` |
| r38 | 2026-08-11 | retroarch | full | REPROVADO | 10704a795fdc | `2026-08-11-m10-vm-evidence-031159.md` `c51997cdbe7f5ce8` |
| r38b | 2026-08-11 | retroarch | full | APROVADO | 586ed7cb8642 | `2026-08-11-m10-vm-evidence-040205.md` `b3baf049ffa6e58a` |

### Matriz final por emulador (commit `586ed7c`)

| emulador | minimal | full 1 | full 2 | full 3 | restore btrfs |
|---|---|---|---|---|---|
| RetroArch | r35c | r36 | r37 | r38b | SIM |
| PCSX2 | r39 | r40 | r41 | r42 | SIM |
| PPSSPP | r43 | r44 | r45 | r46 | SIM |

Fixes de robustez de rede/I-O que destravaram o ciclo (cada um com causa medida em VM):
`2d134e2` retry de download; `223d087` pacman `--disable-download-timeout`; `6a76f04` retry no
plan; `e1e2c73` retry lê o detail de rede no stdout do envelope; `10704a7` smoke 90 s (primeiro
run frio do flatpak ~23 s); `586ed7c` status Flatpak 60 s (I/O pós-install).

## Histórico de exploração (pré-r25, laboratório)

Runs de exploração do harness no laboratório (Sessão 29+), sem vínculo canônico de run-id.

| data | emulador | protocolo | veredito | commit | evidência (sha256[16]) |
|---|---|---|---|---|---|
| 2026-08-06 | ? | ? | REPROVADO | 77cd4833df7d | `2026-08-06-m10-vm-evidence.md` `0ebaac5528b21af8` |
| 2026-08-07 | ? | full | REPROVADO | 64676d19da23 | `2026-08-07-m10-vm-evidence-060707.md` `383055453663f3fd` |
| 2026-08-07 | ? | minimal | REPROVADO | db52104a574a | `2026-08-07-m10-vm-evidence-063840.md` `b0b934fa9e5c69e6` |
| 2026-08-07 | ? | ? | REPROVADO | e4d680bfc22c | `2026-08-07-m10-vm-evidence.md` `f98aa5cd515795b5` |
| 2026-08-09 | ? | minimal | REPROVADO | c17074148e00 | `2026-08-09-m10-vm-evidence-103822.md` `0fa3277cb3afdd57` |
| 2026-08-09 | ? | minimal | REPROVADO | e5f5cd58d8da | `2026-08-09-m10-vm-evidence-113550.md` `32f9b3602eb2b16f` |
| 2026-08-09 | ? | minimal | REPROVADO | 2810de7900c4 | `2026-08-09-m10-vm-evidence-132417.md` `3688cc8d88eaa75f` |
| 2026-08-09 | ? | minimal | REPROVADO | ef4e03f6175d | `2026-08-09-m10-vm-evidence-141608.md` `85028415dd9252d3` |
| 2026-08-09 | ? | minimal | REPROVADO | 8ee752c732c4 | `2026-08-09-m10-vm-evidence-150541.md` `cc987f2a548e4753` |
| 2026-08-09 | ? | minimal | REPROVADO | 9ff70b5832f0 | `2026-08-09-m10-vm-evidence-153402.md` `de2b9e71b1f3b043` |
| 2026-08-09 | ? | minimal | REPROVADO | f6fa1c304f85 | `2026-08-09-m10-vm-evidence-163847.md` `2e2724ae278fa79c` |
| 2026-08-09 | ? | minimal | REPROVADO | 4e01733724a7 | `2026-08-09-m10-vm-evidence-165349.md` `895faa5e14caa83b` |
| 2026-08-09 | ? | minimal | REPROVADO | b394d2fe797d | `2026-08-09-m10-vm-evidence-170611.md` `78b307ed9592b412` |
| 2026-08-09 | ? | minimal | REPROVADO | 663d3e6f05fb | `2026-08-09-m10-vm-evidence-174258.md` `b2daa8994c75615e` |
| 2026-08-09 | ? | minimal | REPROVADO | 094fd59f7496 | `2026-08-09-m10-vm-evidence-185707.md` `7e121526ea8ced42` |
| 2026-08-09 | ? | minimal | REPROVADO | 5d0171280ebc | `2026-08-09-m10-vm-evidence-194308.md` `047039c1996fb7b5` |
| 2026-08-09 | ? | minimal | REPROVADO | a8053a771527 | `2026-08-09-m10-vm-evidence-213737.md` `ee8dbe0ac770e40b` |
| 2026-08-09 | ? | minimal | REPROVADO | 2486c78a28ea | `2026-08-09-m10-vm-evidence-234208.md` `f37ff07a56f94a8d` |
| 2026-08-09 | ? | minimal | REPROVADO | 9379963792ff | `2026-08-09-m10-vm-evidence.md` `2ca116c319ac146d` |
| 2026-08-09 | retroarch | minimal | APROVADO | c17074148e00 | `2026-08-09-m10-vm-evidence-013051.md` `50cbc1cbe66edb03` |
| 2026-08-09 | retroarch | full | APROVADO | c17074148e00 | `2026-08-09-m10-vm-evidence-021717.md` `9d0a89b453d020f4` |
| 2026-08-09 | retroarch | full | APROVADO | c17074148e00 | `2026-08-09-m10-vm-evidence-091944.md` `3588022db2e5cc11` |
| 2026-08-09 | retroarch | full | APROVADO | c17074148e00 | `2026-08-09-m10-vm-evidence-102006.md` `78b31f035364a8c5` |
| 2026-08-10 | ? | minimal | REPROVADO | 8ccff1c7c1b9 | `2026-08-10-m10-vm-evidence-091026.md` `e01e00bbfe741d5b` |
| 2026-08-10 | ? | minimal | REPROVADO | 8ccff1c7c1b9 | `2026-08-10-m10-vm-evidence-104445.md` `4e293899278409f9` |
| 2026-08-10 | ? | minimal | REPROVADO | 1723cc82a259 | `2026-08-10-m10-vm-evidence.md` `977f8b6a790409c0` |
| 2026-08-10 | pcsx2 | minimal | APROVADO | 8ccff1c7c1b9 | `2026-08-10-m10-vm-evidence-084745.md` `e7b04ea5ee90ee88` |
