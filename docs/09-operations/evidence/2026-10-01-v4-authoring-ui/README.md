# Edição e execução de tema: prova local e roteiro B_VISUAL

## O que esta rodada prova

O teste `tests/integration/test_theme_authoring_e2e.py` abre o `ThemeEditorPanel`
real em um harness QML e envia `mouseClick`/`keyClick` aos controles visíveis. A
ponte usa um `DesktopControlServer`, `DesktopDashboard`, `ThemeEditorManager` e
`ThemeBridge` reais; os dados e a configuração ficam em `XDG_DATA_HOME` e
`XDG_CONFIG_HOME` temporários. O renderer testado é o caminho da **AURA UI**:
`EditorialLibrary` → `MediaEffectLayer`, alimentado pelo `/status` publicado
depois da aplicação explícita do tema.

A biblioteca contém somente um registro sintético e a imagem PNG CC0 de
`tests/fixtures/themes/esde-mini/fundo.png`. Nenhuma biblioteca ou preferência
pessoal é lida pelo teste. A execução usa Qt 6.11.2, plataforma `offscreen` e
renderer software. É uma prova de UI QML e pixels no checkout, não de input
físico, release instalada, sessão gráfica real ou AT-SPI.

O ciclo exercitado pela UI é:

1. Duplicar o tema padrão e editar a pilha de mídia: adicionar blur e vinheta,
   mudar `radius=24` e `strength=0.9`, reordenar, escolher o fallback `minimal`;
   abrir o seletor AURA existente, aplicar `#336699` a uma sombra temporária,
   rejeitar `#zz0000` sem alterar documento/histórico e remover essa sombra.
2. Editar movimento: criar o estado nativo `loading` com `scale=1.2`; criar e
   remover uma timeline de rascunho; criar `entrada` como `parallel`, mudar para
   `sequence`, configurar duas repetições, editar estado/duração dos clips,
   movê-los para cima/baixo, rejeitar duração `9999` e remover um clip.
3. Conferir `dirty`, desfazer/refazer, salvar, fechar e reabrir; a declaração
   semântica reaberta deve ser igual à salva.
4. Aplicar o tema explicitamente à central e confirmar pelo `/status` que a
   bridge publicou o ID escolhido. O `MediaEffectLayer` recebe a vinheta salva;
   a imagem aplicada escurece a borda. O teste compara a soma das médias RGB:
   a borda precisa cair mais de 15 pontos e o controle central pode variar menos
   de 12.

Os valores numéricos e as escolhas fechadas vêm de schemas gerados pelas mesmas
regras de domínio que validam efeitos e movimento. Entradas fora de faixa
mostram os limites e voltam ao valor aceito sem criar histórico; uma cor inválida
é recusada pelo domínio e também preserva documento, histórico e seleção.

## Capturas

Todas são capturas do harness QML/software, não fotografias da sessão instalada.
Os arquivos e hashes estão em `SHA256SUMS`.

| Arquivo | Conteúdo |
|---|---|
| `01-studio-efeitos-movimento.png` | Inspetores de efeito e timeline, estado `loading` selecionado e `scale=1.2`; painel 1100×900. |
| `02-studio-compacto.png` | Controles de efeito acessados com a janela 640×560 e coluna rolável. |
| `03-studio-binding.png` | Binding `text ← item.genre` ligado pela UI e exibido no inspetor. |
| `04-studio-compact-movimento.png` | Timeline e clips no viewport 640×560, incluindo seleção de estado e duração. |
| `05-theme-runtime-baseline.png` | Fixture desenhada pelo `MediaEffectLayer` antes de aplicar a vinheta. |
| `06-theme-runtime-aplicado.png` | Mesma mídia depois da aplicação da declaração salva. |
| `07-aura-library-theme-applied.png` | Superfície completa `EditorialLibrary` com fixture sintética e tema ativo. |
| `08-studio-seletor-cor.png` | Diálogo AURA de seleção de cor, aberto pelo controle de sombra. |
| `09-studio-vinheta-editada.png` | Receita final de vinheta visível no inspetor: fallback `minimal`, cor e força `0.9`. |

## Correção do alvo interativo

Na medição anterior à correção, o harness QML observou `effectAdd` em
**120,125 × 40 px** e `bindingApply` em **55,766 × 40 px**, na escala 1,0. O
helper antigo aceitava alvos de 40 × 36 px, embora a §16 da especificação exija
48 × 48 px.

