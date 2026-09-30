# 104 — RC-01 reconciliada critério a critério com os nove elos (2026-09-29)

Remede o documento-fonte `61-reconcilio-rc01-oito-elos.md` (pasta do oitavo elo) contra a
cabeçada deste nono elo. **Nenhum número foi copiado de 61**: as grandezas abaixo são saída de
comando rodado agora, e o texto só existe porque as premissas bateram — o script que gera este
arquivo (`104-reconcilio-rc01-nono-elo.py`) aborta se qualquer escrita de `…esdeImportBusy =
false` estiver incondicional, se os formatadores já estiverem em `main`, se o `make
status-check` de hoje apontar qualquer obsolescência que não seja a do cartão desta
frente, se alguma das visões geradas não estiver modificada na árvore, ou se os logs do
checkpoint (`100`) e do gate visual (`110`) não trouxerem exatamente o que este documento
lhes atribui.

Enunciado normativo: `docs/12-roadmap/IMPLEMENTATION-ROADMAP.md` (lote RC-01 / P1): "Home
utilizável no orçamento aplicável; sem tela vazia enganosa; contraste essencial conforme
política; controles alcançáveis em viewport compacto e escala de texto; timeout/retry sem
corrida".

Camadas: **I** interface implementada · **C** contrato testado offscreen · **G** código integrado
em `main` · **P** artefato empacotado · **H** experiência comprovada na release instalada.

## Fundo re-medido nesta cabeça

| grandeza | valor medido agora | como conferir |
|---|---|---|
| `origin/main` | `3495c49d5d7c3244267e8292beee34475f70236b` | `git fetch origin main && git rev-parse origin/main` |
| cabeça do elo (branch `codex/rc01-esde-import-generation-2026-09-29`) | `c4975979b93a03e661294b6854146e76f22fa8c3` + o que este lote acrescenta por cima | `git rev-parse HEAD` |
| elos abertos da fileira | #239…#246, todos `OPEN`; **8/8 checks obrigatórios em `SUCCESS`** nas oito cabeças, `mergeStateStatus=CLEAN`, nenhum review pendente exigido | `106-preparar-integracao-da-cadeia.py` → `106-preparar-integracao-da-cadeia.log` |
| ancestralidade | linear, par a par (`merge-base --is-ancestor`): #239 → #240 → … → #246, todas descendentes de `origin/main` | mesmo log, seção de cada elo |
| commits de `#246` acima de `main` | **74** | `git rev-list --count origin/main..c4975979` |
| conta da fileira, por elo | incrementos `2 + 5 + 13 + 4 + 10 + 16 + 8 + 16` = **74**, cada um medido contra a cabeça do elo anterior, fechando com o acumulado da última cabeça; a coluna "acima da base" de `107`, somando **161**, NÃO é tamanho da fileira — em #239…#244 (base `main`) ela já é acumulado e a soma aninha o mesmo trecho | `107-conta-de-commits-da-fileira.log` |
| deriva entre 61 e agora | `61` é um **documento**, não uma contagem: ele media **70** e estava certo na rodada em que foi escrito — `#246` estava em `22773047`, com **12** commits sobre a base `2d6a8957`. A diferença de **4** é a rodada de reconcílio posterior (`c4975979`, `71c49beb`, `7a8af0c1`, `92e1bf4c`), apenas `docs/`, que levou aquela cabeça aos 16 commits próprios de hoje | `git rev-list --count origin/main..22773047` · `git log --oneline 22773047..c4975979` |
| `sizes.js` / `readiness.js` em `main` | `git ls-tree -r --name-only origin/main -- …` devolve **vazio** | os formatadores ainda não existem em `main` |
| contrato de geração ES-DE | `grep -c esdeImportGeneration` → painel **12**, raiz **12** (61 media **0** no painel); RetroFE no painel segue em **13** | os dois arquivos, nesta cabeça |
| escrita da bandeira ES-DE | painel: :223 (revogacao), :242 (guarda), :254 (guarda), :291 (guarda), :301 (guarda) · raiz: :2915 (revogacao), :3010 (guarda), :3022 (guarda), :3125 (guarda), :3132 (guarda) — **zero incondicionais** | `104-reconcilio-rc01-nono-elo.py`, janela de 8 linhas acima de cada escrita |
| checkpoint deste elo | suíte: **1 failed, 6528 passed, 47 skipped in 2529.34s (0:42:09)** · visual: **377 passed, 6199 deselected in 1711.56s (0:28:31)** | `100-checkpoint-integral-nono-elo.log`, `110-gate-visual-apos-governanca.log` |
| o vermelho do checkpoint, e só ele | `tests/unit/test_project_status.py::test_committed_catalog_and_generated_views_are_consistent` — 11 `scopeDigest` envelheceram, e todos são atribuíveis a arquivos deste elo por leitura dos cartões, não de memória: `Main.qml` está no escopo de 8 dos 11, `ThemeEditorPanel.qml` no de 5, os dois em `SZ-THEME-ENGINE`, `SZ-UI-DESKTOP-AUDIT` (2), e a união fecha 8 + 5 − 2 = 11 — exatamente o conjunto renovado, sem sobra (0 fora). As 3 visões geradas do catálogo (`docs/ACTIVE-WORK.md`, `docs/STATUS.md`, `docs/status/COVERAGE.md`) estão modificadas na árvore por este lote. Remédio proporcional de AGENTS §6 aplicado pelo `105`: renovar no valor impresso pela ferramenta (dupla leitura `check` + `digest --item`) e `render --write`; o `make status-check` desta leitura (rc=2) traz **somente** `SZ-UI-DESKTOP-AUDIT` como evidência obsoleta, mais o atraso de visão gerada — `docs/status/COVERAGE.md` — 1 linha(s) de valor: `\| SZ-UI-DESKTOP-AUDIT \| 787 \| 176 \| 106 \| dev \|  \|` → `\| SZ-UI-DESKTOP-AUDIT \| 812 \| 176 \| 106 \| dev \|  \|` — o ponto fixo em trânsito: o cartão desta frente tem a pasta de evidência dentro do próprio escopo, cada arquivo escrito aqui muda a contagem que a visão imprime, e a renovação de digest com `render --write` é a última escrita do lote na árvore. Não é vermelho de contrato nem catálogo desalinhado com o código: é geração atrás da árvore. Os 9 arquivos funcionais são byte a byte os mesmos dos dois logs | `105-renovar-digests.log`, `110-gate-visual-apos-governanca.log` |
| limite que este lote abriu e não tapou | `100` rodou cinco dos seis gates integrais de AGENTS §6 e **omite** `make status-check`; ele foi executado à parte, antes do `110`, e é o que está citado acima. Não se chama de "checkpoint §6 completo" o que não rodou os seis na mesma corrida | `100-checkpoint-integral-nono-elo.py`, linha dos passos |
| bateria de mutações | painel (M1–M5): 5/5 mutações detectadas pelo gate; 0 sobreviveram · raiz (M6–M10): 4/5 mutações detectadas pelo gate; 1 sobreviveram | os dois logs nesta pasta |
| release instalada | `2.0.0rc1-e2af2562ebba` (26/09), valor registrado em `HOST-INSTALL.md`; **não re-medido** nesta sessão porque o host físico não foi acessado | leitura anterior, declarada como anterior |

