# Testes responsivos de UI — estado e pré-requisito

## O que existe aqui

`tst_responsive.qml` é a única suíte de teste responsivo do projeto: 15 casos
cobrindo perfis de composição, navegação por ícones, estado vazio, overlay de
carregamento, feedback de erro com impacto e ação, preferências de
acessibilidade, âncoras semânticas de seção, histórico de navegação, grafo de
foco direcional e limiares de contraste de texto.

Junto vieram 11 componentes (`AccessibilityMenu`, `AdaptiveInspector`,
`EmptyState`, `FeedbackNotice`, `LoadingOverlay`, `NavigationIcon`,
`ResponsiveFooter`, `SectionCard`, `SectionMenu`, `SectionNavigator`,
`UiTokens`) e 20 capturas golden em `../golden/`.

## Por que a suíte ainda não roda

Ela foi escrita contra uma linha de evolução do `Main.qml` que divergiu da que
foi para produção. A `main` de hoje descende de a34 → a37 (transmissão, temas,
fonte única de navegação, `requestAction` com `errorCallback`, resolução
allowlisted de assets); a suíte espera um `Main.qml` que evoluiu em paralelo,
com composição, histórico de seção e preferências de acessibilidade próprias.

Das 22 propriedades e funções de `Main` que a suíte exercita, **17 não existem
na `main` atual**:

`compositionProfile`, `displaySummary`, `doctorState`, `environmentReady`,
`filteredEmulatorItems`, `focusMainNavigation`, `goBack`,
`highContrastPreference`, `interfaceScalePreference`, `loadingOverlayVisible`,
`mainNavigationItem`, `minimumInteractiveTarget`, `motionReduced`,
`navigateToSection`, `reducedMotionPreference`, `sectionHistory`,
`sidebarLogicalWidth`.

Rodar a suíte hoje falharia por ausência de propriedade, não por regressão —
seria ruído, não sinal.

## O que NÃO foi feito, deliberadamente

Não mesclamos os dois `Main.qml`. São 1623 linhas divergentes descrevendo duas
arquiteturas diferentes de navegação e acessibilidade; a fusão cega já foi
tentada e recusada uma vez (a34) e é exatamente o tipo de mudança grande e não
verificável que produziu a regressão da a37.

Também não adaptamos a suíte para passar. Enfraquecer teste para ficar verde é
proibido por `AGENTS.md` §6, e uma suíte adaptada ao `Main.qml` atual perderia
justamente o que ela tem de valioso: o contrato de UI que a outra frente
desenhou.

## Como adotar

Convergência incremental, uma capacidade por vez, cada uma com os quatro gates:

1. escolha um bloco coerente da suíte (por exemplo histórico de seção:
   `sectionHistory`, `navigateToSection`, `goBack`);
2. implemente as propriedades correspondentes na `main`, reusando
   `navigationSections` como fonte única de seções;
3. habilite só os casos daquele bloco;
4. repita.

As capturas golden servem de referência visual para cada bloco adotado; elas não
são comparadas automaticamente hoje.

## Executor

A suíte usa `QtTest` e precisa de `qmltestrunner`, que não está no fluxo de
gates atual (`tests/integration/test_qml_handheld_offscreen.py` executa
harnesses `qml6` comuns). Ao adotar o primeiro bloco, decida se o runner entra
nos gates ou se os casos migram para o formato de harness já usado.