O helper agora mede e exige 48 × 48 px para botões, seletores, campos e controles
numéricos; mede também os alvos de incremento e decremento do `AuthRangeSpinBox`
e exercita ambos por eventos Qt. A execução atual verificou **44 alvos**, com
menor dimensão de **48 × 48 px**, nas escalas 1,0 e 1,5. O passe compacto usa
640 × 560 px, rolagem até o controle e revelação/foco após ampliar os alvos. A
integração QML passou (1 teste, 14,43 s) e o guard do estado real permaneceu
idêntico antes/depois (`files=12818`, `directories=2068`,
`bytes=1372818509`, `max_mtime_ns=1790888510663329431`).

Esta é uma medição de layout e automação Qt no harness `offscreen`; não é input
físico. Os arquivos de captura foram renovados para esta correção e continuam
identificados como evidência de harness.

Os mesmos mínimos também alteram controles dos diálogos de importação ES-DE e
RetroFE. A rodada compacta combinada passou **13 testes em 6,39 s**, incluindo
alcance por evento Qt, geometria dentro dos viewports e capturas de ambos os
diálogos. A primeira captura RetroFE divergiu dos goldens antigos (71.999 a
137.547 pixels, conforme viewport); as quatro baselines RetroFE foram atualizadas
somente depois de inspecionar as capturas de 949×593 e 1280×800. A repetição
terminou com pixel diff zero nos quatro viewports e **13/13 testes passaram**. A
mudança visual corresponde aos alvos efetivos maiores; o corpo e as ações
continuaram alcançáveis. O gate continua sendo harness Qt, sem input físico.

## Comandos e resultados focados

```bash
rtk .venv/bin/python tools/run_tests_isolated.py tests/unit/test_theme_effect_authoring.py -q
rtk env SZ_CAPTURE_DIR="<diretório-de-evidências>" .venv/bin/python tools/run_tests_isolated.py tests/integration/test_theme_authoring_e2e.py -q
```

Na última execução focada, passaram: 10 testes de autoria de efeitos/movimento
(1,20 s), mais 68 testes de `theme_editor`, `scene_motion` e `theme_effects`
(1,54 s), a jornada QML (14,08 s) e os 2 testes separados de cena importada
(2,20 s). O guard observou o estado real idêntico antes/depois
(`files=12818`, `directories=2068`, `bytes=1372818509`). Essa validação pertence
à árvore de trabalho atual.

No checkpoint integral da árvore congelada desta entrega, `.venv/bin/python
tools/run_tests_isolated.py tests -q` terminou com **6560 passed, 47 skipped em
2302,24 s**. O guard do estado real permaneceu idêntico antes/depois
(`files=12818`, `directories=2068`, `bytes=1372818509`, `max_mtime_ns=1790888510663329431`).
Também passaram `ruff check src tools tests`, `ruff format --check src tools
tests` (689 arquivos), `mypy src` (299 arquivos), `make independence
boundaries`, `make status-check` e `git diff --check`. O checkpoint anterior de
6557/47 continua como histórico, não como resultado desta árvore.

`tests/integration/test_theme_scene_runtime_e2e.py` é uma prova separada:
`SceneEsdeView` decodifica fixtures válidas/licenciadas ES-DE e RetroFE e verifica
pixels. Ela não executa o tema criado nesta jornada. `SceneEsdeView`/Theme Engine,
AURA Launcher e AURA Cinema não são promovidos por capturas da AURA UI.

## Roteiro B_VISUAL para a release autorizada

**Pré-condições:** usar a release construída do SHA completo que será informado
após os gates e o CI; verificar que o manifesto do pacote aponta para o mesmo
`sourceCommit`; registrar release, digest, sessão, resolução e escala. A prova
requer instalação governada autorizada pelo operador. Não instalar nem publicar
esta branch por este roteiro. A release observada antes deste lote era
`2.0.0rc1-5715d7962691`; o rollback preservado era
`2.0.0rc1-e2af2562ebba`. Nenhuma delas contém as mudanças atuais.

Use um perfil de teste isolado e uma mídia sintética licenciada na sessão gráfica
real. Não aponte o teste para a biblioteca Steam pessoal nem ative ações de jogo.
Se a release não oferecer um modo isolado para essa mídia, registre a etapa de
runtime como pendente em vez de alterar a biblioteca pessoal.

