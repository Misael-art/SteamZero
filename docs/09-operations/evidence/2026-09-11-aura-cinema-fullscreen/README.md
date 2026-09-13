# AURA Cinema fullscreen — prova física instalada

Data: 2026-09-11  
Release ativa: `2.0.0rc1-9caa2c223cfb`  
Source commit: `9caa2c223cfb9f901e8c4dde74ed534a396c9bba`  
Wheelhouse CI: run `34585110023`  
Rollback disponível: `2.0.0rc1-172c020e03b6`

## Jornada provada

1. O Launcher instalado abriu em fullscreen. Uma consulta read-only separada a `/cinema` retornou HTTP 200 e a receita para o foco inicial; essa consulta não mede o bootstrap da janela.
2. A cena exibiu o cover-flow com capa central, vizinhas reduzidas e fallback legível sem arte.
3. `Right` moveu o foco horizontal para outro jogo sem mouse.
4. `Enter` abriu a página de detalhes do jogo focado, com capa fallback, plataforma, descrição fallback, ação `Jogar` focada e rodapé de controles.

Capturas:

- `01-cinema-fullscreen.png` — Cinema visível na coleção Steam. A captura inicial anterior mostrava a grade clássica; a causa e o tempo dessa troca não foram instrumentados.
- `02-carousel-navigation.png` — foco após navegação horizontal.
- `03-details-fallback.png` — detalhes e fallback sem mídia.
- `07-bridge-unavailable.png` — defeito posterior: janela instalada sem supervisor, ponte recusando conexão e aviso de sessão não confirmada sobreposto à capa. Não é captura de entrega funcional; ver `SESSION-NEXT-CYCLE.md`.

## Desempenho

As correções locais de HTTP/layout estão nos commits `035a7f76` e `1d0a7380`. A suíte teve 5.936 testes aprovados e 47 ignorados; ruff, formatação, mypy, independência e fronteiras passaram. `09-http-layout-gates.json` registra hashes, limites de atribuição do state real e falha do wrapper de logging. Nenhum desses commits foi instalado nesta etapa.

Os arquivos `04-performance.json`, `05-performance-repeat-2.json` e `06-performance-repeat-3.json` são preservados como ensaios **inadequados para certificar o Launcher**. O comando usado foi:

```sh
QT_QPA_PLATFORM=offscreen python tools/theme_perf_probe.py --qml-dir /opt/steamzero/current/venv/lib/python3.14/site-packages/steamzero/ui/qml --duration 10 --warmup 2 --width 1280 --height 800
```

Sem `--preview-json`, a ferramenta carrega `org.steamzero.asset-recipes-demo` e renderiza sete `SceneRepeater` em uma janela de sonda. Ela não instancia `LauncherMain` nem `LauncherCinema`. O backend offscreen tampouco apresenta frames no compositor. Os números da primeira amostra dessa cena de referência foram:

- 625 frames do render loop;
- média 15,999 ms;
- p50 15,866 ms;
- p95 16,735 ms;
- startup 77 ms;
- pico RSS 57.616 KiB;
- VRAM não medida pela API disponível.

As duas repetições foram executadas simultaneamente e também não constituem medições independentes de desempenho. Nenhum desses valores prova aprovação ou reprovação da meta do AURA. FPS apresentado, frame time, startup do Launcher e VRAM continuam sem medição válida nesta etapa. A próxima medição precisa identificar a janela e a release, carregar o catálogo real, executar navegação e observar a própria superfície fullscreen.

## Limites observados

O catálogo instalado resolveu vários jogos sem mídia de capa/fanart. O fallback do cartão e a página de detalhes estão legíveis, mas o título abaixo do carousel aparece parcialmente encoberto pela capa central nas capturas 01/02: o layout ainda precisa de correção. A prova cobre a navegação observada `carousel → detalhes` e a resposta da ponte em consulta separada. Não prova escolha/aplicação de pacote de tema, bootstrap completo, busca, erro/recuperação ou desempenho do Launcher. Pause/OSD, save-state, troca de disco, bezels por jogo e execução/retorno de um jogo real permanecem sem prova nesta release.

## Ciclo físico de 2026-09-12

