# 28 — RC-01 reconciliada critério a critério (2026-09-29, cinco camadas separadas)

Enunciado normativo: `docs/12-roadmap/IMPLEMENTATION-ROADMAP.md:38` —
"Home utilizável no orçamento aplicável; sem tela vazia enganosa; contraste essencial
conforme política; controles alcançáveis em viewport compacto e escala de texto;
timeout/retry sem corrida", com UX-01/02 e UX-03/04/05/07 mapeados em `:72-73`.

Camadas (item 8 do operador, aplicadas como colunas, nunca uma no lugar da outra):

- **I** interface implementada (código na árvore da fileira)
- **C** contrato testado offscreen (gate QtTest com eventos reais + ponte real, verde
  medido; CI no SHA da própria cabeça)
- **G** código integrado em `main`
- **P** artefato empacotado (wheel do CI, medido entrada por entrada)
- **H** experiência comprovada na release instalada no host

Medição de fundo, válida para a linha inteira: `origin/main` remoto =
`3495c49d5d7c3244267e8292beee34475f70236b` (26/09 07:55), e **nenhum** dos seis elos
abertos é ancestral dele (`git merge-base --is-ancestor` sobre `069501ab` e `af6a5c6e` →
"não está em main"). A release instalada continua `2.0.0rc1-e2af2562ebba` (`e2af2562`,
26/09 06:16), e `git ls-tree` em `origin/main` e em `e2af2562` **não** encontra
`src/steamzero/ui/qml/sizes.js` nem `readiness.js`. Portanto: **G = não** para todos os
critérios abaixo e **H = não** para todos, sem exceção, independentemente do verde.

