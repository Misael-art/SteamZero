# 48 — Reconcílio do critério "primeira dobra da Home", nas cinco camadas

Documento deste lote. Não substitui nem edita `2026-09-29-rc01-retrofe-shell-late/29-reconcilio-rc01-cinco-camadas.md`,
que permanece como registro do estado na data em que foi escrito; aqui se lê o estado
**depois** da oitava fatia, com as camadas separadas como exige o item 8 da diretiva.

A linha correspondente naquele reconcílio dizia:

> | Primeira dobra da Home | sim (estrutura em `EditorialHome.qml`) | sim, **com o pior caso medido e não corrigido** | **não** | não | não | **parcial — gap funcional real aberto** | `2026-09-26-rc01-central-loading/README.md` §"Ressalva de experiência" |

## Estado agora, camada por camada

| camada | agora | prova |
|---|---|---|
| interface implementada | **sim** — `ErrorCard.qml` (forma compacta, prosa dentro do cabeçalho, 48 px por alvo) e `Main.qml` (`statusBandFailureCode` + `cardDuplicaAFaixa`) | `40-matriz-dobra-pos-correcao.log` |
| contrato testado offscreen | **sim** — 13 verificações em 4 cenas, argv da produção, testemunhas lidas pelo gate; 4 mutantes mortos | `46-pytest-verde.log`, `47-gate-verde-e-bateria-de-mutacoes.log` |
| código integrado | **não** — o oitavo elo ainda não tem SHA mergeado em `main` | PR aberto, base `2d6a8957` |
| artefato empacotado | **não** — nenhum wheel deste elo | — |
| experiência comprovada na release instalada | **não** — `2.0.0rc1-e2af2562ebba` (26/09) não contém nada da fileira | — |

Ou seja: o gap funcional está **corrigido e provado offscreen**, e o critério continua
**parcial** nas camadas de integração, empacotamento e host. "Corrigido" aqui não significa
"entregue no host".

## O que mudou de fato, medido (não narrado)

| grandeza | antes (`39`) | depois (`40`) | fonte |
|---|---|---|---|
| banda visível da Home, atenção máxima 100 % | 434 px | **493 px** | `scroll_h` |
| banda visível, atenção máxima 150 % | 405 px | **493 px** | `scroll_h` |
| altura do cartão de erro | 135 / 164 px | **76 px** compacto | `cartao_h` |
| alvo "Exportar diagnóstico" | 36 px | **48 px** | `cartao_alvo_h` |
| chrome de atenção agregado | 264 px | **205 px** | 698 − `scroll_h` |
| fim do primeiro alvo vs. dobra (100 % / 150 %) | 449 > 434 / 468 > 405 | 449 ≤ 493 / 468 ≤ 493 | `primeiro_y + primeiro_h` |

A premissa da nota de 26/09 também foi corrigida por leitura: ela forçava
`bridgeUnavailable` junto de dados reais, combinação que os bindings de produção não
alcançam (`apiUrl`/`apiToken` vêm de argumento na inicialização). O pior caso **alcançável**
é faixa de fase + banner + cartão pelo mesmo código da renovação recusada — e ele corta
**264 px**, não os 209 px daquela nota.

## Atribuição por arquivo: o que cada mudança comprou

Medido sob o mutante M1 (`cardDuplicaAFaixa` sempre falso — `ErrorCard.qml` já reorganizado,
compactação nenhuma), no log `47`:

| cena | cartão | banda | fim do 1º alvo | cabe? |
|---|---|---|---|---|
| atenção 100 % | 89 px | 480 px | 449 px | **sim** |
| atenção 150 % | 118 px | 451 px | 468 px | **não — 17 px fora** |
| sem dados | 89 px | 547 px | 449 px | sim |

* A reorganização do `ErrorCard.qml` (prosa dentro do cabeçalho + 48 px por alvo) leva o
  cartão de 135 → 89 px e **fecha a dobra a 100 % sozinha**.
* A regra de compactação do `Main.qml` leva 89 → 76 px (100 %) e 118 → 76 px (150 %), e é
  **ela** que fecha a dobra a 150 % — sem ela o teto agregado (230 px) também reprova, com
  247 px medidos.

Publicar "a dobra foi corrigida" sem essa separação seria atribuir à regra nova um resultado
que, a 100 %, já veio do rearranjo. A 150 %, nenhuma das duas isoladas basta.

## Limite declarado, não conquistado

* **`Pendências` continua abaixo da dobra** no pior caso: medido `pend_y` = 581 px (100 %) e
  597 px (150 %) contra banda de 493 px. Este lote alega apenas o **primeiro alvo acionável
  inteiro na dobra**; meter o cartão de pendências na dobra com as três superfícies ativas é
  decisão de arquitetura da Home, não deste corte.
* **Nenhuma captura PNG** — a geometria vem de testemunhas offscreen (`qml6` + `QT_QPA_PLATFORM=offscreen`).
* **Prosa que some não é dobra**: verificada por igualdade com a forma estendida do mesmo
  cartão (`45`: 107 px == 107 px, 198 caracteres == 198, 6 rótulos == 6). Os dois rótulos que
  seguem ocultos nos dois estados ("Ação automática", "ID da operação") chegam **vazios**
  nesta cena, e é por isso que a asserção é contra a referência, não contra um piso de píxeis.
* O seletor nativo de diretório, a cauda de latência do `/status`, o contrato de geração do
  ES-DE e F-1/F-2 da prontidão seguem abertos e não são tocados por este lote.
