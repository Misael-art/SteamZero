# AURA — roteiro do próximo ciclo de sessão

Revisão de código em 2026-09-11, branch `codex/aura-cinema-physical-2026-09-11`.
Este registro contém diagnóstico estático e reprodução isolada com processo sintético, não evidência de jogo instalado.

## Ordem de execução

1. Fechar o ciclo já em teste: HTTP keep-alive concorrente e geometria do carousel.
2. Corrigir o acompanhamento e a confirmação de lançamento antes de expor Pause/OSD.
3. Instalar pelo fluxo governado, validar erro/recuperação e jogo/retorno reais.
4. Instrumentar a própria janela do Launcher e só então medir desempenho.
5. Conectar comandos semânticos declarados pelos adapters, com capacidades ausentes explicitamente indisponíveis.

## Causas identificadas para a etapa 2

- `launcher/app.py:LaunchRouter` inicia `steamzero emulation launch --game-id` desacoplado; confirmação de spawn não confirma o jogo.
- `cli/main.py:_cmd_emulation_launch` retorna logo após `EmulationController.launch_game`; `close()` apenas fecha o contexto do State Store.
- `adapters/emulation.py:launch_game` inicia `_watch_tracked_game` como thread daemon. A saída do CLI elimina esse observador mesmo que o emulador siga vivo. Isso pode impedir o registro canônico de encerramento/playtime.
- O preflight de emulação acontece antes de `_create_tracked_game_session`: uma falha pode não criar linha alguma. A ponte e a UI continuam esperando confirmação, sem resultado terminal recuperável.
- `adapters/steam_launcher.py:run` registra o PID do filho sem `start_ticks`. O observador do Launcher exige ambos e retorna `unknown` quando falta identidade.
- A rota Steam do Launcher abre `steam://rungameid`; isso por si só não demonstra que o wrapper canônico está configurado nas opções de lançamento.

## Contrato e testes a acrescentar

Reprodução executada: `python docs/09-operations/evidence/2026-09-11-aura-cinema-fullscreen/session_lifetime_repro.py`. O script usa CLI, criação de sessão, spawn e watcher de produção; apenas o preflight de plataforma e argv são injetados. O processo sintético dorme por 2 segundos. O CLI terminou com código 0 em 1,324 s; após o filho terminar, o banco ainda dizia `running` e o observador devolvia `unknown`. Resultado em `08-session-lifetime-diagnostic.json`. O exit 0 desse diagnóstico significa **defeito reproduzido**, não correção aprovada.

- Manter o dono da sessão vivo até o encerramento do processo observado, sem prender a vida do jogo à janela do Launcher.
- Transportar confirmação/erro tipados do pedido de lançamento; não remover o bloqueio só por timeout, porque isso permite duplicação de um jogo possivelmente vivo.
- Correlacionar cada pedido à sua sessão, distinguindo registros antigos e PID reutilizado.
- Reproduzir em subprocesso real com ambiente/DB temporários: wrapper sai cedo, jogo termina e registro não terminaliza; depois provar a correção.
- Testar falha de preflight, spawn recusado, jogo curto entre polls, saída normal, crash e reinício do Launcher.
- Registrar `start_ticks` no adapter proprietário; não enfraquecer a verificação no observador.
- Não declarar janela visível apenas porque existe PID; separar estado de processo e evidência de superfície.
- Reservar os arquivos adicionais no workstream antes de editar; testes novos em arquivo próprio evitam os testes de emulação reservados por outra frente.

## Medição de desempenho

- O Launcher atualmente fixa `QT_QUICK_BACKEND=software`; medir e relatar o backend efetivo, sem inferir aceleração GPU.
- `theme_perf_probe.py` sem preview renderiza cena demonstrativa, não o Launcher. Seus resultados anteriores permanecem invalidados para AURA.
- Medir release/PID/janela identificados, catálogo real, navegação/detalhes/retorno e modo visual; separar render-loop de apresentação no compositor.
- Startup inclui processo, catálogo e primeira superfície utilizável; não apenas o primeiro callback de uma sonda.
- VRAM precisa de contador atribuível ao processo; ausência de medição não equivale a zero ou aprovação.
- Executar amostras sequenciais, sem a suíte integral concorrente; preservar dados brutos e PNG funcional da release instalada.

