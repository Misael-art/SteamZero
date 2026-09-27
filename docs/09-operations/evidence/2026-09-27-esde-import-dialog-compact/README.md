# Evidência — RC-01 (3ª fatia): foco e viewport no diálogo "Importar tema ES-DE"

Lote: `WS-2026-09-RC01-READINESS-FOCUS` · branch `codex/rc01-readiness-focus-2026-09-27` · HEAD de partida `330401ac`
Itens tocados: UX-05 (foco/teclado real) e UX-07 (ações e conteúdo alcançáveis em viewport compacto), agora no
segundo diálogo do `ThemeEditorPanel`. **RC-01 não se encerra aqui** — ver "Pendências".

## O que foi demonstrado

O mesmo defeito da fatia anterior, reproduzido **sem** a correção com o mecanismo de teste real do projeto
(`qmltestrunner`, teclas e cliques reais): exit code **5**, cinco falhas nomeadas. Corrigido **pela menor
mudança completa** — a forma já provada no modal RetroFE, sem mecanismo novo — e medido de novo: exit code
**0**, 13/13. Todo número abaixo vem de leitura direta dos logs desta pasta.

| Cenário (painel isolado, moldura 640×560) | Antes | Depois |
| --- | --- | --- |
| 949×593, conteúdo normal | banda 560; ações dentro do corpo, `apply=(493,506)-(634,554)`; `nodes=20 foraDaBandaSemRolagem=0` | corpo rolável + rodapé: banda útil 471; `apply=(499,512)-(640,560)` **no rodapé fixo**; `foraDaBandaSemRolagem=0 espremidos=0 overflowHorizontal=0` |
| 949×593, relatório extenso (24 frases do próprio caminho de erro) | `body=519/1102` — 1102 px de conteúdo em corpo de 519, sem rolagem; primary em `(493,1041)-(634,1089)`, **fora da moldura**; **9 controles de texto fora da banda "sem como alcançar"** | banda 560, aviso implícito 816 px rolável; primary `(499,512)-(640,560)` sempre na moldura; **6 pressões reais de `Down`** até ele; `fora=0 espremidos=0 overflow=0` |
| 1280×800, relatório extenso | mesma classe de corte: 9 controles fora, sem área rolável | `foraDaBandaSemRolagem=0`, `apply=(499,512)-(640,560)` |
| D-pad percorrendo o diálogo | 24 pressões de `Down` e o foco **não saiu** de `themeImportEsdeSource` | descida e subida reais em **6 pressões cada**, visitando os alvos esperados |
| Lista com 24 esquemas | `ScrollView` aninhado: **1 visita distinta em 40 pressões** (foco preso no primeiro `RadioButton`) | `nodes=89` no corpo único, `fora=0`; **6 pressões → 6 visitas distintas** |
| Seta dentro do campo de origem | `Left`/`Backspace` editam (caret/texto 18→17) mas `Down` é **engolido** pela edição | edição intacta (18→17) e `Down` tira o foco do campo e navega |
| `Tab`/`Shift+Tab`, `Escape`/Cancelar, payload, alvos ≥ 48 px, escala de texto 1.5 | já passavam | continuam passando |

As três últimas linhas da tabela são honestas por dois motivos: os dois casos que já passavam estão na
mesma corrida vermelha (`test_04`, `test_08`, `test_10`, `test_11` = PASS com o painel sem correção), então
eles **pinam contrato, não corrigem defeito**; e o `test_10` de 48 px vale para os alvos **deste diálogo** —
a certificação de 48 px no shell inteiro é o recorte 5(b), pendente.

Além do ES-DE, este lote fechou uma corrida que a fatia anterior deixou no ar: a cena de captura do
RetroFE perdia capturas sob carga (`capturas=5 de 4`, um `undefined-gate.png`, rc=1). Reproduzido 4×4
com a guarda removida e corrigido com a mesma linha (`harness.phase = 500` antes do `grabToImage`),
agora 6/6 no par combinado. Bruto na seção 4/5 de `05-gates-rapidos.log`.

## Arquivos desta pasta

