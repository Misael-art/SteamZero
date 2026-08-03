# P0-03 — Handoff da fatia vertical de texto

**Estado:** fatia vertical fechada de ponta a ponta. **P0-03 NÃO está completo** —
faltam a migração das 388 propriedades do corpus RetroFE e as etapas seguintes.

Este documento existe para que quem continuar não precise reconstruir o
raciocínio a partir dos diffs.

## Commits

| etapa | commit | entrega |
|---|---|---|
| VS-01 (correções) | `5e4b516` | gramática fechada de valor pendente e de handle de asset |
| VS-02 | `f6e0182` | `ResolvedTextNode` → `QmlTextRenderModel` → `SceneText.qml` |
| — | `354b6d6` | `DimensionValue` fechado na construção e no parsing |
| — | `08bb787` | `AdaptationResult`: falha do adapter deixa de ser ignorável |
| — | `f544ca1` | degradação registra valor declarado e valor resolvido |
| **VS-03** | `7850461` | harness de captura QML próprio do projeto |
| — | `16efa46` | reserva de `ClipSpec`/`MaskSpec`/`HitTestShape` (P0-08) |
| — | `639370c` | handles de fonte opacos + regressões de todos os achados do VS-03 |
| **VS-04** | `4faa843` | fatia vertical RetroFE ponta a ponta |
| — | `90dba92` | política de namespace antes da busca no registro |
| **VS-05** | `37e9983` | round-trip semântico, contabilidade e diagnósticos |
| **VS-06** | `b8ba02c` | cache por dependência, invalidação seletiva, lifecycle |
| **VS-06.1** | `76e0ec2` | invalidação de layout dependente de display |
| **VIS-01** | `1d9a52e` | Liberation Sans 2.1.5 empacotada |
| **VS-07** | `6fb2a75` | dez baselines visuais versionadas |

Base: `9109483` (VS-01).

## PR 1 tema default — fundação de cena (2026-08-02)

A primeira PR do tema default (`codex/theme-scene-foundation`) entregou a
fundação do IR sobre a qual a migração das 388 propriedades vai acontecer.
Quatro commits, gates verdes:

| commit | entrega |
|---|---|
| `954f970` | `children` no `ElementContract`, `scene_tree.py` (limites 40/128/4096, ids únicos) e serialização v2 com leitura v1 |
| `6793766` | `DisplaySpec` fechado e bindings `display.*` por eixo com invalidação seletiva |
| `50151db` | `CONTRACT_PROPERTY_TYPES` (44 entradas) como tabela única; registro derivado, sem `content`/`source` fantasmas |
| `e6be003` | auditoria executável da migração (`theme_migration_audit`, `tools/audit_theme_migration.py`) com fidelidade por área |

Com isso, dois itens de "O que falta" abaixo mudaram de estado: a árvore de
cena tem contrato e serialização (item 2) e o display tem estado fechado além
de largura/altura (item 5) — a fatia de texto ainda não os PRODUZ, o que o
gate `test_no_scene_tree_is_introduced` afirma por escolha, não por ausência
de projeto.

A auditoria executável (`python tools/audit_theme_migration.py`) é o corpo do
gate de escopo: relata por área quantas declarações reais têm tradutor e a
lista nominal do que ficou para trás (hoje, nas fixtures, `layer` e `src`).

## O pipeline que está provado

```
arquivo RetroFE
  → declarações com identidade (id estável, arquivo, linha)
  → TranslationLog (exatamente um veredito por declaração)
  → Value<T>  →  ElementContract
  → serialização canônica → desserialização → comparação semântica
  → Resolver (cache por dependência)
  → ResolvedTextNode  →  adapter  →  AdaptationResult  →  require_model()
  → QmlTextRenderModel  →  harness  →  SceneText.qml
  → captura, geometria e métricas
```

Medido nas duas fixtures reais: **65 e 73 propriedades, cobertura 100%, zero sem
julgamento, zero duplicata, zero diferença semântica, zero valor dinâmico
congelado.**

