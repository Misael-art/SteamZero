# RC-01 — Central legível e utilizável durante o carregamento (2026-09-26)

Workstream `WS-2026-09-RC01-CENTRAL-LOADING`, item `SZ-UI-DESKTOP-AUDIT`, frente
`codex/rc01-central-loading-2026-09-26`. Registro da frente: `64932141a276`.
Release instalada no host no momento das medições: `2.0.0rc1-e2af2562ebba` — nenhuma
evidência aqui é prova dessa release: as mudanças desta pasta não foram empacotadas
nem instaladas.

## Escopo medido

UX-02 (o primeiro frame da Central afirmava ausências que nunca foram medidas; a
consulta `GET /status` demorava sem nenhum estado visível) e UX-01 na parte
calculável (avisos sobre superfícies fixas escuras com tinta do tema), mais a
regra de renovação do `GET /status` pedida durante uma mutação (UX-02/`timeout/retry
sem corrida`).

**Isto é uma fatia de RC-01, não RC-01 inteiro.** Do enunciado do roadmap
(`docs/12-roadmap/IMPLEMENTATION-ROADMAP.md:38`) ficam **pendentes** e sem prova
aqui: a cauda de latência (~11,4 s, dominada por `emulation`), a experiência dos
alertas empilhados na dobra de 800 px, a validação física na release instalada, e
os itens UX-03/UX-04/UX-05/UX-07 — prontidão compreensível, unidades de
armazenamento legíveis, foco/scroll em viewport compacto e o modal RetroFE
completo. Nada neste lote promove esses pontos.

## Artefatos

| Arquivo | O que é |
| --- | --- |
| `01-baseline-status-probe.log`, `status-probe-baseline.json` | `GET /status` contra a bridge do produto, 5 consultas, antes da correção de custo |
| `02-final-status-probe.log`, `status-probe-final.json` | mesmas 5 consultas, mesma metodologia, depois |
| `03-contraste-antes.log` | harness de contraste rodando contra a árvore anterior à correção |
| `04-contraste-depois.log` | mesmo harness, árvore da entrega |
| `05-carregamento-antes.log` | harness de fases rodando contra `Main.qml`/`EditorialHome.qml` de `64932141a276` |
| `06-carregamento-depois.log` | mesmo harness, árvore da entrega, com os dois quadros |
| `07-suite-integral.log` | checkpoint integral (`run_tests_isolated.py tests -q`) e a fotografia do estado real do operador; carrega uma `RETIFICAÇÃO` de 2026-09-27 sobre duas afirmações do cabeçalho |
| `08-duas-suites-concorrentes.log` | conciliação das **duas suítes integrais simultâneas** no mesmo checkout: proveniência, sobreposição de 17 min 53 s, o que cada uma testou e a perda dos logs brutos no reboot. Renomeado em 2026-09-27 de `08-suítes-concorrentes.log`: o gate de posse de `tools/project_status.py` não desescapa nome não-ASCII (`core.quotepath`) e reprova ao versionar — limitação registrada, não corrigida nesta fatia |
| `09-refresh-coercido.log` | o refresh descartado por uma leitura em andamento (`Main.qml:1103`): vermelho, correção, verde, sonda de não-vacuidade e mudança de contrato declarada |
| `10-refresh-red-bruto.log` … `13-gates-focais-bruto.log` | saídas brutas do passo anterior, sem edição, com md5 registrado em `09` |
| `14-contraste-politica-normativa.log` | os números do contraste conferidos contra a **política normativa** (`ACCESSIBILITY.md:8`, `THEME-ENGINE-AND-STUDIO.md:309`), não contra o piso que o teste escolheu |
| `15-checkpoint-integral-bruto.log` | saída verbatim da suíte integral do checkpoint de 2026-09-27, com pré-lançamento, janela, `rc` e os dois fingerprints do estado real do operador |
| `16-tentativa-1-pre-flight.log` | o lançamento que não chegou a rodar (`/usr/bin/time` inexistente, `rc=127`) e o pré-lançamento que casava o próprio invólucro |
| `17-gates-rapidos-bruto.log` | as duas passadas dos gates rápidos: a 1ª com as duas violações de lint no código do lote, a 2ª verde, mais a validação de status reexecutada (69 passed) |
| `18-checkpoint-integral.log` | o registro do checkpoint: o que rodou, a falha atribuída e reproduzida, o que a corrida cobre e o que ela não cobre |