| Arquivo | Conteúdo |
| --- | --- |
| `01-preflight.log` | branch/HEAD/ponta remota, worktree único, ausência de processos de teste concorrentes, o painel no estado byte a byte de `7fe9e8b2` (sha256 `79dc0e5f…`, 3014 linhas, blob `b5e5212d`), e a versão do runtime por duas fontes que concordam (`qmake6 -query QT_VERSION` = 6.11.2; `pacman -Q qt6-base` = 6.11.2-3) |
| `02-vermelho-medido-panel-sem-correcao.log` | harness **final** (sha256 `d0d8aa15…`, 880 linhas) contra o painel **sem** a correção (árvore `83b683dc…`, 3019 linhas, montada a partir de `git show HEAD:` — referência no cabeçalho): `Totals: 8 passed, 5 failed`, `# rc=5`, com as cinco falhas nomeadas e as linhas `PASSO 1..24` mostrando o foco parado no campo |
| `03-verde-medido-com-correcao.log` | mesmo harness, painel corrigido (`fea75dea…`): `Totals: 13 passed, 0 failed`, `# rc=0` |
| `04-capturas-viewport.log` | §1 o defeito do próprio arquivo de captura reproduzido (8 capturas para 5 nomes, rc=1) e a cena restaurada por hash; §2 as cinco capturas **antes**, com o painel `83b683dc` em uso; §3 as cinco **depois**, com `fea75dea`; §4 conferência final das árvores; §5 sha256 e tamanho das dez PNGs |
| `05-gates-rapidos.log` | `ruff check`, `ruff format --check` (672 arquivos), `mypy src` (297 arquivos), `make independence boundaries` — todos rc=0; o par de gates de viewport 5× seguido (`11 passed` nas cinco); a corrida da fatia anterior reproduzida sem a guarda (4/4 falham) e corrigida com ela (6/6 passam); e a **regressão dirigida** dos 96 testes que leem o painel e os diálogos (`test_qml_handheld_offscreen.py` + cobertura/jornadas de diálogos + identidade/matriz de controles): `96 passed in 1158.03s`, rc=0, com a árvore congelada no intervalo 11:30:17→11:49:35 |
| `06-reproducao-no-codigo.log` | as quatro causas estruturais com linha do arquivo, a referência Git recuperável da árvore vermelha com as **cinco** linhas de superfície de teste, o comando único de reprodução, as cinco falhas verbatim, os âncoras da correção, a prova `grep -rl "esdeImportDialog"` de que não há cópia alternativa, e o limite offscreen |
| `1-compacto-acoes-e-corpo-{antes,depois}.png` | 949×593, um esquema |
| `2-compacto-listagem-24-esquemas-{antes,depois}.png` | 949×593, 24 esquemas |
| `3-compacto-rodape-fixo-com-campo-de-nome-focado-{antes,depois}.png` | 949×593, foco programático no campo de nome |
| `4-compacto-relatorio-extenso-{antes,depois}.png` | 949×593, relatório de erro de 24 frases |
| `5-largo-relatorio-extenso-{antes,depois}.png` | 1280×800, mesmo relatório |

As dez imagens foram inspecionadas uma a uma. O que cada par mostra, sem interpretação generosa:

* `1-`: com um único esquema as ações aparecem **nas duas** imagens — a diferença é estrutural: antes o
  campo de nome e as ações estão colados no fim de um corpo fixo com uma faixa vazia no meio; depois o
  campo fica junto da lista, o corpo vazio é a banda rolável, e o rodapé está encostado na borda inferior
  da moldura.
* `2-`: antes, 24 esquemas viram **5 visíveis** presos num scroll aninhado de ~250 px, com nome e ações
  fora dele; depois, a lista inteira vive num corpo rolável único (6 visíveis na banda) e o nome fica
  abaixo da dobra — alcançável por D-pad, que é o que o `test_03`/`test_07` medem.
* `3-`: o foco aqui é **programático de propósito** (ver o comentário na cena de captura): a imagem prova
  que o rodapé continua fixo com o destino fora da dobra, e **não** prova rolagem — revelar o destino
  focado é caminho do D-pad real, medido no harness de contrato.
* `4-`: antes, o relatório de 24 frases preenche o diálogo e **nenhuma ação aparece**; depois, o mesmo
  relatório está na banda rolável com "Cancelar" e "Importar como editável" fixos no rodapé.
* `5-`: antes, em 1280×800 o texto **vaza pela borda inferior da moldura** e as ações não existem na tela;
  depois, o texto corta na banda e o rodapé está dentro da moldura.

## Como reproduzir

