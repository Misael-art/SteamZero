# Plano — Ingestão automática de conteúdo PS4, mídia e armazenamento resiliente

**Capacidade:** PS4 content ingestion and reconciliation  
**Identidade de exemplo:** `CUSA03173`  
**Estado:** planejamento; não promove instalação nem prova física  
**Dependência:** contrato do adapter shadPS4 e catálogo PS4 já existente

## Objetivo

Permitir que o usuário selecione uma pasta, disco, share ou arquivo e receba um
jogo organizado automaticamente, sem renomear arquivos nem separar manualmente
base, patch, pasta extraída ou imagem. O SteamZero preserva a origem e evita
cópias desnecessárias de aproximadamente 30,07 GiB.

Identidade técnica, proveniência, mídia e rollback continuam disponíveis, mas a
apresentação usa o padrão canônico:

```text
Bloodborne - Game of the Year Edition [CUSA03173]
```

O ID técnico pode aparecer nos detalhes, mas não deve obrigar o usuário a
entender a estrutura interna do PS4.

## Promessa de experiência do usuário

O fluxo principal é:

```text
selecionar pasta/arquivo
→ escanear automaticamente
→ agrupar conteúdo relacionado
→ localizar mídia correta
→ mostrar um plano compreensível
→ confirmar somente o que for mutável ou ambíguo
```

O usuário não deve precisar renomear arquivos, criar pastas, remover
identificadores técnicos ou informar manualmente `titleId`/`contentId`. Em caso
de incerteza, o sistema preserva o conteúdo, mostra a causa e oferece confirmar
uma associação; nunca exige limpeza manual como pré-condição.

## Descoberta automática de conteúdo PS4

O scanner deve percorrer diretórios de forma segura e classificar o conteúdo
pela estrutura e pelos metadados internos:

| Entrada | Interpretação |
|---|---|
| PKG de jogo | pacote base, identificado pelo conteúdo |
| PKG de atualização | patch vinculado ao base compatível |
| pasta com `sce_sys`, `param.sfo`, `eboot.bin`, `app0` ou `patch` | jogo extraído |
| SELF, ELF, `eboot.bin`, `.sprx`, `.prx` | componentes internos, não jogos independentes |
| ISO/disco | imagem candidata; só fica `ready` se o adapter comprovar suporte |
| PUP | firmware/update de sistema, fora do catálogo de jogos |
| BLS | container/lote a ser inspecionado antes de associação |

O nome externo é apenas uma pista. A identidade deve ser derivada nesta ordem:

```text
metadados internos (param.sfo/PKG/ISO)
→ title ID e content ID
→ catálogo conhecido
→ título, edição e região normalizados
→ nome do arquivo como último fallback
```

Variantes físicas — PKG, pasta extraída, ISO e patch — devem convergir para um
único `gameId`, nunca criar jogos duplicados.

## Forma física gerenciada

```text
ps4/
└── Bloodborne - Game of the Year Edition [CUSA03173]/
    ├── packages.manifest.json
    ├── install/
    └── steamzero-record.json
```

`packages.manifest.json` é um índice lógico. A pasta não deve receber uma cópia
de cada PKG por padrão. Se o adapter exigir um caminho local estável, o plano
escolhe, nesta ordem:

1. referência ao arquivo original;
2. hardlink, se o mesmo filesystem permitir;
3. reflink, se o filesystem oferecer cópia sob demanda;
4. cópia local, somente com custo de espaço explícito e confirmação.

Os nomes canônicos podem ser usados em aliases gerenciados, mas o arquivo de
origem nunca é renomeado, movido ou apagado.

## Identidade e resolução de origem

Um caminho absoluto não é identidade. Cada pacote deve guardar:

```json
{
  "source": {
    "kind": "local|removable|sdcard|network",
    "rootIdentity": "UUID-do-volume-ou-identidade-do-share",
    "relativePath": "roms/ps4/Bloodborne/base.pkg",
    "pathHint": "/media/misael/DISCO/roms/ps4/Bloodborne/base.pkg"
  }
}
```

`pathHint` é apenas informativo. Na reabertura, o resolver procura a raiz com a
mesma identidade e reconstrói o caminho relativo. Se o volume ou share não
estiver disponível, o pacote fica `missing`; o sistema não fixa o caminho atual
nem altera o registro silenciosamente.

Hardlink e reflink são otimizações locais, nunca requisitos para mídia removível
ou rede. O registro deve guardar também `storageMode` e `additionalBytes` para
que a UI explique exatamente o que será ocupado.

## Registro mínimo

`steamzero-record.json` deve guardar:

- `gameId`: `ps4:cusa03173`;
- título de apresentação, nome canônico e aliases;
- `titleId`, `contentId`, versão e tipo extraídos do PKG;
- hash SHA-256 obrigatório e BLAKE2 opcional;
- tamanho em bytes, papel `base` ou `patch`;
- dependências, especialmente patch → base compatível;
- `contentSources[]` para PKG, pasta extraída, ISO ou container, com formato,
  caminho relativo, metadados internos e capacidade do adapter;
- `mediaIdentity`, papéis de mídia, candidatos, confiança e proveniência;
- origem, caminho relativo e caminho anterior;
- estado `staged`, `verified`, `ready`, `installed`, `conflict`, `missing`,
  `stale` ou `needs-review`;
- método de armazenamento e espaço adicional previsto/real;
- histórico de plan/apply/verify/rollback.

## Validação

O nome do arquivo serve para descoberta e apresentação, nunca para prova. O
scanner deve validar o conteúdo real do PKG e extrair:

