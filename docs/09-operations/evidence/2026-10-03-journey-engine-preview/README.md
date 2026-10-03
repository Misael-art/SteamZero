# Preview da composição de Jornada — 2026-10-03

## Escopo e estado

Este registro documenta uma extensão local/offscreen do painel de Jornadas no
checkout `/home/misael/Projects/Steam Zero/Canonical/2026-09-21`, branch
`codex/v1-v3-theme-journey-2026-10-01`, baseado em
`09033bd5919f25317ff4449b8426f0223e21cecd`. O delta funcional foi commitado
localmente em `461499d43322f6b8e3d68a2cddaa5bf98ef8e583`; não foi enviado,
instalado ou validado fisicamente.

### Atualização da branch — bridge e resolver native

Depois do registro inicial deste diretório, a branch acrescentou ações
allowlisted `journey.studio.*` ao `DesktopControlServer`. O harness QML usa o
catálogo de contratos e faz requests autenticados por loopback; cria menus,
aplica filtros e bindings, salva/reabre a jornada e exporta/importa uma cópia.
Isso é prova da bridge no checkout, não da release instalada.

`journey.studio.engine-preview` lê novamente a jornada pela geração esperada,
calcula a consulta a partir do read model público no servidor, resolve a
cobertura da etapa e chama `DesktopDashboard.editor_preview` com o modelo
filtrado em `preview.items`. O `ThemeEditorManager` resolve os bindings nativos
de `sceneLayouts`; `ThemeStudioCanvas` consome a mesma composição. O teste de
round-trip reabre uma jornada filtrada por gênero, usa o tema
`org.steamzero.asset-recipes-demo` e verifica que `previewTitles` contém apenas
`Synthetic Platformer`, sem `Axiom Verge`. Temas ausentes/incompatíveis usam
AURA com diagnóstico. Cada sessão de tema aberta para a consulta é cancelada.

Um segundo round-trip cria um tema filho de `asset-recipes-demo`, altera
`previewTitles.maxItems` para 2 no Theme Studio, salva e reabre o pacote, e então
executa a mesma jornada no Theme Engine. A prévia recebe os três registros
filtrados, materializa apenas os dois primeiros e mantém a edição persistida. A
cobertura avalia `sceneSurfaces` herdado pela cadeia `extends`, então a herança
visual não é tratada como slot ausente.

A mesma route retorna manifesto, declaração, preview e coverage. O read model
aceita somente campos já publicados e projetados pelo servidor; nenhum registro
arbitrário vem do QML. Os probes do dashboard determinam `highContrast` e
`reducedMotion` no preview normal. A rota também valida a geração antes/depois
da consulta. O canvas corre em Qt offscreen; não medimos pixels de release,
frame time, VRAM ou input físico.

## Testes focados

```text
rtk .venv/bin/python tools/run_tests_isolated.py \
  tests/unit/test_theme_editor.py \
  tests/integration/test_experience_journey_bridge_e2e.py \
  tests/integration/test_experience_journey_e2e.py \
  tests/integration/test_desktop_ui_bridge.py \
  tests/integration/test_ui_action_inventory.py \
  tests/unit/test_desktop_contracts.py \
  tests/unit/test_journey_studio.py \
  tests/unit/test_experience_journey.py \
  tests/integration/test_theme_authoring_e2e.py \
  tests/integration/test_theme_scene_runtime_e2e.py -q --tb=short
132 passed em 56,14 s
```

Guard real antes/depois: `files=12818`, `directories=2068`,
`bytes=1372834271`, `max_mtime_ns=1791029212908907544`.

O teste da bridge cria quatro menus, três conexões para um destino compartilhado,
filtros por gênero e ano, salva/reabre e testa a cena native com o resultado
reaberto. A projeção preserva o registro selecionado e omite o path privado. O
harness do componente cobre bridge ausente, resposta tardia, erro visível e
retry. O teste de autoria de tema e o teste separado do renderer de cena foram
repetidos para preservar os fluxos já existentes.

O caso de tema editado verifica separadamente a persistência do manifesto, a
declaração efetiva reaberta e os itens realmente materializados pelo Engine.

O harness de autoria mede o `GET /status` contra `DesktopControlServer`. Três
leituras reais do snapshot completo levaram 4,95 s, 5,52 s e 6,18 s. A espera QML
desse caso foi ajustada de 5 s para 10 s, continuando a exigir a resposta do
servidor; a execução isolada passou em 27,85 s. A repetição do conjunto focal
depois das correções passou com 132 testes.

