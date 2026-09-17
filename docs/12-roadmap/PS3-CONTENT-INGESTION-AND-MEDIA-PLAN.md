# Plano PS3 — ingestão unificada, firmware, licenças e mídia

## Objetivo

Entregar uma experiência em que o usuário aponta uma pasta, arquivo, unidade removível ou compartilhamento e o SteamZero descobre jogos de PlayStation 3 sem exigir renomeação, separação manual de PKGs ou conhecimento de `PARAM.SFO`, RAP, EDAT e firmware.

O catálogo deve apresentar uma obra lógica no formato:

```text
Título do jogo - Edição [TITLEID]
```

As diferenças técnicas continuam preservadas nos detalhes: título ID, content ID, região, edição, mídia física/digital, versão, hashes, dependências, firmware e licenças.

## Situação atual

O projeto já declara a plataforma `playstation-3`, o adapter RPCS3, o perfil DualShock 3 e a exigência de firmware. Porém, o manifesto ainda expõe apenas `iso`, `ps3` e `ps3dir` como fontes de mídia; a reconciliação automática de PKG, patch, DLC, RAP e EDAT ainda não está fechada. O item de requisitos também registra que o store de firmware PS3 ainda não está ligado ao produto.

O adapter de componente RPCS3 comprova o runtime, não a ingestão completa de jogos. A prova física de firmware, instalação de conteúdo e lançamento real permanece separada.

## Contrato externo do RPCS3

O RPCS3 trabalha com jogos em disco, conteúdo digital, firmware e licenças como entidades diferentes. O firmware `PS3UPDAT.PUP` é instalado como requisito do emulador; uma licença RAP ausente ou inválida pode impedir a descriptografia de conteúdo digital. Essas condições aparecem no código oficial de instalação e diagnóstico do RPCS3: [main_window.cpp](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/rpcs3qt/main_window.cpp).

