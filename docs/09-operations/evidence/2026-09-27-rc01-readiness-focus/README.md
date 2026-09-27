# Evidência — RC-01 (2ª fatia): foco e viewport no diálogo "Importar cena RetroFE"

Lote: `WS-2026-09-RC01-READINESS-FOCUS` · branch `codex/rc01-readiness-focus-2026-09-27` · HEAD de partida `449b68c3`
Itens tocados: UX-05 (foco/teclado) e UX-07 (conteúdo e ações alcançáveis em viewport compacto). **RC-01 não se encerra aqui** — ver "Pendências" abaixo.

## O que foi demonstrado

Defeito reproduzido **sem** a correção (saída do runner com exit code 6, 6 falhas nomeadas) e
corrigido **pela menor mudança completa** no diálogo RetroFE (mesmo runner, exit code 0, 13/13).
Todo número deste README vem de leitura direta do disco ou da saída capturada nos logs desta pasta.

| Viewport | Antes | Depois |
| --- | --- | --- |
| 949×593, conteúdo normal | moldura 700×569; linha de ações em `(610,547)-(694,591)` → **22 px fora da moldura**, sem rolagem alguma | banda útil 484; conteúdo 396; `Publicar cena` em `(616,525)-(700,569)` **dentro da moldura**, no rodapé fixo |
| 949×593, relatório extenso (24 frases de erro) | primary caía em `y=1210`, **inacessível** — não existia corpo rolável | corpo rolável: banda 569, aviso implícito 680; **11 pressões de Down** reais até o primary; `foraDaBandaSemRolagem=0 espremidos=0 overflowHorizontal=0` |
| 1280×800, relatório extenso | mesma classe de corte/overflow de foco | banda 650; primary em `(616,606)-(700,650)`; contagens de corte/overflow em 0 |
| Navegação por D-pad | 24 pressões de Down **sem sair do primeiro RadioButton** da lista de layouts | descida e subida reais em 11 pressões cada, visitando os alvos esperados |
| Edição em campo de texto | — | `Left`/`Backspace` seguem editando (caret 7→5, texto 7→6); `Down` navega |

## Arquivos desta pasta

| Arquivo | Conteúdo |
| --- | --- |
| `01-preflight-e-estado-do-disco.log` | branch/HEAD/worktree único/`ps` de processos de teste; registro do arquivo cuja leitura divergiu no início do lote (caminho absoluto, sha256, mtime, `git diff` vazio) e o padrão de teclado real já existente no projeto (`check_dialog_keys.qml`, 7 passed) |
| `02-ux05-ux07-vermelho-medido.log` | 99 linhas, `# exit_code=6` — saída integral do harness **com o painel sem a correção**; os 6 contratos violados nomeados no cabeçalho |
| `03-ux05-ux07-verde-medido.log` | 118 linhas, `# exit_code=0` — mesma cena **com a correção**; 13 casos (11 cenários + init/cleanup), executado 3× com resultado estável |
| `04-capturas-viewport.log` | comandos de captura (antes e depois), `exit_code=0` nas duas corridas e sha256 das 8 PNGs |
| `05-gates-rapidos.log` | os gates rápidos do checkpoint: `ruff check`, `ruff format --check` (671 arquivos), `mypy src` (297 arquivos) e `make independence boundaries` — quatro dos seis verdes na primeira passada; `make status-check` reprovou 5 digests + 3 visões, ordem de escrita e não comportamento. Bruto em `10-gates-rapidos-bruto.log`, nesta mesma pasta |
| `06-checkpoint-integral.log` | a **única** suíte integral: comando, janela 08:50:33→09:21:16, `1 failed, 6402 passed, 47 skipped`, rc=1, fingerprint da árvore idêntico no lançamento e no fim (`ee04994d…`), state home do operador byte a byte igual, a reconciliação `6397 + 5 = 6402` e o que a corrida não cobre. Bruto em `11-checkpoint-integral-bruto.log`, nesta mesma pasta |
| `07-status-final.log` | a coerência final do catálogo: os cinco digests renovados pela ferramenta, as três visões regravadas, `STATUS-CHECK: OK` e `13 passed` em `tests/unit/test_project_status.py`, com o limite auto-referente declarado |
| `08-reproducao-no-codigo.log` | a reprodução **por leitura**, anterior a qualquer mudança: UX-03 (sete produtores alimentando o mesmo `percent` sem denominador), UX-04 (quatro formatadores de bytes, três saídas diferentes para 1 GiB), UX-05/UX-07 (o corpo do modal fora de qualquer `ScrollView`), cada linha conferida no arquivo |
| `09-sonda-foco-mecanismos.log` | a sonda executada no Qt 6.11.2 instalado que respondeu à dúvida de foco (3 passed, exit 0) antes de qualquer generalização |
| `10-gates-rapidos-bruto.log` | saída bruta dos gates rápidos, incluindo a reprovação do `status-check` com os cinco digests esperados/atuais |
| `11-checkpoint-integral-bruto.log` | saída bruta da suíte integral única |
| `12-estado-dos-prs-no-sha-consultado.log` | o estado real de 239/240/241 consultado no SHA exato (comando + resposta crua), em duas leituras (09:42 e 10:01–10:02), a pilha de dependência e as correções numéricas a claims anteriores |
| `1-compacto-acoes-e-corpo-{antes,depois}.png` | 949×593, conteúdo normal |
| `2-compacto-foco-rola-destino-{antes,depois}.png` | 949×593, foco navegado e destino revelado |
| `3-compacto-relatorio-extenso-{antes,depois}.png` | 949×593, relatório de erro extenso |
| `4-largo-relatorio-extenso-{antes,depois}.png` | 1280×800, relatório de erro extenso |

