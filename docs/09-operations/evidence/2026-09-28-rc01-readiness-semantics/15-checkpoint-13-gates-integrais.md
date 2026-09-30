# 15 — Checkpoint 13: os gates integrais na árvore com o harness corrigido

Instrução do operador (2026-09-28, itens 1, 4 e 8): *uma* suíte integral na árvore
congelada, sem a alterar durante a execução, preservando resultado, comando,
identidade da árvore e estado; o vermelho precisa de causa; testes focados não
substituem o resultado. Item 8: um foco por vez, sem mutar a árvore durante a
execução.

Executada em 2026-09-28 a partir das ~19:05, envoltório `/tmp/ux03_gates_14.sh`,
saída crua em `15-comandos-e-saidas.log` (232 linhas, gravadas pelo
próprio comando). Quem executou: esta frente, no checkout canônico, com o venv do
projeto (`.venv/bin/python tools/run_tests_isolated.py`).

## 1. Identidade da árvore, conferida antes e depois de CADA passo

Diferente do checkpoint 10 (identidade no topo e no pé), o envoltório desta vez
imprimiu branch, HEAD, `git status --short`, `sha256` do harness e `sha256` da
árvore `src`+`tests` **depois de cada um dos sete passos**. As sete leituras são
idênticas:

```
HEAD=ec86c228eeeb6814af2aa6363889341cfff40358
branch=codex/rc01-readiness-semantics-2026-09-28
git status --short:
 M tests/qml/check_readiness_surface.qml
sha256 harness=73c5c4cde10aa2f2
sha256 arvore(src+tests)=5939c47ca0cff1da
```

A única modificação de trabalho era o harness da UX-03 reescrito na rodada 14
(`14-geometria-transitoria-vs-assentada-e-mutacoes.md`) — produto e schemas
intactos, `git status` sem outra linha. O `run_tests_isolated.py` também registrou
o estado do HOME antes e depois de cada suíte (`files=12816`,
`bytes=1372712391`, `max_mtime_ns` idêntico): a execução não escreveu fora do tmp
delimitado.

## 2. Os sete passos, com o veredito de cada um

| # | comando | resultado | exit |
| --- | --- | --- | --- |
| 1 | `.venv/bin/python tools/run_tests_isolated.py tests -q` | **1 failed, 6484 passed, 47 skipped** em 1966,18 s (32:46) | 1 |
| 2 | `.venv/bin/python tools/run_tests_isolated.py -m visual --tb=short -q` | **356 passed**, 6176 deselected em 1307,21 s (21:47) | 0 |
| 3 | `.venv/bin/ruff check src tools tests` | `All checks passed!` | 0 |
| 4 | `.venv/bin/ruff format --check src tools tests` | `676 files already formatted` | 0 |
| 5 | `.venv/bin/mypy src` | `Success: no issues found in 298 source files` | 0 |
| 6 | `make independence boundaries` | `independência de runtime: OK` + `lint de fronteiras: OK (0 violações)` | 0 |
| 7 | `make status-check` | **FALHOU** — uma linha, o mesmo item do passo 1 | 2 |

`rc_total=1` no rollup do envoltório é o acumulado dos passos, não o código de
saída do pytest.

O passo 2 é o que interessa para o vermelho publicado: é o **mesmo comando que o
CI executa** (`-m visual`), rodado no runner real (`test_qml_handheld_offscreen.py`
com `subprocess` de 30 s por harness), e não um harness isolado chamado à mão. O
harness corrigido passou lá — `check_readiness_surface.qml` está na lista
parametrizada do gate.

## 3. A única falha tem causa medida, e a causa é desta frente

Saída bruta do passo 7 (idêntica à acusação do passo 1,
`tests/unit/test_project_status.py::test_committed_catalog_and_generated_views_are_consistent`):

```
STATUS-CHECK: FALHOU
- SZ-UI-DESKTOP-AUDIT: evidencia obsoleta; scopeDigest esperado
  5eec5ba5d84b9036a4940b8076f1c1cfd6c6aede13f4fae8a6ab191452e6e92b, atual
  e47bf54b4c82b1e141650af46027e0bbbb0953003b35ce8cd2aa5714793475a2
```