| `quadro-carregando.png`, `quadro-nao-renovado.png` | 1280×800 capturados pelo próprio harness offscreen |


O instrumento é `tools/central_status_probe.py` (contratos em
`tests/unit/test_central_status_probe.py`). Ele existe porque o "14,26 s e 3,2 MB"
registrado em UX-02 veio de uma captura improvisada: sem comando refazível, o número
não sustenta nem um "antes" nem um "depois".

## Latência — o que a medição diz, e até onde ela vai

Comando (idêntico nos dois logs, mudando apenas `--role`):

```
.venv/bin/python tools/central_status_probe.py --repeats 5 --role baseline \
  --outdir docs/09-operations/evidence/2026-09-26-rc01-central-loading
.venv/bin/python tools/central_status_probe.py --repeats 5 --role final \
  --outdir docs/09-operations/evidence/2026-09-26-rc01-central-loading
```

| | antes | depois |
| --- | --- | --- |
| p50 | 8 944 ms | 6 432 ms |
| p95 / max | 11 709 ms | 11 409 ms |
| corpo p50 | 3 131 KiB | 3 131 KiB |
| `themeState` | 4 100,2 ms/consulta | 413,3 ms/consulta |
| `emulation` | 3 867,1 ms/consulta | 5 106,6 ms/consulta |
| não atribuído | −385,2 ms/consulta | 38,4 ms/consulta |

O que a correção toca é o bloco `theme`: compilar o validador do manifesto uma vez
por processo em vez de rechecar o schema empacotado a cada manifesto (305 ms por
manifesto medidos na ponte) e trocar o despejo de `str(ValidationError)` por
`json_path: mensagem` limitado a 400 caracteres. A instância do manifesto continua
validada do mesmo jeito, com a mesma primeira falha — isso está preso em
`tests/unit/test_themes.py`.

Limites honestos desta comparação:

* **cinco amostras são exploratórias, não evidência estatística de cauda.** Com
  n = 5 o "p95" é o próprio máximo ordenado — um ponto, sem intervalo. O que a
  tabela sustenta é "a mediana baixou 2 512 ms nesta série" e "a cauda continua
  da ordem de 11 s"; qualquer afirmação de percentil precisa de n maior e de
  ensaio controlado, e nada aqui a faz;
* as duas corridas (baseline e final) rodaram **sobrepostas a uma segunda suíte
  integral** no mesmo checkout (ver `08-duas-suites-concorrentes.log`). Isso contamina
  a *medição de tempo*, não a correção dos contratos: os números de latência
  abaixo são, portanto, pior-case de carga concorrente, e a diferença entre as
  duas séries não pode ser atribuída só ao código;
* a queda é do **p50** (2 512 ms, ~28 %). O p95 mal se moveu (11 709 → 11 409 ms)
  porque a cauda é dominada por `emulation`, que a RC-01 não tocou e que **subiu**
  1 239,5 ms/consulta entre as duas execuções;
* as duas execuções são sequenciais no mesmo host vivo, não um ensaio controlado.
  A variação de `emulation` entre elas mostra que o ruído do host é da ordem de
  segundos; o que sustenta a atribuição é a queda local do bloco `theme`, que
  mudou de forma desproporcional a qualquer ruído plausível;
* o "não atribuído" de −385,2 ms na baseline significa que a soma das atribuições
  excedeu o tempo medido (envoltórios aninhados contando duas vezes). A aritmética
  é a mesma nos dois relatórios, e por isso ele fica impresso, não escondido;
* nenhuma rota de mutação foi exercida **pelo probe de latência** — ele só lê
  `GET /status`. O inquérito de estado antes/depois de cada corrida registrou a
  árvore intacta (12 818 arquivos; bytes totais 1 372 737 639 → 1 372 739 007,
  acréscimo de 1 368 bytes produzido pelo próprio host entre as duas corridas, não
  pelo probe — o probe compara a árvore antes e depois de cada corrida, e cada log
  afirma "estado intacto: sim" para a sua). Uma mutação volta a ser exercida em
  `09-refresh-coercido.log`, e lá é contra a **ponte de teste** com carga
  sintética, nunca contra o acervo real do host.

