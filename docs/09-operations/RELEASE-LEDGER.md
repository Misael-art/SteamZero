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
| `0.1.0a12-105cce61a9a3` | `105cce61a9a3d471429f3af520537f29f8025f72` | `72130dd966690ec1e87c1863d9ed1b2a9b35119df0c451d2c7ac9221cdf0a1cd` | R2 incremental instalado; SQLite v5 e deduplicação do reconciliador validados no host |
| `0.1.0a13-3730f7322c80` | `3730f7322c80c25d320c71c6b68405300064698b` | `2b4ad296fcacc6aaec56b063bfce9ef479cb8933f6a542ff467045c5427bad16` | detecção pós-resume instalada; relógios reais validados sem suspender o host principal |
| `0.1.0a14-60712ad3972c` | `60712ad3972cca6b23ecfb19233f7de1076bd471` | `1231695893f075be48f8d7b70c0424d58ae61b12f1dd14a570b7f06fd20d60fe` | ativa; helper e policy Polkit instalados, health root/audit 0600 validados, mutações desabilitadas |
| `0.1.0a15-ba87f9ee5c44` | `ba87f9ee5c4420cf6a063ef28569d4ee0cdbac4d` | `fe815e5dda7c796589d8421a658be8ad30948ae216c01f717c96ebda8636849f` | instalada; smoke revelou que autenticação interativa não deve atravessar o daemon user-scoped |
| `0.1.0a16-592dba1628a4` | `592dba1628a4396ea226f3d03b1126f54f48de45` | `8de1930b362d9bb9d2ed9ad1b17bd089a5c9c4875621c49c32d674f43b004132` | correção instalada; CLI→Polkit direta validada e método ausente das capabilities RPC |
| `0.1.0a17-76d764ad773e` | `76d764ad773e95c2485d5a88d853513b723c4caa` | `b511b02df87e75bfb66f04b2d47b99c8e102dbded23a5ab6b6510891071a8376` | ativa; limites reais TDP/GPU observados read-only, mutações continuam desabilitadas |
| `0.1.0a18-1d76d7986330` | `1d76d7986330053240c9001d64468d112303be88` | `618718da9c919471a9c5583ba4c449e67acaf6eb35001045d3719d7256dd98b0` | ativa; motor TDP G-STATE validado em sysfs descartável, transporte mutável ainda gated |
| `0.1.0a19-364185ac7d87` | `364185ac7d8750a1a7a8f920baccb8893205f94c` | `e58bded9177b60ae20cd453220275008a80cbf2f8dcdbca38140ba6c94a6596c` | ativa; motor GPU SCLK G-STATE validado no wheel instalado contra sysfs descartável, transporte mutável ainda gated |
| `0.1.0a20-ced9e2157548` | `ced9e21575485afd337eb70f5ffae9dbcb08b11f` | `68344159cc2258151c6d6e74e691445cd5f22f1741c89e2cc2b87fb9be1704f0` | ativa; lock interprocesso e motor sysctl G-STATE validados no wheel instalado sem escrever `/proc/sys` real |
| `0.1.0a21-7e1136cc80ae` | `7e1136cc80aecf2d5e5c1e5be4c931c25f9c5218` | `8f53b5429726f99231f197ff35c0a6286ec454322e923c6eb850ab54c7a6f2b4` | ativa; lifecycle exige identidade do wrapper/filho e recupera PID reutilizado sem sinalizar processo alheio |
| `0.1.0a22-7c1084e35707` | `7c1084e357075ebe5374f6a752ca9c24077d4510` | `dec3cc2bba2a8f201e1c6865fb769a9c624e01c66cc0e89f4618042f49cd1c05` | instalada; introduziu boot Game Mode próprio, preparo agnóstico do host e Área Modo Desktop; smoke revelou classificação DMI ausente no comando standalone |
| `0.1.0a23-f24b59e2c860` | `f24b59e2c860a7c75438b5be0788a4ecf16b795f` | `db1b0d304ea42c1f92a1b0e1fe2de46ea4ab95f8bc90ec12d5d5b4463f81ff2f` | instalada; reconheceu o Deck LCD automaticamente; preparação real revelou corrida ao iniciar a rede libvirt |
| `0.1.0a24-e5dc9b35e9d4` | `e5dc9b35e9d4bfa99a9215516ca3584881b8ac04` | `22e884609743987d512cfe7f5227debeabc0e0d465fd4be8477d26b92e5a859f` | instalada; rechecou a rede após corrida; host revelou que o parser ainda dependia da formatação textual do `virsh` |
| `0.1.0a25-2b9f65e54a4b` | `2b9f65e54a4b2314cc293c4a20e389f37c40a6f5` | `fc88b41a9d08996321da8ada10c48f0a694dc6cd52e807ab00fdecb6d21aff47` | ativa; probe libvirt independente de locale, KVM/libvirt pronto no Deck LCD e cadeia GRUB→SDDM→Game Mode ativada; falta observação pós-reboot |

Nenhum desses wheels foi republicado sob a mesma versão. Os desvios encontrados no host
geraram versões sucessivas, mantendo os artefatos e manifests anteriores imutáveis.

## Releases fisicamente certificadas — 2026-07-29

| Release | Commit exato | SHA-256 do wheel | Resultado |
|---|---|---|---|
| `0.1.0a39-8e17159d5122` | `8e17159d51222adf2efaa445c19de40999954d8b` | `591ae8a07205192d67cbcd78a072ff07e98d41d6ec11561e27d41e939cc4c161` | ciclo físico `a39→a37→a39` aprovado; convergência e idempotência provadas nas duas direções; tag `v0.1.0a39` aponta para este commit |
| `0.1.0a41-31b30211ba85` | `31b30211ba85ec9ef60096809616771ff1aef6b5` | `e31e84a92a51f2de64e4ad3c83b021dc53f0050eee595ea9ecb33fd24dfb6d20` | ciclo físico `a41→a40→a41` aprovado; composição real da emulação observada no host; tag `v0.1.0a41` aponta para este commit |

## Release instalada — 0.1.0a42

| Release | Commit | SHA-256 do wheel | Estado |
|---|---|---|---|
| `0.1.0a42-39bd325cee60` | `39bd325cee60dc8477ed2a1886dbe516d53aa7a8` | não registrado no ledger | **instalada no host** (release ativa, confirmada por `inspect`); certificação física adiada, tag `v0.1.0a42` não publicada |

A versão do pacote foi elevada a `0.1.0a42` e o CI construiu o wheel do commit
mesclado na `main`; a release foi instalada no host com autorização explícita do
operador. Os gates físicos adiados continuam obrigatórios para publicação: a tag
`v0.1.0a42` não foi publicada — tag é a afirmação de que eles passaram.

## Candidata em preparo — 0.1.0a43

| Release | Commit | SHA-256 do wheel | Estado |
|---|---|---|---|
| `0.1.0a43-<pendente>` | pendente do merge na `main` | pendente do build do CI | **candidata — não construída, não instalada, não certificada** |

A versão do pacote foi elevada a `0.1.0a43`; o identificador completo da release
só existe depois que o CI construir o wheel a partir do commit exato mesclado na
`main`. Até lá, esta linha registra a intenção, não um artefato.

Nada aqui autoriza instalação: promover a a43 no host exige autorização explícita
do operador na thread em curso (AGENTS.md §1), nomeando o ID completo. O rollback
previsto é a release fisicamente certificada `0.1.0a41-31b30211ba85`, presente no
host.

A tag `v0.1.0a43` **não** será publicada nesta etapa: os gates físicos adiados
continuam obrigatórios para publicação, e tag é a afirmação de que eles passaram.
