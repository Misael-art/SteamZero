# Evidência do lote RC-01 / UX-04 — armazenamento em unidades compreensíveis (2026-09-28)

Frente: `WS-2026-09-RC01-STORAGE-UNITS`, branch
`codex/rc01-storage-units-2026-09-28`, base `c0de54c9` (ponta do PR #243), sexto
elo da pilha #239 → #240 → #241 → #242 → #243. Item normativo:
`SZ-UI-DESKTOP-AUDIT`.

Conteúdo funcional do lote: `ed2fd930` (`sizes.js`), `6910e613` (`Main.qml`,
arquivo compartilhado isolado em commit próprio), `748d532b` (páginas restantes +
contrato do cartão), `3bf68498` (gate delegando ao locale em vigor + oráculo de
grandeza + matriz de locales), `f9ec2815` (registro do gate no harness visual —
arquivo compartilhado isolado em commit próprio, AGENTS.md §2).

## O que o lote entrega

1. **Um formatador** (`src/steamzero/ui/qml/sizes.js`) em vez de quatro: as páginas
   delegam, a escolha de andar e a localização saem da superfície.
2. **Medida tipada no contrato**: o cartão de armazenamento publica
   `metricBytes`/`capacityBytes` inteiros, validados por
   `emulation-workspace-v1.schema.json`; a prosa explica o estado e para de
   reimprimir grandeza.
3. **Gate parametrizado no CI**: `tests/qml/check_storage_units.qml` roda as quatro
   páginas reais e é um caso do `@pytest.mark.visual` em
   `tests/integration/test_qml_handheld_offscreen.py:253`. O harness não escolhe
   fuso: lê o `Qt.locale()` em vigor, afirma a grandeza contra um oráculo declarado
   no próprio teste, e `tests/integration/test_storage_units_locale_matrix.py` exige
   que ele passe nos dois fusos da matriz **e** que os separadores sejam distintos.

## Arquivos

| arquivo | conteúdo |
|---|---|
| `18-vermelho-e-verde-do-gate.md` | leitura do vermelho (30/72) e do verde (109 ok), com SHA de harness e comando |
| `18-vermelho-no-gate-visual-do-checkout.log` | saída crua do gate antes de qualquer correção |
| `19-verde-no-gate-visual.log` | saída do mesmo gate depois, mais a contagem declarada pelo harness |
| `20-bateria-de-mutacoes.md` | 8 mutações, como cada uma foi morta e os dois falsos resultados corrigidos |
| `20-bateria-de-mutacoes.log` | saída corrida da bateria |
| `21-varredura-do-produtor.log` | varredura dos 303 cartões do workspace: 3 ofensas antes, 0 depois |
| `22-empacotamento-do-formatador.md` | o que a configuração prova, o que ficou **pendente** sobre o wheel na rodada e o fechamento por leitura de artefato em `28` |
| `23-congelamento-*.txt`, `23-suite-integral.log` | guarda de estado da árvore e a suite integral **interrompida** — substituída pelo re-congelamento e pela suite do checkpoint final, sem valor de veredito |
| `24-matriz-de-locales.md` (+ `.py`, `-antes.log`, `-depois.log`) | o defeito da rodada 2: o gate pinava `pt_BR`; medido em cinco contextos, 6/109 em `C`/`C.UTF-8`/`en_US` antes, 145 ok nos dois fusos depois |
| `25-bateria-de-mutacoes-rodada-2.md` (+ `.py`, `.log`) | 8 mutantes sob dois locales, os dois verdes falsos da rodada 1 corrigidos e o gap real (divisor decimal sob rótulo IEC) fechado por oráculo |
| `26-fora-de-escopo.md` | as duas grandezas que apareceram ao rodar as páginas e **não** pertencem a esta frente, medidas com dono e corte |
| `27-checkpoint-integral-e-gates.md` | os sete gates na árvore congelada (14 leituras de identidade, `real-state` idêntico), os dois vermelhos com causa lida, o `EEEEEE` da execução anterior desfeito por medição e o que a árvore recebeu depois do veredito |
| `27-gates-integrais.sh`, `27-comandos-e-saidas.log{,.rc,.concluido}` | invólucro dos sete passos e a saída crua com os códigos de saída (`1,0,1,1,0,0,2`) |
| `27-congelamento-*.txt`, `27-atribuicao-digests.{py,log}`, `27-pos-execucao-sha256.txt` | guarda da árvore sob teste, atribuição por arquivo dos 31 digests obsoletos (lendo stderr) e o estado re-verificado depois da execução |
| `28-ci-terminal-e-wheel-no-sha-final.md` | o veredito terminal da cabeça `37f0add4` (run `36521236686`, oito jobs `success`), a matriz de locales exercida dentro da imagem do CI por reconciliação de contagem, o wheel lido arquivo por arquivo, a cobertura do mesmo run e o que a leitura **não** cobre (captura física) |
| `28-ci-terminal-e-wheel-no-sha-final.log`, `28-verificacao-wheel.py` | as 14 seções cruas (`gh`, log do job, `sha256sum -c`, verificador governado, coleção do host) e o comparador wheel × blobs, reproduzível por argumento |
| `29-ci-terminal-no-sha-final.md` | o veredito terminal na cabeça **final** `2d04ac96` (run `36544698400`) com identidade da árvore pinada nos 12 ciclos de espera; suíte lida dos junit publicados (3 × 6185, 0 falhas), rollup do gate do log do job e cobertura; a prova de empacotamento elevada a **pacote inteiro** (619/619 byte a byte) e a correção honesta de que a árvore **não** recebeu só documento depois do checkpoint |
| `29-ci-terminal-no-sha-final.log`, `29-verificacao-wheel-no-sha-final.py` | as 13 seções cruas (inclusive a comparação dos dois wheels do CI, entrada a entrada, e a cadeia de seis PRs re-medida) e o varredor reproduzível: recebe o diretório do artefato e a lista do PR, lê o merge ref da própria proveniência |
| `30-ci-terminal-na-cabeca-ee09dbcc.md` | o veredito terminal na cabeça `ee09dbcc` (run `36554123223`), os 11 ciclos com o `ERRO` transitório do ciclo 9 preservado, a **correção do claim de footprint** (a evidência 29 dizia "os oito arquivos deste PR"; o PR muda 359 arquivos, 19 em `src/`), a reconciliação dos seis artefatos por tamanho **e** digest, e a comparação dos dois wheels que limita a diferença do produto ao carimbo de proveniência |
| `30-ci-terminal-na-cabeca-ee09dbcc.log`, `30-verificacao-wheel-na-cabeca-ee09dbcc.py` | as 17 seções cruas e o varredor com o bloco C sobre a lista completa de 19; inclui o defeito encontrado no temporário próprio (nome do artefato truncado em dois caracteres), o renomeio para o nome da API e a re-execução do varredor depois disso. O varredor não carrega caminho absoluto da máquina do autor — deriva o checkout da própria localização — e o `diff` entre a saída gravada e a reexecução portável é vazio (§9). A seção 17 foi remedida ao fechar: a linha de `status` original era verdadeira no instante em que rodou e ficou estreita depois |

## Pendências declaradas (não escondidas)

* **Empacotamento de `sizes.js`**: lido no artefato — `28` sobre a cabeça funcional
  `37f0add4` (8 caminhos do lote) e `29` sobre a cabeça final `2d04ac96`, agora o pacote
  inteiro (619 arquivos de `src/steamzero` iguais aos blobs, +`_build_info.py` conferido
  por conteúdo). `30` re-levou tudo na cabeça `ee09dbcc` e corrigiu o rótulo do bloco C:
  os 19 caminhos em `src/` do PR, não 8.
* **Claim de footprint corrigido por medição, não por edição (30 §3)**: a evidência 29
  chamou "os oito arquivos deste PR" a um bloco que leu 8 caminhos. O PR #244 muda 359
  arquivos (`gh api pulls/244/files --paginate` ≡ `git diff --name-only origin/main...HEAD`),
  dos quais 19 estão em `src/`. Aquilo que 29 afirmou sobre os 8 continua verdadeiro — 29
  rodou o bloco sobre a lista que usou; o que estava errado era o rótulo. Evidência
  publicada não se reescreve: a correção é a evidência nova.
* **Grandezas fora do cartão**: `adapters/emulation.py:2898` (texto de limite de
  verificação) e as mensagens de erro de teto de arquivo (`:434`, `:5942`) ainda
  escrevem `GiB`/`MiB`/`bytes` em prosa. Não são cartões: são descrições de política
  e diagnósticos, onde a unidade fixa é intencional. Ficam nomeadas aqui para não
  parecer varredura completa do que era varredura de cartões.
* **Unidade do `statusLabel`**: alguns rótulos de estado seguem sendo contagem
  textual (`"3 arquivo(s)"` via `status`/`statusLabel`), o que é outro eixo da
  UX-04 e não foi tocado.
* **F-1 e F-2 (evidência 26)**: memória disponível impressa como `"GB"` sobre
  divisor binário (`SteamGameplay.qml:1320` + `steam_gameplay.py:965-972`,
  -6,87 % de afirmação) e o preview do plano de empacotamento com bytes crus
  separados por vírgula (`emulation.py:2989-2996`, mostrado em `Main.qml:1906`).
  Nenhuma foi corrigida aqui: os arquivos têm dono exclusivo de outra frente
  ativa, e o lote não editorsa arquivo de terceiro. Ficam como primeiro corte da
  próxima frente, com serialização declarada.
* **Rodada 2 fechou um defeito do GATE, não da produção**: o harness pinava
  `Qt.locale("pt_BR")`, ficou verde na máquina do autor e vermelho nas cabeças do
  CI, cuja imagem fixa `LC_ALL=C.UTF-8`. Corrigido por delegação ao locale em
  vigor mais um oráculo de grandeza declarado no próprio teste, e guardado por
  `tests/integration/test_storage_units_locale_matrix.py`, que falha se o pino
  voltar (24, 25).
* **Risco residual da matriz, declarado antes do merge**: o teste exige que o harness
  informe `locale=C` sob `LC_ALL=C.UTF-8` e `locale=pt_BR` sob `LC_ALL=pt_BR.UTF-8`.
  A resolução de nome é do Qt, medida localmente em cinco contextos (24), mas **não**
  medida na imagem do CI. Se a imagem resolver o nome de outro modo, o teste falha
  alto com a dupla `LC_ALL=… / harness rodou sob …` no corpo da asserção — vermelho
  ruidoso, não verde silencioso. É esta a escolha: preferimos o gate que se queixa a
  verificar a mesma formatação duas vezes.
* **Como ficou a perna `pt_BR` na imagem do CI (28, re-medida em 29)**: o gate visual
  terminou verde na cabeça `37f0add4`, e a coleção do host (`360` testes) bate com o
  rollup do runner (`348 passed + 12 skipped`), com os 12 skips atribuídos por linha a
  `test_qml_asset_recipes.py` — os três testes da matriz não estão entre eles. Na cabeça
  final `2d04ac96` o rollup do próprio job é `348 passed, 12 skipped, 6185 deselected in
  1222.86s` com as mesmas quatro linhas de skip (29 §2), e o `real-state before/after`
  do isolador segue `exists=False`. A resolução de nome do Qt na imagem foi portanto
  exercida, não presumida. O limite é o do log: o job roda `-q` e não imprime nomes,
  então a prova é reconciliação de contagem sobre o rollup do CI, e isso está escrito na
  evidência em vez de virar alegação de "linha por linha".
* **Empacotamento**: a pendência 2a do lote está fechada por leitura de artefato (28,
  seção 3; 29, seção 3 — pacote inteiro na cabeça final; 30, §4 — a mesma prova re-levada na
  cabeça `ee09dbcc` com os seis artefatos conciliados por tamanho **e** digest, `SHA256SUMS`
  6/6 `SUCESSO`, `verify-wheel` rc=0 e o `requirements-runtime.lock` pinado na proveniência).
  O que continua aberto é o `GAP-UI-VISUAL-CAPTURE-NOT-CERTIFIED-IN-CI`: o run terminal
  publica 41 PNG (20 `esde-import`, 16 `retrofe-import`, 5 `shell-esde-import`) — zero
  capturas de armazenamento em 100/125/150 % de escala de texto, critério da RC-01.
* **O que a árvore testada recebeu depois do checkpoint (29, seção 4)**: **não** foi só
  documento. Entre `f9ec2815` (checkpoint integral da evidência 27) e `2d04ac96` há 6
  commits — `src/` 0, `tools/` 0, `docs/` 71 e **1 arquivo de teste**
  (`tests/integration/test_storage_units_locale_matrix.py`, `1eae804c`). Medido
  estruturalmente: 9 unidades de código com sequências de opcodes idênticas e uma única
  constante diferente, a mensagem de uma asserção. A revalidação proporcional existe: o
  arquivo re-rodou verde local nesta cabeça (`3 passed`) e os três jobs Python do run
  `36544698400` executaram a suíte inteira sobre ela. O produto, esse, é byte a byte o
  do checkpoint — `src/` inalterado (29 §9) e os 619 arquivos do pacote iguais aos blobs
  da cabeça final (29 §8). A frase "a árvore estava congelada" não é usada aqui.
* **O span seguinte (`2d04ac96`→`ee09dbcc`, 30 §7) é puramente documental**: 3 commits, 9
  arquivos, todos em `docs/` (`src/` 0, `tools/` 0, `tests/` 0 medidos por `git diff
  --name-only` no intervalo). Aqui a frase estrita vale sem ajuste, e a prova material está
  no artefato, não na narrativa: comparando o wheel deste run com o do run anterior,
  **623 das 625 entradas são byte a byte iguais** e as duas que mudam são
  `steamzero/_build_info.py` (a linha `SOURCE_COMMIT`, que aponta o merge ref de cada run)
  e o hash dela no `RECORD`. Nenhum `.py`, `.qml`, `.js` ou schema mudou (30 §6, log §14).
* **Delta de cobertura atribuído, não comemorado (30 §2)**: os totais dos dois runs têm
  `num_statements` idêntico (47 366) e um arquivo com `missing_lines` diferente — `adapters/
  linux_runtime.py`, 25→24, que não está entre os 19 `src/` do PR e não é tocado por nenhum
  commit do intervalo. O fallback de nome de partição depende do que o host do runner monta:
  variância de execução, não melhoria deste lote.