Consequência fixa, igual à de 61: **G = não** e **H = não** para todas as linhas abaixo, sem
exceção. Nenhum SHA desta fileira está em `main` nem no artefato instalado.

## Tabela

| critério | I | C | G | P | H | situação nesta cabeça | evidência |
|---|---|---|---|---|---|---|---|
| Contraste essencial conforme política | sim | sim | **não** | não | não | **parcial — travado por decisão de produto (4,5:1 vs ≥7:1)**, não por falta de teste | `2026-09-26-rc01-central-loading/14-contraste-politica-normativa.log` |
| Loading/erro/vazio explícitos, sem tela vazia enganosa | sim | sim | **não** | não | não | **parcial** — falta integrar e provar na release | `#240`, `check_central_loading.qml` + `check_status_refresh_coalesced.qml` |
| `timeout/retry` sem corrida | sim | sim | **não** | não | não | **parcial** | `2026-09-26-rc01-central-loading/09-refresh-coercido.log` |
| Custo da consulta de status (latência) | parcial | sim, medido antes/depois | **não** | não | não | **parcial — cauda de ~11,4 s em `emulation` segue aberta**, backend, fora das fatias de UI | `01/02-baseline-e-final-status-probe.log` |
| Semântica da prontidão (UX-03) | sim | sim | **não** | sim (`readiness.js` no wheel de `af6a5c6e`) | não | **parcial — F-1 (`memoryGb`) ainda não implementado**; F-2 é de outra frente | `#243`; `2026-09-28-rc01-readiness-semantics/` |
| Unidades de armazenamento (UX-04) | sim | sim (matriz de locales, 8/8 mutações) | **não** | **sim** (`sizes.js` 2 377 bytes, `6d5ca418…` idêntico ao blob) | não | **parcial** — empacotado no CI, não integrado | `#244`; varredura 619/619 do wheel |
| Primeira dobra da Home | sim | sim, pior caso corrigido (alvo 48 px, primeiro alvo 449/468 px) | **não** | não | não | **parcial** — gap funcional (a) fechado em contrato offscreen no oitavo elo; resta G/P/H | oitavo elo: `38`, `39`, `40`, `46`, `47`, `48`, `52` |
| Foco, escala e alcance (UX-05/UX-07) | sim | sim, **só nas superfícies exercitadas** | **não** | sim | não | **parcial — cinco superfícies roláveis seguem não medidas** | `#241`, `#242` |
| **ES-DE dentro do shell — resposta tardia** | **sim** (painel e rota raiz) | **sim, agora com contrato de geração**: dez cenas com atraso real, bridge sem stub, 9/10 mutantes mortos (M9 declarado equivalente e pinado por teste de reachability) | **não** | **não** (sem varredura de wheel desta cabeça) | não | **gap funcional (b) FECHADO em C** — era a pendência nomeada pelo sétimo elo; as cinco escritas incondicionais de 61 viraram 10 escritas guardadas/revogadas | este lote: `70`, `73`, `74`, `98`, `100`, `105`, `110`, README |
| RetroFE dentro do shell | sim | sim (9 cenas, 10 testemunhos, mutações) | **não** | **não ainda** — CI lido em `2d6a8957`, wheel deste elo não varrido | não | **parcial — falta a prova P** | sétimo elo, `2026-09-29-rc01-retrofe-shell-late/` |
| Respostas tardias, reabertura, erro e recuperação | **sim nas duas frentes** | **sim nas duas frentes** | **não** | não | não | **parcial — o par (b) deixou de ser exceção**: ES-DE e RetroFE obedecem ao mesmo contrato, com a mesma classe de gate | limite declarado: o pedido em voo não é cancelado; descarta-se o efeito |
| Seletor nativo de diretório | existe na árvore (`FolderDialog`) | **não dirigível por evento sob offscreen** (medido) | **não** | não | não | **PENDENTE** — a rota por Enter funciona e não promove a rota não testada | `06-medida-seletor-nativo-offscreen.md`, `17-sonda-qmltestrunner-dialogo-nativo.log` |
| Captura visual certificada em CI | — | parcial (9 capturas byte-idênticas no run 36341332344) | **não** | — | não | **parcial — `GAP-UI-VISUAL-CAPTURE-NOT-CERTIFIED-IN-CI` aberto também para este elo**: nenhuma PNG é alegada | `2026-09-27-gate-visual-causa-e-contrato/` |