O primeiro gate integral após publicar as ações da bridge terminou com
**6593 passed, 47 skipped e 1 failed em 3367,80 s**. A única falha foi
`tests/unit/test_capability_matrix.py::test_committed_matrix_matches_the_code`:
o documento gerado listava 137 ações enquanto o código já publicava 151. A
matriz foi regravada pelo comando previsto (`make update-capability-matrix`),
o delta revisado foi de 14 ações `journey.studio.*`, e o teste focal passou
**7/7**; `make capability-matrix` também passou.

A repetição integral final passou: **6594 passed, 47 skipped, 0 failed em
2420,39 s (40:20)**, código de saída 0. O guard ficou idêntico antes/depois:
`files=12818`, `directories=2068`, `bytes=1372834633`,
`max_mtime_ns=1791031942518989555`. O log bruto está em
[`full-tests-2026-10-03.log`](full-tests-2026-10-03.log); a falha intermediária
e seu diagnóstico estão em
[`full-tests-2026-10-03-matrix-drift-failed.log`](full-tests-2026-10-03-matrix-drift-failed.log).
Na primeira janela, o guard identificou escritas externas em `logs/core.jsonl`
e `state.db` pelo daemon da release já ativo; a repetição final partiu do estado
resultante e não detectou nova escrita durante os testes.

## Liberação serial necessária

| Path | Delta mínimo restante | Dono/dependência | Prova de liberação |
|---|---|---|---|
| `desktop_contracts.py`, `desktop_ui.py` | ações allowlisted e bridge autenticada, incluindo `engine-preview`, publicadas nesta árvore | integração serial do workstream atual; sharedPaths devem permanecer no commit de integração | loopback verifica edição, round-trip, geração, fallback de referência ausente e cena native com linhas filtradas; shell Main/instalada ainda não exercitada |
| `desktop_dashboard.py`, `theme_editor.py` | `editor_preview` recebe read model público e usa probes do dashboard; tema editado/reaberto e `sceneSurfaces` herdados alimentam o resolver native | integração local comprovada pelos testes de bridge, sem build/instalação | testar a mesma composição pela janela Main instalada e medir pixel/tempo em hardware/release |
| Launcher e Cinema | consumir grafo, filtros, tema/slot e contexto persistidos | LauncherShell/Main/Home seguem com owner codex-aura-launcher-exit ativo | mesmo documento no Launcher, retorno de contexto, saída/recuperação |
| sessão e adapters | ligar ações semânticas a capacidades reais de launch/pause/resume/save/load/exit | bridge e contratos atuais de adapter | sucesso, falha, timeout, late response, capability ausente e preservação do host |

`desktop_contracts.py`, `desktop_dashboard.py` e `desktop_ui.py` compõem o
commit funcional local `461499d`; `Main.qml`, Launcher e adapters de sessão não
foram alterados. Theme Engine, Studio, Launcher/Cinema e sessão permanecem
parciais.

## Estado do checkout e da release instalada

Ponteiros locais lidos em 2026-10-03, antes do commit funcional abaixo e sem
fetch:

| Superfície | Identidade observada | Situação desta entrega |
|---|---|---|
| Branch | `codex/v1-v3-theme-journey-2026-10-01` | HEAD observado antes do commit: `09033bd5919f25317ff4449b8426f0223e21cecd`; checkpoint funcional local posterior: `461499d43322f6b8e3d68a2cddaa5bf98ef8e583` |
| Ref local `origin/main` | `c9d3196bab819ad9a9b9f602bb5257f40c60a7b7` | ref local não atualizada durante esta continuação; nenhum push foi feito |
| Ref local da branch remota | `9bd5947c1e75a319191948b11be36c5398881fc8` | ref de acompanhamento local não atualizada; nenhum push foi feito |
| Ponteiro instalado | `/opt/steamzero/current` → `/opt/steamzero/releases/2.0.0rc1-5715d7962691` | a branch desta entrega não está instalada; ponteiro apenas lido |

O checkout e `/opt/steamzero/current` são superfícies distintas. Esta revisão não
abriu uma instância do código-fonte nem atribui à release instalada as mudanças
locais. O inventário KWin consultado sem input não encontrou janela do SteamZero;
o desktop estava em outra aplicação. A interação física foi pausada antes de
ativar uma janela ou guardar captura. Isto é um bloqueio ambiental da inspeção,
não um defeito observado no produto.

## Capacidade entregue, prova e gap

