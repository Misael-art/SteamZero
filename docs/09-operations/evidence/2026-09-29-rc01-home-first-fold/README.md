# Evidência do lote RC-01 / primeira dobra da Home (2026-09-29)

Frente: `WS-2026-09-RC01-HOME-FIRST-FOLD`, branch `codex/rc01-home-first-fold-2026-09-29`,
base `2d6a8957` (ponta do PR #245), **oitavo elo** da pilha #239 → #240 → #241 → #242 →
#243 → #244 → #245. Item normativo: `SZ-UI-DESKTOP-AUDIT`; eixo tocado: a própria
superfície da Home sob as três superfícies de atenção (faixa de fase, banner, cartão de erro).

Conteúdo funcional: `8a93b01a` (harness + gate desta frente, caminhos exclusivos),
`ace01c30` (`ErrorCard.qml`, arquivo compartilhado isolado em commit próprio, AGENTS.md §2),
`da218e36` (`Main.qml`, idem) e `c2bae146` (**reconfrontação de 56 citações de número de
linha em seis arquivos**, cinco deles de outras frentes — confissão explícita abaixo).

## O que o lote entrega

1. **Medição do pior caso alcançável, não do pior caso imaginado.** A nota de 26/09
   (`2026-09-26-rc01-central-loading/README.md` §"Ressalva de experiência") cortava 209 px
   de chrome e alegava `bridgeUnavailable` **junto** de dados reais — combinação que os
   bindings de produção não alcançam, porque `apiUrl`/`apiToken` vêm de argumento na
   inicialização (`Main.qml:901`-`:908`); sem eles não há leitura bem-sucedida, logo
   `desktopTruthNeedsAttention` (`:339`) e `hasConflicts` (`:334`) ficam falsos e o banner
   não acende. Medido com o argv da produção: o que a produção **sim** empilha corta
   **264 px** dos 698 da cena quieta, e os alvos do cartão têm **36 px**.
2. **Contrato da dobra, estreito e verificável:** o primeiro alvo acionável da Home
   (`overview.open-library`) tem de caber **inteiro** na dobra em 100 % e em 150 %, no pior
   caso alcançável. Não alega que `Pendências` caiba — isso é decisão de arquitetura da Home
   e está registrado como pendência.
3. **Correção pela via do agregado, não pelo corte de conteúdo:** um `/status` recusado
   anuncia o mesmo fato em duas superfícies (`request()` → callback de erro **e** `pushError`).
   A faixa é a persistente; o cartão que reporta o **mesmo código** entra em forma compacta e
   leva a prosa de orientação para trás do "Ver detalhes", que já existia. Alvos do cartão
   de 36 → 48 px, o mínimo já contratual dentro do shell (UX-05/UX-07).

Geometria antes/depois, cena a cena, está no `48-reconcilio-do-criterio-dobra.md`. Resultado
medido: cartão 135/164 → **76 px**, agregado 264 → **205 px**, primeiro alvo terminando em
449 px (100 %) e 468 px (150 %) dentro de uma banda visível de **493 px** — `cabe=SIM` nas
quatro cenas do gate.

## Vermelho meu, vermelho do produto

O gate foi escrito antes da correção e reproveu 5 de 8 verificações com **defeito do
próprio harness** (`36`), depois 5 de 8 com defeito real do produto (`38`). Depois da
correção ele ainda reprovou uma vez, e a causa era minha: a asserção codificava um piso de
`ceil(3·11·escala) = 33 px` que eu derivei de um palpite de linha, e a referência medida em
`45` mostra o cartão estendido a 107 px com 198 caracteres — dois rótulos ("Ação automática",
"ID da operação") chegam **vazios** nesta cena e ficam ocultos nos dois estados. O vermelho
era do modelo do teste, não do produto (`41`). A correção **fortaleceu** a asserção: agora a
forma compacta expandida é comparada com a forma estendida do mesmo cartão (igualdade de
altura, de rótulos visíveis e de caracteres visíveis), que é o que "compactar não é apagar"
quer dizer. Nenhum teste foi enfraquecido ou deletado (AGENTS.md §6).

Duas outras falhas minhas ficaram registradas: altura lida no mesmo tick do clique
(`clickTick + 2` resolveu) e leitura de prosa filtrada por `contentItem`, que o
`QQuickLabel` não expõe a JS — provado pelo dump de árvore em `44` (`temCI=0`).

## Arquivos

| arquivo | conteúdo |
|---|---|
| `34-sonda-geografia-dobra.log` | a primeira sonda de geografia (escala 100 % e 1.5), ainda com argv próprio — antes de perceber que ele não era o da produção |
| `36-gate-primeiro-vermelho-harness-com-defeito.log` | `FFFFFFF.` — o vermelho era do harness (árvore de walk errada e altura no tick errado) |
| `37-matriz-dobra-medida.log` | matriz das quatro cenas no argv errado |
| `38-gate-dobra-vermelho-real.log` | `5 failed, 3 passed` — o defeito do produto medido: alvos de 36 px e banda de 434/405 px |
| `39-matriz-dobra-argv-producao.log` | a mesma matriz com o argv da produção (o `subprocess.Popen` de `launch_desktop_ui()` em `adapters/desktop_ui.py`): 264 px de chrome, `cabe=NÃO (+15)` e `(+63)` |
| `40-matriz-dobra-pos-correcao.log` | depois da correção: `scroll_h` 493/560, cartão 76 px, alvo 48 px, `cabe=SIM` nas quatro cenas |
| `41-gate-modelo-de-altura-reprovou.log` | `........F.F..` — o falso vermelho do meu modelo de 33 px |
| `42-sonda-alturas-expansao.log` | alturas compacta/expandida por cena |
| `43-sonda-prosa-varredura-vazia.log` | a varredura que devolvia `prosa_itens=0` (filtro por `contentItem`) |
| `44-sonda-arvore-do-cartao.log` | dump `SONDA\|` da árvore do cartão — prova de que `QQuickLabel` não expõe `contentItem` a JS |
| `45-drv-sonda-testemunhas.py`, `45-sonda-referencia-forma-estendida.log` | a referência medida: `cartao_expandido_h == cartao_referencia_h` (107/143) e 198 caracteres nos dois estados |
| `46-pytest-verde.log` | verde do gate: `13 passed in 107.76s` |
| `47-drv-bateria-de-mutacoes.py`, `47-gate-verde-e-bateria-de-mutacoes.log` | M1 (`cardDuplicaAFaixa` sempre falso: 5 reprovações, e o passo de medição dele gera a atribuição por arquivo do `48`), M2 (prosa não volta: 3), M3 (alvo a 36 px: 3), M4 ("Ver detalhes" some em compacto: 6); árvore restaurada byte a byte (`b682f286…`, `281215854ac35f4a…`) |
| `48-reconcilio-do-criterio-dobra.md` | o critério nas cinco camadas + atribuição por arquivo (o que cada mudança comprou) + limite declarado |
| `49-tres-portas-pos-citacoes.log` | `42 passed in 194.61s` nos três gates envolvidos pela reconfrontação de citações, com `real-state` antes/depois idêntico |
| `50-nextaction-verbatim-sz-ui-desktop-audit.md` | o texto integral que estava no cartão normativo antes de encurtá-lo (909 caracteres agora, 1 341 preservados), conferido byte a byte contra `git show HEAD:…` na cabeça `c2bae146` |
| `51-atribuicao-digests.py`, `51-atribuicao-digests.log` | `make status-check` reprovou 11 itens; a atribuição por arquivo mostra que **todos os 11** têm arquivo desta frente no escopo — 9 com um só (`Main.qml` ou `ThemeEditorPanel.qml`), o `SZ-THEME-ENGINE` com 3 e o `SZ-UI-DESKTOP-AUDIT` com 11 — e **0** itens acusados sem causa desta frente. `rc=0` |
| `52-gates-integrais.sh`, `52-comandos-e-saidas.log`, `52-comandos-e-saidas.log.rc` | o checkpoint dos sete gates na árvore congelada `e7167080`: sete passos `rc=0`, integral `6520 passed, 47 skipped in 2240.73s`, gate visual `375 passed, 6192 deselected in 1594.46s`, identidade impressa antes e depois de **cada** passo |
| `53-auditoria-de-citacoes.md` | a auditoria que achou as quatro citações falsas do `desktop_ui.py`, com o texto falso preservado na tabela e a linha real onde cada trecho do argv mora hoje |
| `55-revalidacao-proporcional.sh`, `55-revalidacao-proporcional.log` | a revalidação proporcional pós-correção de citações: format/check/mypy `rc=0`, gate afetado `13 passed in 115.05s`, e o `status-check` **reprovando** porque os arquivos deste lote ainda não estavam no digest renovado — a causa, não um resultado escondido |

**Redação aplicada no arquivamento (AGENTS.md: não redistribuir caminhos pessoais):** o
prefixo do checkout virou `<checkout-canônico>` e a pasta temporária de fora do checkout virou
`<tmp-fora-do-checkout>`. Foram 1 linha no `45-drv-sonda-testemunhas.py`, 1 no
`47-drv-bateria-de-mutacoes.py` e 5 no `47-gate-verde-e-bateria-de-mutacoes.log`; nenhuma linha
de resultado, contagem ou veredito foi tocada. Antes da redação os dois arquivos do `47` tinham
sha256 `1f0f365f…` (driver) e `9a8ae855…` (log); depois, `19c94a0a1f81f1ba…` e
`35df52cf41f6c620…`. Os hashes citados abaixo são os **pós-redação**, que são os que um leitor
reproduz sobre o que está commitado.

Na segunda rodada de arquivamento (fechamento, já com o checkpoint rodado) a mesma redação
atingiu 1 ocorrência no `52-gates-integrais.sh` (`d4a14bd972249450…` → `4c37963f8df4232a…`), 3 no
`52-comandos-e-saidas.log` (`64af11708a0f6df2…` → `97cff6cf4c9bffec…`), 1 em cada arquivo do `55`
(`7220f53856169f4f…` → `ed0461d437b6ed9a…` o driver; `8189a4e0c8c1f477…` → `d57a34323b332642…` o
log) e zero em `52-comandos-e-saidas.log.rc` (`f4ff1f6a6aa5cad0…`) e `53-auditoria-de-citacoes.md`
(`bd1c673ac83f5a23…`). Verificação: nenhum `/home/misael` residual nos sete arquivos arquivados.

**Divergência conhecida entre driver e log:** o `47-drv-bateria-de-mutacoes.py` arquivado
(sha256 `19c94a0a…`) difere da versão que produziu o `47-gate-verde-e-bateria-de-mutacoes.log`
(sha256 `35df52cf…`) em **uma linha de rótulo**. Cada mutante roda dois passos — `[gate]`, com
veredito, e `[sonda]`, que só mede. No M1 o passo de medição imprimia
`RESULTADO: VERDE sob a mutação — a asserção NÃO morde`, frase que sugere um gate indiferente
quando o que houve foi um passo sem asserção alguma (o `[gate]` do M1 reprovou 5 verificações,
linhas 11-54 do log). O texto do log conserva a saída como foi impressa; o driver arquivado diz
"passo de medição … sem veredito de gate". Nenhuma asserção, mutação ou veredito mudou.

## A reconfrontação de citações (commit `c2bae146`)

O `Main.qml` deste elo insere 18 linhas antes de `:4139`, e toda citação viva apontando para
depois desses pontos passou a ser um endereço falso. Foram reconfrontados **56 números em 45
linhas de 6 arquivos**, todos em prosa (docstring e comentário), nenhum em asserção:

| arquivo | números | posse |
|---|---|---|
| `tests/integration/test_ui_shell_esde_import_dialog.py` | 6 | WS-2026-09-RC01-SHELL-ESDE-DIALOG |
| `tests/qml/check_shell_esde_import_dialog_journey.qml` | 6 | WS-2026-09-RC01-SHELL-ESDE-DIALOG |
| `tests/integration/test_ui_shell_retrofe_import_late_response.py` | 6 | WS-2026-09-RC01-RETROFE-SHELL-LATE (PR #245) |
| `tests/qml/check_shell_retrofe_import_late_response.qml` | 26 | WS-2026-09-RC01-RETROFE-SHELL-LATE (PR #245) |
| `src/steamzero/ui/qml/ThemeEditorPanel.qml` | 3 | produto compartilhado |
| `tests/integration/test_ui_shell_home_first_fold.py` | 9 | esta frente |

O mapa antigo→novo saiu dos cinco hunks `-U0` do próprio `Main.qml`; cada número só foi
substituído quando o conteúdo da linha nova no HEAD coincidiu, linha a linha, com o conteúdo da
linha antiga na base `2d6a8957` — zero substituições às cegas, zero pulos. Precedente: `690a1b84`
(sétimo elo), mesma regra, mesma confissão.

Também neste push, na pasta do lote anterior:
`2026-09-29-rc01-retrofe-shell-late/32-ci-terminal-pr245-2d6a8957.log` — o CI terminal do PR #245
lido no SHA efetivamente entregue (`2d6a8957`), quatro segmentos de 90 s, `CLEAN` no segmento 4
com `Gate visual QML (Linux)=COMPLETED/SUCCESS`.

## O checkpoint integral (52) e a que árvore ele pertence

Os sete gates de AGENTS §6 rodaram **uma** vez, na árvore congelada `e7167080` com
`git status` vazio sob `src`/`tests`/`tools`; o invólucro imprime branch, HEAD e o sha256 por
conteúdo dos quatro arquivos do corte antes e depois de **cada** passo. Resultado: sete passos
`rc=0`, com `make independence boundaries` e `make status-check` verdes, a integral
`6520 passed, 47 skipped in 2240.73s (0:37:20)` e o gate visual `375 passed, 6192 deselected in
1594.46s (0:26:34)`. As contagens fecham com o sétimo elo (`6507 → 6520` e `362 → 375`): as
**13** verificações a mais são exatamente as deste gate, nenhuma outra apareceu nem sumiu.

**Estes números pertencem a `e7167080` e a mais nada.** Depois do checkpoint este lote ainda
acrescentou arquivos nesta pasta e corrigiu quatro citações; essa segunda árvore **não** é
revalidada pela integral acima, e não é a ela que o commit `6d8034fa…` deve ser atribuído. A
revalidação proporcional da segunda árvore é o `55`, e seu resultado é o que se lê ali — com o
`status-check` reprovando por digest envelhecido **pelos próprios arquivos deste lote**, que é
por que a renovação do digest vem depois e o `make status-check` final é relido na árvore
congelada posterior (registrado no PR, não aqui: escrever aqui envelheceria o digest que ele
certifica).

## A correção das quatro citações falsas

`53-auditoria-de-citacoes.md` registra o achado: as quatro ocorrências de
`adapters/desktop_ui.py:990-:1001` descreviam "o argv da produção", mas esse intervalo é
`stdin=subprocess.DEVNULL`, `env={…}`, o laço de `process.poll()` e `server.server_close()`. O
argv sai do `subprocess.Popen` de `launch_desktop_ui()`. Não é deriva de número de linha causada
pelo `Main.qml` deste elo: a citação já era falsa na base `2d6a8957`, ou seja, foi erro de
escrita meu.

Corrigidas as quatro sedes — docstring de `_rodar()` no gate, cabeçalho do harness QML, linha do
README e texto de evidência do cartão — por **referência ao símbolo** (`o subprocess.Popen de
launch_desktop_ui() em adapters/desktop_ui.py`) em vez de número de linha, que é o endereço que
não envelhece quando o arquivo cresce. A diff dos dois arquivos de teste tem só comentário e
docstring: nenhuma asserção executável foi tocada, então o trecho não é alteração de teste e não
pede revalidação de comportamento além da porta afetada. O `55` roda essa porta: `13 passed in
115.05s`, com format/check/mypy verdes.

## Pendências declaradas (não escondidas)

* **Integração**: nada deste lote está em `main`. `origin/main` continua `3495c49d…` e nenhum
  elo da fileira é ancestral dele. Merge é decisão do operador. Este README descreve a
  situação **antes** do push do oitavo elo.
* **Release instalada**: `2.0.0rc1-e2af2562ebba` (26/09) não contém nada da fileira.
  Experiência comprovada na release instalada continua **zero**.
* **`Pendências` continua abaixo da dobra** no pior caso: `pend_y` = 581 px (100 %) e 597 px
  (150 %) contra banda de 493 px. Meter o cartão de pendências na dobra com as três
  superfícies ativas exige decisão de arquitetura da Home, não deste corte.
* **Nenhuma captura PNG**: toda a geometria vem de testemunhas offscreen;
  `GAP-UI-VISUAL-CAPTURE-NOT-CERTIFIED-IN-CI` segue aberto para esta fatia.
* **Teto agregado é uma constante derivada, não uma lei**: `CAPA_CHROME_AGREGADO = 230` nasce
  de 698 − 468. Se a Home ganhar outra superfície fixa acima do `ScrollView`, o número muda de
  natureza e o gate precisa de reavaliação, não de reajuste.
* **Não tocado por este lote**: seletor nativo de diretório, contrato de geração do ES-DE,
  F-1/F-2 do contrato de prontidão, e as duas divergências de leitura registradas no sétimo elo.