## O que mudou desde 61, e o que não mudou

1. **Moveu uma linha e meia.** "ES-DE dentro do shell" passou de `C = não (sem contrato de
   geração)` para `C = sim`, com vermelho antes, gate novo, dez cenas, duas baterias de mutação e
   checkpoint integral + gate visual nesta árvore — com a ressalva devida: o checkpoint integral
   fechou com **um** falho, o gate de governanca (`100`), regenerado pelo `105` conforme o remedio
   proporcional de AGENTS §6, e o visual foi corrido depois disso pelo `110`, sobre os mesmos
   hashes funcionais. Não se escreve "suíte integral verde nesta árvore" a partir daqui; escreve-se
   "6 528 testes de comportamento verdes, o único vermelho era gerado e está regenerado". A meia linha é "Respostas tardias": ES-DE deixou de
   ser a exceção declarada.
2. **Nenhuma coluna G, P ou H se moveu** — integration é decisão do operador e nada foi varrido
   ou instalado.
3. **Remedio explícita onde 61 podia ter envelhecido:** contagem de commits da fileira (70 → 74),
   `grep -c esdeImportGeneration` (0 → 12 no painel) e a lista das escritas da bandeira,
   agora com classe por escrita.

## O que falta para a RC-01, em ordem de dependência

* **G** — mergear a fileira na ordem de ancestralidade (#239 → … → #246 → PR deste elo). Nada
  aqui depende desta frente. **Mas a ordem sozinha não basta**, e isso foi medido agora e não em
  `61`: `#245` tem base no ramo de `#244` e `#246` no ramo de `#245`. Um merge nesses dois
  entregaria no **ramo de base**, não em `main`; é preciso recolocar a base em `main`
  (`gh pr edit N --base main`) no ponto em que o elo anterior já estiver integrado — só aí o
  diff volta a ser o delta daquele elo. Sequência completa, com o que reler depois de cada
  merge, em `106-preparar-integracao-da-cadeia.log`.
* **P** — varrer os artefatos dos elos 7, 8 e 9 (procedimento provado no `#244`: baixar o wheel,
  comparar `sha256` de cada QML com o blob da cabeça).
* **H** — validação física **preparada** em `62-preparacao-de-validacao-fisica.md`, sujeita à
  autorização específica de instalação.
* **Funcional executável dentro do escopo desta frente**: F-1 (`memoryGb` → bytes via `sizes.js`).
* **Funcional fora do escopo desta frente**: F-2 vive em `adapters/emulation.py`, dono exclusivo
  `WS-2026-09-LIBRARY-GOVERNED-MANAGEMENT` — declarado, não editado.
* **Decisão de produto**: contraste. **Limitação de plataforma**: seletor nativo fora do
  offscreen. Nenhum dos dois se resolve com teste.