| Capacidade | Comportamento pela UI/serviço | Prova local e identidade | Artefato | Prova física | Gap restante |
|---|---|---|---|---|---|
| Documento de Jornada v2 | editor cria menus conectados, filtros e bindings públicos, sort, agrupamento, temas por etapa, histórico e arquivo | QML de autoria dirigido contra bridge autenticada real por loopback; focados passaram | `ExperienceJourneyPanel.qml`, `JourneyStudioService`, schemas v1/v2, teste bridge | não executada fisicamente | branch não instalada; navegação/retorno no Launcher pendentes |
| Preview de consulta | mostra contagem, diagnóstico/recuperação e até 64 linhas públicas filtradas | loopback contra `DesktopControlServer`; QML exercita erro, late response e retry | `check_experience_journey_bridge_e2e.qml` | não executada | shell Main e release instalada não exercitadas |
| Cena XML ES-DE | componente fornece o modelo filtrado ao renderer existente sem substituir a resposta compilada | contrato/harness do componente e teste isolado de `SceneEsdeView`; round-trip não provado nessa bridge | `ThemeScenePreview.qml`, `check_theme_scene_preview.qml` | não executada | precisa de prova loopback do documento persistido/reaberto na cena XML |
| Cena native `sceneLayouts` | bridge envia rows públicos filtrados ao ThemeEditorManager; tema editado/reaberto limita a lista e `ThemeStudioCanvas` usa a resolução resultante | teste loopback round-trip verifica filtros, fallback, herança de superfícies e edição persistida | ação `journey.studio.engine-preview`, `test_experience_journey_bridge_e2e.py` | não executada fisicamente | sem oracle de pixels, tempo ou release instalada |
| Cobertura visual/AURA | ação native retorna cobertura; tema/slot ausente cai em AURA com causa | `ThemeEditorManager` real na bridge; ausência de tema produz `theme-reference-missing` e fallback declarado | `journey.studio.engine-preview`, testes bridge | não executada fisicamente | capabilities de sessão desconhecidas; falta janela Main instalada |
| Theme Engine/Launcher/Cinema | Engine native recebe o documento reaberto; Launcher/Cinema ainda não consomem Jornada | prova local do resolver Engine; nenhuma prova no Launcher/Cinema | checkout desta branch | não executada | handoff serial ao workstream Launcher e integração session/adapters |
| Sessão de jogo | aparência declarada é separada de launch/pause/resume/save/load/exit | contratos de domínio apenas; nenhum adapter acionado por este fluxo | `experience_journey.py` | não executada | capabilities precisam vir do adapter e as transições aguardarem seu resultado |

SHA-256 dos arquivos que sustentam esta prova local:

```text
404f36be3a2cfdf42c3d3e7dd2dc0f841b30d15022e4bf761f34d2843e334e32  src/steamzero/ui/qml/ExperienceJourneyPanel.qml
9fdc6690c6729a72ef3e815997285103ff01008c27fb5993e2ca4ceeca8b435d  src/steamzero/ui/qml/ThemeScenePreview.qml
3a969e0b6b62c928df7df8364e90620770ed769380d937cbc4f395362efcf7bf  src/steamzero/adapters/desktop_contracts.py
03e76864b802480abc5f974ae4f4ac4f65c0196f87554b741757d3e8ace8db39  src/steamzero/adapters/desktop_dashboard.py
eba075e766946e804f93df5b3a0cf1af6ac0abf4d029ed4d32bbf201f26fce69  src/steamzero/adapters/desktop_ui.py
1cf72884b90322f90181f2a37735a6c130ed3f8e133ea9f853b9433fb9347769  src/steamzero/adapters/journey_studio.py
66991eaca917da754c6a37f49b70f978e30e248a58eb19cfad1b6989177bfc14  src/steamzero/domain/experience_journey.py
3157beef5e138d67359ea721bfdca58d99e1f1ddcd74014e5b2f99eeff775fa5  src/steamzero/domain/theme_editor.py
f7067d0e151c04e2835c32bfb46ee9404edffccd9986b0b3bf0956d7a5830266  src/steamzero/schemas/experience-journey-v1.schema.json
625a33daac5decf60ce85b6b576fc923366c4cdfcfceb3185e6a8fffa614909f  src/steamzero/schemas/experience-journey-v2.schema.json
03dc16b6ebc921dac164aa059dac9f4606c90908f88be9515ee87621000576e7  tests/integration/test_experience_journey_bridge_e2e.py
ded5fe990f214bad3e588fd7b264558fe5f0d61e9098a2a0dc1f36ffdef3032c  tests/qml/check_theme_scene_preview.qml
8cb3cb23ec87e32b8ce8b77f0dacfaa87ab8516960d34bd692a05ad7e2bd1be6  tests/integration/test_experience_journey_e2e.py
de9c5644ad95fb54e9bd761a6b21789dd04a6c8ebe318c351d9dcea712b5fdc8  tests/integration/test_theme_authoring_e2e.py
069402c55b50ad62b3153699a64dd8f846a4321bfeda787dd3c7b3dc4366d91a  tests/qml/check_experience_journey.qml
3e63df4269e7e015d037d5b0590bb85f328bdcb82f313685fef4e84fa26ce9ee  tests/qml/check_experience_journey_bridge_e2e.qml
df460db0ff4c99ade8b577ff4a47f88cc64d14855cf2049742066110f2944b16  tests/qml/check_theme_authoring_e2e.qml
9cc1389f73609a7f5c78bab11e22d7939f5265c69ad809819b031b092bee6f78  tests/unit/test_experience_journey.py
bab1885198689f2042729f7dc5f980b8ebae90f23091e2f5fe9f3a2fa265204e  tests/unit/test_journey_studio.py
5ec1d14ac598bdcdad2803e3476513e40e9fd6290228860af16be83845e47c41  tests/unit/test_theme_editor.py
```

