# RELEASE-LEDGER — vínculo entre artefato e fonte

Este ledger corrige retrospectivamente a reutilização de `0.1.0.dev0`. A análise de
2026-07-16 comparou byte a byte todo arquivo `steamzero/` de cada wheel instalado com
os objetos Git candidatos e comparou também o instalador preservado na release.

| Release legada | SHA-256 do wheel | Fonte associável | Classificação |
|---|---|---|---|
| `0.1.0.dev0-1bb00d7-host1` | `c5771ea08b0f643384a5244f461b57a1ea435850f70bc5b4f31df9c2c56bd407` | wheel compatível com `1bb00d754ff1a28259b02038f5201e70db545450`; instalador não corresponde a commit | **não reproduzível** |
| `0.1.0.dev0-1bb00d7-host2` | `c5771ea08b0f643384a5244f461b57a1ea435850f70bc5b4f31df9c2c56bd407` | wheel compatível com `1bb00d754ff1a28259b02038f5201e70db545450`; instalador não corresponde a commit | **não reproduzível** |
| `0.1.0.dev0-1bb00d7-host3` | `c5771ea08b0f643384a5244f461b57a1ea435850f70bc5b4f31df9c2c56bd407` | `635429c373d16efb68ba105aa5e8c9e1e93be45d` | **associação exata retrospectiva**; o nome antigo está incorreto |
| `0.1.0.dev0-635429c-conflict-ui1` | `aa9835da767d9e9e462fcf6e7ec3be90ced0c0cfafdf0d25411266b79824c87e` | nenhuma árvore Git coincide; difere em dois arquivos do commit posterior | **não reproduzível** |
| `0.1.0.dev0-635429c-conflict-ui2` | `3a0cfd9106df739fdbc05c0afae941d3b4e1be9f838242a6c2f90587dd19f21a` | `99bdd33d3a2bebacd8853228c5a4bd0adeafdeaa` | **associação exata retrospectiva** |
| `0.1.0.dev0-20260716-systemstudio1` | `ce1c74bf22fb1b14da4de3b732c6b3741104751147807ee1a970778f9f3f6886` | `8c037c3f68148acdcd75cf823b47189cfa8e1b46` | **associação exata retrospectiva** |

“Associação exata retrospectiva” significa que todos os artefatos versionados da
release coincidem com o commit indicado; não equivale a uma atestação assinada criada
no momento do build. As três releases não reproduzíveis ficam disponíveis somente
para rollback de emergência e não podem ser promovidas, republicadas ou tagueadas.

A partir de `0.1.0a1`, uma release nova deve cumprir simultaneamente:

1. checkout sem alterações rastreadas e `HEAD` completo registrado;
2. ID canônico `<versão>-<commit[0:12]>`;
3. manifesto v2 ou superior com `packageVersion`, `sourceCommit` e
   `sourceTreeState=clean`; daemon e Session Manager exigem v3;
4. wheel, lock, SBOM, auditoria OSV, checksums e proveniência publicados juntos;
5. tag criada somente depois dos gates verdes e apontando para o mesmo commit.

## Releases host reproduzíveis — 2026-07-17

| Release | Commit exato | SHA-256 do wheel | Resultado |
|---|---|---|---|
| `0.1.0a8-d2bf3819d12d` | `d2bf3819d12d16f5b5a682db06af3e63c091efcd` | `f159a3447ec051d74247ad7541baf479ae984dad9ec640c5f3c5424fb9e231d0` | instalada e preservada para rollback; smoke revelou ausência do comando público da sessão |
| `0.1.0a9-e38b3762f144` | `e38b3762f1449ad664877a390b3729963d4c6fb6` | `1fc320521f036a98f60cf8806adf64938fcd39d85dc87a8d5446973d08edf21d` | instalou o comando estável; smoke offscreen revelou timeout KDE não degradado |
| `0.1.0a10-1c4527ae3961` | `1c4527ae39612062742b318b102c33c8b311d918` | `a8a77ab25fcd3267d9fc2f756a56d63ae3600c9d68e857daf84d462d2b465d91` | ativa e validada no host |
| `0.1.0a11-11e57d269fb2` | `11e57d269fb205f5c0258888e1afd56b826ca96c` | `a8caada99aa4049f56ae05a680d67f698aae94fd4f30898797e8a709f7f64641` | R1 instalado; ambiente de sessão real validado read-only |

Nenhum desses wheels foi republicado sob a mesma versão. Os desvios encontrados no host
geraram versões sucessivas, mantendo os artefatos e manifests anteriores imutáveis.
