# Plano de implantação — SharpEmu / PlayStation 5

**Item proposto:** `SZ-PLATFORM-PS5-CATALOG`  
**Workstream proposto:** `WS-2026-09-PS5-SHARPEMU`  
**Estado:** planejado; nenhuma implementação ou instalação é declarada  
**Data do plano:** 2026-09-17

**Implementação atual:** parcial em `codex/platform-ps5-sharpemu`; contrato
declarativo, lockfile, payload `tar.gz`, identidade `param.sfo`/`param.json`, scanner
`ps5dir`, catálogo, perfil DualSense e snapshot pinned dos 46 relatórios
públicos de compatibilidade implementados. A promoção só ocorre para Title ID,
build e sistema operacional exatos; a instalação física e a prova Linux
continuam pendentes.

## 1. Decisão de produto

Integrar o SharpEmu como uma plataforma PS5 experimental e independente. Ele não
será uma extensão do PS4/shadPS4: a plataforma será `playstation-5`, o sistema
será `ps5` e o adapter será `sharpemu`.

O upstream informa que o projeto é experimental, escrito em C#, focado
exclusivamente em PS5 e capaz de carregar `eboot.bin` e arquivos `.elf`. A
compatibilidade publicada ainda é pequena: 46 de 9.055 títulos foram testados,
com 2 em `Ingame` e 3 em `Playable`. Portanto, o catálogo deve exibir
`experimental`, build e estado por jogo; nenhum título deve ser apresentado como
pronto apenas porque o runtime foi instalado.

Fontes externas verificadas em 2026-09-17:

