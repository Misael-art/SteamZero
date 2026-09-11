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