- title ID;
- content ID;
- versão;
- tipo base/patch;
- tamanho e hashes;
- dependências declaradas ou inferíveis pelo contrato do adapter.

Um patch sem base compatível não vira `ready`. Pacotes com mesmo hash são uma
única fonte canônica; pacotes com metadados conflitantes ou hashes diferentes
permanecem preservados e entram em `conflict`/`needs-review`.

## Identidade e busca de mídia

A organização do conteúdo e a busca de arte devem usar a mesma identidade. O
scanner publica uma `MediaIdentity` sem depender do nome bruto:

```json
{
  "platformId": "playstation-4",
  "titleId": "CUSA03173",
  "canonicalTitle": "Bloodborne - Game of the Year Edition",
  "edition": "Game of the Year",
  "region": "USA",
  "aliases": ["Bloodborne", "Bloodborne GOTY"]
}
```

A ordem de resolução é:

```text
title ID + plataforma + edição
→ content ID + região
→ título canônico + edição + plataforma
→ aliases normalizados
→ nome externo apenas como fallback
```

O resultado deve ser um conjunto de mídia por jogo, com papéis independentes:
`cover`, `boxFront`, `fanart`, `screenshot`, `logo`, `video`, `icon` e `manual`.
Cada candidato guarda provider, ID externo, URL, hash, licença, timestamp,
confiança e `matchedBy`.

Regras de segurança da associação:

1. correspondência exata por title ID pode ser aceita automaticamente;
2. content ID, edição e região devem ser compatíveis;
3. título semelhante sem ID exige limiar de confiança e pode exigir confirmação;
4. conflito de candidatos vira `needs-review`, não escolha silenciosa;
5. patch, pasta extraída e ISO reutilizam a mídia do mesmo `gameId`;
6. nenhum provider conhecido deve resultar em fallback visual legível, nunca em
   arte de outro jogo.

Download de mídia também segue `plan → apply → verify`, com cache deduplicado por
hash, licença/proveniência preservadas e fallback offline. O scan não baixa nem
substitui arte sem um plano; a experiência, porém, não fica bloqueada aguardando
mídia: o jogo já pode aparecer com título, sistema e placeholder.

## Modelo lógico unificado

```text
GameRecord: ps4:cusa03173
├── displayName: Bloodborne - Game of the Year Edition [CUSA03173]
├── contentSources
│   ├── PKG base
│   ├── PKG patch v1.09
│   ├── extracted folder
│   └── ISO candidate
├── MediaIdentity
├── media roles + provenance + confidence
├── adapter requirements/capabilities
└── storage/install/verification state
```

O catálogo apresenta um único jogo. Detalhes técnicos, fontes, versões,
conflitos e espaço ficam disponíveis em uma seção avançada.

## Espaço em disco

Com a medição atual:

```text
Base:        ~29,9 GiB
Patch v1.09: ~173 MiB
PKGs fonte:  ~30,07 GiB
```

O plano deve separar três números:

| Componente | Valor esperado |
|---|---:|
| PKGs fonte | ~30,07 GiB |
| acréscimo de referência/hardlink/reflink | insignificante ou sob demanda |
| cópia local, se obrigatória | ~30,07 GiB adicionais |
| dados instalados pelo shadPS4 | medidos pelo adapter |

Não se deve inferir o tamanho instalado a partir do PKG. Após o apply, o verify
mede a área `install/` e publica o total real. O `plan` deve mostrar tanto o
espaço adicional quanto o total envolvido antes da confirmação.

## Transação e rollback

```text
scan
→ varrer fontes e classificar conteúdo
→ validar cabeçalho, estrutura e conteúdo
→ calcular hashes
→ agrupar GameRecord e detectar duplicatas/dependências
→ resolver MediaIdentity e candidatos
→ plan com storageMode, mídia e espaço
→ confirmação explícita
→ reference/link/copy
→ instalar base
→ instalar patch
→ verify
→ verificar mídia e fallback
→ publicar no catálogo
```

Se qualquer fase falhar, o manifesto anterior permanece intacto. Cópias
parciais entram em staging/quarentena; o rollback restaura o registro anterior.
Arquivos antigos não são apagados automaticamente.

## Fora do escopo desta frente

- alterar o manifesto PS4 ou o lockfile do shadPS4;
- alterar a UI/QML do Launcher ou do AURA Cinema;
- substituir o contrato do adapter;
- instalar o shadPS4 no host;
- alegar lançamento físico sem executar `verify` e uma prova real.

Essas mudanças devem ser entregues ao owner correspondente como contrato
isolado, sem editar seus arquivos exclusivos.

## Critérios de aceite

1. Uma pasta ou arquivo importado sem renomeação manual produz um único jogo lógico.
2. A apresentação usa `Bloodborne - Game of the Year Edition [CUSA03173]`.
3. O scanner distingue base, patch, pasta extraída, ISO, PUP e componentes pelo conteúdo.
4. Base e patch compatíveis convergem para o mesmo `gameId`.
5. O mesmo PKG nunca é copiado duas vezes por hash.
6. Mídia local, removível, SD e rede resolve por identidade da raiz + caminho relativo.
7. A mídia é buscada por title ID/edição/região antes do nome e nunca mistura jogos.
8. O plano informa espaço adicional e dados instalados separadamente antes do apply.
9. Hardlink/reflink só são usados quando suportados e verificáveis.
10. Falhas preservam origem, mídia anterior e manifesto anterior.
11. O catálogo mostra fallback legível quando mídia ou adapter não estão disponíveis.
12. O catálogo só recebe o jogo como `ready` depois de hashes, dependência, mídia
    e lançamento pelo adapter serem verificados.