Os testes focados de bridge/Engine passaram: **132 passed em 56,14 s**, com
guarda XDG idêntica. Depois, `tests/unit/test_capability_matrix.py` passou
**7/7** após a matriz ser regenerada. O resultado integral final está registrado
acima com seu log bruto. A primeira tentativa integral posterior falhou somente
pela matriz gerada obsoleta; a correção não alterou código de runtime e a rodada
final aprovou todos os testes. O registro histórico de execuções anteriores
continua no [`WORKLOG.md`](../../../WORKLOG.md).

## Matriz de etapa, aparência e capacidade operacional

| Etapa usada | Tema declarado | Origem esperada | Motivo/fallback | Capacidade operacional |
|---|---|---|---|---|
| `menu:<id>` | custom, herdar AURA, ou omitido | tema do menu; AURA se omitido/herdado | referência ausente e cena/slot incompatível precisam diagnóstico separado | não requer operação de sessão |
| `entryFade` | `sessionStages` ou omitido | tema atribuído ou AURA | sem declaração, AURA por padrão | fade não confirma launch |
| `gameplay` | `sessionStages` ou omitido | tema atribuído ou AURA | sem declaração, AURA por padrão | launch depende do adapter |
| `pause` | `sessionStages` ou omitido | tema atribuído ou AURA | sem declaração, AURA por padrão | pause depende do adapter |
| `saves` | `sessionStages` ou omitido | tema atribuído ou AURA | sem declaração, AURA por padrão | listar/salvar/carregar dependem de capabilities distintas |
| `bezel`, `osd` | `sessionStages` ou omitido | tema atribuído ou AURA | bezel ainda não tem slot declarativo no contrato atual | exibir não habilita controle do jogo |
| `exitFade` | `sessionStages` ou omitido | tema atribuído ou AURA | sem declaração, AURA por padrão | fade não confirma término |
| `loading`, `empty`, `error`, `offline` | `sessionStages` ou omitido | tema atribuído ou AURA | falta de componente deve aparecer como incompatibilidade/fallback | estado visual não prova operação |

Nesta árvore, a bridge monta manifestos para cobertura visual e separa esse
resultado das capabilities operacionais. O adapter da sessão ainda não fornece
capabilities nesta rota; nenhum badge visual prova pause, saves, bezel ou exit.

## B_VISUAL da Jornada — roteiro preparado, não executado

Pré-condição para retomar: integrar e identificar uma release governada que
contenha o checkpoint desejado, autorização específica vigente para instalação e mesa
sem atividade simultânea. A release apontada agora é a base anterior; esta branch
não foi instalada. Na inspeção read-only de 2026-10-03, a mesa estava ocupada por
outra aplicação e não havia janela SteamZero identificada; nenhum input foi
enviado e nenhuma captura do desktop foi mantida.

Roteiro depois que a bridge, os consumidores e a candidata estiverem disponíveis:

1. Confirmar release/SHA, rollback, daemon/doctor, resolução, escalas, locale,
   tema ativo, dispositivo de input e estado XDG; identificar a janela instalada.
2. Criar um documento sintético por controles acessíveis: **Plataformas → Jogos**,
   **Gêneros → Jogos**, com pelo menos três menus, submenu compartilhado, IDs
   estáveis e ordenação. Adicionar filtros combinados e um campo público novo via
   catálogo; observar desconhecido, zero resultados e fonte indisponível.
