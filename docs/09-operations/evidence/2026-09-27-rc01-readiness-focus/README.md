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
| `05-gates-rapidos.log` | os cinco gates rápidos do checkpoint: `ruff check`, `ruff format --check` (671 arquivos), `mypy src` (297 arquivos) e `make independence boundaries` verdes na primeira passada; `make status-check` reprovou 5 digests + 3 visões — ordem de escrita, não comportamento |
| `06-checkpoint-integral.log` | a **única** suíte integral: comando, janela 08:50:33→09:21:16, `1 failed, 6402 passed, 47 skipped`, rc=1, fingerprint da árvore idêntico no lançamento e no fim (`ee04994d…`), state home do operador byte a byte igual, a reconciliação `6397 + 5 = 6402` e o que a corrida não cobre |
| `07-status-final.log` | a coerência final do catálogo: os cinco digests renovados pela ferramenta, as três visões regravadas, `STATUS-CHECK: OK` e `13 passed` em `tests/unit/test_project_status.py`, com o limite auto-referente declarado |
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

Para o "vermelho", troque `src/steamzero/ui/qml/ThemeEditorPanel.qml` pelo painel sem a
correção (sha256 `13d5c644ce82d36c357b0d9d957078ca6c22b849ffb0826c412292e808c36140`, já com a
superfície de teste) e rode os dois comandos com `--label=antes`. O painel corrigido mede
sha256 `79dc0e5f68ff4008ddd0ebcd07985544b48c9974cc4fe4a11878ae5b49c790ed`.

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