- [site oficial](https://sharpemu.app/)
- [downloads oficiais](https://sharpemu.app/downloads/)
- [compatibilidade oficial](https://sharpemu.app/compatibility/)
- [repositório oficial](https://github.com/sharpemu/sharpemu)
- [release v0.0.3-release.4](https://github.com/sharpemu/sharpemu/releases/tag/v0.0.3-release.4)

## 2. Contrato de catálogo

O recorte deverá criar, em branch própria, os seguintes artefatos:

- manifesto de plataforma `playstation-5`;
- adapter `sharpemu`;
- perfil declarativo de DualSense;
- asset visual autoral, sem redistribuir marca proprietária;
- entrada no catálogo canônico;
- fixtures e testes unitários/integrados;
- item de status e workstream próprios.

Contrato inicial:

| Campo | Valor planejado | Regra |
|---|---|---|
| `platformId` | `playstation-5` | nunca compartilhar com PS4 |
| `systemId` | `ps5` | usado para diretórios e filtros |
| `adapterId` | `sharpemu` | runtime experimental |
| formato lógico | `ps5dir` | pasta de dump identificada |
| entrada de execução | `eboot.bin` | resolver dentro da pasta validada |
| alternativa | `.elf` | somente quando identificada como executável PS5 |
| requisitos | x64 + Vulkan + driver atual | não inventar firmware ou keys |
| estado inicial | `experimental` | compatibilidade por build e título |

O launcher deve executar o equivalente a:

```text
SharpEmu <caminho-seguro>/eboot.bin
```

O caminho absoluto nunca será a identidade. A identidade usará `volume_id` ou
`share_id`, caminho relativo, origem removível/rede, tamanho e hash.

## 3. Fonte e ciclo de implantação

A release Linux atual é `v0.0.3-release.4`, publicada em 8/9/2026, como
`sharpemu-0.0.3-release.4-linux-x64.tar.gz`. A página oficial também lista
Windows e macOS, mas o alvo SteamZero é Linux x64; a compatibilidade de host,
GPU e driver deve ser verificada localmente.

Antes de criar o manifesto definitivo, registrar:

- URL exata do asset;
- tag e commit de origem (`6d4e5b4` na release consultada);
- SHA-256 do asset obtido da fonte oficial;
- lista de membros e executável esperado;
- licença e upstream;
- smoke test e códigos de saída observados.

A página de downloads informa URL e tamanho, mas não apresenta um digest
diretamente. Sem hash confiável, o adapter permanece `blocked-with-cause` e não
entra no lockfile.

O engine atual possui extração segura para payload declarado em ZIP. Como o
SharpEmu publica `tar.gz`, o primeiro contrato compartilhado é ampliar o engine
para tarballs com:

- allowlist de um único payload executável;
- rejeição de caminho absoluto, traversal, symlink e hardlink;
- limite de bytes e membros;
- hash do artefato e do payload separados;
- staging, verify, repair, rollback e idempotência;
- origem preservada até a confirmação da operação.

O updater interno do SharpEmu não será acionado. Atualização e rollback serão
controlados exclusivamente pelo ciclo SteamZero:

```text
scan → plan → validate → apply → verify → publish
```

## 4. Organização dos jogos e formatos

Raiz recomendada:

```text
roms/
└── ps5/
    └── Nome do jogo/
        ├── eboot.bin
        ├── sce_sys/
        │   └── param.sfo (ou param.json em dumps convertidos)
        └── módulos e dados do dump
```

| Conteúdo | Classificação | Comportamento |
|---|---|---|
| pasta com `eboot.bin` | `ps5dir` / base | candidato de jogo após preflight |
| `.elf` reconhecido | `ps5dir` / base | candidato apenas com identidade PS5 |
| `sce_sys/param.sfo` | metadado canônico | Title ID, título, versão e região quando observáveis |
| `sce_sys/param.json` | metadado declarativo de fallback | Title ID e versão em dumps extraídos/convertidos; só é aceito com `eboot.bin` |
| `prx`, `sys_module` | auxiliar | nunca criar jogo separado |
| outros `.bin` | auxiliar/desconhecido | não tratar extensão genérica como executável |
| `.pkg` | `unsupported` ou `needs-extraction` | não prometer suporte sem parser e teste real |
| `.zip`, `.7z`, `.tar.gz` de jogo | `needs-extraction` | inspecionar com segurança; origem não é alterada |
| dump incompleto | `content-incomplete` | mostrar causa e próximo passo |
| origem ausente | `source-missing` | preservar registro e revalidar depois |

O scanner deve ser orientado pela estrutura e pelos nomes de entrada, não por
qualquer arquivo `.bin`. `eboot.bin`, módulos e arquivos de dados precisam ser
particionados antes da criação do `GameRecord`.

### Base, update e DLC

Não classificar `.pkg` por suposição. A reconciliação base/update/DLC só será
publicada quando houver parser validado, Title ID e versão confiáveis e uma
relação comprovada com a base. Até lá:

- base identificada pode aparecer com estado experimental;
- update/DLC sem semântica comprovada ficam em `needs-user-content` ou
  `unsupported-with-policy`;
- conteúdo criptografado só recebe `encrypted`/`keys-missing` se o runtime
  realmente demonstrar esse requisito;
- firmware e keys não serão declarados por analogia com outra plataforma.

## 5. Preflight e experiência do usuário

Ao selecionar uma pasta, disco removível, SD, USB ou compartilhamento, o fluxo
deve:

1. descobrir a estrutura sem mover arquivos;
2. reconhecer `eboot.bin` e metadados disponíveis;
3. resolver Title ID e identidade estável;
4. calcular hash, tamanho e origem resiliente;
5. verificar arquitetura, Vulkan e driver;
6. consultar compatibilidade pelo título e pela build do SharpEmu;
7. apresentar avisos e bloqueios antes do lançamento;
8. iniciar uma única sessão gerenciada;
9. capturar logs sem segredos ou caminhos sensíveis desnecessários;
10. retornar ao launcher com foco e contexto preservados.

O card do jogo deve mostrar:

- badge `Experimental`;
- status `Nothing`, `Boots`, `Menus`, `Ingame`, `Playable` ou `Not tested`;
- build usada na compatibilidade;
- origem e estado do conteúdo;
- ação concreta para corrigir o bloqueio.

Para PS5, a origem exibida usa somente `sourceIdentity.sourceKind` e
`sourceIdentity.relativePath`; o caminho absoluto nunca é renderizado no card.

Falhas de arte, rede, Vulkan, runtime, permissões ou conteúdo não podem produzir
tela vazia. A ausência de `param.sfo` ou de metadados não deve destruir a
identidade já encontrada; deve reduzir a confiança e explicar a pendência.

## 6. Mídia e limpeza

- associar artwork ao Title ID e à identidade canônica;
- manter `roms/ps5` somente como origem do usuário;
- guardar cache, thumbnails, logs e metadados derivados no State Store;
- não criar entradas para `prx`, módulos, `sce_sys` ou arquivos auxiliares;
- deduplicar por hash sem remover a origem;
- nunca sobrescrever playlist ou artwork editado manualmente;
- exibir fallback tipográfico e ícone de plataforma quando não houver mídia;
- registrar conflitos de edição, região ou Title ID para revisão.

## 7. Ondas de execução

### Onda PS5-0 — contrato e handoff

Criar `SZ-PLATFORM-PS5-CATALOG` e `WS-2026-09-PS5-SHARPEMU`, com branch
`codex/platform-ps5-sharpemu`. Coordenar antes de editar caminhos compartilhados
com os owners de lifecycle de componentes, biblioteca canônica e launcher.

### Onda PS5-1 — supply chain

Fixar asset Linux, hash, commit, licença e payload. Implementar e testar a
extração segura de `tar.gz` no workstream proprietário do engine. Até essa
entrega, o adapter não deve declarar instalação funcional.

### Onda PS5-2 — catálogo e identidade

Adicionar manifesto, adapter, DualSense, asset e catálogo. Implementar o
scanner `ps5dir`, leitura controlada de `param.sfo`/`param.json`, distinção de `eboot.bin` e
particionamento de auxiliares.

### Onda PS5-3 — relações e biblioteca

Adicionar deduplicação, fontes removíveis/rede, arquivos compactados, conteúdo
incompleto e reconciliação base/update/DLC somente onde houver evidência.

O inventário publica `contentState` explícito: `complete`,
`content-incomplete` ou `source-missing`, preservando a causa recuperável no
card sem transformar ausência de `param.sfo`/`param.json` em jogo pronto.

Para preservar a origem entre remontagens, cada entrypoint PS5 também publica
`sourceIdentity` com namespace opaco de volume/compartilhamento, caminho
relativo, tamanho e SHA-256 do entrypoint. O `id` não depende do caminho
absoluto nem do timestamp; falha de hash degrada a identidade sem apagar a
origem.
Se o namespace do volume não puder ser observado, a identidade degrada para
`unknown-namespace` e não deriva nenhum token do caminho absoluto.

Diretórios `updates` e `dlc` são classificados como conteúdo auxiliar e só
entram na base quando a associação nominal é única; sem base correspondente,
permanecem fora dos jogos lançáveis e contam como conteúdo não associado.

### Onda PS5-4 — preflight e launch/return

Integrar seleção de executável, validação Vulkan, sessão gerenciada, captura de
logs, retorno ao launcher, restauração de foco e recuperação de processo.

### Onda PS5-5 — mídia e UX

Adicionar card experimental, compatibilidade por build, filtros, fallback de
artwork e mensagens de bloqueio. Não promover Theme Engine, Theme Studio ou
AURA Launcher por consequência desta integração.

O snapshot empacotado em `src/steamzero/adapters/ps5_compatibility.json` é
fixado ao commit do site oficial e mantém o estado `unknown` quando o relatório
é de outra build ou outro sistema operacional. Nenhum resultado Windows/macOS
é promovido automaticamente para o host Linux.

### Onda PS5-6 — validação e release

Executar os cinco gates do projeto, gerar release somente de fonte commitada e,
com autorização explícita do operador, instalar no host e validar um dump legal
real. A prova física deve capturar sucesso, erro controlado e recuperação quando
aplicável.

## 8. Critérios de aceite

- fonte oficial com hash, licença, commit e payload verificáveis;
- install/update/verify/repair/rollback/uninstall idempotentes;
- tarball malformado ou malicioso rejeitado sem tocar a origem;
- pasta PS5 reconhecida sem transformar módulos em jogos;
- `.pkg` não promovido sem suporte comprovado;
- identidade estável em disco removível e rede;
- base/update/DLC com estado explícito, nunca inferido silenciosamente;
- preflight bloqueia host sem Vulkan ou runtime ausente com causa recuperável;
- uma única abertura do processo e retorno ao mesmo foco;
- compatibilidade sempre vinculada à build exata;
- testes legais e sintéticos cobrindo sucesso, erro e recuperação;
- evidência PNG da release instalada antes de qualquer estado `verified-hw`;
- nenhum P0 é promovido por causa desta capacidade isolada.

## 9. Dependências e bloqueios conhecidos

| Dependência | Tipo | Ação |
|---|---|---|
| suporte seguro a `tar.gz` | técnica/ownership compartilhado | handoff ao lifecycle de componentes |
| SHA-256 do asset oficial | supply chain | obter e registrar antes do lockfile |
| parser `param.sfo`/Title ID | domínio | coordenar com biblioteca canônica |
| GPU Vulkan e driver | host | somente diagnóstico e prova física |
| dump PS5 pertencente ao operador | conteúdo | nunca fornecer, mover ou baixar |
| autorização para instalar/validar host | externa | aguardar operador |
| compatibilidade baixa do upstream | produto | manter estados experimentais explícitos |

## 10. Evidências esperadas

As evidências do item devem ficar em um diretório próprio, com pelo menos:

- `01-baseline.png` — estado antes da integração;
- `02-entrega-funcional.png` — card/lançamento na release instalada;
- `03-recuperacao.png` — erro controlado e retorno recuperado, quando aplicável;
- manifesto de hashes, versão, origem e hardware;
- relatório de contagem de arquivos, bytes, symlinks e não classificados;
- resultado dos testes e dos cinco gates.

Sem runtime, conteúdo legal, autorização ou hardware, o resultado deve ser
`blocked-with-cause`, nunca sucesso presumido.