```sh
# contrato (harness de teclado real; raiz Item → qmltestrunner) — 13 casos, rc 0
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software QT_FORCE_STDERR_LOGGING=1 QT_LOGGING_RULES="" \
  /usr/lib/qt6/bin/qmltestrunner -input tests/qml/check_esde_import_dialog_compact_viewport.qml

# capturas (raiz Window → qml; argumentos após "--") — 5 de 5, rc 0
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software QT_FORCE_STDERR_LOGGING=1 QT_LOGGING_RULES="" \
  /usr/lib/qt6/bin/qml tests/qml/capture_esde_import_viewport.qml -- --output-dir=/tmp/cap-esde --label=depois

# gates pytest (6 ES-DE + 5 RetroFE = 11)
.venv/bin/python -m pytest tests/integration/test_esde_import_dialog_compact.py \
  tests/integration/test_retrofe_import_dialog_compact.py -q
```

O vermelho é montado a partir do **Git**, não de cópia solta. A árvore anterior é
`git show HEAD:src/steamzero/ui/qml/ThemeEditorPanel.qml` → sha256
`79dc0e5f68ff4008ddd0ebcd07985544b48c9974cc4fe4a11878ae5b49c790ed` (3014 linhas, blob `b5e5212d`; idêntica
em `7fe9e8b2`, o commit funcional da fatia anterior). O harness consome quatro nomes que ela não expõe,
então acrescente **exatamente estas cinco linhas** — nenhuma muda comportamento (`id`/`objectName`/`alias`):

| Local | Linha a inserir |
| --- | --- |
| depois de `property alias retrofeImportApplyControl: retrofeImportApplyButton` | `property alias esdeImportDialogControl: esdeImportDialog` |
| logo abaixo | `property alias esdeImportApplyControl: esdeImportApplyButton` |
| primeira linha do `Label {` ligado a `text: panel.esdeImportNotice` | `objectName: "themeImportEsdeNotice"` |
| primeira linha do `Button { text: qsTr("Cancelar") }` do `RowLayout` de ações | `objectName: "themeImportEsdeCancel"` |
| primeira linha do `Button {` cujo `objectName` já era `"themeImportEsdeApply"` | `id: esdeImportApplyButton` |

Conferência: com as cinco linhas o arquivo mede sha256
`83b683dc02f4344d9ac36a858e55e756b204e855d93d43a6f7c5d54a9f77a926` (3019 linhas) — é a árvore exata do log
`02`, e é o hash impresso no cabeçalho da seção 2 do log `04`. Copiado sobre
`src/steamzero/ui/qml/ThemeEditorPanel.qml`, o harness dá **rc=5, 5 falhas nomeadas**; o painel corrigido
(sha256 `fea75dead9d4839d0f8bb66043dc306c0621e0dac9bb4f1d9b106cdfb78b1656`, 3086 linhas) dá **rc=0, 13
passed**. Ao terminar, devolva o checkout com `git checkout -- src/steamzero/ui/qml/ThemeEditorPanel.qml`
e confirme `git status --porcelain` para este caminho. Nada desta evidência depende de cópia alternativa:
`grep -rl "esdeImportDialog" src tests` devolve apenas o painel, os três arquivos de teste deste lote e
`Main.qml` — que tem **outro** diálogo ES-DE duplicado, fora deste recorte (ver Pendências).

## Caminho canônico desta evidência

Tudo que sustenta as afirmações está **dentro do checkout**, em
`docs/09-operations/evidence/2026-09-27-esde-import-dialog-compact/`, no mesmo formato da pasta anterior
(`2026-09-27-rc01-readiness-focus/`). Os temporários das trocas de árvore viveram em `/tmp`
(`/tmp/esde-capturas-1790515955/`) e nenhuma árvore vermelha ficou no repositório.

## Pilha de PRs (dependência declarada)

`239` (RC-00, `069501ab`) → `240` (1ª fatia de RC-01, UX-01/UX-02, `c959be13`) → `241` (2ª fatia
RetroFE **e esta** 3ª fatia). Base `main` nos três, todos OPEN. Esta fatia depende das duas anteriores de
forma concreta: a árvore vermelha aqui medida é `git show HEAD:` do painel **já com** o commit funcional da
2ª fatia (`7fe9e8b2`, blob `b5e5212d`), e o `moveVertical`/`reveal…` do ES-DE espelha o mecanismo criado
lá. Nada do conteúdo de 239/240 é reapresentado como mudança nova; o que é novo aqui são os commits desta
frente, e o corpo do PR 241 passa a declará-los.

## Limite honesto da evidência