## Decisões que custaram caro e não devem ser revertidas

**A chave de cache olha só as gerações que a propriedade usa.** A versão
anterior incluía todas, e um bump em `tokens` tornava inalcançável o cache de
toda a cena — trocar de idioma recompunha as 65 propriedades.

**Falha do adapter não carrega modelo.** Em `failed` o modelo é `None`. Não
existe payload parcial para um consumidor distraído entregar ao QML.

**Cor inválida não vira transparente.** Transparente é um valor que um tema pode
ter pedido de propósito; usá-lo como marca de erro tornaria os dois casos
indistinguíveis.

**`indeterminate` não escolhe o ramo `otherwise`.** Escolher decidiria sem base
e produziria uma interface plausível e semanticamente errada.

**Default não conta em `sourcePropertyCount`.** Contá-lo faria 100% de cobertura
significar "julgamos tudo que produzimos" em vez de "traduzimos tudo que o autor
escreveu".

**O fontconfig é isolado na fonte empacotada.** Sem isolar, a Liberation Sans do
SISTEMA sombreava a do repositório mesmo com o arquivo certo carregado.

## Armadilhas verificadas na bancada

Cada uma tem teste de regressão. Foram descobertas medindo, não supondo.

| armadilha | por que engana |
|---|---|
| `font.family` ecoa o valor atribuído | família inexistente e real dão o mesmo `font.family` E o mesmo `contentWidth` |
| XHR síncrono em `file://` | trava o runtime sem mensagem nenhuma |
| `grabToImage` no `contentItem` | não captura a cor da `Window` |
| `getbbox()` do Pillow | usa `alpha_only=True`; devolve `None` com centenas de pixels alterados |
| `QT_LOGGING_RULES=*=false` no host | a coleta de warnings verifica o silêncio de um Qt amordaçado |
| RHI sob `offscreen` | não inicializa e NÃO retorna; consome o timeout inteiro |
| Regular e Italic da Liberation | têm largura IDÊNTICA; largura não prova que a face itálica carregou |
| `asset://font/{família}` | quebra com qualquer nome de duas palavras |
| pacote de distro rotulado 2.1.5 | hash diferente do artefato oficial 2.1.5 |

## O que falta para fechar o P0-03

1. **Migração das 388 propriedades** do corpus RetroFE. A fatia cobre texto; o
   corpus tem imagem, som, menu, timeline e eventos.
2. **Árvore de cena.** Hoje a fatia é plana, e um teste reprova se alguém
   introduzir `children` sem projeto.
3. **Rich text, wrapping, elide, auto-fit.**
4. **Acessibilidade** — ver G15: a geração existe, nenhum consumidor real.
5. **Display além de largura/altura** — `safeArea`, `orientation`,
   `devicePixelRatio` e `aspectRatio` estão previstos e não implementados.

## Escopo explicitamente adiado

| item | destino |
|---|---|
| `ClipSpec`, `MaskSpec`, `MaskStack`, `HitTestShape` | P0-08 |
| transições mascaradas | P0-08 |
| gate `visual-rhi` | P0-08 |
| CJK, RTL, fallback por script | entrega de internacionalização |
| migração dos dez harnesses QML legados | `QML-HARNESS-MIGRATION` (G13) |

Testes reprovam se qualquer um deles for introduzido sem a entrega
correspondente. Não são promessas: são afirmações executáveis.

## Como rodar

```bash
make check                    # os quatro gates + cobertura
make qml-visual               # as dez baselines
make check-qml-goldens        # relata divergência visual sem regravar
make update-qml-goldens       # regrava baselines (exige revisão do diff)
python tools/audit_theme_migration.py   # relatório de migração por área
```

O job `qml-visual-linux` do CI nasce sem `continue-on-error`: ambiente sem Qt
reprova com `QML-VISUAL-ENVIRONMENT-001` em vez de produzir verde.