1. **Sucesso:** abrir a central instalada; duplicar o tema padrão; no Studio,
   adicionar blur e vinheta, ajustar `24`/`0.9`, escolher `minimal`, abrir o
   seletor AURA, alterar a cor de uma sombra e removê-la. Criar o estado
   `loading`, configurar `scale=1.2`, criar `entrada`, editar tipo/repetição e
   pelo menos dois clips. Navegar pelos controles com mouse e teclado; repetir
   com gamepad quando o foco estiver disponível.
2. **Persistência:** conferir `Não salvo`, desfazer/refazer, salvar, fechar,
   reabrir e comparar os valores. Capturar Studio, seletor de cor, catálogo e
   versão da release.
3. **Execução central:** aplicar explicitamente a cópia à central; observar a
   mídia sintética na `EditorialLibrary` e registrar se a vinheta altera a borda
   da imagem. Restaurar a preferência anterior ou encerrar o perfil temporário.
4. **Erro e recuperação:** inserir um valor numérico acima do limite; confirmar
   mensagem com faixa, valor anterior, seleção e histórico preservados. Digitar
   hexadecimal inválido; confirmar mensagem do domínio e restauração do campo.
   Corrigir, salvar/reabrir e capturar o erro e a recuperação.
5. Registrar input físico e foco. O seletor desta tela é o diálogo AURA existente;
   não declarar um portal nativo testado. Se AT-SPI falhar, registrar a limitação
   do instrumento, sem classificar o produto como reprovado por isso.

**Consumidor desta entrega:** AURA UI central (`EditorialLibrary` /
`MediaEffectLayer`). **Consumidor Engine separado:** `SceneEsdeView`; a ligação
entre um pacote editado e uma cena importada ainda exige uma fatia própria.
Launcher/AURA Cinema não consomem cenas importadas neste recorte. O host atual
permanece na release anterior até existir autorização e instalação governada.

## Jornada de experiência: fundação local do sidecar v1 (checkpoint anterior)

O manifesto `theme-manifest-v1` continua estrito. O sidecar
`experience-journey-v1` agora valida menus com IDs estáveis, organização separada
do grafo, conexões semânticas, filtros tipados por read model público e aparências
por menu/etapa. O domínio preserva contexto de menu, filtros, seleção, rolagem e
foco; ciclos por input são válidos, ciclos automáticos e referências ausentes
recebem diagnóstico. A consulta pública diferencia fonte indisponível, zero
resultados, campo ausente e valor desconhecido. A cobertura diferencia herança
por omissão, AURA escolhida explicitamente, referência de tema ausente, recurso
visual incompatível e capability operacional ausente.

`JourneyStore` grava atomicamente e exporta/importa uma cópia do documento. Esse
bundle contém somente o sidecar: referências a temas continuam declaradas como
dependências e não incluem os pacotes de tema. Os tetos publicados são 4 MiB por
documento, 4.096 menus, 16.384 conexões, 8.192 posições de organização, 64
filtros por menu e 512 retornos empilhados. O teste unitário mede validação e
comportamento funcional; não mede memória/latência no Engine/Launcher.

Comando e resultado local:

```bash
rtk env SZ_CAPTURE_DIR='' .venv/bin/python tools/run_tests_isolated.py tests/unit/test_experience_journey.py -q
```

Resultado histórico: **11 passed em 0,46 s**, guard real idêntico antes/depois
(`files=12818`, `directories=2068`, `bytes=1372818509`,
`max_mtime_ns=1790888510663329431`); `ruff check` e `ruff format --check` dos
arquivos Python novos também passaram. A prova é a árvore de trabalho local
baseada no HEAD `cff16895a0ecdab68e81ac09cfb52d206b5bee2b`; ainda não existe um
commit que contenha este delta.

Naquele checkpoint, havia documento, persistência local e lógica de domínio,
sem autoria dessa jornada na UI. O texto e o resultado acima descrevem aquela
árvore, não o checkpoint desta continuidade.

## Continuidade local 2026-10-02 — Experience Journey v2

**Checkout:** `/home/misael/Projects/Steam Zero/Canonical/2026-09-21`.
**Branch:** `codex/v1-v3-theme-journey-2026-10-01`.
**HEAD base:** `09033bd5919f25317ff4449b8426f0223e21cecd`. A mudança desta seção
está em árvore local não commitada; não existe SHA de commit candidato, release
ou hash de bundle desta revisão. O host segue na release previamente instalada;
nenhuma instalação, publicação, push ou teste físico foi executado.

### O que a árvore implementa

