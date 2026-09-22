# Guidance de diagnóstico na tela Sistema — 2026-09-22

## Escopo

O Doctor já publicava `what`, `impact`, `manualAction` e `action`, mas a tela
Sistema mostrava apenas nome e status. Esta entrega fecha a projeção visual
sem criar mutação: ações `system.operations` abrem a Central de tarefas e
`system.diagnostics.export` abre o fluxo de exportação, que continua exigindo
confirmação própria.

Também foi removido o caminho absoluto do state home da mensagem do check
`state.layout`. O dado técnico continua no payload local `stateHome`, mas não é
repetido no texto que a UI publica.

## Verificação

- `tests/unit/test_doctor.py` + `tests/integration/test_diagnostics.py`: **22 passed**
- UI/bridge/dashboard/diagnóstico: **97 passed**
- `QT_QPA_PLATFORM=offscreen qml6 tests/qml/check_main_handheld_sections.qml`: **passed**
- `git diff --check`: **passed**

## Comparação com a release instalada

Em rechecagem somente leitura, `/opt/steamzero/current` continuou apontando
para `2.0.0rc1-13c933c30ace`. O host publicou `staleJobs=0`,
`pendingOperations=0`, zero staging/backup/journal órfão, `deckInputKeys=false`
e `bootDirect=unknown`. A mensagem instalada de `state.layout` ainda contém o
caminho absoluto do state home; isso é esperado da release anterior e contrasta
com o canonical deste fechamento, que mantém o caminho somente no payload
técnico e o remove das mensagens dos checks.

Nenhum restart, cleanup, exportação ou instalação foi executado para produzir
essa fotografia.

## Limite

Nenhuma ação de recovery, exportação ou alteração no host foi executada. A
prova em release instalada, com foco e estado de atenção reais, permanece
`HARD-EXTERNAL-SUBITEM`.
