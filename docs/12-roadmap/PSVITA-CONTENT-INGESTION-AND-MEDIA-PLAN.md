# Plano PS Vita — ingestão unificada, firmware, keys e mídia

## Objetivo

Permitir que o usuário escolha uma pasta, arquivo, unidade removível ou compartilhamento e o SteamZero descubra jogos de PlayStation Vita sem renomeação, extração manual ou conhecimento de `param.sfo`, VPK, VCI, PKG, firmware e licenças.

O catálogo deve apresentar uma entrada amigável:

```text
Título do jogo - Edição [TITLE_ID]
```

Title ID, content ID, região, edição, versão, origem, hashes, firmware, keys e licença permanecem nos detalhes técnicos.

## Situação atual

O projeto já possui manifesto PS Vita, adapter Vita3K, perfil portátil e declaração de `keys`/`firmware`. Porém, o manifesto ainda precisa alinhar `vci`, política de containers, pacote de fontes, licença/zrif e associação por title ID/content ID. O adapter comprova o runtime, mas não fecha ingestão, store de requisitos nem prova física de jogo real.

## Contrato Vita3K

O Vita3K documenta instalação de `.pkg`, `.vpk`, `.zip` e `.vci`, além de pastas de jogos extraídos. Também informa que dumps Vitamin não são suportados e que Maidump é instável: [FAQ oficial](https://vita3k.org/faq) e [Quickstart](https://vita3k.org/ja/quickstart).

O código oficial expõe instalação de firmware, PKG e conteúdo VPK/ZIP, além de `--zrif` para conteúdo PKG que exige licença: [configuração do Vita3K](https://github.com/Vita3K/Vita3K/blob/master/vita3k/config/src/config.cpp) e [fluxo de instalação](https://github.com/Vita3K/Vita3K/blob/master/vita3k/main.cpp).

## Identidade

Separar obra, variante e fonte:

```text
gameGroupId: psvita:<canonical-work-id>
mediaId: psvita:<titleId>:<contentId>:<edition>
sourceId: fingerprint + volume/share + relative path
```

Campos:

```text
canonicalTitle
edition
region
titleId
contentId
version
aliases[]
sourceKind
licenseState
firmwareRequirements
keyRequirements
installedTarget
```

O ID deve vir de `sce_sys/param.sfo` ou metadados internos do pacote. Nome de pasta e nome de arquivo são apenas fallback.

## Fontes reconhecidas

- **Pasta extraída:** localizar `sce_sys/param.sfo`, `eboot.bin` e conteúdo do aplicativo;
- **VPK:** inspecionar índice, validar traversal, extrair somente em `plan → apply → verify`;
- **ZIP:** identificar se contém VPK, dump NoNpDrm ou pasta de conteúdo;
- **VCI:** tratar como formato próprio, sem reduzi-lo a ZIP;
- **PKG:** classificar como base, update, DLC, demo, aplicação ou desconhecido;
- **NoNpDrm/FAGDec:** aceitar somente após metadados e estrutura válidos;
- **Vitamin:** `unsupported`;
- **Maidump:** `needs-review`;
- **firmware e fontes:** requisitos globais do perfil Vita3K;
- **cache, shaders, saves e configuração:** não são jogos.

Nenhum arquivo `eboot.bin`, módulo ou diretório interno pode virar um jogo independente.

## Firmware, fontes, keys e licença

O Vita3K informa que alguns jogos precisam de módulos de firmware e de um pacote adicional de fontes. O SteamZero deve registrar ambos separadamente:

```text
requirementId
kind: firmware | font-package | key | license
version
sha256
sourceReference
targetProfile
state
```

Estados:

```text
present
missing
invalid
incompatible
verified
installed
```

O sistema não deve baixar, fabricar ou alterar keys, firmware ou licenças. Deve oferecer ações claras como “Localizar firmware”, “Localizar pacote de fontes” e “Associar licença”.

## Reconciliação

Associar fontes nesta ordem:

1. title ID e `param.sfo`;
2. content ID;
3. relação explícita de update/DLC;
4. região e edição;
5. hash e estrutura;
6. nome normalizado como fallback confirmado.

Variantes regionais, edições e hashes diferentes não podem ser mescladas silenciosamente. Duplicatas idênticas permanecem como fontes alternativas sem nova cópia gerenciada.

## Armazenamento resiliente

```text
volumeOrShareIdentity
relativePath
contentFingerprint
lastKnownPath
mountHints
```

O jogo continua reconhecido em SSD, HD externo, SD e rede, mesmo com ponto de montagem alterado. Fonte ausente vira `missing-source`, nunca desaparece.

Hardlink/reflink somente no mesmo filesystem. O padrão para conteúdo grande é referência externa; staging ou instalação no Vita3K deve ser planejado e mensurado.

## Mídia

```text
platformId: playstation-vita
titleId
contentId
canonicalTitle
edition
region
mediaType
aliases[]
```

Prioridade:

1. plataforma + title ID;
2. content ID;
3. região/edição;
4. título canônico;
5. aliases;
6. nome do arquivo como fallback.

Candidato de mídia deve registrar provider, ID externo, papel, hash, licença, confiança e método de correspondência. Conflito vira `needs-review`; ausência usa fallback legível.

## Fluxo transacional e espaço

```text
scan
→ inspect archive safely
→ read param.sfo
→ identify title/content ID
→ classify VPK/ZIP/VCI/PKG/folder
→ associate DLC/updates/license
→ resolve firmware/font package/keys
→ resolve media
→ plan
→ apply
→ verify
→ publish catalog
→ launch preflight
```

O plano deve separar:

```text
sourceBytes
installedBytes
firmwareBytes
fontPackageBytes
derivedBytes
mediaCacheBytes
vita3kDataBytes
additionalBytes
```

Falhas preservam origens, licenças e catálogo anterior. Artefatos gerenciados devem ter rollback e ownership próprio.

## Estados

```text
discovered
classified
identified
firmware-missing
keys-missing
license-missing
unsupported-dump
invalid-source
conflict
missing-source
verified
ready
needs-review
```

`ready` exige metadados válidos, formato aceito, requisitos satisfeitos, fonte íntegra e preflight Vita3K aprovado.

## Fases

1. **Contrato e fixtures** — `param.sfo`, VPK, ZIP, VCI, PKG, NoNpDrm, Vitamin, firmware e licença.
2. **Resolver seguro** — inspeção de archives, classificação e agrupamento por IDs.
3. **Store de requisitos** — firmware, fontes, keys, licença/zrif e estados.
4. **Catálogo e mídia** — read model por title/content ID e fallback seguro.
5. **Adapter Vita3K** — staging, preflight e lançamento por source kind.
6. **Validação física** — firmware, fonte real, erro controlado e lançamento/retorno.

## Critérios de aceite

- O usuário escolhe uma raiz e não precisa renomear ou extrair manualmente.
- Pasta, VPK, ZIP, VCI e PKG são distinguidos pelo conteúdo real.
- Vitamin nunca aparece como `ready`.
- Firmware, pacote de fontes, keys e licença são requisitos separados.
- Variantes regionais e digitais preservam title/content IDs.
- SD, USB e rede sobrevivem à mudança do ponto de montagem.
- O scan não duplica arquivos grandes.
- O plano informa espaço adicional antes do apply.
- Falhas não removem fontes nem corrompem instalação anterior.
- Mídia é resolvida por title ID/content ID antes do nome.
- A entrada só fica `ready` após preflight Vita3K.
- Nenhum arquivo de tema, launcher, PS3 ou PS4 é alterado.

