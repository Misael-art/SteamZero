# Evidência do lote RC-01 / RetroFE dentro da shell — resposta tardia do importador (2026-09-29)

Frente: `WS-2026-09-RC01-RETROFE-SHELL-LATE`, branch
`codex/rc01-retrofe-shell-late-response-2026-09-29`, base `af6a5c6e` (ponta do PR #244),
sétimo elo da pilha #239 → #240 → #241 → #242 → #243 → #244. Item normativo:
`SZ-UI-DESKTOP-AUDIT`; eixos tocados `theme-import-retrofe.json` (RetroFE) e
`theme-import-surface.json` (superfície de importação), ambos com renovação de escopo
compartilhado registrada em vez de passada como verificação nova.

Conteúdo funcional: `dab12e95` (harness + gate desta frente), `6109fc54`
(`ThemeEditorPanel.qml`, arquivo compartilhado isolado em commit próprio, AGENTS.md §2) e
`690a1b84` (**uma linha de citação reconfrontada no harness de outra frente** — confissão
explícita: `tests/qml/check_shell_esde_import_dialog_journey.qml` está em `exclusivePaths`
de `WS-2026-09-RC01-SHELL-ESDE-DIALOG`, e a linha 22 citava
`ThemeEditorPanel.qml:968`, que as 48 linhas acrescentadas acima dela neste lote moveram
para `:1016`). Deixar a citação antiga seria publicar um endereço falso; o reparo é de
uma linha de comentário, não de asserção, e vai em commit próprio pelo mesmo precedente
de `f9ec2815` (sexto elo). O `make status-check` do checkpoint rodou com esse arquivo
alterado e devolveu `OK` porque a posse existe — no cartão da outra frente. Os hashes do voo do
checkpoint: produto `bddd117ac33fcbcf…`, harness `bc9d76d646685e20…`, gate
`0cb7744eff344587…`.

## O que o lote entrega

1. **Contrato de geração** para a resposta tardia do importador RetroFE:
   `retrofeImportGeneration` (`ThemeEditorPanel.qml:103`) incrementa em cada disparo
   (`:354`-`:355`, `:412`-`:413`) **e** em cada fechamento (`:335`); cada callback confere
   a própria geração antes de escrever (`:361`, `:373`, `:423`, `:430`). Resposta que
   chega depois de o diálogo fechar, de o pedido ser revogado ou de um segundo clique ser
   recusado por deduplicação **descarta o efeito** — o pedido em voo não é cancelado, e
   isso é limite declarado, não conquista.
2. **Rollback do dedup**: a recusa por payload idêntico devolve a geração e a bandeira ao
   valor anterior (`:392`, `:441`) em vez de escrever `retrofeImportBusy = false`
   incondicional. O verde com a escrita incondicional é exatamente o mutante M1.
3. **Gate de jornada com eventos reais**: `tests/qml/check_shell_retrofe_import_late_response.qml`
   dirigido por `tests/integration/test_ui_shell_retrofe_import_late_response.py` contra a
   ponte real em loopback com atraso por alavanca — 9 cenas (o runner fecha com
   `Totals: 11 passed`: as 9 mais `initTestCase`/`cleanupTestCase`), dez testemunhos
   obrigatórios em `TESTEMUNHOS`, `status_calls=9`, `unauthorized=0`, 8 `POST /inspect` e
   2 `POST /apply` reconciliados com `ESPERADO_INSPECT`/`ESPERADO_APPLY`.

## Arquivos

| arquivo | conteúdo |
|---|---|
| `00-vermelho-reproduzido.md` | o vermelho antes de qualquer edição, com comando e SHA do harness |
| `01-pytest-arquivo-novo.log`, `02-runner-jornada.log`, `03-ponte-jornada.log` | saídas cruas da primeira execução |
| `04-runner-ordem.log`, `05-ponte-ordem.log` | a mesma jornada com a ordem de resposta invertida |
| `06-medida-seletor-nativo-offscreen.md` | **limite medido**: sob offscreen o `FileDialog`/`FolderDialog` fica com `contentItem` nulo e não dispara `onAccepted` nem `onRejected` |
| `07-vermelho-rollback-do-dedup.md` | o segundo vermelho: botão travado em `busy=true` depois de recusa |
| `08-bateria-de-mutacoes.md` | M1, M2, M3, M4 e o guarda G, cada um com a cena que matou; M3 derruba cenas 02/04/09 **mais** o contrafactual de re-listagem |
| `09-verde-medido.md` | verde reconciliado, as duas invocações do runner, a contagem da ponte e o passo de citações (33 citações reconfrontadas) |
| `11-pytest-vermelho-rollback.log`, `12-pytest-verde.log`, `13-gates-retrofe-mais-esde-pos-citacoes.log` | saídas cruas do vermelho → verde → vizinho ES-DE |
| `14-mutante-m2-sem-rollback-de-geracao.log`, `15-mutante-m3-sem-bump-no-fechamento.log`, `16-mutante-m4-sem-porta-de-teclado.log` | cada mutante, morto |
| `17-sonda-qmltestrunner-dialogo-nativo.log`, `18-sonda-dialogo-nativo-fonte.qml` | a sonda que produziu a medição do `06` |
| `19-runner-verde-jornada.txt`, `20-ponte-verde-jornada.txt`, `21-runner-verde-ordem.txt`, `22-ponte-verde-ordem.txt` | as quatro leituras que o `09` reconcilia |
| `23-guarda-da-rota-real-vermelho-reproduzido.log` | o portão de intenção: harness chamando a função do painel em vez de tecla → `1 failed, 8 deselected` |
| `24-gates-integrais.sh` | o invólucro dos sete passos (identidade antes/depois, `.rc` por passo, marcador de conclusão) |
| `24-comandos-e-saidas.log`, `.log.rc`, `.log.concluido` | a saída crua dos sete passos com os códigos de saída (`1..7` todos `rc=0`) |
| `25-checkpoint-integral-e-gates.md` | os sete gates na árvore congelada: contagens reconciliadas (6545 + 9 = 6554 coletados; 360 + 2 = 362 visuais), as 14 leituras de identidade idênticas, o `real-state` do guarda inalterado e **duas divergências de leitura com causa medida** (a banda de ritmo sob contenção externa e o log parado por bufferização de 8 KiB) |
| `26-nextaction-verbatim-sz-ui-desktop-audit.md`, `27-nextaction-verbatim-ws-2026-09-rc01-retrofe-shell-late.md` | o texto integral que estava nos dois cartões antes da redução de `nextAction` (item 9 do operador), preservado sem cortes e conferido contra um extrato tirado **antes** da mudança |
| `28-fora-de-escopo-esde-geracao.md` | o importador ES-DE sem contrato de geração: medido (`grep -c esdeImportGeneration` = 0 contra 12), com dono nomeado e com o que o corte próprio precisa provar |
| `29-reconcilio-rc01-cinco-camadas.md` | a RC-01 critério a critério nas cinco camadas (interface / contrato offscreen / integrado / empacotado / experiência na release), com os três gaps funcionais que restam e as duas travas que não se resolvem com teste |

Também neste push, na pasta do lote anterior: `2026-09-28-rc01-storage-units/31-varredura-wheel-x-head.{md,py,log}`
(prova de **artefato** do #244: 619 entradas do wheel byte-idênticas aos blobs da cabeça,
denominador medido nos dois sentidos) e
`2026-09-28-rc01-storage-units/32-nextaction-verbatim-ws-2026-09-rc01-storage-units.md`.

## Pendências declaradas (não escondidas)

* **Integração**: nada deste lote está em `main`. `origin/main` continua `3495c49d…` e
  nenhum elo da fileira é ancestral dele. Merge é decisão do operador.
* **Release instalada**: `2.0.0rc1-e2af2562ebba` (26/09) não contém `sizes.js`,
  `readiness.js` nem o contrato de geração deste lote. Experiência comprovada na release
  instalada é **zero** para a fileira inteira.
* **Seletor nativo de diretório**: permanece **PENDENTE** — a porta por Enter é caminho
  alternativo, não prova do caminho nativo (`06`, `17`, `18`).
* **Captura visual**: nenhuma PNG é alegada aqui; `GAP-UI-VISUAL-CAPTURE-NOT-CERTIFIED-IN-CI`
  segue aberto para as fatias de 243/244 e deste elo.
* **ES-DE**: o mesmo contrato ainda não existe no importador ES-DE (`28`), e este lote não
  o corrigiu por pertencer a outra frente.
* **Primeira dobra da Home**: as três superfícies de atenção somam 209 px fixos acima do
  conteúdo (`Main.qml:3905`, `:3989`, `:4093`) e empurram `Pendências`/`Recentes` para
  baixo da dobra em 800 px. Registrado, não corrigido aqui.