Imagens inspecionadas uma a uma. `3-…-antes.png` mostra a grade de créditos e as duas ações
totalmente fora do diálogo, sem qualquer área de rolagem; `3-…-depois.png` mostra a banda
rolável (a linha seguinte aparece cortada no rodapé da banda) com as ações fixas acima da
divisória do rodapé.

## Como reproduzir

```sh
# contrato (harness de teclado real; raiz Item → qmltestrunner)
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software QT_FORCE_STDERR_LOGGING=1 QT_LOGGING_RULES="" \
  /usr/lib/qt6/bin/qmltestrunner -input tests/qml/check_retrofe_import_dialog_compact_viewport.qml

# capturas (raiz Window → qml; argumentos após "--")
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software QT_FORCE_STDERR_LOGGING=1 QT_LOGGING_RULES="" \
  /usr/lib/qt6/bin/qml tests/qml/capture_retrofe_import_viewport.qml -- --output-dir=/tmp/cap-rc01 --label=depois
```

Para reproduzir o **"vermelho"**, monte a árvore anterior a partir do Git — não de cópia solta. O
painel sem a correção é o blob `7368fd385b8dc793c2ba83c6dc647c0b20f0dc9d094be8783bf01d1a35bb4dda`,
idêntico em `origin/main` (`3495c49d`), em `c959be13` (PR 240) e em `449b68c3`:

```sh
git show origin/main:src/steamzero/ui/qml/ThemeEditorPanel.qml > /tmp/ThemeEditorPanel.qml   # fora do checkout
```

Esse arquivo ainda não expõe nada ao harness, então acrescente **exatamente estas seis linhas** (nenhuma
muda comportamento; elas só dão nome/identidade ao que o teste alcança):

| Local (número de linha do blob) | Linha a inserir |
| --- | --- |
| depois de `property var exportPlan: null` (~49), antes de `signal applied()` | `property alias retrofeImportDialogControl: retrofeImportDialog` |
| logo abaixo | `property alias retrofeImportApplyControl: retrofeImportApplyButton` |
| e uma linha em branco antes de `signal applied()` | *(em branco)* |
| primeira linha de `Label {` ligado a `text: panel.retrofeImportNotice` (~1109) | `objectName: "themeImportRetrofeNotice"` |
| primeira linha do `Button { text: qsTr("Cancelar") }` do rodapé (~1238) | `objectName: "themeImportRetrofeCancel"` |
| primeira linha do `Button {` do primary (~1245; o `objectName: "themeImportRetrofeApply"` já existia) | `id: retrofeImportApplyButton` |

Conferência: com as seis linhas, o arquivo deve medir sha256
`13d5c644ce82d36c357b0d9d957078ca6c22b849ffb0826c412292e808c36140` (2930 linhas) — é a árvore exata do
log `02-…-vermelho-medido.log`. O apêndice daquele log traz o **unified diff** dessas seis linhas, e ele
foi aplicado ao blob de `origin/main` como verificação: o resultado saiu byte a byte idêntico ao arquivo
usado na corrida vermelha (`cmp` sem saída, mtime 09:54:32-03:00). Copie-o sobre
`src/steamzero/ui/qml/ThemeEditorPanel.qml`, rode os dois
comandos acima com `--label=antes` e o harness deve dar **exit 6, 6 falhas nomeadas**. O painel corrigido
é `git show 7fe9e8b2:src/steamzero/ui/qml/ThemeEditorPanel.qml`, sha256
`79dc0e5f68ff4008ddd0ebcd07985544b48c9974cc4fe4a11878ae5b49c790ed`, e dá **exit 0, 13 passed**.
Ao terminar, devolva o checkout ao estado do PR com `git checkout -- ThemeEditorPanel.qml` (a partir de
`src/steamzero/ui/qml`, ou o caminho completo) e confirme `git status --porcelain` vazio. Não deixe a árvore
do vermelho dentro do repositório: nada aqui depende de cópia alternativa, e `grep -rl
retrofeImportDialog src tests` deve devolver apenas o painel e os três arquivos de teste deste lote.

