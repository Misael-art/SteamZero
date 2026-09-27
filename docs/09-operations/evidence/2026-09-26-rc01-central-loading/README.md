# RC-01 — Central legível e utilizável durante o carregamento (2026-09-26)

Workstream `WS-2026-09-RC01-CENTRAL-LOADING`, item `SZ-UI-DESKTOP-AUDIT`, frente
`codex/rc01-central-loading-2026-09-26`. Registro da frente: `64932141a276`.
Release instalada no host no momento das medições: `2.0.0rc1-e2af2562ebba` — nenhuma
evidência aqui é prova dessa release: as mudanças desta pasta não foram empacotadas
nem instaladas.

## Escopo medido

UX-02 (o primeiro frame da Central afirmava ausências que nunca foram medidas; a
consulta `GET /status` demorava sem nenhum estado visível) e UX-01 na parte
calculável (avisos sobre superfícies fixas escuras com tinta do tema).

## Artefatos

| Arquivo | O que é |
| --- | --- |
| `01-baseline-status-probe.log`, `status-probe-baseline.json` | `GET /status` contra a bridge do produto, 5 consultas, antes da correção de custo |
| `02-final-status-probe.log`, `status-probe-final.json` | mesmas 5 consultas, mesma metodologia, depois |
| `03-contraste-antes.log` | harness de contraste rodando contra a árvore anterior à correção |
| `04-contraste-depois.log` | mesmo harness, árvore da entrega |
| `05-carregamento-antes.log` | harness de fases rodando contra `Main.qml`/`EditorialHome.qml` de `64932141a276` |
| `06-carregamento-depois.log` | mesmo harness, árvore da entrega, com os dois quadros |
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
* nenhuma rota de mutação foi exercida; o inquérito de estado antes/depois de cada
  corrida registrou a árvore intacta (12 818 arquivos; bytes totais 1 372 737 639 →
  1 372 739 007, acréscimo de 1 368 bytes produzido pelo próprio host entre as
  duas corridas, não pelo probe — o probe compara a árvore antes e depois de cada
  corrida, e cada log afirma "estado intacto: sim" para a sua).

## Estado da Central — o contrato comportamental

`tests/qml/check_central_loading.qml` atravessa quatro fases contra uma ponte que
atrasa a primeira consulta, devolve `E-STATUS-SCENE` na segunda e recupera na
terceira: `loading → ready → stale → ready`. São 43 contratos na captura de
carregamento e 42 na de estado não renovado. O gate pytest é

```
.venv/bin/python tools/run_tests_isolated.py tests/integration/test_qml_handheld_offscreen.py -k central_loading -q
```

→ 3 passed em 11,98 s (a cena de fases e os dois quadros capturáveis, estes últimos
marcados `visual`).

`05-carregamento-antes.log` é a prova de que a cena não é vazia: executada contra os
dois arquivos de `64932141a276`, ela reprova com rc=1 (a API de fase não existia) e
não grava nenhum quadro. A árvore anterior foi obtida por `git show HEAD:<caminho>`
com md5 conferido antes e depois; o script auxiliar morou fora do checkout
(`/tmp/rc01_revert_*.py`, `/tmp/rc01_capture_antes.sh`) e não foi versionado — a
reprodução usa o próprio `git show`, descrito nos cabeçalhos dos logs.

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

## Ressalva de experiência registrada, sem correção neste lote

No cenário de atenção máxima (faixa de fase + banner de perfil + cartão de falha ao
mesmo tempo), as três superfícies escuras empurram "Pendências" e "Recentes" para
baixo da dobra em 800 px de altura. É o pior caso, não o caminho comum; fica como
pendência de revisão de experiência e nenhum comportamento foi alterado por causa
disso nesta batch.

## O que estas evidências NÃO provam

Nada aqui é prova de release instalada, gesto físico ou sessão do operador: os
quadros vêm do `QT_QPA_PLATFORM=offscreen` de uma ponte de teste local, com dados
sintéticos. A latência é real, medida na bridge do produto sobre o estado do host,
mas em 5 consultas consecutivas de um processo de laboratório, não no app empacotado.