## Estado da Central — o contrato comportamental

`tests/qml/check_central_loading.qml` atraveta as fases `loading → ready → stale →
ready` contra uma ponte que atrasa a primeira consulta, devolve `E-STATUS-SCENE` na
segunda e recupera na terceira, e depois sonda a regra de sobreposição no fim da
cena (ver abaixo): são **cinco** leituras e sete fases. São 43 contratos na captura
de carregamento e 42 na de estado não renovado. O gate pytest é

```
.venv/bin/python tools/run_tests_isolated.py tests/integration/test_qml_handheld_offscreen.py -k central_loading -q
```

→ 3 passed em 11,98 s na cena de fases e nos dois quadros capturáveis (estes
marcados `visual`). Depois da coerção de refresh, o mesmo seletor mais o novo
harness — `-k "central_loading or mutation_refresh"` — fecha
`6 passed, 50 deselected em 15,85 s`, com a contagem de leituras da ponte regravada
de 3 para 5: mudança de contrato declarada em `09-refresh-coercido.log` §5, não um
teste enfraquecido.

`05-carregamento-antes.log` é a prova de que a cena não é vazia: executada contra os
dois arquivos de `64932141a276`, ela reprova com rc=1 (a API de fase não existia) e
não grava nenhum quadro. A árvore anterior foi obtida por `git show HEAD:<caminho>`
com md5 conferido antes e depois; o script auxiliar morou fora do checkout
(`/tmp/rc01_revert_*.py`, `/tmp/rc01_capture_antes.sh`) e não foi versionado — a
reprodução usa o próprio `git show`, descrito nos cabeçalhos dos logs.

## Renovação coercida — uma mutação nunca perde o estado novo

`Main.qml:1103` (antes) devolvia cedo quando `statusInFlight`: qualquer renovação
pedida enquanto uma leitura rodava era **descartada** — inclusive a que vem depois
de uma mutação, que é exatamente o caso em que o operador espera ver o resultado do
que acabou de fazer. Reprodução determinística, sem aposta em tempo: a ponte de
teste segura a leitura #2 aberta até o harness confirmar que a mutação
(`POST /emulation/library/scan`) chegou, e então responde com o payload antigo. O
log de sequência da ponte é a prova; o harness exige leitura #3 com o estado pós
-mutação. Vermelho (`3 failed`), correção, verde (`3 passed`), e a sonda de
não-vacuidade (injetar `return` em `drainStatusRefresh()` → `3 failed` → reverter,
`diff -q` idêntico) em `09-refresh-coercido.log`, com as saídas brutas em
`10`–`13`.

A correção é um slot único (`statusRefreshQueued`): dez mutações durante uma leitura
lenta viram **uma** relênia, não dez, e o dreno roda nos dois callbacks — o sucesso
e a falha da leitura em andamento — para não perder retry nem o estado
`stale`/`error`. Coberto nas três cenas (sucesso, leitura em andamento falha,
renovação falha).

## Contraste — causa calculável, tratada como calculável

`03-contraste-antes.log`: 44 verificações, 37 falhas, exit 3. `04-contraste-depois.log`:
44 verificações, 0 falhas, exit 0. A causa não é opinião sobre a captura: os
parâmetros de `Main._relativeLuminance/_contrastRatio/_contrastTextColor` não eram
tipados como `color`, então uma superfície literal `"%24180b"` chegava como texto, a
luminância dava `NaN`, toda comparação falhava em silêncio e a função devolvia a
própria cor de fundo do tema — escuro sobre escuro. O harness executa a função real;
`tests/unit/test_ui_attention_surface_contrast.py` prova a regra contra os tokens dos
quatro temas empacotados e reprova se algum dia uma cor fixa servir para todos.

Um quarto ponto de contorno foi encontrado lendo o quadro capturado, não o código: o
botão "Tentar novamente" da faixa de fase herdava a tinta escura do tema claro sobre
a faixa escura e media 1,06:1. A asserção que o trava está na fase `stale` do harness
de fases e foi provada por mutação (remover a linha reprova com a razão exata;
repor aprova).