Não houve mutação de host nesta revisão. A release permanece `2.0.0rc1-9caa2c223cfb`; rollback conhecido `2.0.0rc1-172c020e03b6`. KDE não pode ser reiniciado nem encerrado.

## Observação física adicional

A janela instalada `LauncherMain.qml` (PID 3835345) permaneceu aberta sem o supervisor original (PID 3835330 ausente). Uma consulta autenticada à ponte devolveu `Connection refused`; o token foi usado internamente, sem impressão. A captura `07-bridge-unavailable.png` mostra detalhes de Oniken com `LAUNCHER-SESSION-UNCONFIRMED-001` sobreposto à capa. Ela comprova a degradação observada, não a causa da morte do supervisor nem a execução do jogo.

`launcher_process.py:supervised_child` documenta que SIGKILL do supervisor não encerra o filho. Não foi identificado qual evento encerrou o supervisor neste caso; não atribuir a SIGKILL sem evidência. Necessário tratar desconexão da ponte explicitamente na UI e deixar saída/recuperação acionáveis, sem afirmar que a observação continua quando o canal está recusando conexões.

A única ação de interface nesta revisão foi ativar a janela existente para captura. Nenhum jogo foi iniciado, nenhum processo encerrado e nenhuma release alterada.

## Fechamento do lifetime e próxima reprodução

`8a400aab` mantém o watcher vivo até persistir o encerramento, sem retirar o processo do jogo de sua sessão independente. Os testes de subprocesso cobrem saída 0/7 e resposta do CLI enquanto o jogo está vivo. Gates em `10-session-lifetime-gates.json`: 5.939 passed, 47 skipped, exit 0; mudança ainda não instalada.

`preflight_receipt_repro.py` reproduziu a pendência restante tanto na árvore quanto importando o pacote da release instalada. Com banco e XDG temporários, CLI exit 1 sem sessão criada deixou a ponte em `awaiting` e a próxima tentativa bloqueada. Resultado instalado em `11-preflight-failure-diagnostic.json`. É diagnóstico de código da release, não jornada física nem jogo real. A correção precisa transportar o resultado do pedido e correlacioná-lo à sessão; liberar por timeout ou pelo foco da janela não é confirmação segura.

Revisão adicional: o harness inicial imprimia o resultado do handler com flush próprio. O teste reforçado com main/_emit reais reprovou porque a resposta ficava no buffer durante a espera do watcher. Flush explícito corrigiu essa fronteira: 4 testes de ciclo/resposta (JSON e texto) e 71 testes de CLI passaram. Essa emissão é pré-requisito, não implementação da confirmação de falha de preflight.

## Recuperação da composição e gate integral

A limpeza de `/tmp` do host apagou o worktree desta frente com mudanças não commitadas (flush de `_emit`, teste reforçado e atualizações de status) e o JUnit do gate integral que as provava. O worktree foi recriado em caminho durável, os diffs reaplicados a partir do registro da sessão — blobs idênticos (`4615fcf8..9f8db5bc`, `fc7b6660..ad05c905`, `acd64134..8ec76300`) — e os gates re-executados; a execução anterior não foi reivindicada sem artefato.

Gate integral reaplicado (`13-cli-reply-gates.xml`, caminho durável): 5.939 passed, 47 skipped e 1 reprovação de consistência de catálogo/visões geradas, causada pelas próprias edições de status desta composição e corrigida pela regeneração (`status-render --write`, digests recomputados em 16 itens); 10 testes de status aprovados depois da regeneração. Focados: 61 testes de lifetime/CLI. ruff check/format, mypy, independência e fronteiras verdes na composição. Mudança ainda não instalada; preflight/desconexão seguem abertos.