## Caminho canônico desta evidência

Tudo que sustenta as afirmações do lote está **dentro do checkout**, em
`docs/09-operations/evidence/2026-09-27-rc01-readiness-focus/` — inclusive os brutos (`10-`, `11-`), no
precedente da pasta `2026-09-26-rc01-central-loading/`. As versões que existiam só no host
(`~/evidence-logs/2026-09-27-rc01-readiness/`, `~/evidence-logs/2026-09-27-rc01-slice2/`) continuam lá,
com md5 declarado nos logs `05` e `06`, mas não são referência: um revisor que clone o repositório
encontra aqui o mesmo conteúdo, byte a byte.

## Pilha de PRs (dependência declarada)

`239` (RC-00, `069501ab`) → `240` (1ª fatia de RC-01, UX-01/UX-02, `c959be13`) → `241` (esta fatia,
ponta `f9256642`). Todos têm base `main` e todos seguem **OPEN**; nenhum dos 12 commits entre
`origin/main` (`3495c49d`) e esta ponta é ancestral do main, verificado um a um. Portanto o **241 depende
do 240**, que depende do 239: a ordem de integração é 239 → 240 → 241, e mesclar o 241 sem os anteriores
arrastaria o conteúdo deles. O que é novo neste PR são os cinco commits desta frente (`449b68c3`,
`7fe9e8b2`, `3fd059da`, `244bf550`, `f9256642`), dos quais **só `7fe9e8b2` toca código** — `244bf550` é
governança e `f9256642` é documental (18 arquivos, zero fora de `docs/`); o resto do histórico visível no
PR é o que já está em 239/240. Comando e resposta crua em `12-estado-dos-prs-no-sha-consultado.log`, que
tem duas leituras: 09:42 e 10:01–10:02-03:00.

## Limite honesto da evidência

* **Nada aqui é prova da release instalada no host.** As duas corridas usam
  `QT_QPA_PLATFORM=offscreen` + backend `software`: medem geometria, foco e rolagem no runtime
  Qt 6.11.2 do projeto. A `2.0.0rc1-e2af2562ebba` instalada **não** foi alterada nem revalidada
  visualmente — exige validação no host com autorização do operador.
* As capturas carregam o `ThemeEditorPanel` isolado, sem o tema do shell; os controles aparecem
  no estilo claro padrão. O que se mede é retângulo, alcance e rolagem, não cor.
* Os dados são locais e sintéticos (uma cena de exemplo, relatório de erro repetido). **Nenhum
  conteúdo real foi publicado** e nenhum caminho pessoal, acervo ou segredo entra nestes logs.
* O teste de contrato é geometria+foco no QML; não cobre toque real em dispositivo nem
  desempenho.

## Decisões de projeto registradas aqui

1. **Corpo rolável + ações no rodapé** (em vez de só ações fixas): com um relatório de erro longo
   o texto precisa ser lido por inteiro, e o primary continua sempre alcançável.
2. **A lista de layouts deixou de ser um `ScrollView` aninhado.** Medido: dentro dele o foco
   ficava preso no primeiro `RadioButton` (24 pressões de Down sem progresso), e
   `contentItem.keyNavigationEnabled = false` **não** liberava — só a remoção do scroll aninhado
   resolveu. Agora é um `ColumnLayout` simples dentro do scroll do corpo.
3. **Setas verticais são navegação do diálogo; horizontais continuam edição.** Um `Keys.onUpPressed`
   /`onDownPressed` no `ScrollView` do corpo e no `footer` chama o mesmo `moveVertical`, porque o
   rodapé **não** é descendente do corpo rolável. O passo filtra itens fora do diálogo e itens
   desabilitados, então o D-pad não atravessa para os controles atrás do modal nem empaca em
   botão desabilitado.
4. **Nenhuma conclusão geral sobre propriedades anexadas.** A dúvida de foco foi resolvida
   medindo no Qt instalado: o probe sintético não conseguia focar um `TextField` dentro de
   `Popup`, mas isso foi tratado como limite do probe — a prova veio do painel real (cenário 05),
   onde os handlers do ancestral disparam a partir de um campo focado.

## Pendências (por que isto não fecha RC-01)

* **Diálogo ES-DE** tem a mesma classe de defeito (corpo sem rolagem própria, ações que podem
  sair da moldura). Registrado, **não** alterado neste lote — fora do menor recorte.
* UX-03 (readiness) e UX-04 (unidades de armazenamento legíveis) permanecem pendentes; UX-04
  depende de `adapters/emulation.py`, reivindicado por `WS-2026-09-LIBRARY-GOVERNED-MANAGEMENT`.
* Validação visual na release instalada do host: não feita (exige autorização).