Release ativa: `2.0.0rc1-47511fbe3067`, source commit
`47511fbe3067ad3c16d7700e431d1b25dfee431f`, wheelhouse CI
`34692714900`; rollback disponível: `2.0.0rc1-9caa2c223cfb`.
O instalador governado confirmou convergência e idempotência, sem staging,
backup ou operação órfã. O KDE não foi reiniciado nem encerrado.

O Launcher instalado abriu o catálogo real, navegou horizontalmente e entre
coleções, abriu detalhes e busca por teclado. `Tatsunoko vs. Capcom - Ultimate
All-Stars (Europe)` foi lançado pela ação `Jogar`; o Dolphin exibiu a tela real
do Wii e, após o encerramento do emulador, o Launcher retornou ao mesmo cartão
e coleção (`22` e `26` têm conteúdo byte-idêntico). Capturas `17`, `18`, `22`,
`23`, `24`, `26` e `27` registram essa jornada.

O jogo Saturn `Akumajou Dracula X Gekka no Yasoukyoku` reproduziu a falha
pré-spawn real por ausência do core `mednafen_saturn`. A captura `31` prova que
o erro e o botão de retry chegaram à tela; `32` prova que Enter liberou a nova
tentativa. A mesma captura revelou dois defeitos: alfa `0x07` no overlay e uso
da causa genérica no lugar do detalhe allowlisted. O commit funcional
`861a43e` corrige ambos, limita a mensagem e adiciona timeout/recuperação
acionável para a ponte local. Essa correção ainda não está na release das
capturas e precisa de nova instalação e recaptura; portanto `31` é baseline de
defeito, não evidência de aceite visual.

Não há medição nova válida de FPS, p95, startup ou VRAM nesta etapa. O ciclo
real não promove OSD, saves, bezels, troca de disco nem fades.

## Revisão de recuperação — 2026-09-12

A release `2.0.0rc1-183a1f0dfce7` (source commit
`183a1f0dfce75d2a5efdea02b01efd51cc42999b`, CI `34698828661`) instalou e
convergiu de forma idempotente, com rollback `2.0.0rc1-47511fbe3067`.

`35-installed-preflight-error-corrected-183a1f0d.png` prova a correção física
do erro pré-spawn: overlay legível, código e detalhe verdadeiro do core
`mednafen_saturn`; `36-installed-preflight-retry-corrected-183a1f0d.png`
prova a volta à página de detalhes após retry.

Ao suspender a ponte loopback real, a captura `43-installed-bridge-timeout-183a1f0d.png`
mostrou a cena presa em “Preparando”: o `XMLHttpRequest.timeout` do Qt não
vence uma conexão que foi aceita e cujo servidor foi suspenso. É baseline de
defeito, não aceite. O commit `ee7f70f` adiciona watchdog Timer por requisição,
com prova automatizada contra peer que aceita e não responde. Requer nova
release e recaptura física antes de fechar GAP-AURA-LAUNCHER-BRIDGE-DISCONNECT-RECOVERY.

## Gate integral após a correção — 2026-09-12

O gate da composição `ee7f70f` com a correção da corrida de leitura de `/proc`
executou 5.958 testes aprovados e 47 ignorados. Houve uma única falha, em
`test_committed_catalog_and_generated_views_are_consistent`, porque o arquivo
de teste alterado havia tornado o `scopeDigest` do item obsoleto. O JUnit bruto
está em `34-aura-failure-recovery-gates-rerun.xml`, SHA-256
`61a53d0a57770111a1ac71b59ba5b4ad7228a0d3ea37e79a1c05c72fbc39ac22`.

O digest foi atualizado para `329b7e015aee080383617681787068148d1eee25bc68f4aef4672b10e53ed3ef`;
`tests/unit/test_project_status.py`, `make VENV=/mnt/sdcard/Projects/Port_Steam/.venv
status-check`, Ruff, mypy, independência e fronteiras passaram depois disso.
Durante a suíte o `steamzero-core` já ativo alterou seus próprios logs/state.db;
o runner identificou esse escritor externo e não atribuiu a mutação à suíte.
O state audit posterior devolveu `clean: true`, com zero staging, backup ou
journal órfão. O gate integral é registrado como parcial por causa da falha
autorreferente, não como verde retroativo; não houve nova suíte integral.
