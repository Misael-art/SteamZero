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

## Limite

Nenhuma ação de recovery, exportação ou alteração no host foi executada. A
prova em release instalada, com foco e estado de atenção reais, permanece
`HARD-EXTERNAL-SUBITEM`.