A compatibilidade é acompanhada por Game ID e separa versões de disco e digitais. O SteamZero deve preservar essa distinção para lançamento e mídia, mesmo quando a interface agrupa as versões sob uma obra única: [RPCS3 Game Compatibility](https://github.com/RPCS3/rpcs3/wiki/Game-Compatibility).

## Modelo de identidade

Uma única identidade textual não é suficiente para todas as variantes PS3. O modelo deve separar obra, mídia e fonte:

```text
gameGroupId: ps3:<canonical-work-id>
  canonicalTitle
  edition
  aliases[]
  mediaVariants[]

mediaId: ps3:<titleId>:<contentId>:<mediaType>
  titleId
  contentId
  mediaType: disc | digital
  region
  edition
  sourceVariants[]
  launchTarget
```

O `TITLEID` deve ser obtido do `PARAM.SFO`, metadados do PKG ou outro identificador interno validado. O nome da pasta ou do arquivo só pode ser usado como fallback de descoberta, nunca como prova final.

Cada fonte deve guardar:

```text
sourceId
kind: disc-folder | iso | pkg | patch | dlc | rap | edat | firmware
pathReference
relativePath
volumeOrShareIdentity
sha256/blake2
internalMetadata
version
parentMediaId
state
```

## Fontes suportadas

### Pasta de disco extraída

Detectar a estrutura interna, independentemente do nome externo:

```text
PS3_GAME/
PS3_GAME/PARAM.SFO
PS3_GAME/USRDIR/
PS3_DISC.SFB
```

`EBOOT.BIN`, SELF, SPRX, PRX e arquivos de `USRDIR` são componentes do jogo e não entradas independentes no catálogo.

### ISO

Uma ISO deve ser registrada como variante de mídia física. O resolver deve validar o formato, hash e metadados internos antes de associá-la ao jogo.

Não extrair ou converter a ISO durante o scan. Se o adapter exigir staging, o plano deve mostrar o custo e manter o arquivo original somente leitura.

### PKG digital

Todo PKG deve ser classificado pelo conteúdo real:

```text
base game
patch/update
DLC/add-on
demo
application/theme
firmware ou pacote desconhecido
```

O registro deve conter title ID, content ID, versão, região quando disponível, dependências, tamanho, hash e tipo de conteúdo. O nome do PKG não pode decidir sozinho se ele é base, patch ou DLC.

O resultado esperado é:

```text
Jogo principal
  ├─ base PKG
  ├─ patch v1.x
  ├─ DLC 1
  ├─ RAP
  └─ EDAT
```

Nenhum desses componentes deve criar um jogo duplicado.

### RAP e EDAT

RAP é tratado como licença fornecida pelo usuário; EDAT é tratado como conteúdo protegido. O SteamZero deve apenas localizar, validar, registrar e associar esses arquivos ao `mediaId` correto.

Estados possíveis:

```text
license-present
license-missing
license-invalid
protected-data-present
protected-data-unresolved
```

Não baixar, fabricar, alterar ou publicar licenças. A interface deve oferecer ações claras como “Localizar licença” e “Ver detalhes do bloqueio”, sem exigir que o usuário edite nomes.

### Firmware

`PS3UPDAT.PUP` é requisito global do perfil RPCS3, não um jogo. O store deve deduplicar firmware por hash e registrar versão, origem, destino e compatibilidade.

```text
firmwareId
version
sha256
sourceReference
installedTarget
state: discovered | verified | installed | invalid | missing
```

Firmware ausente bloqueia o lançamento de forma explicável, mas não remove o jogo do catálogo.

### Saves, troféus, cache e configurações

Saves, troféus, cache de shaders, logs, configurações e dados persistentes do RPCS3 não são fontes de jogos. Devem ser associados ao perfil do emulador ou ao jogo somente quando o contrato correspondente existir.

## Regras de reconciliação

As fontes serão associadas nesta ordem:

1. title ID e metadados internos;
2. content ID;
3. vínculo explícito de patch/DLC com o jogo base;
4. região e edição;
5. hash e estrutura física;
6. nome normalizado como fallback sujeito a confirmação.

Variantes de região, mídia física/digital, edição e hashes diferentes não podem ser mescladas silenciosamente. Duplicatas byte-a-byte devem ser preservadas como fontes alternativas, sem criar cópia gerenciada desnecessária.

## Caminhos resilientes

O registro deve guardar referências transportáveis:

```text
volumeOrShareIdentity
relativePath
contentFingerprint
lastKnownPath
mountHints
```

O sistema deve funcionar com SSD, HD externo, SD, rede e pontos de montagem variáveis. Fonte ausente vira `missing-source`, não desaparece do catálogo.

Hardlink e reflink só são válidos no mesmo filesystem. Para ISO e PKG grandes, o padrão é referência externa; uma cópia local, instalação ou extração só ocorre em operação planejada com custo explícito.

## Mídia

```text
platformId: playstation-3
gameGroupId
titleId
contentId
mediaType
region
edition
canonicalTitle
aliases[]
```

Prioridade da busca:

1. plataforma + title ID;
2. content ID;
3. title ID + mídia física/digital;
4. título canônico + edição + região;
5. aliases;
6. nome do arquivo como fallback.

A imagem encontrada deve registrar provider, ID externo, papel, hash, licença, confiança e método de correspondência. Conflitos ficam em `needs-review`; ausência de provider gera fallback legível.

## Fluxo transacional

```text
scan
→ inspect internal metadata
→ classify source
→ resolve gameGroupId/mediaId
→ associate base, patch, DLC, RAP and EDAT
→ resolve firmware
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
stagingBytes
mediaCacheBytes
rpcs3DataBytes
additionalBytes
```

Se o apply falhar, fontes, firmware e licenças permanecem intactos; a instalação gerenciada sofre rollback e o catálogo anterior continua válido.

## Estados

```text
discovered
classified
identified
linked
firmware-missing
license-missing
invalid-source
conflict
missing-source
verified
ready
unsupported
needs-review
```

`ready` só é permitido quando a identidade, a fonte, o firmware, as licenças necessárias e o alvo de lançamento forem validados pelo adapter RPCS3.

## Fases

1. **Contrato e fixtures** — identidade obra/mídia/fonte, firmware, PKG, RAP e EDAT.
2. **Resolver seguro** — pasta PS3, ISO, PKG, `PARAM.SFO`, duplicatas e relações.
3. **Store de firmware/licenças** — hash, associação, estados, referência externa e rollback.
4. **Catálogo e mídia** — read model por title ID/content ID e fallback seguro.
5. **Adapter RPCS3** — preflight, instalação governada e launch target por tipo de mídia.
6. **Validação física** — firmware, jogo em disco, jogo digital com licença fornecida pelo usuário, erro controlado e recuperação.

## Critérios de aceite

- O usuário escolhe uma raiz e não precisa renomear ou separar arquivos.
- Pasta PS3 e ISO são reconhecidas pelo conteúdo interno.
- PKG é classificado em base, update, DLC, demo ou desconhecido.
- RAP e EDAT são associados sem duplicar o jogo.
- Firmware aparece como requisito global, nunca como jogo.
- Jogo físico e digital podem compartilhar a obra exibida, mas preservam media IDs diferentes.
- Região e edição conflitantes não são mescladas automaticamente.
- SD, USB e rede sobrevivem à mudança de ponto de montagem.
- O scan não copia nem extrai arquivos grandes sem plano.
- O espaço adicional é mostrado antes do apply.
- Falha de firmware, RAP ou EDAT gera causa e próxima ação.
- O apply é reversível e não apaga fontes originais.
- A entrada só fica `ready` após preflight real do RPCS3.
- Nenhum arquivo de Theme Engine, QML, AURA Launcher ou PS4 é tocado.

