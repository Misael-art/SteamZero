# Plano Xbox 360 — ingestão unificada, identidade e mídia

## Objetivo

Entregar uma experiência em que o usuário aponta uma pasta, arquivo, disco removível ou compartilhamento e o SteamZero descobre automaticamente os jogos Xbox 360. O usuário não deve renomear arquivos, separar manualmente ISO/GOD, encontrar `default.xex`, distinguir DLC de jogo ou reorganizar pastas anônimas.

O catálogo deve mostrar uma entrada lógica por jogo, com nome estável no formato:

```text
Título do jogo - Edição [TITLEID]
```

O `TITLEID`, content ID, media ID, região, edição, hashes e caminhos físicos permanecem nos detalhes técnicos. O nome do arquivo nunca é a identidade primária.

## Referência do adapter

O Xenia documenta jogos extraídos com `default.xex`, estruturas GOD compostas por arquivo e pasta `.data`, conteúdo digital em árvores `Content` e jogos XBLA que podem aparecer como arquivo único. `ContentCache.pkg` é cache e não deve virar um jogo no catálogo: [Xenia Quickstart](https://github.com/xenia-project/xenia/wiki/Quickstart).

O ponto de entrada do Xenia aceita caminhos `.iso` e `.xex`, mas isso não substitui o preflight do adapter: uma fonte só é `ready` após a identidade e o alvo de lançamento terem sido validados. [Fonte do Xenia](https://github.com/xenia-project/xenia/blob/master/src/xenia/app/xenia_main.cc)

Jogos do Xbox original não devem ser promovidos como Xbox 360/Xenia; devem ser classificados como outra plataforma ou `unsupported`, conforme a capacidade do adapter. [FAQ oficial do Xenia](https://github.com/xenia-project/xenia/wiki/faq)

## Modelo de identidade

```text
gameId: xbox360:<titleId>
canonicalTitle
edition
region
titleId
contentIds[]
mediaIds[]
aliases[]
launchTarget
sourceVariants[]
auxiliaryContent[]
mediaIdentity
storageReferences[]
```

Cada fonte física deve guardar:

```text
sourceId
kind: iso | extracted | god | digital | package | dlc | title-update
pathReference
relativePath
contentFingerprint
sha256/blake2
internalMetadata
state
```

O estado da fonte e do jogo deve distinguir `discovered`, `classified`, `grouped`, `verified`, `ready`, `missing`, `ambiguous`, `conflict`, `unsupported` e `needs-review`.

## Classificação automática

O resolver deve inspecionar primeiro a estrutura e os metadados, sem depender do nome externo:

- `.iso`: candidato a imagem de disco, validado pelo adapter;
- pasta extraída: localizar `default.xex` e reconhecer múltiplos `.xex` sem pedir ao usuário para escolher arbitrariamente;
- GOD: vincular o arquivo principal à pasta `.data` de mesmo identificador;
- XBLA/digital: reconhecer pela estrutura e pelos metadados internos;
- `Content/...`: inspecionar os níveis internos e usar IDs técnicos, não os nomes anônimos das pastas;
- DLC e title updates: associar ao jogo principal por identidade e versão;
- saves, perfis, cache e `ContentCache.pkg`: excluir do catálogo de jogos;
- pacote não interpretável: preservar a origem e marcar `needs-review`.

O scan não deve extrair uma ISO ou copiar uma pasta grande. Para containers, deve ler índice e cabeçalhos com limites de tamanho, bloquear traversal e nomes inválidos e somente criar conteúdo derivado durante um `plan → apply → verify` explícito.

## Ordem de reconciliação

As fontes serão unificadas nesta ordem:

1. `TITLEID` e metadados internos;
2. content ID, media ID, edição e região;
3. vínculo estrutural conhecido, como arquivo GOD e `.data`;
4. relação explícita entre jogo, DLC e update;
5. nome normalizado como fallback;
6. confirmação somente quando a confiança for insuficiente.

Regiões, edições, hacks, traduções e hashes diferentes não podem ser silenciosamente mesclados. Duplicatas idênticas devem apontar para uma fonte canônica, preservando as demais referências; variantes diferentes permanecem disponíveis como fontes alternativas.

## Caminhos locais, removíveis e rede

O SteamZero deve guardar uma referência transportável, nunca um caminho absoluto como identidade:

```text
volumeOrShareIdentity
relativePath
contentFingerprint
lastKnownPath
mountHints
```

Se o volume ou compartilhamento estiver ausente, o jogo passa a `missing` sem ser apagado. Hardlink e reflink só são permitidos no mesmo filesystem. Para SD, USB, rede ou pontos de montagem variáveis, o padrão é referenciar a origem; uma cópia local só pode ser feita com consentimento e com o espaço declarado.

## Mídia

A identidade de mídia deve ser:

```text
platformId: xbox-360
titleId
canonicalTitle
edition
region
contentId
aliases[]
```

Prioridade de busca:

1. `TITLEID + plataforma`;
2. content ID/media ID;
3. título canônico + edição + região;
4. aliases;
5. nome do arquivo apenas como fallback.

Cada candidato deve registrar provider, ID externo, papel, URL/cache, hash, licença, confiança, método de correspondência e data. Conflitos entram em `needs-review`; ausência de provider gera fallback legível, nunca arte de outro jogo.

## Espaço e operação transacional

Todo plano deve separar:

```text
sourceBytes       ISO/GOD/pasta original
metadataOverhead  índices e registro do SteamZero
derivedBytes      extração ou staging opcional
mediaCacheBytes   capas, fanart e vídeos
xeniaDataBytes    saves/cache criados pelo emulador
additionalBytes   custo adicional da operação
```

O fluxo de mutação é:

```text
scan → classify → group → resolve identity → resolve media
→ plan → apply → verify → publish catalog → launch preflight
```

Falhas deixam a fonte original intacta. Nenhum arquivo é removido automaticamente, e uma operação de staging deve ter rollback e registro de proveniência.

## Contrato mínimo do manifesto/adapter

O manifesto Xbox 360 deve declarar, sem prometer além da prova:

- formatos e source kinds aceitos;
- política de containers e extração;
- metadados que resolvem `TITLEID`, edição e região;
- relação jogo/DLC/update/cache/save;
- alvos de lançamento (`iso`, `default.xex`, GOD ou digital);
- comportamento para múltiplos `.xex`;
- estados de readiness e razões de recusa;
- política de dados persistentes do Xenia;
- providers de mídia compatíveis.

O adapter não deve escolher um `.xex` arbitrário nem tratar uma pasta de dados como jogo. A opção correta, quando a identidade não puder ser comprovada, é `needs-review` com causa e próximo passo.

## Fases de implementação

1. **Contrato e fixtures** — modelos de identidade, source reference, estados e fixtures representando ISO, extraído, GOD, digital, DLC, cache, duplicata e volume ausente.
2. **Resolver seguro** — classificação estrutural, leitura limitada de containers, agrupamento por IDs e exclusão de cache/saves.
3. **Catálogo e adapter** — read model Xbox 360, preflight de lançamento e integração sem editar o núcleo compartilhado da biblioteca.
4. **Mídia** — consulta por identidade, cache, confiança, fallback e conflitos.
5. **Espaço e referências** — relatório de bytes, referências externas, staging opcional e rollback.
6. **Validação física** — release instalada, fonte real representativa, captura de sucesso, recusa controlada e recuperação. A prova de Xenia não deve ser inferida dos testes offscreen.

## Critérios de aceite

- O usuário escolhe uma raiz e não precisa renomear ou separar fontes.
- ISO, pasta com `default.xex`, GOD e conteúdo digital não criam duplicatas quando os metadados apontam para o mesmo jogo.
- Um arquivo GOD e sua pasta `.data` são tratados como uma única fonte lógica.
- DLC, updates, cache e saves não aparecem como jogos independentes.
- Duplicatas idênticas são preservadas sem ocupar uma segunda cópia gerenciada.
- Regiões e edições conflitantes permanecem separadas ou pedem confirmação.
- A mídia é buscada por `TITLEID` antes do título textual.
- Removível, SD e rede continuam válidos quando o ponto de montagem muda.
- O scan não duplica arquivos grandes nem extrai conteúdo sem plano.
- O plano exibe o espaço adicional real antes do apply.
- Falhas deixam a origem intacta e publicam a causa em `needs-review` ou `unsupported`.
- A entrada só fica `ready` após o preflight do adapter.
- Nenhum arquivo de Theme Engine, QML, AURA Launcher ou asset de tema é tocado.

