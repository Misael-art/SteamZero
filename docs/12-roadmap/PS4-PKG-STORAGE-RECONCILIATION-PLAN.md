# Plano — Reconciliação e armazenamento de PKG do PS4

**Capacidade:** PS4 PKG storage/reconciliation  
**Identidade de exemplo:** `CUSA03173`  
**Estado:** planejamento; não promove instalação nem prova física  
**Dependência:** contrato do adapter shadPS4 e catálogo PS4 já existente

## Objetivo

Permitir que o SteamZero reconheça base e patch de um jogo PS4, preserve os PKGs
originais e evite criar cópias desnecessárias de aproximadamente 30,07 GiB.
Identidade técnica, proveniência e rollback continuam disponíveis, mas a
apresentação usa o nome canônico:

```text
Bloodborne - Game of the Year Edition [CUSA03173]
```

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
- título de apresentação e título técnico;
- `titleId`, `contentId`, versão e tipo extraídos do PKG;
- hash SHA-256 obrigatório e BLAKE2 opcional;
- tamanho em bytes, papel `base` ou `patch`;
- dependências, especialmente patch → base compatível;
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
→ validar cabeçalho e conteúdo
→ calcular hashes
→ detectar duplicatas e dependências
→ plan com storageMode e espaço
→ confirmação explícita
→ reference/link/copy
→ instalar base
→ instalar patch
→ verify
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

1. O diretório exibido mantém exatamente `Bloodborne - Game of the Year Edition [CUSA03173]`.
2. O scanner distingue base e patch pelo conteúdo, não pelo nome.
3. O mesmo PKG nunca é copiado duas vezes por hash.
4. Mídia local, removível, SD e rede resolve por identidade da raiz + caminho relativo.
5. O plano informa espaço adicional antes do apply.
6. Hardlink/reflink só são usados quando suportados e verificáveis.
7. Falhas preservam origem e manifesto anterior.
8. O catálogo só recebe o jogo depois de hashes, dependência e lançamento pelo adapter serem verificados.
