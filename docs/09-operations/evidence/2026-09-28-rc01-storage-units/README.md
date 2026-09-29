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
| `22-empacotamento-do-formatador.md` | o que a configuração prova e o que fica **pendente** sobre o wheel |
| `23-congelamento-*.txt`, `23-suite-integral.log` | guarda de estado da árvore e a suite integral **interrompida** — substituída pelo re-congelamento e pela suite do checkpoint final, sem valor de veredito |
| `24-matriz-de-locales.md` (+ `.py`, `-antes.log`, `-depois.log`) | o defeito da rodada 2: o gate pinava `pt_BR`; medido em cinco contextos, 6/109 em `C`/`C.UTF-8`/`en_US` antes, 145 ok nos dois fusos depois |
| `25-bateria-de-mutacoes-rodada-2.md` (+ `.py`, `.log`) | 8 mutantes sob dois locales, os dois verdes falsos da rodada 1 corrigidos e o gap real (divisor decimal sob rótulo IEC) fechado por oráculo |
| `26-fora-de-escopo.md` | as duas grandezas que apareceram ao rodar as páginas e **não** pertencem a esta frente, medidas com dono e corte |
| `27-checkpoint-integral-e-gates.md` | os sete gates na árvore congelada (14 leituras de identidade, `real-state` idêntico), os dois vermelhos com causa lida, o `EEEEEE` da execução anterior desfeito por medição e o que a árvore recebeu depois do veredito |
| `27-gates-integrais.sh`, `27-comandos-e-saidas.log{,.rc,.concluido}` | invólucro dos sete passos e a saída crua com os códigos de saída (`1,0,1,1,0,0,2`) |
| `27-congelamento-*.txt`, `27-atribuicao-digests.{py,log}`, `27-pos-execucao-sha256.txt` | guarda da árvore sob teste, atribuição por arquivo dos 31 digests obsoletos (lendo stderr) e o estado re-verificado depois da execução |

## Pendências declaradas (não escondidas)

* **Empacotamento de `sizes.js`**: configuração inclui, artefato da CI ainda não
  lido para esta branch (22).
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