- Evolui o sidecar para `experience-journey-v2` e lê v1 por migração. A
  validação rejeita filtros sem valor/coleção e comparações numéricas com
  `null`; documentos expostos são snapshots imutáveis. O executor oferece
  grafo, bindings tipados, agrupamento, ordenação, contexto e diagnóstico.
- `JourneyStudioService` usa as mesmas validações e store, mantém sessões
  transacionais com dirty/undo/redo, save/reopen e import/export como cópia.
  Preview/coverage recebem rows, fields, manifestos e capabilities fornecidos
  pelo chamador; não consultam o banco interno.
- `ExperienceJourneyPanel` está anexado ao `ThemeEditorPanel` pela entrada
  **Abrir Jornadas**. Expõe menus/árvore, rotas, filtros, bindings, grouping,
  aparências por menu/etapa, cobertura AURA, preview dos dados, histórico e
  operações de arquivo. No compacto, árvore e inspetor alternam explicitamente.
- As ações esperadas pelo componente são `journey.studio.list`, `.catalog`,
  `.create`, `.load`, `.transact`, `.save`, `.preview`, `.coverage`, `.import`,
  `.export.prepare`, `.export.apply`, `.undo` e `.redo`. A sessão de produção
  ainda não as publica. O componente mostra o motivo e deixa a autoria
  desativada; o teste do componente recusa as chamadas. Não há escrita QML
  direta nem bridge simulada apresentada como produção.
- A autoria de efeitos e movimento continua exercitada na QML real do Studio:
  eventos Qt adicionam/editam/reordenam/removem efeitos, editam estados,
  timelines e clips, rejeitam valores inválidos, desfazem/refazem, salvam,
  reabrem e aplicam o tema à **AURA UI central** sintética. As capturas
  `05-theme-runtime-baseline.png`, `06-theme-runtime-aplicado.png` e
  `07-aura-library-theme-applied.png` mostram esse consumidor; o teste confirma
  pixels distintos na borda da mídia. Isso não é Theme Engine ou Launcher.

### Matriz de aparência e capacidade operacional neste checkpoint

| Etapa | Aparência configurável no documento | Motivo de AURA quando herdada | Capability operacional comprovada aqui |
|---|---|---|---|
| Menu (plataformas, jogos ou faceta) | tema por menu; escolha explícita AURA ou omissão | aparência ausente; o resolver de cobertura distingue omissão de escolha explícita | nenhuma navegação de produção; a bridge não publica o documento |
| Fade de entrada | tema de etapa próprio, AURA explícita ou padrão | etapa omitida ou AURA selecionada | launch não foi solicitado ao adapter |
| Gameplay | tema próprio ou herança AURA | etapa visual omitida | sessão/jogo não foi iniciado |
| Pausa | tema próprio ou herança AURA | etapa visual omitida | pause/resume não foi chamado nem inferido da aparência |
| Saves | tema próprio ou herança AURA | etapa visual omitida | save/load não foi chamado; nenhum tipo de save foi confundido |
| Bezel | tema próprio ou herança AURA | etapa visual omitida | capability de bezel não foi consultada em adapter ativo |
| OSD | tema próprio ou herança AURA | etapa visual omitida | eventos/estados de OSD não foram conectados |
| Fade de saída | tema próprio ou herança AURA | etapa visual omitida | exit governado não foi solicitado |
| Loading | tema próprio ou herança AURA | etapa visual omitida | nenhuma operação de sessão real associada |
| Vazio | tema próprio ou herança AURA | etapa visual omitida | fallback visual não altera contagem nem fonte real |
| Erro | tema próprio ou herança AURA | etapa visual omitida | retry/timeout de operação real não foi exercitado |
| Offline | tema próprio ou herança AURA | etapa visual omitida | indisponibilidade de fonte não foi lida da aplicação |

A cobertura do domínio pode diferenciar também referência de tema ausente,
recurso visual incompatível e capability operacional ausente quando recebe os
catálogos correspondentes. A aplicação não fornece esses catálogos para a
Jornada nesta árvore; portanto nenhuma linha acima certifica um tema ou adapter
real.

### Verificações locais desta revisão

- `tests/unit/test_experience_journey.py`,
  `tests/unit/test_journey_studio.py` e
  `tests/integration/test_experience_journey_e2e.py`: 29 passed em 1,62 s,
  guard de estado real idêntico.
- `tests/integration/test_theme_authoring_e2e.py`: 1 harness passou em 24,07 s
  depois de cobrir Theme Studio → Jornadas → voltar quando a bridge não existe;
  efeitos/movimento e execução em pixels na AURA UI central continuam passando.