Atribuição, lida da própria ferramenta e não inferida: **um** item obsoleto, e é
o item desta frente. `tests/qml/check_readiness_surface.qml` está em `scopePaths`
de `SZ-UI-DESKTOP-AUDIT` (verificado: `"tests/qml/check_readiness_surface.qml" in
scopePaths` → `True`), então qualquer mudança honesta no harness envelhece o
digest por construção. Diferente do checkpoint 10, que tinha 33 itens obsoletos,
aqui nenhum item alheio está obsoleto — a frente não contaminou outrem.

O `atual` impresso pela ferramenta é o valor que entra no cartão (§5). Ele foi
renovado **depois** da passada documental, sobre a árvore final, porque os
arquivos de evidência desta própria pasta também estão em `scopePaths` — renovar
antes seria renovar um digest que a passada seguinte envelheceria.

## 4. O que o checkpoint prova e o que não prova

Prova: com o harness reescrito, a suíte integral não tem defeito de produto, de
formato, de tipos, de independência nem de cobertura; o gate visual — o que
reprovou no PR #243 — está verde no runner; a única falha é o guard de catálogo
pedindo renovação de digest, que é o mecanismo funcionando.

Não prova, e continua pendente: o `GAP-UI-VISUAL-CAPTURE-NOT-CERTIFIED-IN-CI`
(escala de texto 100/125/150 % na release instalada) e as duas pendências físicas
listadas no cartão. Nada aqui toca a release `2.0.0rc1-e2af2562ebba`.

## 5. O que aconteceu depois do checkpoint: só documento

Declaração exigida pelo item 4 da instrução, feita com o conjunto declarado e não
com uma promessa:

- Árvore testada = `ec86c228` + `tests/qml/check_readiness_surface.qml`
  modificado (sha256 `73c5c4cde10aa2f2`). Este é o conteúdo funcional enviado.
- Depois do passo 7, a árvore recebeu **apenas** arquivos documentais:
  `13-*.md`/`13-*.log`, `14-*.md`/`14-*.log`, `15-*.md`/`15-*.log`,
  `README.md` desta pasta, `docs/status/items/ui-desktop-audit.json` (cartão +
  digest renovado + evidências), `docs/status/workstreams/rc01-readiness-semantics-2026-09-28.json`
  e as visões regeradas por `tools/project_status.py render --write`.
- O gate de catálogo re-rodou focado depois da renovação (é o passo que estava
  vermelho por construção) e os gates de §2 foram reconfirmados na ponta, com saída
  crua em `15-gates-focados-pos-documental.log`: **70 passed** — 13 de
  `tests/unit/test_project_status.py` mais os 57 harnesses parametrizados de
  `tests/integration/test_qml_handheld_offscreen.py`, arquivo que executa
  `check_readiness_surface.qml` (13 + 57 = 70, conferido em `--collect-only`), com ruff check,
  ruff format --check, mypy, `make independence boundaries` e `make status-check`
  todos verdes, e o `sha256` do harness inalterado (`73c5c4cde10aa2f2`) — o conteúdo
  funcional testado no checkpoint é exatamente o conteúdo enviado. A integral
  **não** foi re-rodada localmente — ela volta a valer como prova no SHA
  publicado, onde o CI a executa do zero. Este é o mesmo tratamento declarado na
  rodada 12 (`12-isolamento-mainqml.md`), e é a razão de o `nextAction` exigir CI
  terminal no SHA final antes de qualquer fecho.
- Nenhum arquivo funcional (produto, schema, teste) foi tocado depois do passo 7.
  Uma mudança funcional posterior exigiria revalidação proporcional, não um
  carimbo.

## 6. Regra nova de harness, estabelecida por esta rodada

Toda asserção geométrica neste checkout passa a esperar a layout assentar por
**condição** (largura estável entre dois ticks) em vez de ler no mesmo tick da
atribuição do modelo, e nenhum pino de pixel pode carregar tolerância escolhida à
mão. A justificativa completa, com a medição, está em
`14-geometria-transitoria-vs-assentada-e-mutacoes.md`.

## 7. Consumidores do contrato v2: onde cada exigência do operador tem prova

Item 3 da instrução de 2026-09-28 pede que se **verifique** o que os consumidores
fazem, não que se repita a alegação. A tabela abaixo cita o teste pelo nome, na
árvore deste lote; cada linha foi conferida no arquivo, não no relatório anterior.