3. Selecionar uma plataforma e um gênero e confirmar que os bindings restringem
   o menu de Jogos. Voltar por ambos os percursos e comparar filtro, seleção,
   rolagem e foco com a origem correta. Testar um ciclo de input válido e um ciclo
   automático sem saída; registrar diagnóstico e recuperação.
4. Atribuir temas diferentes a menu, gameplay e bezel; deixar pausa, saves e
   fades sem atribuição. Antes de aplicar, conferir contagem AURA, origem/versão,
   motivo e acesso a personalizar; remover uma referência e declarar um slot
   incompatível para observar diagnósticos distintos.
5. Editar efeito e movimento no tema, desfazer/refazer, salvar, fechar, reabrir,
   exportar/importar como cópia e executar exatamente esse documento na Preview
   e na Engine. Capturar a cena, conferir seleção, pixels/tempo, asset ausente,
   binding ausente, tier reduzido, `highContrast` e `reducedMotion`.
6. No Launcher/Cinema, abrir o mesmo documento isolado, percorrer os menus,
   confirmar retorno contextual e testar loading/vazio/erro/offline. Não agregar
   biblioteca pessoal, iniciar jogo real ou alegar sessão operacional a partir de
   uma transição visual.
7. Com adapter controlado e conteúdo seguro, testar launch, pause/resume, save e
   load separados, exit, capacidade ausente, falha, retry, timeout e resposta
   tardia. Repetir resposta obsoleta e atual: descarte só a obsoleta e preserve a
   resposta válida; conferir busy, geração, foco e retorno ao contexto.
8. Repetir navegação com teclado e gamepad separadamente. Registrar cada cenário
   como passou/falhou/não executado/inconclusivo, com release, passos, artefato,
   log, input e hash. Não inferir contraste, área de toque, FPS ou resolução.

| Critério físico | Estado em 2026-10-03 | Bloqueio/resultado |
|---|---|---|
| B_VISUAL preparação e identificação da janela | parcialmente observado, sem input | mesa ocupada por outra aplicação; janela SteamZero não identificada |
| Journey UI, três menus e bindings | não executado fisicamente; loopback local passou | branch com Jornada v2/bridge não está instalada |
| Retorno contextual na UI/Launcher | não executado fisicamente | consumidor Launcher e estado de sessão não integrados |
| Cobertura/herança AURA e erro/recuperação | não executado fisicamente; fallback de tema ausente passou por loopback | exige candidata instalada e input observado |
| Mesmo tema salvo/reaberto em Preview/Engine | resolver native passou por loopback no checkout; pixels físicos não executados | branch e bridge não estão na release ativa |
| Launcher/Cinema | não executado | consumidor e seleção de Jornada não integrados |
| sessão, capabilities, teclado/gamepad | não executado | adapters reais não ligados a este fluxo; gamepad não observado |
| capturas e hashes físicos | não produzido | nenhuma captura foi feita/guardada durante esta inspeção |

Nenhum defeito físico de Jornada foi confirmado nesta inspeção. As ausências
acima são provas não executadas ou integração ainda inexistente, não aprovação.

### Matriz física RC-01 solicitada pelo roteiro B_VISUAL

| Critério | Estado | Razão objetiva e próxima observação segura |
|---|---|---|
| A. Loading, erro e retry | não executado | não abri a aplicação; na candidata, observar estados reais e só provocar erro por mecanismo já disponível |
| B. Prontidão v2 | não executado | não há leitura visual da aplicação nesta rodada; comparar estado conhecido/desconhecido/bloqueado no dado publicado |
| C. Unidades de armazenamento | não executado | quatro vistas e valores subjacentes precisam ser observados na janela instalada |
| D. Primeira dobra da Home | não executado | requer janela da aplicação e escalas oferecidas; não foi redimensionada nenhuma janela |
| E. Foco, escala e rolagem | não executado | Tab/setas/rolagem e gamepad não foram enviados; cinco superfícies ainda precisam ser medidas separadamente |
| F. Importação ES-DE/RetroFE no shell | não executado | nenhuma fixture foi importada nem diálogo aberto |
| G. Seletor nativo | não executado | nenhum `FolderDialog`/`FileDialog` foi aberto |
| H. Resposta tardia e geração | não executado fisicamente | exige operação real com correlação observável; harness QML não substitui a ordem observada na sessão |
| Theme Studio, catálogo, temas portados e AURA Cinema | não executado | janela SteamZero não identificada; nenhum consumidor foi ativado |

Classificação de achados físicos: nenhum achado de produto confirmado. O único
resultado é ambiental: havia outra aplicação em primeiro plano e a listagem de
janelas não identificou SteamZero; por segurança, não houve input.