- ES-DE + RetroFE: 13 passed em 10,26 s após revisar e atualizar nove goldens.
  O delta era a nova entrada no fundo do ThemeEditorPanel; os diálogos mantêm
  geometria e conteúdo. A evidência é Qt offscreen, não input físico.
- Primeira integral desta árvore: `rtk .venv/bin/python
  tools/run_tests_isolated.py tests -q` terminou com 6586 passed, 47 skipped e
  3 failed em 2498,23 s. As falhas foram os dois baselines acima e
  `tests/unit/test_project_status.py`, porque digests/views ainda não tinham
  sido regenerados. A guarda real permaneceu idêntica
  (`files=12818`, `directories=2068`, `bytes=1372818509`,
  `max_mtime_ns=1790888510663329431`). Esse resultado vermelho é preservado;
  a corrida terminal e sua repetição focal estão registradas a seguir.
- Integral terminal desta revisão, 2026-10-03: `rtk .venv/bin/python
  tools/run_tests_isolated.py tests -q` — 6588 passed, 47 skipped e 1 failed
  em 2763,12 s. A única falha foi
  `tests/integration/test_qml_handheld_offscreen.py::test_central_loading_phases_are_observable_offscreen`:
  a ponte serviu 6 leituras `/status` quando o teste esperava 5. A guarda real
  ficou idêntica antes/depois (`files=12818`, `directories=2068`,
  `bytes=1372818509`, `max_mtime_ns=1790888510663329431`).
- Repetição isolada da falha, 2026-10-03: `rtk .venv/bin/python
  tools/run_tests_isolated.py
  tests/integration/test_qml_handheld_offscreen.py::test_central_loading_phases_are_observable_offscreen
  -q --tb=short` — 1 passed em 5,58 s; a guarda real permaneceu idêntica.
  A falha não se reproduziu, mas a integral continua registrada com 1 falha.

### Capacidade → UI → evidência → prova física → gap

| Capacidade | Comportamento disponível pela UI | Prova/artefato desta árvore | Prova física | Gap atual |
|---|---|---|---|---|
| Efeitos e movimento de tema | editar efeitos/estados/timelines/clips, histórico, save/reopen e aplicação explícita à AURA UI central | `tests/integration/test_theme_authoring_e2e.py`; capturas enumeradas e hashes em `SHA256SUMS` | não houve sessão/release desta branch | tema editado não foi executado pela Theme Engine ou Launcher |
| Autoria da Jornada | componente e rota existem; sem bridge a escrita é corretamente desativada | schema v2, `JourneyStudioService`, `ExperienceJourneyPanel`; QML testa rota e falha segura | não houve input físico | bridge allowlisted `journey.studio.*` não está publicada |
| Preview de dados/cobertura | serviço consulta somente rows/fields públicos fornecidos e relata cobertura quando chamado | 29 testes de domínio/serviço/componente; callback de produção negado no harness | não há preview na aplicação instalada | catálogo público real não é entregue ao serviço; preview não desenha cena |
| Theme Engine | nenhuma execução da Jornada | nenhum consumidor do documento | não executada | `ThemeScenePreview`/`SceneEsdeView` não recebem Jornada v2 nem tema salvo/reaberto |
| AURA Launcher/Cinema | nenhuma execução da Jornada | nenhuma mudança nos consumidores | não executada | grafo/contexto não está no Launcher; sessões e capabilities sem ligação |
| Sessão (launch, pausa, saves, saída) | nenhuma ação operacional é emitida pela Jornada | nenhum adapter foi acionado por este fluxo | não executada | bridge/consumidores precisam aguardar o resultado real do adapter |

### Handoff serial: arquivo → delta mínimo → dono → dependência → prova → liberação