| exigência | prova (arquivo · teste) |
| --- | --- |
| numerador e denominador expostos junto com o percent | `tests/unit/test_readiness_contract.py` · `test_proporcao_medida_expoe_numerador_denominador_e_percent_juntos` (:106) |
| denominador zero → traço, nunca 100 | :120 `test_denominador_zero_produz_percent_ausente_em_vez_de_cem` · :132 `..._exige_motivo_em_vez_de_silencio` · `tests/unit/test_readiness_producers.py` · `test_workspace_denominador_zero_esconde_o_numero_em_vez_de_dizer_cem` (:153) |
| dado ausente → traço, nunca 0 | :137 `test_dado_ausente_produz_percent_ausente_em_vez_de_zero` · producers :136 `test_workspace_emulador_ausente_e_causa_e_acao_sem_fabricar_percentual` · :509 `test_plataforma_editorial_sem_jogos_nao_recebe_zero_como_medido` |
| unknown / não verificado | contract :97 `test_estado_e_verificacao_e_base_validados_em_vez_de_string_quaisquer` · :231 `test_pronto_exige_verificacao_realizada` · :398 `test_schema_recusa_pronto_sem_verificacao_realizada` · producers :454 `test_gameplay_sondagem_falha_e_verificacao_pendente_com_causa_do_dado` |
| requisitos opcionais não drenam o obrigatório | contract :153 `test_proporcao_de_requisitos_separa_obrigatorios_de_opcionais` · :197 `..._sem_nenhum_obrigatorio_e_denominador_zero` · producers :98 `test_workspace_requisito_nao_exigido_fica_fora_da_proporcao_sem_contar_pendencia` · :121 `..._pendencia_que_nao_barra_o_jogo_e_atencao_e_ajuste_opcional` · :207 `..._pendencia_bloqueante_nao_e_contada_como_ajuste_opcional` · :415 `test_gameplay_pronto_com_opcional_pendente_separa_as_duas_contagens` |
| compatibilidade com v1 (cache e fixtures) | contract :390 `test_schema_continua_aceitando_a_forma_v1_de_cache_e_fixtures` · :293 `test_normalizar_payload_legido_preserva_texto_mas_esconde_o_percent` · :315 idempotência · :321 `test_normalizar_recusa_payload_malformado_em_vez_de_derivar_zero` · :443 `test_as_duas_formas_sao_mutuamente_exclusivas` |
| nenhum percentual artificial | producers :274 `test_cloud_abridor_disponivel_nao_vira_cinquenta_por_cento` · :301 `test_placeholder_planejado_nao_divulga_zero_como_se_for_medicao` · :339 `test_composer_launchavel_nao_transforma_booleem_percentual` · :482 `test_plataforma_editorial_com_jogos_nao_afirma_prontidao_cem_por_cento` · :524 `test_fallback_do_shell_nao_fabrica_percentual_sem_medicao` · contract :414 `test_schema_recusa_numero_e_motivo_de_ausencia_juntos` |
| a UI explica o estado | `tests/qml/check_readiness_surface.qml` :371-380 (título, causa, valor e dimensão do cartão da Emulação), :536-547 (os quatro no cartão do ambiente), :290 (a ação vem do contrato), :742-767 (painel de contexto com a tinta do estado e o glifo do estado) |
| a UI oferece a próxima ação pertinente | `Emulation.qml:456` `readinessAction()` → pino renderizado `readinessAction` (:450); `SteamGameplay.qml:1184` → pino `gameplayReadinessAction` (:577); `testPainelNaoRepeteAProximaAcao` (:823) garante que a ação não é duplicada como bloqueio |
| prontidão ≠ jogabilidade certificada | contract :236 `test_pronto_exige_base_de_evidencia_declarada` · :243 `test_pronto_com_base_de_mera_existencia_e_recusado` (`READY_BASES`) · :258 `test_bases_de_existencia_continuam_legitimas_para_outros_estados` · :271 `test_pronto_legitimo_nao_e_bloqueado_pelo_contrato`; e o mecanismo na tela é o nome da grandeza (`Readiness.dimensionCaption`, `Emulation.qml:3381`, `SteamGameplay.qml:1149`): o cartão diz **o que** foi medido, então "12 de 14 requisitos da plataforma" nunca se lê como "o jogo roda" |

O que a tabela **não** cobre, e continua pendente: `GAP-UI-VISUAL-CAPTURE-NOT-CERTIFIED-IN-CI`
(escala de texto na release instalada) e as pendências físicas
(`GAP-UI-LIVE-LAUNCHER-ROUTING`, `GAP-HARMONIZE-SCOPE-PHYSICAL-EVIDENCE-PRECEDES`).