* **Nada aqui é prova da release instalada no host.** `QT_QPA_PLATFORM=offscreen` + backend `software`:
  mede geometria, foco e teclado real no runtime Qt 6.11.2 do projeto. A `2.0.0rc1-e2af2562ebba` instalada
  não foi alterada nem revalidada visualmente — exige autorização do operador.
* As capturas carregam o `ThemeEditorPanel` isolado, sem o tema do shell: os controles aparecem no estilo
  claro padrão. Mede-se retângulo, alcance e rolagem, não cor.
* **Nenhuma suíte integral foi corrida para esta fatia.** O checkpoint integral deste lote continua
  sendo a corrida única da 2ª fatia (`1 failed, 6402 passed, 47 skipped`, 08:50→09:21), sobre árvore
  diferente. O que cobre o risco real desta mudança são os 96 testes dirigidos do log `05` §7 — os que
  carregam o painel e os diálogos — mais os dois gates de viewport. A integral da sequência vem no fim
  dos recortes 5(d)/5(b)/5(c), sobre a árvore final congelada.
* O `test_10` (alvos ≥ 48 px) e o `test_11` (escala de texto 1.5) passam **também na árvore vermelha**:
  são contrato pinado, não resultado desta correção. E o registro da fatia anterior mantém UX-05 aberto
  justamente onde este lote não mede — na primeira dobra da Home e nos alvos que, no painel isolado sem
  tema, marcam **44 px**. A certificação de 48 px por alvo dentro do shell é o recorte 5(b).
* Dados locais e sintéticos (caminho `/tmp/esde-tema`, relatório repetido). Nenhum tema foi importado ou
  ativado, nenhum acervo, caminho pessoal ou segredo entra nestes logs.
* O gate de capturas depende de carga: sem a guarda de fase ele falha intercaladamente (medido 4/4 sem a
  guarda, 6/6 com ela). A guarda está no arquivo e o gate que a verifica também.

## Decisões de projeto registradas aqui

1. **Espelhar a forma da fatia anterior, não reinventar.** Corpo `ScrollView` único + ações em `footer` +
   `moveVertical` filtrando por pertencimento ao modal e `enabled`. Nenhum mecanismo novo de foco ou
   rolagem foi introduzido; as duas famílias de helpers (`retrofe*`/`esde*`) ficaram simétricas de
   propósito, porque a simetria é o que torna o próximo recorte (Main.qml) comparável.
2. **As duas pontas chamam o mesmo passo.** `Keys.onUpPressed`/`onDownPressed` existem no `ScrollView` do
   corpo **e** no `footer`, porque `Dialog.footer` não é descendente do corpo rolável (fato medido na
   fatia anterior) — sem isso, o D-pad morre ao chegar nas ações.
3. **O `ScrollView` aninhado da lista de esquemas virou `ColumnLayout` simples.** Medido: dentro dele o
   foco percorria 1 alvo em 40 pressões; o mecanismo é o mesmo já provado no modal RetroFE, e a remoção é
   a correção, não uma configuração do scroll.
4. **Setas verticais navegam, horizontais editam.** Medido no `test_05` nas duas árvores: antes o `Down`
   era engolido pelo `TextField`; depois a edição continua intacta (18→17) e o `Down` sai do campo.
5. **Nada de comportamento de importação foi tocado.** O payload de `theme.import.esde.apply` continua
   `{source, scheme, name}`, o tema continua sem ser ativado, `onClosed: panel.resetEsdeImport()` continua
   limpando o importador — as três coisas são o `test_08`.

## Pendências (por que isto não fecha RC-01)

* **O diálogo ES-DE duplicado em `Main.qml`** (aberto de `Main.qml:6313`, dialog em 2822-2971) tem a mesma
  classe de defeito — corpo sem `ScrollView`, sem navegação por tecla — e **não** foi tocado: `Main.qml`
  está em `exclusivePaths` de `WS-2026-09-LIBRARY-GOVERNED-MANAGEMENT`. A conciliação desse claim contra a
  evidência de hoje é o passo 5(d) desta frente, e a correção dentro do shell (com 48 px por alvo e escala
  de texto) é o 5(b). Ordem: 5(d) → 5(b), não o contrário.
* **UX-03** (explicar a prontidão sem confundir preflight com gameplay) continua pendente — os sete
  produtores de `percent` já estão mapeados no log `08` da pasta anterior.
* Validação visual na release instalada e a primeira dobra da Home: não feitas (exigem autorização).
* Esta frente não se declara integrada antes do merge efetivo do 241 — decisão do operador.