| Arquivo/camada | Delta mínimo preparado | Dono/reserva atual | Dependência e teste necessário | Condição para liberar |
|---|---|---|---|---|
| `src/steamzero/adapters/desktop_contracts.py` | registrar allowlist e despacho dos 13 IDs `journey.studio.*` para `JourneyStudioService`; montar catálogo de read models públicos, manifestos/versões de tema e capabilities reais | `codex-continuation`, `WS-2026-09-LIBRARY-GOVERNED-MANAGEMENT`, ativo e exclusivo neste arquivo | preservar autenticação e geração; testar ações/catálogos com servidor real, mais harness do Studio contra a bridge | dono serializa a alteração e confirma o contrato; painel só habilita escrita após publicação real |
| `src/steamzero/ui/qml/Main.qml` | rotear/abrir Jornadas, vincular catálogo/ações e revogar respostas antigas ao fechar/trocar de rota | `codex-continuation`, mesmo workstream ativo e exclusivo | bridge acima; testar abrir/fechar, foco, refresh e mutação em voo no harness QML | alteração do dono concluída antes da integração compartilhada |
| `src/steamzero/adapters/desktop_dashboard.py` / `desktop_ui.py` | apenas o último vínculo serial caso a sessão/catálogo público esteja nesses adaptadores | paths compartilhados nesta frente; sem editar até conciliar o diff e os claims no último passo | API real de read models/tema/sessão; teste de integração do dashboard | claim livre, diff revisado e commit de integração isolado |
| `ThemeScenePreview.qml`, `SceneEsdeView.qml`, resolvers da Theme Engine | executar a aparência do documento v2 reaberto no renderer existente e verificar pixels/tempo e fallbacks | workstreams anteriores de cena estão fechados; esta frente ainda não reservou esses paths | bridge/catálogo/manifesto, IDs de assets e slots `sceneSurfaces`/`sceneMotion`; teste novo deve consumir o mesmo documento em vez de fixture/demonstração | reservar paths no workstream antes de editar; só promover depois do teste de renderer |
| `LauncherShell.qml`, `LauncherMain.qml`, `LauncherHome.qml` | selecionar jornada e preservar navegação/contexto | `codex-aura-launcher-exit`, `WS-2026-09-AURA-LAUNCHER-EXIT`, ativo e exclusivo | Jornada já validada na aplicação; integrar serialmente e testar mesmo documento/filtros/volta | aguardar liberação do dono; não alterar nesta frente |
| `LauncherCinema.qml`, `launcher/cinema.py`, `session_control.py` | mapear etapas a eventos do domínio e capabilities reais, sem controle de processo pelo tema | claims históricos estão fechados; criar reserva atual antes de qualquer delta | bridge, contratos/adapters publicados, testes de sucesso/falha/timeout/contexto | reserva e contrato de sessão definidos; não interpretar fade como sucesso operacional |

### Roteiro B_VISUAL da Jornada (preparado; ainda não executável)

Pré-condições: uma release futura construída de commit identificado, proveniência e
hashes conferidos, modo de dados sintéticos isolado, autorização de instalação e
um adapter de teste controlado. Este checkout não oferece ainda essa release nem
uma instalação autorizada.

1. Abrir a release e anotar versão/commit; confirmar que o perfil contém apenas
   registros e mídia sintéticos/licenciados. Registrar resolução, escala e
   método de input.
2. No Theme Studio, criar três menus por controles visíveis: plataformas,
   facetas (gênero/ano ou outro campo publicado) e jogos. Conectar dois caminhos
   ao mesmo menu compartilhado, renomear/reordenar e revisar a árvore e o mapa.
3. Configurar bindings públicos, filtros combinados e ordenação; testar valor
   desconhecido, zero resultados, limpar filtro e fonte indisponível. Entrar por
   cada origem e usar Voltar para verificar filtros, seleção, rolagem e foco.
4. Atribuir temas a plataformas/jogos e omitir pause, saves e os dois fades; antes
   de aplicar, conferir a contagem/origem AURA e cada motivo. Personalizar uma
   etapa e confirmar que as demais mantêm sua origem.
5. Salvar, fechar, reabrir e importar como cópia; comparar IDs remapeados,
   conexões, bindings e aparências. Percorrer o mesmo documento no Preview, na
   Theme Engine e no Launcher/Cinema, identificando cada consumidor.
6. Com adapter controlado, testar play, pause confirmado, saves disponíveis e
   indisponíveis, load, retomar, exit, falha/retry/timeout e uma resposta tardia
   após trocar de rota. O estado de jogo precisa refletir o adapter; fallback de
   aparência não altera capability.
7. Repetir com teclado e gamepad físicos, testar reducedMotion e preservar o
   contexto de origem. Capturar sucesso, uma etapa AURA e erro/recuperação com
   release, documento, consumidor e hashes visíveis.

Resultado deste checkpoint: roteiro registrado, sem execução física, sem teste
do Launcher/Cinema e sem instalação. Não promover V1–V4, Theme Engine, Theme
Studio completo ou AURA Launcher a concluídos.