| critério | I | C | G | P | H | situação | evidência |
|---|---|---|---|---|---|---|---|
| Contraste essencial conforme política | sim | sim (harness `check_warning_surface_contrast.qml`, tinta do cabeçalho do painel) | **não** | não | não | **parcial — e bloqueado por decisão de produto** | `2026-09-26-rc01-central-loading/14-contraste-politica-normativa.log`: os números medidos conflitam com a política (`ACCESSIBILITY.md:8` vs `THEME-ENGINE-AND-STUDIO.md:309`); adotar 4,5:1 formal ou subir tokens para ≥7:1 é decisão do operador, nenhum comportamento de tema foi alterado |
| Loading/erro/vazio explícitos, sem tela vazia enganosa | sim | sim | **não** | não | não | **parcial** | fatia UX-01/UX-02 (`#240`), gates `check_central_loading.qml` + `check_status_refresh_coalesced.qml`, CI verde na cabeça `c959be13` |
| `timeout/retry` sem corrida (renovação durante mutação) | sim | sim | **não** | não | não | **parcial** | `09-refresh-coercido.log` (vermelho → correção → verde) + integral com `real-state` idêntico |
| Custo da consulta de status (latência) | parcial | sim, medido antes/depois | **não** | não | não | **parcial — cauda de ~11,4 s dominada por `emulation` continua aberta** | `01/02-baseline-e-final-status-probe.log`; a cauda é trabalho de backend, fora das fatias de UI já entregues |
| Semântica da prontidão (UX-03) | sim | sim (contrato v2, schema, produtores, consumidores, bateria de mutações) | **não** | sim — `readiness.js` está no wheel de `af6a5c6e` e bate com o blob | não | **parcial** — F-1 (`memoryGb`) e F-2 (prosa do plano) não implementados | `#243`; `2026-09-28-rc01-readiness-semantics/`; varredura do wheel `sweep244_wheel_x_head.log` |
| Unidades de armazenamento (UX-04) | sim | sim (109 verificações, matriz de locales, mutações) | **não** | **sim, provado no artefato** — `sizes.js` 2 377 bytes, `sha256 6d5ca418…`, idêntico ao blob do head | não | **parcial** (empacotado no artefato do CI, não integrado; `statusLabel` de contagem é outro eixo, aberto) | `#244`; `2026-09-28-rc01-storage-units/`; varredura 619/619 |
| Primeira dobra da Home | sim (estrutura em `EditorialHome.qml`: `Pendências` :434, `Recentes` :471 dentro de `homeContent` :204) | sim, **com o pior caso medido e não corrigido** | **não** | não | não | **parcial — gap funcional real aberto** | `2026-09-26-rc01-central-loading/README.md` §"Ressalva de experiência": com faixa de fase + banner de perfil + cartão de falha juntos, as três superfícies escuras empurram `Pendências` e `Recentes` para baixo da dobra em 800 px |
| Foco, escala e alcance dos controles (UX-05/UX-07) | sim (viewport compacto, 48 px por alvo) | sim, **só para as superficies exercitadas** | **não** | sim (mesmo wheel) | não | **parcial — cinco superficies rolaveis seguem nao medidas** (Emulation.qml, SectionNavigator.qml, SteamGameplay.qml e os dois dialogos de ThemeEditorPanel.qml) | `#241`, `#242`; `2026-09-27-rc01-readiness-focus/`, `2026-09-27-shell-touch-targets/` |
| ES-DE dentro do shell | sim | sim para a jornada; **a resposta tardia do `inspect` continua sem contrato de geração** | **não** | sim | não | **parcial — gap funcional real aberto** | `ThemeEditorPanel.qml`: `grep -c esdeImportGeneration` = **0** contra `retrofeImportGeneration` = **12**; cinco escritas incondicionais em `panel.esdeImportBusy = false` — linhas **215** (`resetEsdeImport`), **229** e **239** (callbacks de `inspectEsdeImport`), **263** e **271** (callbacks de `applyEsdeImport`) |
| RetroFE dentro do shell | sim | sim (9 cenas, 10 testemunhos, ponte reconciliada 8+2, mutações M1/M2/M3/M4/G) | **não** | ainda **não** — este elo ainda não virou SHA nem wheel | não | **parcial** (verde local neste checkpoint; CI terminal no SHA entregue é o próximo passo) | este lote: `09-verde-medido.md`, `25-checkpoint-integral-e-gates.md` |
| Respostas tardias, reabertura, erro e recuperação | sim no RetroFE; **não** no ES-DE | sim no RetroFE | **não** | não | não | **parcial** | limite declarado: o pedido em voo **não** é cancelado — o que se descarta é o efeito (`retrofeImportGeneration` :95-103); reabertura restaura bindings; recusa por dedup devolve `ocupadoAntes` |
| Seletor nativo de diretório (entrada por diálogo) | existe na árvore (`FolderDialog`) | **não dirigível por evento sob offscreen** — `contentItem` nulo, sem `accepted` nem `rejected` (medido, `06-medida-seletor-nativo-offscreen.md`, `17-sonda-qmltestrunner-dialogo-nativo.log`) | **não** | não | não | **PENDENTE, e continua pendente embora a porta por Enter funcione** | a porta real de teclado (`onAccepted` no campo de origem) é caminho **alternativo**, não prova do caminho nativo; item 8 do operador aplicado literalmente |
| Captura visual certificada em CI | — | parcial: igualdade pixel a pixel + geografia declarada, 9 capturas byte-idênticas às baselines no artefato `qml-visual-artifacts` (run 36341332344) | **não** | — | não | **parcial — `GAP-UI-VISUAL-CAPTURE-NOT-CERTIFIED-IN-CI` segue aberto** para as fatias de 243/244/7º elo | `2026-09-27-gate-visual-causa-e-contrato/`; nenhuma PNG é alegada por este lote |

## Leitura honesta do conjunto

1. **Nada da RC-01 está integrado.** As seis camadas acima mostram por que "CI verde na
   cabeça do PR" responde a **C** e, no caso do wheel, a **P** — e não responde a **G** nem
   a **H**. A liberação instalada no host é de 26/09 e não contém `sizes.js` nem
   `readiness.js`: a experiência comprovada na release instalada é, hoje, **zero** para
   todos os critérios desta fileira.
2. **Três gaps funcionais reais** (não documentais) restam para a RC-01: (a) primeira dobra
   da Home no cenário de atenção máxima; (b) contrato de geração no importador ES-DE, que é
   o mesmo defeito já corrigido no RetroFE e ainda vivo em `esdeImport*`; (c) F-1/F-2 do
   contrato de prontidão. (d) A cauda de latência de `GET /status` é backend, e (e) as cinco
   superfícies roláveis não medidas são revalidação, não feature.
3. **Uma decisão de produto trava o critério de contraste** (4,5:1 vs ≥7:1) e **uma
   limitação de plataforma trava o seletor nativo** — nenhum dos dois se resolve com mais
   teste; resolvem-se com decisão do operador ou com prova em ambiente não-offscreen.
4. O catálogo (`docs/status/items/*.json`) registra 33 completos / 54 parciais / 5
   planejados e 13 prontos / 40 degradados / 39 desconhecidos. Esses números **não** são
   percentual de conclusão do produto: são contagem de registros por eixo, e a coluna
   integrados (`feature-branch` 31, `integrated` 51) só se move com merge, que é decisão
   do operador.