### Conferido contra a política normativa, não contra o piso do teste

O teste impõe 4,5:1 (`WCAG_AA_NORMAL`) para os temas regulares, mas a norma escrita
do projeto é outra: `docs/07-ui-ux/ACCESSIBILITY.md:8` pede razão **≥ 7:1 para texto
essencial** no tema de alto contraste, e `docs/01-product/THEME-ENGINE-AND-STUDIO.md:309`
repete "contraste essencial ≥7:1 ou política aprovada equivalente" — sem ata que
adote a equivalente. `14-contraste-politica-normativa.log` mede os números reais:

* **o que esta entrega afirma passa na norma:** os 24 pares (4 temas empacotados ×
  6 superfícies fixas de aviso) caem entre **12,67:1 e 16,50:1**, e o alto contraste
  (branco puro do `ThemeBridge` sobre as mesmas superfícies) entre **15,12:1 e
  19,49:1** — zero pares abaixo de 7:1, muito acima do piso de 4,5:1;
* **o que a norma ainda não cobre, e não foi este lote que criou:** dos 32 pares
  semânticos (`success`/`warning`/`danger`/`textMuted` sobre `surface`,
  `surfaceRaised`, `background`), **28 ficam abaixo de 7:1**, pior valor **4,99:1**
  (`#167a45` sobre `#f4f7f5` nos três temas claros). O docstring do teste chama esse
  texto de "essencial", o que conflita com as duas linhas normativas acima;
* a decisão (adotar 4,5:1 formalmente, ou subir os tokens dos temas para ≥7:1) é de
  produto, não deste lote. **Nenhum comportamento de tema foi alterado aqui** — fica
  registrado como pendência documental/experiência, sem agrupar mudança não
  relacionada.

## Ressalva de experiência registrada, sem correção neste lote

No cenário de atenção máxima (faixa de fase + banner de perfil + cartão de falha ao
mesmo tempo), as três superfícies escuras empurram "Pendências" e "Recentes" para
baixo da dobra em 800 px de altura. É o pior caso, não o caminho comum; fica como
pendência de revisão de experiência e nenhum comportamento foi alterado por causa
disso nesta batch.

## Checkpoint integral de 2026-09-27

`15-checkpoint-integral-bruto.log`: **`1 failed, 6397 passed, 47 skipped em 1815,74 s`,
rc=1** — uma execução só, log gravado fora do checkout, e o state home real do operador
idêntico antes e depois (12 816 arquivos / 2 068 diretórios / 1 372 712 391 bytes /
mesmo `max_mtime_ns`). A falha é de consistência do catálogo
(`test_committed_catalog_and_generated_views_are_consistent`), foi atribuída a um erro de
ordem meu — renovei os `scopeDigest` e *depois* `ruff format` reescreveu um arquivo que
está no escopo dos seis itens apontados — e resolvida pelo caminho que `AGENTS.md` §6
abre para digest/visão envelhecidos: regenerar pela ferramenta e reexecutar a validação
aplicável (`69 passed em 61,20 s`, em `17-gates-rapidos-bruto.log`). Nenhuma outra falha
existia para virar flake. `18` discrimina o que a corrida cobre do que ela não cobre.

## O que estas evidências NÃO provam

Nada aqui é prova de release instalada, gesto físico ou sessão do operador: os
quadros vêm do `QT_QPA_PLATFORM=offscreen` de uma ponte de teste local, com dados
sintéticos. A latência é real, medida na bridge do produto sobre o estado do host,
mas em 5 consultas consecutivas de um processo de laboratório, não no app empacotado
— e essas duas corridas decorreram sob a carga de uma segunda suíte integral
simultânea, o que as torna inadequadas como estimativa de tempo (`08`).

O contrato de renovação coercida é provado no **modelo** que alimenta o rótulo da
linha visível (geração do payload, `statusStale`, faixa de fase, contagem de
confirmações e de consultas em voo), não em pixels; cobre uma rota de mutação
(`library.scan`) e um teto **estrutural** — um slot de coalescência —, não um teto
estatístico de carga. Nada aqui declara isolamento global do host: `08` registra a
concorrência encontrada, o que ela invalida e o que não.
